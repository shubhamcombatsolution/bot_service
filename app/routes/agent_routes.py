from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt, create_access_token
from app.models import Agent, LLM, Tools, KnowledgeBase, BaseLLM, LoginUser,AgentVersion
from app.database.DatabaseOperationPostgreSQL import db_session
from sqlalchemy.orm import aliased
from langchain_openai import ChatOpenAI
from app.models.mcp_agent_tools import McpAgentTools
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import json
import uuid
import logging
import networkx as nx
import spacy
import os
from dotenv import load_dotenv
import matplotlib
from app.routes.helpers.response_utils import success_response, error_response
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sqlalchemy import text , desc
from qdrant_client import QdrantClient
from openai import OpenAI
from datetime import datetime
from app.routes.helpers.agent_utils import (
    validate_agent_access, update_agent_behaviour,
    process_agent_kb_ids,build_guardrails_payload,validate_llm,
    build_agent_dashboard_analytics,build_agent_snapshot,resolve_agent_config
    )

from app.models.agent import AgentStatusEnum
from flask import g
from app.models.tenant import Tenant
import json
from app.models import db
from app.routes.helpers.common_utils import compute_snapshot_hash

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Define Blueprint
agents_blueprint = Blueprint("agents", __name__)

# Initialize NLP and Knowledge Graph
nlp = spacy.load("en_core_web_lg")
knowledge_graphs = {}  # Dictionary to store graphs per agent_id

# Initialize Qdrant client
qdrant = QdrantClient(url="http://localhost:6333", timeout=120)

def get_embedding_model():
    """Return the default OpenAI embedding model configuration."""
    OPENAI_MODEL_DIMENSIONS = {"text-embedding-ada-002": 1536}
    try:
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set.")
        client = OpenAI(api_key=openai_api_key)
        model_name = "text-embedding-ada-002"
        vector_size = OPENAI_MODEL_DIMENSIONS[model_name]
        logger.info(f"Using default OpenAI embedding model: {model_name}")
        return {
            "provider": "openai",
            "model_name": model_name,
            "client": client,
            "vector_size": vector_size
        }
    except Exception as e:
        logger.error(f"Failed to initialize embedding model: {str(e)}")
        raise ValueError(f"Cannot initialize embedding model: {str(e)}")

def get_embeddings(texts, embedding_config):
    """Generate embeddings for a list of texts."""
    try:
        if embedding_config["provider"] == "openai":
            response = embedding_config["client"].embeddings.create(
                model=embedding_config["model_name"],
                input=texts
            )
            return [item.embedding for item in response.data]
        else:
            raise ValueError(f"Unsupported provider: {embedding_config['provider']}")
    except Exception as e:
        logger.error(f"Error generating embeddings: {str(e)}")
        raise RuntimeError(f"Failed to generate embeddings: {str(e)}")

def create_knowledge_graph(text, agent_id):
    logger.debug(f"Processing text for knowledge graph: {text[:100]}...")
    if agent_id not in knowledge_graphs:
        knowledge_graphs[agent_id] = nx.DiGraph()
    G = knowledge_graphs[agent_id]
    doc = nlp(text)
    stop_words = {'you', 'me', 'i', 'it', 'them', 'that', 'which', 'anything', 'today', 'is', 'are', 'be'}
    excluded_types = {'PRON', 'DET', 'AUX', 'PART'}

    # Extract entities and noun chunks
    entities = [(ent.text.lower().strip(), ent.label_) for ent in doc.ents if ent.label_ not in excluded_types and ent.text.lower().strip() not in stop_words]
    noun_chunks = [(chunk.text.lower().strip(), 'NOUN') for chunk in doc.noun_chunks if chunk.text.lower().strip() not in stop_words and not any(ent.text.lower().strip() == chunk.text.lower().strip() for ent in doc.ents)]
    all_entities = entities + noun_chunks
    unique_entities = list(dict.fromkeys([(e, l) for e, l in all_entities if len(e.split()) <= 4 and len(e) > 2]))
    logger.debug(f"Extracted unique entities: {unique_entities}")

    # Add nodes
    for entity, label in unique_entities:
        if entity not in G:
            G.add_node(entity, type=label)

    # Create edges based on dependency parsing
    for sent in doc.sents:
        sent_entities = [e[0] for e in unique_entities if e[0] in sent.text.lower()]
        if not sent_entities:
            continue
        for token in sent:
            if token.dep_ in ('nsubj', 'dobj', 'pobj', 'compound', 'appos') and token.text.lower() in sent_entities:
                head = token.head
                if head.dep_ in ('ROOT', 'conj') and head.pos_ == 'VERB' and head.lemma_.lower() not in stop_words:
                    for child in head.children:
                        if child.dep_ in ('dobj', 'pobj') and child.text.lower() in sent_entities and child.text.lower() != token.text.lower():
                            G.add_edge(token.text.lower(), child.text.lower(), relation=head.lemma_.lower())
                            logger.debug(f"Added edge: {token.text.lower()} -> {child.text.lower()} (relation: {head.lemma_.lower()})")
                elif head.text.lower() in sent_entities and head.text.lower() != token.text.lower():
                    relation = token.dep_ if token.dep_ in ('compound', 'appos') else 'related_to'
                    G.add_edge(token.text.lower(), head.text.lower(), relation=relation)
                    logger.debug(f"Added edge: {token.text.lower()} -> {head.text.lower()} (relation: {relation})")

        for i, entity1 in enumerate(sent_entities):
            for entity2 in sent_entities[i+1:]:
                if entity1 != entity2 and not G.has_edge(entity1, entity2) and not G.has_edge(entity2, entity1):
                    G.add_edge(entity1, entity2, relation='co_occurs')
                    logger.debug(f"Added co-occurrence edge: {entity1} -> {entity2} (relation: co_occurs)")

    knowledge_graphs[agent_id] = G
    logger.debug(f"Graph for agent {agent_id}: {len(G.nodes)} nodes, {len(G.edges)} edges")

def get_graph_context(user_input, agent_id):
    if agent_id not in knowledge_graphs:
        return "No relevant graph context."
    G = knowledge_graphs[agent_id]
    doc = nlp(user_input)
    entities = [ent.text.lower().strip() for ent in doc.ents]
    context = []
    
    for entity in entities:
        if entity in G:
            neighbors = list(G.neighbors(entity))
            if neighbors:
                neighbor_strs = [f"{n} ({G.nodes[n].get('type', 'Unknown')})" for n in neighbors]
                context.append(f"{entity} ({G.nodes[entity].get('type', 'Unknown')}) is related to {', '.join(neighbor_strs)}")
            for other_entity in G.nodes:
                if other_entity != entity and other_entity in entities:
                    try:
                        path = nx.shortest_path(G, entity, other_entity)
                        if len(path) <= 3:
                            context.append(f"{entity} is connected to {other_entity} via path: {' -> '.join(path)}")
                    except nx.NetworkXNoPath:
                        pass
    
    return "; ".join(context) if context else "No relevant graph context."

def print_knowledge_graph(agent_id):
    if agent_id not in knowledge_graphs:
        return {"nodes": [], "edges": []}
    G = knowledge_graphs[agent_id]
    nodes = [f"{node} ({data.get('type', 'Unknown')})" for node, data in G.nodes(data=True)]
    edges = [f"{source} -> {target} ({data.get('relation', 'Unknown')})" for source, target, data in G.edges(data=True)]
    return {"nodes": nodes, "edges": edges}

def generate_graph_image(agent_id, output_path="static/graph_{}.png"):
    if agent_id not in knowledge_graphs or not knowledge_graphs[agent_id].nodes:
        return None
    G = knowledge_graphs[agent_id]
    output_path = output_path.format(agent_id)
    plt.figure(figsize=(12, 10))
    pos = nx.spring_layout(G, seed=42, k=0.5)
    node_colors = ['lightblue' if G.nodes[n]['type'] in ('NOUN', 'ORG') else 'lightgreen' for n in G.nodes]
    nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=800)
    node_labels = {node: f"{node}\n({data['type']})" for node, data in G.nodes(data=True)}
    nx.draw_networkx_labels(G, pos, node_labels, font_size=10)
    nx.draw_networkx_edges(G, pos, arrows=True, arrowstyle='->')
    edge_labels = {(u, v): d['relation'] for u, v, d in G.edges(data=True)}
    nx.draw_networkx_edge_labels(G, pos, edge_labels, font_size=8)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.savefig(output_path, format="png", dpi=300, bbox_inches="tight")
    plt.close()
    return output_path

def assign_all_tools_to_agent(agent_id, tenant_id, session):
    """
    ✅ NEW FUNCTION: Assign all available tools to a newly created agent
    
    Loads all tools from tools_config.json and creates McpAgentTools records
    for each tool with all its available actions enabled by default.
    
    Args:
        agent_id: The ID of the newly created agent
        tenant_id: The tenant ID
        session: Database session
    """
    try:
        # Load tools config from langgraph service
        tools_config_path = os.path.join(
            os.path.dirname(__file__),
            '../../bb_langgraph_service/tools_config.json'
        )
        
        if not os.path.exists(tools_config_path):
            logger.warning(f"tools_config.json not found at {tools_config_path}, skipping tool assignment")
            return
        
        with open(tools_config_path, 'r') as f:
            tools_config = json.load(f)
        
        # Extract all tools and their actions
        tools_to_assign = {}
        for tool_category, tool_list in tools_config.items():
            if isinstance(tool_list, list):
                for tool_def in tool_list:
                    action = tool_def.get('action')
                    if action:
                        if tool_category not in tools_to_assign:
                            tools_to_assign[tool_category] = []
                        tools_to_assign[tool_category].append(action)
        
        logger.info(f"[TOOL ACCESS] Assigning {len(tools_to_assign)} tools to agent {agent_id}")
        
        # Create McpAgentTools records for each tool with all actions
        for tool_name, actions in tools_to_assign.items():
            try:
                # Check if tool already exists for this agent
                existing_tool = session.query(McpAgentTools).filter_by(
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    tool_name=tool_name,
                    del_flag=False
                ).first()
                
                if existing_tool:
                    # Merge actions if tool already exists
                    existing_tool.action_tools = list(set((existing_tool.action_tools or []) + actions))
                    logger.info(f"[TOOL ACCESS] Updated {tool_name} with {len(existing_tool.action_tools)} actions for agent {agent_id}")
                else:
                    # Create new tool assignment
                    new_tool_assignment = McpAgentTools(
                        tenant_id=tenant_id,
                        agent_id=agent_id,
                        tool_name=tool_name,
                        action_tools=actions,
                        action_tools_description=[],
                        del_flag=False
                    )
                    session.add(new_tool_assignment)
                    logger.info(f"[TOOL ACCESS] Assigned {tool_name} with {len(actions)} actions to agent {agent_id}")
            except Exception as e:
                logger.error(f"[TOOL ACCESS] Failed to assign {tool_name} to agent {agent_id}: {str(e)}")
        
        session.commit()
        logger.info(f"[TOOL ACCESS] ✅ All tools successfully assigned to agent {agent_id}")
        
    except Exception as e:
        logger.error(f"[TOOL ACCESS] Error assigning tools to agent: {str(e)}")
        session.rollback()
        # Don't raise, allow agent creation to succeed even if tool assignment fails

def generate_generalized_instructions(features, safe_ai_settings):
    logger.debug(f"Generating instructions with features: {features}, safeAISettings: {safe_ai_settings}")
    instructions = []
    feature_summary = []
    if features.get("soundNatural", False):
        feature_summary.append("use a natural, engaging tone")
    if features.get("thinkBack", False):
        feature_summary.append("reflect on past interactions for context")
    if features.get("stayOnTopic", False):
        feature_summary.append("stay focused on relevant topics")
    if features.get("explainClearly", False):
        feature_summary.append("provide clear, concise explanations")
    if feature_summary:
        instructions.append(f"Respond professionally, {', '.join(feature_summary)}.")
    
    try:
        safe_ai = json.loads(safe_ai_settings) if isinstance(safe_ai_settings, str) else safe_ai_settings
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse safeAISettings: {e}")
        safe_ai = {}
    
    safe_ai_summary = []
    if safe_ai.get("harmfulContent", False):
        safe_ai_summary.append(f"filter harmful content (threshold: {safe_ai.get('harmfulThreshold', 0.5)})")
    if safe_ai.get("maliciousInstructions", False):
        safe_ai_summary.append(f"block malicious commands (threshold: {safe_ai.get('maliciousThreshold', 0.5)})")
    if safe_ai.get("allowedTopics", False) and safe_ai.get("allowedKeywords", []):
        safe_ai_summary.append(f"focus on professional topics: {', '.join(safe_ai.get('allowedKeywords', []))}")
    if safe_ai.get("blockedTopics", False) and safe_ai.get("blockedKeywords", []):
        safe_ai_summary.append(f"avoid topics: {', '.join(safe_ai.get('blockedKeywords', []))}")
    if safe_ai.get("secrets", False):
        sensitive_items = safe_ai.get("secretKeywords", []) or ["API keys", "tokens", "passwords"]
        safe_ai_summary.append(f"mask sensitive information ({', '.join(sensitive_items)})")
    if safe_ai.get("keywordsEnabled", False) and safe_ai.get("keywordList", []):
        keyword_summary = []
        for keyword in safe_ai.get("keywordList", []):
            if keyword.get("type") == "block":
                keyword_summary.append(f"block '{keyword.get('key')}'")
            elif keyword.get("type") == "mask":
                keyword_summary.append(f"mask '{keyword.get('key')}' as '{keyword.get('mask')}'")
        if keyword_summary:
            safe_ai_summary.append(f"manage keywords: {', '.join(keyword_summary)}")
    
    if safe_ai_summary:
        instructions.append(f"Ensure safety by {', '.join(safe_ai_summary)}.")
    
    combined_instructions = " ".join(instructions) if instructions else ""
    if not combined_instructions:
        logger.warning("No instructions generated")
        return None
    summary = combined_instructions
    logger.debug(f"Generated summarized instructions: {summary}")
    return summary

# # Initialize LLM
# llm = ChatOpenAI(
#     model_name="gpt-3.5-turbo",
#     temperature=0.7,
#     openai_api_key=os.getenv("OPENAI_API_KEY")
# )

# # Initialize memory stores per agent
# agent_histories = {}

# def get_session_history(agent_id):
#     if agent_id not in agent_histories:
#         agent_histories[agent_id] = InMemoryChatMessageHistory()
#     return agent_histories[agent_id]

# # Create prompt template with agent instructions
# prompt = ChatPromptTemplate.from_messages([
#     ("system", "You are a helpful assistant named {agent_name}. Follow these instructions: {agent_instructions} {additional_instructions}. Base your response on the provided knowledge base chunks and graph context, prioritizing information from the knowledge base. If no relevant information is found, use your general knowledge to respond in a friendly, empathetic, and patient manner. Knowledge Base Chunks: {kb_context}\nKnowledge Graph Context: {graph_context}"),
#     MessagesPlaceholder(variable_name="history"),
#     ("human", "{input}")
# ])


@agents_blueprint.route("/create", methods=["POST"])
@jwt_required()
def create_agent():
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")

        agent_key = str(uuid.uuid4())
        if not tenant_id:
            return error_response(message = "Tenant ID not found", data = None, code = 401)

        session = next(db_session())

        # Give a default name to satisfy NOT NULL constraint
        default_name = f"New Agent {datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

        new_agent = Agent(
            tenant_id=tenant_id,
            agent_name="",
            agent_description="",
            llm_model_id=None,
            # tool_id=None,
            agent_status=AgentStatusEnum.DRAFT,  # ✅ ADD THIS
            knowledge_base_ids=[],
            Examples="",
            additional_instructions="",
            memory_mode="",
            deployment_method="local",
            agent_key=agent_key,
            del_flg=False
        )
        session.add(new_agent)
        session.commit()
        session.refresh(new_agent)
        
        # ✅ AUTOMATICALLY ASSIGN ALL TOOLS TO NEW AGENT FOR TOOL-RELATED TASKS
        assign_all_tools_to_agent(new_agent.agent_id, tenant_id, session)
        logger.info(f"[BOT CREATION] Agent {new_agent.agent_id} created with full tool access")

        return success_response(message = "Agent created successfully with full tool access", data = {"agent_id": new_agent.agent_id}, code = 201)

    except Exception as e:
        session.rollback()
        logger.error(f"Error saving agent: {str(e)}")
        return error_response(message = str(e), data = {}, code = 500)
    finally:
        session.close()


@agents_blueprint.route("/agent_kb/<int:agent_id>", methods=["GET"])
@jwt_required()
def list_agent_kbs(agent_id):
    tenant_id = _tenant_id_from_token()
    if not tenant_id:
        return error_response(message = "Tenant ID not found in token", data = None, code = 401)

    session = next(db_session())
    try:
        agent = (
            session.query(Agent)
            .filter_by(agent_id=agent_id, tenant_id=tenant_id, del_flg=False)
            .first()
        )
        if not agent:
            return error_response(message = "Agent not found", data = None, code = 404)

        kb_ids = agent.knowledge_base_ids if isinstance(agent.knowledge_base_ids, list) else []
        kb_ids = [int(x) for x in kb_ids if str(x).isdigit()]

        if not kb_ids:
            return success_response(message = "Success", data = [], code = 200)

        # fetch KB rows
        kbs = session.query(KnowledgeBase).filter(
            KnowledgeBase.tenant_id == tenant_id,
            KnowledgeBase.del_flg == False,
            KnowledgeBase.knowledge_base_id.in_(kb_ids)
        ).all()

        # keep same order as stored in agent.knowledge_base_ids
        kb_map = {kb.knowledge_base_id: kb for kb in kbs}
        ordered_kbs = [kb_map[kid] for kid in kb_ids if kid in kb_map]

        data = [{
            "knowledge_base_id": kb.knowledge_base_id,
            "knowledge_base_name": kb.knowledge_base_name,
            "collection_name": kb.collection_name,
            "created_at": kb.created_at.isoformat() if kb.created_at else None
        } for kb in ordered_kbs]

        return success_response(message = "Success", data = data, code = 200)

    except Exception as e:
        logger.exception("list_agent_kbs failed")
        return error_response(message = str(e), data = None, code = 500)
    finally:
        session.close()


@agents_blueprint.route("/agent_kb/", methods=["POST"])
@jwt_required()
def add_kb_to_agent():
    """
    Body JSON:
    {
      "agent_id": 12,
      "knowledge_base_id": 5
    }
    Adds kb_id into Agent.knowledge_base_ids (no duplicates).
    """
    tenant_id = _tenant_id_from_token()
    if not tenant_id:
        return error_response(message = "Tenant ID not found in token", data = None, code = 401)

    payload = request.get_json(silent=True) or {}
    agent_id = payload.get("agent_id")
    kb_id = payload.get("knowledge_base_id")

    if not agent_id or not kb_id:
        return error_response(message = "agent_id and knowledge_base_id are required", data = None, code = 400)

    session = next(db_session())
    try:
        agent = (
            session.query(Agent)
            .filter_by(agent_id=int(agent_id), tenant_id=tenant_id, del_flg=False)
            .first()
        )
        if not agent:
            return error_response(message = "Agent not found", data = None, code = 404)

        kb = (
            session.query(KnowledgeBase)
            .filter_by(knowledge_base_id=int(kb_id), tenant_id=tenant_id, del_flg=False)
            .first()
        )
        if not kb:
            return error_response(message = "Knowledge base not found", data = None, code = 404)

        kb_ids = agent.knowledge_base_ids if isinstance(agent.knowledge_base_ids, list) else []
        kb_ids = [int(x) for x in kb_ids if str(x).isdigit()]

        if int(kb_id) not in kb_ids:
            kb_ids.append(int(kb_id))
            agent.knowledge_base_ids = kb_ids
            session.commit()

        return success_response(message = "KB added to agent", data = {
                "agent_id": agent.agent_id,
                "knowledge_base_ids": agent.knowledge_base_ids
            }, code = 200)

    except Exception as e:
        session.rollback()
        logger.exception("add_kb_to_agent failed")
        return error_response(message = str(e), data = None, code = 500)
    finally:
        session.close()


@agents_blueprint.route("/agent_kb/<int:agent_id>/<int:kb_id>", methods=["DELETE"])
@jwt_required()
def remove_kb_from_agent(agent_id, kb_id):
    """
    Removes kb_id from Agent.knowledge_base_ids
    """
    tenant_id = _tenant_id_from_token()
    if not tenant_id:
        return error_response(message = "Tenant ID not found in token", data = None, code = 401)

    session = next(db_session())
    try:
        agent = (
            session.query(Agent)
            .filter_by(agent_id=agent_id, tenant_id=tenant_id, del_flg=False)
            .first()
        )
        if not agent:
            return error_response(message = "Agent not found", data = None, code = 404)

        kb_ids = agent.knowledge_base_ids if isinstance(agent.knowledge_base_ids, list) else []
        kb_ids = [int(x) for x in kb_ids if str(x).isdigit()]

        if kb_id in kb_ids:
            kb_ids.remove(kb_id)
            agent.knowledge_base_ids = kb_ids
            session.commit()

        return success_response(message = "KB removed from agent", data = {
                "agent_id": agent.agent_id,
                "knowledge_base_ids": agent.knowledge_base_ids
            }, code = 200)

    except Exception as e:
        session.rollback()
        logger.exception("remove_kb_from_agent failed")
        return error_response(message = str(e), data = None, code = 500)
    finally:
        session.close()


@agents_blueprint.route("/chat/<int:agent_id>", methods=["POST"])
@jwt_required()
def chat(agent_id):
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")
        if not tenant_id:
            return error_response("Tenant ID not found in token", {}, 401)

        session = next(db_session())
        agent = session.query(Agent).filter_by(
            agent_id=agent_id,
            tenant_id=tenant_id
        ).first()

        if not agent:
            return error_response("Agent not found or not authorized", {}, 404)

        # 🔥 NEW: Resolve config (LIVE → snapshot, CREATED → draft)
        config = resolve_agent_config(agent)

        data = request.json
        user_input = data.get("message")
        if not user_input:
            return error_response("Message is required", {}, 400)

        memory_type = config.get("memory_mode")
        kb_context = ""
        graph_context = ""
        graph_details = {"nodes": [], "edges": []}
        graph_image_path = None

        # Knowledge Base
        kb_ids = config.get("knowledge_base_ids", [])
        kb_id = kb_ids[0] if kb_ids else None

        if kb_id:
            knowledge_base = session.query(KnowledgeBase).filter_by(
                knowledge_base_id=kb_id,
                tenant_id=tenant_id
            ).first()

            if knowledge_base and knowledge_base.collection_name:
                try:
                    embedding_config = get_embedding_model()
                    query_embedding = get_embeddings([user_input], embedding_config)[0]

                    search_result = qdrant.search(
                        collection_name=knowledge_base.collection_name,
                        query_vector=query_embedding,
                        limit=5,
                        with_payload=True
                    )

                    kb_chunks = [
                        hit.payload.get("chunk_text")
                        for hit in search_result
                        if hit.payload.get("chunk_text")
                    ]
                    kb_context = "\n".join(kb_chunks)

                except Exception:
                    kb_context = "Error retrieving knowledge base context."

        graph_context = get_graph_context(user_input, agent_id)

        # Memory handling remains same
        if memory_type:
            conversation = RunnableWithMessageHistory(
                runnable=prompt | llm,
                get_session_history=lambda session_id: get_session_history(agent_id),
                input_messages_key="input",
                history_messages_key="history"
            )

            try:
                response = conversation.invoke(
                    {
                        "input": user_input,
                        "kb_context": kb_context,
                        "graph_context": graph_context,
                        "agent_instructions": config.get("agent_instructions", ""),
                        "additional_instructions": config.get("additional_instructions", ""),
                        "agent_name": config.get("agent_name"),
                    },
                    config={"configurable": {"session_id": str(agent_id)}}
                ).content
            except Exception as e:
                return error_response(f"Failed to get response: {str(e)}", {}, 500)

        else:
            try:
                response = (prompt | llm).invoke({
                    "input": user_input,
                    "kb_context": kb_context,
                    "graph_context": graph_context,
                    "agent_instructions": config.get("agent_instructions", ""),
                    "additional_instructions": config.get("additional_instructions", ""),
                    "agent_name": config.get("agent_name"),
                    "history": []
                }).content
            except Exception as e:
                return error_response(f"Failed to get response: {str(e)}", {}, 500)

        return success_response(
            "Response generated successfully",
            {
                "response": response,
                "knowledge_graph": graph_details,
                "graph_image": f"/{graph_image_path}" if graph_image_path else None
            },
            200
        )

    except Exception as e:
        session.rollback()
        return error_response(str(e), {}, 500)
    finally:
        session.close()      
        
        
        
def summarize_conversation(history):
    messages = [msg.content for msg in history.messages]
    if not messages:
        return "No conversation to summarize."
    summary_prompt = f"Summarize the following conversation in 1-2 sentences:\n{' '.join(messages)}"
    try:
        summary = llm.invoke([HumanMessage(content=summary_prompt)]).content
        return summary
    except Exception as e:
        logger.error(f"Error summarizing: {str(e)}")
        return f"Error summarizing: {str(e)}"

# Update Agent
@agents_blueprint.route("/update/<int:agent_id>", methods=["PUT"])
@jwt_required()
def update_agent(agent_id):
    session = next(db_session())
    try:
        identity = get_jwt_identity()
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")
        if not tenant_id:
            return error_response(message = "Tenant ID not found in token", data = {}, code = 401)

        data = request.json
        agent = session.query(Agent).filter_by(agent_id=agent_id, tenant_id=tenant_id).first()
        if not agent:
            return error_response(message = "Agent not found or not authorized", data = {}, code = 404)
        
        if "agent_name" in data:
            agent.agent_name = data["agent_name"]
        if "agent_description" in data:
            agent.agent_description = data["agent_description"]
        if "llm_model_id" in data:
            try:
                llm_model_id = int(data["llm_model_id"])
                llm_model = session.query(LLM).filter_by(llm_id=llm_model_id, tenant_id=tenant_id).first()
                if not llm_model:
                    return error_response(message = "Invalid LLM model for this tenant", data = {}, code = 400)
                agent.llm_model_id = llm_model_id
            except ValueError:
                return error_response(message = "Invalid LLM model ID", data = {}, code = 400)
        if "agent_role" in data:
            agent.instruction_mode = data["agent_role"]
        if "agent_instructions" in data:
            agent.agent_instructions = data["agent_instructions"]
        # if "tool_id" in data:
        #     try:
        #         tool_id = int(data["tool_id"])
        #         tool = session.query(Tools).filter_by(tool_id=tool_id).first()
        #         if not tool:
        #             return jsonify({"data": {}, "message": "Invalid Tool ID", "status": "error"}), 400
        #         agent.tool_id = tool_id
        #     except ValueError:
        #         return jsonify({"data": {}, "message": "Invalid Tool ID", "status": "error"}), 400
        if "Examples" in data:
            agent.Examples = data["Examples"]
        if "memoryPlugin" in data:
            agent.memory_mode = data["memoryPlugin"]

        kb_ids_payload = None
        if "knowledge_base_ids" in data:
            if isinstance(data["knowledge_base_ids"], list):
                kb_ids_payload = data["knowledge_base_ids"]
            else:
                return error_response(message = "knowledge_base_ids must be a list", data = {}, code = 400)
        elif "knowledge_base_id" in data:
            kb_ids_payload = [data["knowledge_base_id"]]

        if kb_ids_payload is not None:
            valid_kbs = session.query(KnowledgeBase).filter(
                KnowledgeBase.knowledge_base_id.in_(kb_ids_payload),
                KnowledgeBase.tenant_id == tenant_id,
                KnowledgeBase.del_flg == False
            ).all()
            agent.knowledge_base_ids = [kb.knowledge_base_id for kb in valid_kbs]


        session.commit()
        
        return success_response(message = "Agent updated successfully", data = {"agent_id": agent.agent_id, "tenant_id": agent.tenant_id}, code = 200)
        
    except Exception as e:
        session.rollback()
        logger.error(f"Error updating agent: {str(e)}")
        return error_response(message = str(e), data = {}, code = 500)
    finally:
        session.close()

# Get Agent by ID
@agents_blueprint.route("/get/<int:agent_id>", methods=["GET"])
@jwt_required()
def get_agent_by_id(agent_id):
    try:
        identity = get_jwt_identity()
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")
        if not tenant_id:
            return error_response(message = "Tenant ID not found in token", data = {}, code = 401)

        session = next(db_session())
        agent = session.query(Agent).filter_by(agent_id=agent_id, tenant_id=tenant_id).first()
        if not agent:
            return error_response(message = "Agent not found or not authorized", data = {}, code = 404)
        
        agent_data = {
            "agent_id": agent.agent_id,
            "tenant_id": agent.tenant_id,
            "agent_name": agent.agent_name,
            "agent_description": agent.agent_description,
            "llm_model_id": agent.llm_model_id,
            "agent_role": agent.instruction_mode,
            "agent_instructions": agent.agent_instructions,
            # "tool_id": agent.tool_id,
            "Examples": agent.Examples,
            "memory_plugin": agent.memory_mode
        }
        agent_data["knowledge_base_ids"] = agent.knowledge_base_ids
        if isinstance(agent.knowledge_base_ids, list) and agent.knowledge_base_ids:
            agent_data["knowledge_base_id"] = agent.knowledge_base_ids[0]
        else:
            agent_data["knowledge_base_id"] = None

        
        return success_response(message = "Agent retrieved successfully", data = agent_data, code = 200)
        
    except Exception as e:
        logger.error(f"Error fetching agent: {str(e)}")
        return error_response(message = str(e), data = {}, code = 500)
    finally:
        session.close()
        
@agents_blueprint.route("/edit/<int:agent_id>", methods=["GET"])
@jwt_required()
def edit_agent(agent_id):
    session = next(db_session())
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")

        if not tenant_id:
            return error_response(message = "Tenant ID not found in token", data = {}, code = 401)

        agent = (
            session.query(Agent)
            .filter_by(
                agent_id=agent_id,
                tenant_id=tenant_id,
                del_flg=False
            )
            .first()
        )

        if not agent:
            return error_response(message = "Agent not found or not authorized", data = {}, code = 404)

        return success_response(message = "Agent fetched successfully", data = {
                "agent_id": agent.agent_id,
                "tenant_id": agent.tenant_id,
                "agent_name": agent.agent_name,
                "agent_description": agent.agent_description,
                "llm_model_id": agent.llm_model_id,
                "agent_role": agent.instruction_mode,
                "agent_instructions": agent.agent_instructions,
                "Examples": agent.Examples,
                "memory_plugin": agent.memory_mode,
                "knowledge_base_ids": agent.knowledge_base_ids,
                "knowledge_base_id": agent.knowledge_base_ids[0] if isinstance(agent.knowledge_base_ids, list) and agent.knowledge_base_ids else None
            }, code = 200)

    except Exception as e:
        session.rollback()
        logger.error(f"Error fetching agent: {str(e)}")
        return error_response(message = str(e), data = {}, code = 500)

    finally:
        session.close()


        
@agents_blueprint.route("/", methods=["GET"])
@jwt_required()
def get_all_agents():
    try:
        identity = get_jwt_identity()
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")
        if not tenant_id:
            return jsonify({
                "data": {},
                "message": "Tenant ID not found in token",
                "status": "error"
            }), 401

        session = next(db_session())

        # Aliases
        LLMModel = aliased(LLM)
        BaseProvider = aliased(BaseLLM)
        BaseModel = aliased(BaseLLM)

        # Use the selected LLM row as the source of truth.
        agents = (
            session.query(
                Agent,
                BaseProvider.base_provider.label("llm_provider_name"),
                BaseModel.base_model_name.label("llm_model_name"),
                Tools.tool_name.label("tool_name")
            )
            .outerjoin(LLMModel, Agent.llm_model_id == LLMModel.llm_id)
            .outerjoin(BaseProvider, LLMModel.provider_id == BaseProvider.base_llm_id)
            .outerjoin(BaseModel, LLMModel.model_name_id == BaseModel.base_llm_id)
            .outerjoin(Tools, Agent.tool_id == Tools.tool_id)
            .filter(
                Agent.tenant_id == tenant_id,
                Agent.del_flg == False,
                Agent.agent_name != "",          # exclude blank draft agents
                Agent.agent_name != None,         # exclude null name agents
                Agent.llm_model_id != None,       # exclude agents with no model set
            )
            .distinct(Agent.agent_id)
            .order_by(desc(Agent.agent_id))
            .all()
        )

        agents_list = [
            {
                "agent_id": agent.agent_id,
                "tenant_id": agent.tenant_id,
                "agent_name": agent.agent_name or "",
                "agent_description": agent.agent_description or "",
                "llm_provider_name": llm_provider_name or "",
                "llm_model_name": llm_model_name or "",
                "agent_role": agent.agent_role or "",
                "agent_instructions": agent.agent_instructions or "",
                "tool_name": tool_name or "",
                "Examples": agent.Examples or "",
                "memory_plugin": agent.memory_plugin or "",
                "features": agent.features or {},
                "safe_ai_settings": agent.safe_ai_settings or {},
                "knowledge_base_ids": agent.knowledge_base_ids or [],
                "agent_key": agent.agent_key or "",
                "import_source": agent.import_source,
                "created_at": agent.created_at.isoformat() if agent.created_at else None,
            }
            for agent, llm_provider_name, llm_model_name, tool_name in agents
        ]

        return jsonify({
            "data": agents_list,
            "message": "Agents fetched successfully",
            "status": "success"
        }), 200

    except Exception as e:
        logger.error(f"Error fetching agents: {str(e)}")
        return jsonify({
            "data": {},
            "message": f"Failed to fetch agents: {str(e)}",
            "status": "error"
        }), 500
    finally:
        session.close()

@agents_blueprint.route("/<int:agent_id>", methods=["GET"])
@jwt_required()
def get_all_agentswithId(agent_id):
    try:
        identity = get_jwt_identity()
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")
    
        if not tenant_id:
            return error_response(message = "Tenant ID not found in token", data = {}, code = 401)

        session = next(db_session())
        LLMModel = aliased(LLM)
        BaseProvider = aliased(BaseLLM)
        BaseModel = aliased(BaseLLM)

        agents = (
            session.query(
                Agent,
                BaseProvider.base_provider.label("llm_provider_name"),
                BaseModel.base_model_name.label("llm_model_name"),
                Tools.tool_name.label("tool_name")
            )
            .filter(
                Agent.agent_id == agent_id,
                Agent.tenant_id == tenant_id,
                Agent.del_flg == False
            )
            .outerjoin(LLMModel, Agent.llm_model_id == LLMModel.llm_id)
            .outerjoin(BaseProvider, LLMModel.provider_id == BaseProvider.base_llm_id)
            .outerjoin(BaseModel, LLMModel.model_name_id == BaseModel.base_llm_id)
            .outerjoin(Tools, Agent.tool_id == Tools.tool_id)
            .order_by(desc(Agent.agent_id))
            .all()
        )

        agents_list = [
            {
                "agent_id": agent.agent_id,
                "tenant_id": agent.tenant_id,
                "agent_name": agent.agent_name,
                "agent_description": agent.agent_description,
                "llm_provider_name": llm_provider_name,
                "llm_model_name": llm_model_name,
                "agent_role": agent.instruction_mode,
                "agent_instructions": agent.agent_instructions,
                "tool_name": tool_name,
                "Examples": agent.Examples,
                "memory_plugin": agent.memory_mode,
                "features" : agent.additional_instructions
            }
            for agent, llm_provider_name, llm_model_name, tool_name in agents
        ]

        return success_response(message = "Agents fetched successfully", data = agents_list, code = 200)

    except Exception as e:
        logger.error(f"Error fetching agents: {str(e)}")
        return error_response(message = "Failed to fetch agents. Please try again.", data = {}, code = 500)
    finally:
        session.close()

# Delete Agent
@agents_blueprint.route("/delete/<int:agent_id>", methods=["DELETE"])
@jwt_required()
def delete_agent(agent_id):
    session = next(db_session())
    try:
        identity = get_jwt_identity()
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")
        if not tenant_id:
            return error_response(message = "Tenant ID not found in token", data = {}, code = 401)

        agent = session.query(Agent).filter_by(agent_id=agent_id, tenant_id=tenant_id).first()
        if not agent:
            return error_response(message = "Agent not found or not authorized", data = {}, code = 404)

        agent.del_flg = True
        session.commit()

        return success_response(message = "Agent deleted successfully", data = {"agent_id": agent.agent_id, "tenant_id": agent.tenant_id}, code = 200)

    except Exception as e:
        session.rollback()
        logger.error(f"Error deleting agent: {str(e)}")
        return error_response(message = str(e), data = {}, code = 500)
    finally:
        session.close()




# Middleware to validate API key and fetch tenant details
def validate_api_key():
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        return None, jsonify({"data": {}, "message": "API key is required", "status": "error"}), 401

    session = next(db_session())
    try:
        user = session.query(LoginUser).filter_by(api_key=api_key, del_flg=False).first()
        if not user:
            return None, jsonify({"data": {}, "message": "Invalid API key", "status": "error"}), 401
        return user, None
    finally:
        session.close()





# Initialize memory stores per agent
agent_histories = {}

def get_session_history(agent_id):
    if agent_id not in agent_histories:
        agent_histories[agent_id] = InMemoryChatMessageHistory()
    return agent_histories[agent_id]

# Create prompt template
prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful assistant named {agent_name}. Follow these instructions: {agent_instructions} {additional_instructions}."),
    MessagesPlaceholder(variable_name="history"),
    ("human", "{input}")
])

# Initialize LLM
llm = ChatOpenAI(
    model_name="gpt-3.5-turbo",
    temperature=0.7,
    openai_api_key=os.getenv("OPENAI_API_KEY")
)



# Deploy Agent
@agents_blueprint.route("/deploy/<int:agent_id>", methods=["POST"])
@jwt_required()
@validate_agent_access(allowed_status=[AgentStatusEnum.CREATED,AgentStatusEnum.LIVE, AgentStatusEnum.PAUSED])
def deploy_agent(agent_id):
    session = next(db_session())
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")

        if not tenant_id:
            return error_response("Tenant ID not found in token", {}, 401)

        agent = session.query(Agent).filter_by(
            agent_id=agent_id,
            tenant_id=tenant_id,
            del_flg=False
        ).first()

        if not agent:
            return error_response("Agent not found or not authorized", {}, 404)

        if not agent.agent_key:
            agent.agent_key = str(uuid.uuid4())

        data = request.json
        if not data or "config" not in data:
            return error_response("Configuration is required", {}, 400)

        config = data["config"]

        deployment_method = None
        if config.get("streamingAPI"):
            deployment_method = "streamingAPI"
        elif config.get("webhook"):
            deployment_method = "webhook"
        elif config.get("sdk"):
            deployment_method = "sdk"
        elif config.get("codeSnippet"):
            deployment_method = "codeSnippet"
        else:
            return error_response("No deployment method selected", {}, 400)

        agent.deployment_method = deployment_method

        # 🔥 VERSIONING STARTS HERE

        new_snapshot = build_agent_snapshot(agent)
        new_hash = compute_snapshot_hash(new_snapshot)

        # ✅ Idempotency check
        if agent.published_version_id:
            current_live = session.query(AgentVersion).get(agent.published_version_id)
            if current_live and current_live.snapshot_hash == new_hash:
                return success_response(
                    "No changes detected. Agent already up to date.",
                    {
                        "agent_key": agent.agent_key,
                        "deployment_method": deployment_method,
                        "version_number": current_live.version_number
                    },
                    200
                )

        # Deactivate current live
        if agent.published_version_id:
            current_live = session.query(AgentVersion).get(agent.published_version_id)
            if current_live:
                current_live.is_live = False

        # Get next version number
        last_version = (
            session.query(AgentVersion)
            .filter_by(agent_id=agent.agent_id)
            .order_by(AgentVersion.version_number.desc())
            .first()
        )
        next_number = last_version.version_number + 1 if last_version else 1

        # Create new version
        new_version = AgentVersion(
            agent_id=agent.agent_id,
            version_number=next_number,
            is_live=True,
            snapshot=new_snapshot,
            snapshot_hash=new_hash,   # ✅ NEW FIELD
            deployed_by=tenant_id
        )

        session.add(new_version)
        session.flush()

        agent.published_version_id = new_version.version_id
        agent.agent_status = AgentStatusEnum.LIVE
        agent.last_deployed_at = db.func.now()

        session.commit()

        user = session.query(LoginUser).filter_by(
            tenant_id=tenant_id,
            del_flg=False
        ).first()

        if not user or not user.account_name:
            return error_response("User account configuration error", {}, 500)

        integration_instructions = generate_integration_instructions(
            agent.agent_key,
            deployment_method,
            user.account_name
        )

        return success_response(
            "Agent deployed successfully",
            {
                "agent_key": agent.agent_key,
                "deployment_method": deployment_method,
                "version_number": next_number,
                "integration_instructions": integration_instructions
            },
            200
        )

    except Exception as e:
        session.rollback()
        logger.exception("Deploy failed")
        return error_response(str(e), {}, 500)
    finally:
        session.close()
        
@agents_blueprint.route("/rollback/<int:agent_id>/<int:version_id>", methods=["POST"])
@jwt_required()
@validate_agent_access(allowed_status=[AgentStatusEnum.LIVE])
def rollback_agent(agent_id, version_id):
    session = next(db_session())
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")

        agent = session.query(Agent).filter_by(
            agent_id=agent_id,
            tenant_id=tenant_id,
            del_flg=False
        ).first()

        if not agent:
            return error_response("Agent not found", {}, 404)

        if agent.published_version_id == version_id:
            return error_response("Version is already live", {}, 400)

        target_version = session.query(AgentVersion).filter_by(
            version_id=version_id,
            agent_id=agent.agent_id
        ).first()

        if not target_version:
            return error_response("Version not found", {}, 404)

        # Deactivate current live
        if agent.published_version_id:
            current_live = session.query(AgentVersion).get(agent.published_version_id)
            if current_live:
                current_live.is_live = False

        # Next version number
        last_version = (
            session.query(AgentVersion)
            .filter_by(agent_id=agent.agent_id)
            .order_by(AgentVersion.version_number.desc())
            .first()
        )
        next_number = last_version.version_number + 1 if last_version else 1

        rollback_snapshot = target_version.snapshot
        rollback_hash = compute_snapshot_hash(rollback_snapshot)

        new_version = AgentVersion(
            agent_id=agent.agent_id,
            version_number=next_number,
            is_live=True,
            snapshot=rollback_snapshot,
            snapshot_hash=rollback_hash,  # ✅ added
            deployed_by=tenant_id
        )

        session.add(new_version)
        session.flush()

        agent.published_version_id = new_version.version_id
        agent.agent_status = AgentStatusEnum.LIVE
        agent.last_deployed_at = db.func.now()

        session.commit()

        return success_response(
            "Rollback successful",
            {
                "new_version_number": next_number,
                "rolled_back_from": version_id
            },
            200
        )

    except Exception as e:
        session.rollback()
        logger.exception("Rollback failed")
        return error_response(str(e), {}, 500)
    finally:
        session.close()


def generate_integration_instructions(agent_key, deployment_method, account_name):
    base_url = f"https://{account_name}.jnanic.com"
    instructions = {}

    if deployment_method == "streamingAPI":
        instructions = {
            "method": "Streaming API",
            "description": "Use the Streaming API to receive real-time responses from the agent.",
            "endpoint": f"{base_url}/agents/stream/{agent_key}",
            "headers": {
                "X-API-Key": "<your-x-api-key>",
                "Content-Type": "application/json"
            },
            "example": {
                "request": f"POST /agents/stream/{agent_key}",
                "body": {
                    "message": "Your user input here"
                }
            }
        }
    elif deployment_method == "webhook":
        instructions = {
            "method": "Webhook",
            "description": "Register a webhook URL to receive agent responses asynchronously.",
            "endpoint": f"{base_url}/agents/webhook/register",
            "headers": {
                "X-API-Key": "<your-x-api-key>",
                "Content-Type": "application/json"
            },
            "example": {
                "register_request": f"POST /agents/webhook/register",
                "body": {
                    "agent_key": agent_key,
                    "webhook_url": f"{base_url}/webhook/receive"
                }
            }
        }
    elif deployment_method == "sdk":
        instructions = {
            "method": "SDK",
            "description": "Use the provided SDK to integrate the agent into your application.",
            "example": {
                "python_code": f"""
from agent_sdk import AgentClient

def integrate_agent(agent_key, api_key):
    client = AgentClient(base_url="{base_url}", api_key=api_key)
    agent = client.get_agent(agent_key)
    response = agent.send_message("Hello, agent!")
    print(f"Agent response: {{response}}")

integrate_agent("{agent_key}", "<your-x-api-key>")
"""
            }
        }
    elif deployment_method == "codeSnippet":
        instructions = {
            "method": "Code Snippet",
            "description": "Embed this code snippet into your application to interact with the agent.",
            "example": {
                "python_code": f"""
            import requests

            def chat_with_agent(agent_key, message, api_key):
                url = "{base_url}/agents/stream/{agent_key}"
                headers = {{
                    "X-API-Key": api_key,
                    "Content-Type": "application/json"
                }}
                data = {{"message": message}}
                response = requests.post(url, json=data, headers=headers)
                if response.status_code == 200:
                    return response.text
                else:
                    raise Exception("Failed to get response: " + response.text)

            try:
                response = chat_with_agent("{agent_key}", "Hello, how can you help me?", "<your-x-api-key>")
                print(f"Agent response: {{response}}")
            except Exception as e:
                print(e)
            """
            }
        }
    return instructions

# Add Webhook Registration Route
@agents_blueprint.route("/webhook/register", methods=["POST"])
def register_webhook():
    try:
        user, account_name, error = validate_api_key()
        if error:
            return error

        tenant_id = user.tenant_id
        if not tenant_id:
            logger.error("Tenant ID not found for user")
            return error_response(message = "Tenant ID not found for user", data = {}, code = 401)

        data = request.json
        if not data or "agent_key" not in data or "webhook_url" not in data:
            logger.error("agent_key and webhook_url are required")
            return error_response(message = "agent_key and webhook_url are required", data = {}, code = 400)

        agent_key = data["agent_key"]
        webhook_url = data["webhook_url"]

        session = next(db_session())
        agent = session.query(Agent).filter_by(agent_key=agent_key, tenant_id=tenant_id, del_flg=False).first()
        if not agent:
            logger.error(f"Agent not found for agent_key: {agent_key}, tenant_id: {tenant_id}")
            return error_response(message = "Agent not found or not authorized", data = {}, code = 404)

        logger.info(f"Webhook registered for agent {agent_key}: {webhook_url}")
        return success_response(message = "Webhook registered successfully", data = {
                "agent_key": agent_key,
                "webhook_url": webhook_url
            }, code = 200)
    except Exception as e:
        logger.error(f"Error registering webhook: {str(e)}")
        return error_response(message = str(e), data = {}, code = 500)
    finally:
        session.close()



# Stream Agent Response
@agents_blueprint.route("/stream/<string:agent_key>", methods=["POST"])
def stream_agent(agent_key):
    try:
        user, account_name, error = validate_api_key()
        if error:
            return error

        tenant_id = user.tenant_id
        session = next(db_session())

        agent = session.query(Agent).filter_by(
            agent_key=agent_key,
            tenant_id=tenant_id,
            del_flg=False
        ).first()

        if not agent:
            return error_response("Agent not found or not authorized", {}, 404)

        # 🔥 NEW
        config = resolve_agent_config(agent)

        data = request.json
        user_input = data.get("message")
        if not user_input:
            return error_response("Message is required", {}, 400)

        memory_type = config.get("memory_mode")

        if memory_type:
            conversation = RunnableWithMessageHistory(
                runnable=prompt | llm,
                get_session_history=lambda session_id: get_session_history(agent.agent_id),
                input_messages_key="input",
                history_messages_key="history"
            )

            def generate():
                response = conversation.invoke(
                    {
                        "input": user_input,
                        "agent_instructions": config.get("agent_instructions", ""),
                        "additional_instructions": config.get("additional_instructions", ""),
                        "agent_name": config.get("agent_name"),
                    },
                    config={"configurable": {"session_id": str(agent.agent_id)}}
                ).content

                for i in range(0, len(response), 10):
                    yield response[i:i + 10]

        else:
            def generate():
                response = (prompt | llm).invoke({
                    "input": user_input,
                    "agent_instructions": config.get("agent_instructions", ""),
                    "additional_instructions": config.get("additional_instructions", ""),
                    "agent_name": config.get("agent_name"),
                    "history": []
                }).content

                for i in range(0, len(response), 10):
                    yield response[i:i + 10]

        return current_app.response_class(generate(), mimetype='text/plain')

    except Exception as e:
        return error_response(str(e), {}, 500)
    finally:
        session.close()


# Get Agent Info (API endpoint)
@agents_blueprint.route("/info/<string:agent_key>", methods=["GET"])
def get_agent_info(agent_key):
    """
    Get basic information about an agent
    """
    try:
        user, account_name, error = validate_api_key()
        if error:
            return error

        tenant_id = user.tenant_id
        if not tenant_id:
            return error_response(message = "Tenant ID not found for user", data = {}, code = 401)

        session = next(db_session())
        agent = session.query(Agent).filter_by(agent_key=agent_key, tenant_id=tenant_id, del_flg=False).first()
        if not agent:
            return error_response(message = "Agent not found or not authorized", data = {}, code = 404)

        # Get LLM details
      
        
        llm_config = session.query(LLM).filter_by(llm_id=agent.llm_model_id).first()
        llm_model = llm_config.base_llm if llm_config else None
        
        
        config = resolve_agent_config(agent)

        agent_info = {
            "agent_key": agent.agent_key,
            "agent_name": config.get("agent_name"),
            "agent_description": config.get("agent_description"),
            "agent_role": config.get("instruction_mode"),
            "llm_model": llm_model.base_model_name if llm_model else "Unknown",
            "has_knowledge_base": bool(config.get("knowledge_base_ids")),
            "memory_enabled": bool(config.get("memory_mode")),
            "memory_type": config.get("memory_mode") or "none",
            "created_at": agent.created_at.isoformat() if agent.created_at else None
        }

        return success_response(message = "Agent information retrieved successfully", data = agent_info, code = 200)

    except Exception as e:
        logger.error(f"Error getting agent info: {str(e)}")
        return error_response(message = str(e), data = {}, code = 500)
    finally:
        session.close()


# Get Agent API Details
@agents_blueprint.route("/api/<int:agent_id>", methods=["GET"])
@jwt_required()
def get_agent_api(agent_id):
    """
    Get API details for a specific agent including curl examples and JSON schemas
    Similar to Lyzr.ai's agent API interface
    """
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")
        if not tenant_id:
            logger.error("Tenant ID not found in token")
            return error_response(message = "Tenant ID not found in token", data = {}, code = 401)

        session = next(db_session())
        
        # Get agent details
        agent = session.query(Agent).filter_by(agent_id=agent_id, tenant_id=tenant_id, del_flg=False).first()
        if not agent:
            logger.error(f"Agent not found for agent_id: {agent_id}, tenant_id: {tenant_id}")
            return error_response(message = "Agent not found or not authorized", data = {}, code = 404)

        # Generate agent_key if not exists
        if not agent.agent_key:
            agent.agent_key = str(uuid.uuid4())
            session.commit()

        # Get user account details for subdomain
        user = session.query(LoginUser).filter_by(tenant_id=tenant_id, del_flg=False).first()
        if not user or not user.account_name:
            logger.error(f"No account_name found for tenant_id: {tenant_id}")
            return error_response(message = "User account configuration error", data = {}, code = 500)

        # Get LLM details
        
        llm_config = session.query(LLM).filter_by(llm_id=agent.llm_model_id).first()
        llm_model = llm_config.base_llm if llm_config else None

        # Build API documentation
        base_url = f"https://{user.account_name}.jnanic.com"
        
        api_details = {
            "agent_info": {
                "agent_id": agent.agent_id,
                "agent_key": agent.agent_key,
                "agent_name": agent.agent_name,
                "agent_description": agent.agent_description,
                "agent_role": agent.instruction_mode,
                "llm_model": llm_model.base_model_name if llm_model else "Unknown",
                "deployment_method": agent.deployment_method,
                "memory_plugin": agent.memory_mode,
                "created_at": agent.created_at.isoformat() if agent.created_at else None
            },
            "api_endpoints": {
                "chat": {
                    "endpoint": f"{base_url}/agents/chat/{agent.agent_key}",
                    "method": "POST",
                    "description": "Send a message to the agent and receive a response"
                },
                "stream": {
                    "endpoint": f"{base_url}/agents/stream/{agent.agent_key}",
                    "method": "POST",
                    "description": "Stream responses from the agent in real-time"
                },
                "info": {
                    "endpoint": f"{base_url}/agents/info/{agent.agent_key}",
                    "method": "GET",
                    "description": "Get agent information"
                }
            },
            "authentication": {
                "type": "API Key",
                "header": "X-API-Key",
                "description": "Include your API key in the X-API-Key header"
            },
            "request_schemas": {
                "chat_request": {
                    "message": "string (required) - The message to send to the agent",
                    "session_id": "string (optional) - Session ID for conversation continuity",
                    "temperature": "float (optional) - Control randomness (0.0-1.0)",
                    "max_tokens": "integer (optional) - Maximum response length"
                }
            },
            "response_schemas": {
                "success_response": {
                    "data": {
                        "response": "string - The agent's response",
                        "session_id": "string - Session ID for continuity",
                        "usage": {
                            "prompt_tokens": "integer",
                            "completion_tokens": "integer",
                            "total_tokens": "integer"
                        }
                    },
                    "message": "string - Status message",
                    "status": "string - 'success' or 'error'"
                },
                "error_response": {
                    "data": {},
                    "message": "string - Error description",
                    "status": "error"
                }
            },
            "code_examples": {
                "curl": {
                    "chat": f"""curl -X POST '{base_url}/agents/chat/{agent.agent_key}' \\
  -H 'Content-Type: application/json' \\
  -H 'X-API-Key: <your-api-key>' \\
  -d '{{
    "message": "Hello, how can you help me?",
    "session_id": "unique-session-id",
    "temperature": 0.7
  }}'""",
                    "stream": f"""curl -X POST '{base_url}/agents/stream/{agent.agent_key}' \\
  -H 'Content-Type: application/json' \\
  -H 'X-API-Key: <your-api-key>' \\
  -d '{{
    "message": "Tell me a story"
  }}'""",
                    "info": f"""curl -X GET '{base_url}/agents/info/{agent.agent_key}' \\
  -H 'X-API-Key: <your-api-key>'"""
                },
                "python": f"""import requests
import json

# Configuration
API_KEY = '<your-api-key>'
AGENT_KEY = '{agent.agent_key}'
BASE_URL = '{base_url}'

# Headers
headers = {{
    'Content-Type': 'application/json',
    'X-API-Key': API_KEY
}}

# Chat with agent
def chat_with_agent(message, session_id=None):
    url = f'{{BASE_URL}}/agents/chat/{{AGENT_KEY}}'
    payload = {{
        'message': message,
        'session_id': session_id,
        'temperature': 0.7
    }}
    
    response = requests.post(url, json=payload, headers=headers)
    
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f'Error: {{response.status_code}} - {{response.text}}')

# Stream response
def stream_response(message):
    url = f'{{BASE_URL}}/agents/stream/{{AGENT_KEY}}'
    payload = {{'message': message}}
    
    response = requests.post(url, json=payload, headers=headers, stream=True)
    
    if response.status_code == 200:
        for chunk in response.iter_content(chunk_size=10):
            if chunk:
                print(chunk.decode('utf-8'), end='', flush=True)
    else:
        raise Exception(f'Error: {{response.status_code}} - {{response.text}}')

# Example usage
try:
    # Regular chat
    result = chat_with_agent("What can you help me with?")
    print(f"Agent response: {{result['data']['response']}}")
    
    # Streaming
    print("\\nStreaming response:")
    stream_response("Tell me about your capabilities")
    
except Exception as e:
    print(f"Error: {{e}}")""",
                "javascript": f"""// Using fetch API
const API_KEY = '<your-api-key>';
const AGENT_KEY = '{agent.agent_key}';
const BASE_URL = '{base_url}';

// Chat with agent
async function chatWithAgent(message, sessionId = null) {{
    const url = `${{BASE_URL}}/agents/chat/${{AGENT_KEY}}`;
    
    const response = await fetch(url, {{
        method: 'POST',
        headers: {{
            'Content-Type': 'application/json',
            'X-API-Key': API_KEY
        }},
        body: JSON.stringify({{
            message: message,
            session_id: sessionId,
            temperature: 0.7
        }})
    }});
    
    if (!response.ok) {{
        throw new Error(`HTTP error! status: ${{response.status}}`);
    }}
    
    return await response.json();
}}

// Stream response
async function streamResponse(message) {{
    const url = `${{BASE_URL}}/agents/stream/${{AGENT_KEY}}`;
    
    const response = await fetch(url, {{
        method: 'POST',
        headers: {{
            'Content-Type': 'application/json',
            'X-API-Key': API_KEY
        }},
        body: JSON.stringify({{ message: message }})
    }});
    
    if (!response.ok) {{
        throw new Error(`HTTP error! status: ${{response.status}}`);
    }}
    
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    
    while (true) {{
        const {{ done, value }} = await reader.read();
        if (done) break;
        
        const chunk = decoder.decode(value, {{ stream: true }});
        console.log(chunk);
    }}
}}

// Example usage
(async () => {{
    try {{
        // Regular chat
        const result = await chatWithAgent('Hello, how are you?');
        console.log('Agent response:', result.data.response);
        
        // Streaming
        console.log('\\nStreaming response:');
        await streamResponse('Tell me a joke');
    }} catch (error) {{
        console.error('Error:', error);
    }}
}})();""",
                "node": f"""const axios = require('axios');

// Configuration
const API_KEY = '<your-api-key>';
const AGENT_KEY = '{agent.agent_key}';
const BASE_URL = '{base_url}';

// Headers
const headers = {{
    'Content-Type': 'application/json',
    'X-API-Key': API_KEY
}};

// Chat with agent
async function chatWithAgent(message, sessionId = null) {{
    const url = `${{BASE_URL}}/agents/chat/${{AGENT_KEY}}`;
    const payload = {{
        message: message,
        session_id: sessionId,
        temperature: 0.7
    }};
    
    try {{
        const response = await axios.post(url, payload, {{ headers }});
        return response.data;
    }} catch (error) {{
        throw new Error(`Error: ${{error.response?.status}} - ${{error.response?.data?.message || error.message}}`);
    }}
}}

// Stream response
async function streamResponse(message) {{
    const url = `${{BASE_URL}}/agents/stream/${{AGENT_KEY}}`;
    const payload = {{ message: message }};
    
    try {{
        const response = await axios.post(url, payload, {{
            headers,
            responseType: 'stream'
        }});
        
        response.data.on('data', (chunk) => {{
            process.stdout.write(chunk.toString());
        }});
        
        response.data.on('end', () => {{
            console.log('\\nStream ended');
        }});
    }} catch (error) {{
        throw new Error(`Error: ${{error.response?.status}} - ${{error.response?.data?.message || error.message}}`);
    }}
}}

// Example usage
(async () => {{
    try {{
        // Regular chat
        const result = await chatWithAgent('What is your purpose?');
        console.log('Agent response:', result.data.response);
        
        // Streaming
        console.log('\\nStreaming response:');
        await streamResponse('Explain quantum computing');
    }} catch (error) {{
        console.error('Error:', error.message);
    }}
}})();"""
            },
            "rate_limits": {
                "requests_per_minute": 60,
                "requests_per_hour": 1000,
                "max_tokens_per_request": 4096
            },
            "best_practices": [
                "Use session_id to maintain conversation context across multiple requests",
                "Implement proper error handling for network issues and API errors",
                "Cache responses when appropriate to reduce API calls",
                "Use streaming for long responses to improve user experience",
                "Monitor your API usage to stay within rate limits",
                "Store your API key securely and never expose it in client-side code"
            ],
            "troubleshooting": {
                "common_errors": [
                    {
                        "error": "401 Unauthorized",
                        "cause": "Invalid or missing API key",
                        "solution": "Ensure X-API-Key header is included with valid API key"
                    },
                    {
                        "error": "404 Not Found",
                        "cause": "Invalid agent key or endpoint",
                        "solution": "Verify agent_key and endpoint URL are correct"
                    },
                    {
                        "error": "429 Too Many Requests",
                        "cause": "Rate limit exceeded",
                        "solution": "Implement rate limiting in your application"
                    },
                    {
                        "error": "500 Internal Server Error",
                        "cause": "Server-side error",
                        "solution": "Contact support if error persists"
                    }
                ]
            }
        }

        return success_response(message = "Agent API details retrieved successfully", data = api_details, code = 200)

    except Exception as e:
        logger.error(f"Error getting agent API details: {str(e)}")
        return error_response(message = str(e), data = {}, code = 500)
    finally:
        session.close()

def _tenant_id_from_token():
    claims = get_jwt()
    return claims.get("tenant_id")

@agents_blueprint.route("/create_agent", methods=["POST"])
@jwt_required()
def create_agent_new():

    session = next(db_session())

    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")

        if not tenant_id:
            logger.warning("Tenant ID missing in JWT")
            return error_response(message = "Unauthorized", data = None, code = 401)

        tenant = session.query(Tenant).filter_by(
            tenant_id=tenant_id,
            del_flg=False
        ).first()

        if not tenant:
            logger.warning(f"Invalid tenant | tenant_id={tenant_id}")
            return error_response(message = "Invalid tenant", data = None, code = 401)

        data = request.get_json() or {}

        agent_name = data.get("agent_name")
        agent_description = data.get("agent_description")

        if not agent_name or not agent_description:
            return error_response(message = "agent_name and agent_description are required", data = None, code = 400)

        agent_name = agent_name.strip()
        agent_description = agent_description.strip()

        if len(agent_name) < 3:
            return error_response(message = "Agent name must be at least 3 characters", data = None, code = 400)

        agent_type = data.get("agent_type")
        persona_style = data.get("persona_style")

        new_agent = Agent(
            tenant_id=tenant_id,
            agent_status=AgentStatusEnum.DRAFT,
            agent_name=agent_name,
            agent_description=agent_description,
            agent_type=agent_type,
            persona_style=persona_style
        )

        # ✅ NEW: persist tenant-selected KBs during agent creation
        kb_ids_raw = data.get("knowledge_base_ids")
        if kb_ids_raw is None:
            knowledge_base_config = data.get("knowledge_base_config") or {}
            kb_ids_raw = knowledge_base_config.get("knowledge_base_ids")

        if kb_ids_raw is not None:
            valid_ids, error = process_agent_kb_ids(session, new_agent, kb_ids_raw)
            if error:
                return error_response(message=error, data=None, code=400)
            new_agent.knowledge_base_ids = valid_ids

        session.add(new_agent)
        session.commit()
       
        # ✅ NEW: get agent_id AFTER commit
        agent_id = new_agent.agent_id

        # ✅ NEW: extract tools from payload
        selected_tools = data.get("selected_tools", [])

        # ✅ NEW: LOOP THROUGH TOOLS
        for tool in selected_tools:
            tool_name = tool.get("tool_name")
            mcp_url = tool.get("mcp_url")
            mcp_id = tool.get("mcp_id")

            action_tools = tool.get("action_tools", [])
            action_tools_description = tool.get("action_tools_description", [])

            # Normalize action_tools
            if action_tools is None:
                action_tools = []
            elif isinstance(action_tools, str):
                action_tools = [action_tools]
            elif not isinstance(action_tools, list):
                action_tools = list(action_tools)

            # Normalize descriptions
            if action_tools_description is None:
                action_tools_description = []
            elif isinstance(action_tools_description, str):
                action_tools_description = [action_tools_description]
            elif not isinstance(action_tools_description, list):
                action_tools_description = list(action_tools_description)

            # -------------------------------
            # CHECK EXISTING TOOL
            # -------------------------------
            existing_tool = session.query(McpAgentTools).filter_by(
                tenant_id=tenant_id,
                agent_id=agent_id,
                tool_name=tool_name
            ).first()

            if existing_tool:
                existing_tool.action_tools = list(
                    set(existing_tool.action_tools or []) | set(action_tools)
                )

                existing_tool.mcp_id = mcp_id
                existing_tool.mcp_url = mcp_url

                existing_tool.action_tools_description = list(
                    set(existing_tool.action_tools_description or []) | set(action_tools_description)
                )

            else:
                new_tool = McpAgentTools(
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    tool_name=tool_name,
                    mcp_url=mcp_url,
                    mcp_id=mcp_id,
                    action_tools=action_tools,
                    action_tools_description=action_tools_description
                )
                session.add(new_tool)

        # ✅ NEW: commit tools
        session.commit()
        logger.info(
            f"Agent created from overview | agent_id={new_agent.agent_id} | tenant_id={tenant_id}"
        )

        return success_response(
            message="Agent created successfully",
            data={
                "agent_id": new_agent.agent_id,
                "agent_name": new_agent.agent_name,
                "status": new_agent.agent_status.value
            },
            code=201
        )

    except Exception:
        session.rollback()
        logger.exception("Unexpected error while creating agent")
        return error_response(message = "Unexpected error occurred", data = None, code = 500)
    finally:
        session.close()
        

@agents_blueprint.route("/<int:agent_id>/overview", methods=["POST", "PATCH"])
@jwt_required()
@validate_agent_access(allowed_status=[AgentStatusEnum.DRAFT,AgentStatusEnum.CREATED])
def update_overview(agent_id):

    session = next(db_session())

    try:
        agent = session.query(Agent).filter_by(
            agent_id=agent_id,
            del_flg=False
        ).first()

        data = request.get_json() or {}

        agent.agent_name = data.get("agent_name", agent.agent_name)
        agent.agent_description = data.get("agent_description", agent.agent_description)
        agent.agent_type = data.get("agent_type", agent.agent_type)
        agent.persona_style = data.get("persona_style", agent.persona_style)

        session.commit()

        return success_response(message = "Overview updated successfully", data = {
                "agent_id": agent.agent_id,
                "agent_name": agent.agent_name
            }, code = 200)

    except Exception:
        session.rollback()
        logger.exception(f"Error updating overview | agent_id={agent_id}")
        return error_response(message = "Unexpected error occurred", data = None, code = 500)
    finally:
        session.close()
        
@agents_blueprint.route("/<int:agent_id>/behaviour", methods=["POST", "PATCH"])
@jwt_required()
@validate_agent_access(allowed_status=[AgentStatusEnum.DRAFT, AgentStatusEnum.CREATED, AgentStatusEnum.LIVE])
def update_behaviour(agent_id):

    session = next(db_session())

    try:
        agent = session.query(Agent).filter_by(
            agent_id=agent_id,
            del_flg=False
        ).first()

        data = request.get_json() or {}

        update_agent_behaviour(agent, data)

        session.commit()

        logger.info(f"Behaviour saved | agent_id={agent.agent_id}")

        return success_response(message = "Behaviour saved successfully", data = None, code = 200)

    except Exception:
        session.rollback()
        logger.exception(f"Error saving behaviour | agent_id={agent_id}")
        return error_response(message = "Unexpected error occurred", data = None, code = 500)
    finally:
        session.close()
        
@agents_blueprint.route("/<int:agent_id>/knowledge-base", methods=["POST", "PATCH"])
@jwt_required()
@validate_agent_access(allowed_status=[AgentStatusEnum.DRAFT,AgentStatusEnum.CREATED])
def update_knowledge_base(agent_id):

    session = next(db_session())

    try:
        agent = session.query(Agent).filter_by(
            agent_id=agent_id,
            del_flg=False
        ).first()

        data = request.get_json() or {}
        kb_ids_raw = data.get("knowledge_base_ids")

        valid_ids, error = process_agent_kb_ids(session, agent, kb_ids_raw)

        if error:
            return error_response(message = error, data = None, code = 400)

        # Replace (not merge — since wizard step)
        agent.knowledge_base_ids = valid_ids

        session.commit()

        logger.info(f"Knowledge base updated | agent_id={agent.agent_id}")

        return success_response(message = "Knowledge base updated successfully", data = {
                "knowledge_base_ids": valid_ids
            }, code = 200)

    except Exception:
        session.rollback()
        logger.exception(f"Error updating knowledge base | agent_id={agent_id}")
        return error_response(message = "Unexpected error occurred", data = None, code = 500)
    finally:
        session.close()


@agents_blueprint.route("/<int:agent_id>/guardrails", methods=["POST", "PATCH"])
@jwt_required()
@validate_agent_access(allowed_status=[AgentStatusEnum.DRAFT,AgentStatusEnum.CREATED])
def update_guardrails(agent_id):

    session = next(db_session())

    try:
        agent = session.query(Agent).filter_by(
            agent_id=agent_id,
            del_flg=False
        ).first()

        data = request.get_json() or {}
        agent.guardrails = build_guardrails_payload(data)

        session.commit()

        logger.info(f"Guardrails saved | agent_id={agent.agent_id}")

        return success_response(message = "Guardrails updated successfully", data = {
                "guardrails": agent.guardrails
            }, code = 200)

    except Exception:
        session.rollback()
        logger.exception(f"Error saving guardrails | agent_id={agent_id}")
        return error_response(message = "Unexpected error occurred", data = None, code = 500)
    finally:
        session.close()
        
        
        

@agents_blueprint.route("/<int:agent_id>/ai-config", methods=["PATCH"])
@jwt_required()
@validate_agent_access(
    allowed_status=[AgentStatusEnum.DRAFT, AgentStatusEnum.CREATED]
)
def update_ai_config(agent_id):

    session = next(db_session())

    try:
        agent = session.query(Agent).filter_by(
            agent_id=agent_id,
            del_flg=False
        ).first()

        if not agent:
            return error_response(
                message="Agent not found",
                data=None,
                code=404
            )

        data = request.get_json() or {}

        model_id = data.get("llm_model_id")

        llm = validate_llm(
            session,
            agent.tenant_id,
            model_id
        )

        if not llm:
            return error_response(
                message="Invalid LLM selected",
                data=None,
                code=400
            )

        temperature = data.get("temperature")
        max_tokens = data.get("max_tokens")

        try:
            temperature = float(temperature) if temperature is not None else None
            max_tokens = int(max_tokens) if max_tokens is not None else None
        except (ValueError, TypeError):
            return error_response(
                message="Invalid temperature or max_tokens",
                data=None,
                code=400
            )

        # Optional: enforce limits from LLM config
        if max_tokens and max_tokens > llm.max_output_tokens:
            return error_response(
                message=f"Max tokens cannot exceed {llm.max_output_tokens}",
                data=None,
                code=400
            )

        # Save the selected LLM row; provider/model are derived from it on reads.
        agent.llm_model_id = llm.llm_id
        agent.temperature = temperature
        agent.max_tokens = max_tokens
        agent.memory_mode = data.get("memory_mode")

        session.commit()

        logger.info(f"AI Config updated | agent_id={agent.agent_id}")

        return success_response(
            message="AI configuration saved successfully",
            data=None,
            code=200
        )

    except Exception:
        session.rollback()
        logger.exception(f"Error updating AI config | agent_id={agent_id}")
        return error_response(
            message="Unexpected error occurred",
            data=None,
            code=500
        )
    finally:
        session.close()
        
               
def publish_agent_for_conversation(agent, session, tenant_id, deployment_method=None):
    """Publish the agent from the conversation update flow."""
    if deployment_method:
        agent.deployment_method = deployment_method

    new_snapshot = build_agent_snapshot(agent)
    new_hash = compute_snapshot_hash(new_snapshot)

    if agent.published_version_id:
        current_live = session.query(AgentVersion).get(agent.published_version_id)
        if current_live and current_live.snapshot_hash == new_hash:
            agent.agent_status = AgentStatusEnum.LIVE
            agent.last_deployed_at = db.func.now()
            return {
                "published": False,
                "reason": "No changes detected",
                "version_number": current_live.version_number if current_live else None
            }
        if current_live:
            current_live.is_live = False

    last_version = (
        session.query(AgentVersion)
        .filter_by(agent_id=agent.agent_id)
        .order_by(AgentVersion.version_number.desc())
        .first()
    )
    next_number = last_version.version_number + 1 if last_version else 1

    new_version = AgentVersion(
        agent_id=agent.agent_id,
        version_number=next_number,
        is_live=True,
        snapshot=new_snapshot,
        snapshot_hash=new_hash,
        deployed_by=tenant_id
    )

    session.add(new_version)
    session.flush()

    agent.published_version_id = new_version.version_id
    agent.agent_status = AgentStatusEnum.LIVE
    agent.last_deployed_at = db.func.now()

    return {
        "published": True,
        "version_number": next_number
    }


@agents_blueprint.route("/<int:agent_id>/publish", methods=["PATCH"])
@jwt_required()
@validate_agent_access(allowed_status=[AgentStatusEnum.DRAFT, AgentStatusEnum.CREATED, AgentStatusEnum.LIVE])
def publish_agent_settings(agent_id):

    session = next(db_session())

    try:
        agent = session.query(Agent).filter_by(
            agent_id=agent_id,
            del_flg=False
        ).first()

        if not agent:
            return error_response(message="Agent not found", data=None, code=404)

        data = request.get_json() or {}

        agent.greeting_message = data.get("greeting_message")
        agent.language = data.get("language")
        agent.timezone = data.get("timezone")
        agent.tone = data.get("tone")
        agent.emoji_mode = data.get("emoji_mode")
        agent.availability_mode = data.get("availability_mode")

        # ---------------------------------------
        # STATUS TRANSITION
        # ---------------------------------------
        if agent.agent_status == AgentStatusEnum.DRAFT:
            agent.agent_status = AgentStatusEnum.CREATED
            logger.info(
                f"Agent status updated to CREATED | agent_id={agent.agent_id}"
            )

        publish_flag = data.get("publish", False)
        if isinstance(publish_flag, str):
            publish_flag = publish_flag.strip().lower() in ["true", "1", "yes", "publish"]

        publish_response = None
        if publish_flag:
            deployment_method = data.get("deployment_method") or agent.deployment_method
            publish_response = publish_agent_for_conversation(
                agent,
                session,
                agent.tenant_id,
                deployment_method=deployment_method
            )

        session.commit()

        response_message = "Conversation settings saved successfully"
        if publish_flag:
            if publish_response and publish_response.get("published"):
                response_message = "Conversation settings saved successfully and agent published"
            else:
                response_message = "Conversation settings saved successfully. No publish changes detected"

        return success_response(
            message=response_message,
            data=publish_response,
            code=200
        )

    except Exception:
        session.rollback()
        logger.exception(f"Error publishing agent settings | agent_id={agent_id}")
        return error_response(message = "Unexpected error occurred", data = None, code = 500)
    finally:
        session.close()




@agents_blueprint.route("/<int:agent_id>/behaviour", methods=["GET"])
@jwt_required()
@validate_agent_access()
def get_behaviour(agent_id):

    session = next(db_session())

    try:
        agent = session.query(Agent).filter_by(
            agent_id=agent_id,
            del_flg=False
        ).first()

        return success_response(message = "Success", data = {
                "agent_instructions": agent.agent_instructions,
                "instruction_mode": agent.instruction_mode,
                "agent_type": agent.agent_type
            }, code = 200)

    finally:
        session.close()
        
        
        
@agents_blueprint.route("/<int:agent_id>/knowledge-base", methods=["GET"])
@jwt_required()
@validate_agent_access()
def get_knowledge_base(agent_id):

    session = next(db_session())

    try:
        agent = session.query(Agent).filter_by(
            agent_id=agent_id,
            del_flg=False
        ).first()

        return success_response(message = "Success", data = {
                "knowledge_base_ids": agent.knowledge_base_ids
            }, code = 200)

    finally:
        session.close()
        
        
@agents_blueprint.route("/<int:agent_id>/guardrails", methods=["GET"])
@jwt_required()
@validate_agent_access()
def get_guardrails(agent_id):

    session = next(db_session())

    try:
        agent = session.query(Agent).filter_by(
            agent_id=agent_id,
            del_flg=False
        ).first()

        return success_response(message = "Success", data = agent.guardrails or {}, code = 200)

    finally:
        session.close()

@agents_blueprint.route("/<int:agent_id>/ai-config", methods=["GET"])
@jwt_required()
@validate_agent_access()
def get_ai_config(agent_id):
    session = next(db_session())

    try:
        agent = session.query(Agent).filter_by(
            agent_id=agent_id,
            del_flg=False
        ).first()

        return success_response(message = "Success", data = {
                "llm_model_id": agent.llm_model_id,
                "temperature": agent.temperature,
                "max_tokens": agent.max_tokens,
                "memory_mode": agent.memory_mode
            }, code = 200)

    finally:
        session.close()
        

@agents_blueprint.route("/<int:agent_id>/conversation", methods=["GET"])
@jwt_required()
@validate_agent_access()
def get_conversation(agent_id):

    session = next(db_session())

    try:
        agent = session.query(Agent).filter_by(
            agent_id=agent_id,
            del_flg=False
        ).first()

        return success_response(message = "Success", data = {
                "agent_status": agent.agent_status.value if agent.agent_status else None,
                "greeting_message": agent.greeting_message,
                "language": agent.language,
                "timezone": agent.timezone,
                "tone": agent.tone,
                "emoji_mode": agent.emoji_mode,
                "availability_mode": agent.availability_mode
            }, code = 200)

    finally:
        session.close()
        
        
@agents_blueprint.route("/new/<int:agent_id>", methods=["GET"])
@jwt_required()
def get_agent_by_id_new(agent_id):

    session = next(db_session())

    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")

        # ✅ Validate tenant_id
        if not tenant_id:
            logger.warning("Tenant ID missing in JWT")
            return error_response("Unauthorized", None, 401)

        # ✅ Validate tenant exists
        tenant = session.query(Tenant).filter_by(
            tenant_id=tenant_id,
            del_flg=False
        ).first()

        if not tenant:
            logger.warning(f"Invalid tenant | tenant_id={tenant_id}")
            return error_response("Invalid tenant", None, 401)

        # ✅ Fetch agent
        agent = session.query(Agent).filter(
            Agent.agent_id == agent_id,
            Agent.tenant_id == tenant_id,
            Agent.del_flg == False
        ).first()

        if not agent:
            return error_response("Agent not found", None, 404)

        # ✅ OPTIONAL: fetch tools (like create logic)
        tools = session.query(McpAgentTools).filter_by(
            tenant_id=tenant_id,
            agent_id=agent_id
        ).all()

        tools_data = [
            {
                "tool_name": t.tool_name,
                "mcp_url": t.mcp_url,
                "mcp_id": t.mcp_id,
                "action_tools": t.action_tools,
                "action_tools_description": t.action_tools_description
            }
            for t in tools
        ]

        return success_response(
            message="Success",
            data={
                "agent_id": agent.agent_id,
                "agent_name": agent.agent_name,
                "agent_description": agent.agent_description,
                "agent_status": agent.agent_status.value if agent.agent_status else None,
                "agent_type": agent.agent_type,
                "persona_style": agent.persona_style,

                "agent_instructions": agent.agent_instructions,
                "instruction_mode": agent.instruction_mode,

                "knowledge_base_ids": agent.knowledge_base_ids,
                "guardrails": agent.guardrails,

                "llm_model_id": agent.llm_model_id,
                "temperature": agent.temperature,
                "max_tokens": agent.max_tokens,
                "memory_mode": agent.memory_mode,

                "greeting_message": agent.greeting_message,
                "language": agent.language,
                "timezone": agent.timezone,
                "tone": agent.tone,
                "emoji_mode": agent.emoji_mode,
                "availability_mode": agent.availability_mode,

                "examples": agent.Examples,
                "additional_instructions": agent.additional_instructions,

                "tools": tools_data,  # ✅ NEW

                "created_at": agent.created_at,
                "updated_at": agent.updated_at
            },
            code=200
        )

    except Exception:
        logger.exception("Error fetching agent by ID")
        return error_response("Failed to fetch agent", None, 500)

    finally:
        session.close()

@agents_blueprint.route("/new/<int:agent_id>", methods=["DELETE"])
@jwt_required()
def delete_agent_new(agent_id):

    session = next(db_session())

    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")

        # ✅ Validate tenant_id
        if not tenant_id:
            logger.warning("Tenant ID missing in JWT")
            return error_response("Unauthorized", None, 401)

        # ✅ Validate tenant exists
        tenant = session.query(Tenant).filter_by(
            tenant_id=tenant_id,
            del_flg=False
        ).first()

        if not tenant:
            logger.warning(f"Invalid tenant | tenant_id={tenant_id}")
            return error_response("Invalid tenant", None, 401)

        # ✅ Fetch agent
        agent = session.query(Agent).filter_by(
            agent_id=agent_id,
            tenant_id=tenant_id,
            del_flg=False
        ).first()

        if not agent:
            return error_response("Agent not found", None, 404)

        # ✅ Soft delete
        agent.agent_status = AgentStatusEnum.DELETED
        agent.del_flg = True

        # ✅ OPTIONAL: also delete tools (recommended)
        session.query(McpAgentTools).filter_by(
            tenant_id=tenant_id,
            agent_id=agent_id
        ).delete()

        session.commit()

        logger.info(f"Agent deleted | agent_id={agent_id} | tenant_id={tenant_id}")

        return success_response(
            message="Agent deleted successfully",
            data=None,
            code=200
        )

    except Exception:
        session.rollback()
        logger.exception("Error deleting agent")
        return error_response("Failed to delete agent", None, 500)

    finally:
        session.close()
        
@agents_blueprint.route("/dashboard/analytics", methods=["GET"])
@jwt_required()
def get_agent_dashboard_analytics():
    try:
        tenant_id = get_jwt().get("tenant_id")

        if not tenant_id:
            return error_response(message = "Tenant ID not found in token", data = None, code = 401)

        analytics = build_agent_dashboard_analytics(tenant_id)

        return success_response(message = "Agent analytics fetched successfully", data = analytics, code = 200)

    except Exception as e:
        logger.exception("Error fetching agent analytics")
        return error_response(message = str(e), data = {}, code = 500)
        

@agents_blueprint.route("/get-all", methods=["GET"])
@jwt_required()
def get_all_agents_new():
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")

        if not tenant_id:
            return error_response(message = "Tenant ID not found in token", data = [], code = 401)

        page = request.args.get("page", 1, type=int)
        per_page = min(request.args.get("per_page", 10, type=int), 100)

        status = request.args.get("agent_status")
        date_from = request.args.get("date_from")
        date_to = request.args.get("date_to")

        query = Agent.query.filter(
            Agent.tenant_id == tenant_id,
            Agent.del_flg == False
        )

        # Status Filter
        if status:
            try:
                status_enum = AgentStatusEnum(status)
                query = query.filter(Agent.agent_status == status_enum)
            except ValueError:
                return error_response(message = "Invalid agent_status value", data = [], code = 400)

        # Date Filters
        if date_from:
            query = query.filter(
                Agent.created_at >= datetime.strptime(date_from, "%Y-%m-%d")
            )

        if date_to:
            query = query.filter(
                Agent.created_at <= datetime.strptime(date_to, "%Y-%m-%d")
            )

        query = query.order_by(desc(Agent.agent_id))

        pagination = query.paginate(
            page=page,
            per_page=per_page,
            error_out=False
        )

        agents = query.all()

        agent_list = [
            {
                "agent_id": agent.agent_id,
                "agent_name": agent.agent_name,
                "agent_description": agent.agent_description,
                "agent_status": agent.agent_status.value if agent.agent_status else None,
                "memory_mode": agent.memory_mode,
                "knowledge_base_count": len(agent.knowledge_base_ids or []),
                "llm_model_id": agent.llm_model_id,
                "created_at": agent.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "updated_at": agent.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
            }
            for agent in agents
        ]

        return success_response(
            message="Agents fetched successfully",
            data=agent_list,
            code=200
        )   

    except Exception as e:
        logger.exception("Error fetching agents")
        return error_response(message = str(e), data = [], code = 500)
