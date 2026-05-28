
from langchain.agents import create_react_agent, AgentExecutor
from langchain_core.prompts import PromptTemplate
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain.memory import ConversationBufferMemory, ConversationSummaryBufferMemory
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_anthropic import ChatAnthropic
from langchain_community.vectorstores import Qdrant
from qdrant_client import QdrantClient
from langgraph.graph import StateGraph, END
from langchain_core.language_models import BaseLanguageModel

import networkx as nx
from networkx.readwrite import json_graph
import requests
import json
import logging
from typing import Dict, List, Any, Optional, TypedDict
from enum import Enum
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from pathlib import Path
import os
from langsmith import Client as LangSmithClient
from langchain_core.prompts import FewShotPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnablePassthrough
from langchain_experimental.plan_and_execute import (
    PlanAndExecute, 
    load_agent_executor,
    load_chat_planner
)
from langchain.prompts.chat import ChatPromptTemplate
# Create logs directory next to this file
log_dir = Path(__file__).resolve().parent / "logs"
log_dir.mkdir(parents=True, exist_ok=True)
log_path = log_dir / "rfq_agent.log"

logging.basicConfig(
    level=logging.INFO,  # Use DEBUG for more detailed logs
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.FileHandler(log_path, mode="a", encoding="utf-8"),  # Save logs to file
        logging.StreamHandler(),  # Show logs in console
    ],
)

print(f"Log file path: {log_path}")
print(f"Exists: {log_path.exists()}")

logger = logging.getLogger("rfq_agent")
logger.info("RFQ Agent logger initialized and writing to log file.")


# 1. Setup LangSmith
langsmith_api_key = os.getenv("LANGSMITH_API_KEY")
if not langsmith_api_key:
    raise RuntimeError("LANGSMITH_API_KEY environment variable is required")
langsmith = LangSmithClient(api_key=langsmith_api_key)

app = FastAPI(title="AI Agent Backend")

from fastapi import Request


# Schemas
class LLMS(Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class DecisionAgentInput(BaseModel):
    llm_provider: str = Field(
        ..., description="Provider name, e.g. openai or anthropic"
    )
    llm_model: str = Field(
        ..., description="Model name like gpt-4-turbo or claude-3-sonnet"
    )
    llm_api_key: str = Field(..., description="LLM API key")
    prompt: str = Field(..., description="Prompt or decision scenario")
    parameters: Optional[Dict[str, Any]] = Field(
        default=None, description="Dynamic input values for the decision"
    )


def execute_decision_agent(data: DecisionAgentInput) -> Dict[str, Any]:
    """Executes a Decision Agent using the provided LLM and input parameters."""

    # 1. Choose the LLM provider
    if data.llm_provider.lower() == "openai":
        llm = ChatOpenAI(model=data.llm_model, api_key=data.llm_api_key)
    elif data.llm_provider.lower() == "anthropic":
        llm = ChatAnthropic(model=data.llm_model, api_key=data.llm_api_key)
    else:
        raise ValueError(f"Unsupported LLM provider: {data.llm_provider}")

    # 2. Build prompt template dynamically
    base_prompt = """You are a decision-making AI. Analyze the following context and inputs, then make a clear decision.

Context / Task:
{prompt}

Inputs:
{parameters}

Respond in JSON format:
{{
  "decision": "...",
  "reasoning": "..."
}}
"""
    prompt_template = ChatPromptTemplate.from_template(base_prompt)
    logger.info(f"Using prompt template: {base_prompt}")

    # 3. Prepare chain
    chain = prompt_template | llm | StrOutputParser()

    # 4. Run the chain
    inputs = {
        "prompt": data.prompt,
        "parameters": json.dumps(data.parameters or {}, indent=2),
    }

    result_text = chain.invoke(inputs)
    logger.info(f"LLM output: {result_text}")

    # 5. Try to parse JSON output safely
    try:
        decision_data = json.loads(result_text)
    except Exception:
        decision_data = {
            "decision": result_text,
            "reasoning": "Raw model output (not valid JSON)",
        }

    return {
        "provider": data.llm_provider,
        "model": data.llm_model,
        "decision": decision_data,
    }


class ToolDefinition(BaseModel):
    category: str = Field(..., description="Category of the tool (e.g., Gmaps, HubSpot)")
    action: str = Field(..., description="Action name of the tool (e.g., commute_time)")
    description: str = Field(..., description="Description of the tool")
    endpoint: str = Field(..., description="API endpoint for the tool")
    parameters: List[Dict[str, Any]] = Field(
        default_factory=list, description="Parameters for the tool"
    )

class AgentConfig(BaseModel):
    name: str = Field(..., description="Agent name")
    description: str = Field(..., description="Agent description")
    llm_provider: LLMS = Field(..., description="LLM provider")
    llm_model: str = Field(..., description="LLM model")
    llm_api_key: str = Field(..., description="LLM API key")
    tools_config: Dict[str, List[ToolDefinition]] = Field(
        default_factory=dict,
        description="Tools configuration, grouped by category (e.g., {'Gmaps': [...], 'HubSpot': [...]})",
    )
    examples: Optional[List[Dict[str, str]]] = Field(
        default_factory=list,
        description="Few-shot examples: [{'input': str, 'output': str}]",
    )
    knowledge_base: Optional[str] = Field(None, description="Path to JSON/Excel file")
    remember_now: bool = Field(True, description="Short-term memory")
    remember_long: bool = Field(False, description="Long-term memory")
    sound_natural: bool = Field(False, description="Conversational tone")
    think_back: bool = Field(False, description="Reflection loop")
    stay_on_topic: bool = Field(False, description="Topic guardrails")
    topic: Optional[str] = Field(None, description="Topic for guardrails")
    explain_clearly: bool = Field(False, description="Explain steps")
    mcp_connect_path: Optional[str] = Field(
        None, description="Path to MCP connect JSON"
    )


class TaskInput(BaseModel):
    task: str = Field(..., description="Task for the agent")
    config: AgentConfig


class AgentState(TypedDict):
    messages: List[BaseMessage]
    memory: Optional[str]  # Serialized memory
    plan: Optional[str]
    topic: Optional[str]
    reflection: Optional[str]
    history: Optional[List[BaseMessage]]
    agent_scratchpad: Optional[List[BaseMessage]]

from tenacity import retry, stop_after_attempt, wait_exponential
# Helper: Call /connect_mcp API
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def connect_mcp(mcp_connect_path: Optional[str]) -> bool:
    """
    Connect to the MCP service using the provided configuration.

    Args:
        mcp_connect_path (Optional[str]): Path to the MCP connect JSON file.

    Returns:
        bool: True if connection is successful.

    Raises:
        Exception: If the connection fails after retries.
    """
    if not mcp_connect_path:
        raise Exception("No MCP connect path provided")
    
    try:
        with open(mcp_connect_path, "r") as f:
            mcp_payload = json.load(f)
        response = requests.post("https://mcp.jnanic.com/connect_mcp", json=mcp_payload)
        if response.status_code == 200:
            logger.info("Successfully connected to MCP")
            return True
        else:
            raise Exception(f"Failed to connect MCP: {response.text}")
    except Exception as e:
        logger.error(f"MCP connection error: {str(e)}")
        raise Exception(f"MCP connection error: {str(e)}")


# Helper: Load tool parameters from JSON


def load_tool_parameters(tools_config: Dict[str, List[Dict[str, Any]]], tool_name: str, category: str) -> Optional[List[Dict]]:
    """
    Load parameters for a specific tool from the tools_config dictionary.

    Args:
        tools_config (Dict[str, List[Dict[str, Any]]]): Tools configuration dictionary.
        tool_name (str): Name of the tool action (e.g., 'commute_time').
        category (str): Category of the tool (e.g., 'Gmaps').

    Returns:
        Optional[List[Dict]]: List of parameter definitions or None if not found.
    """
    try:
        tools = tools_config.get(category, [])
        for tool in tools:
            if tool["action"] == tool_name:
                return tool["parameters"]
        logger.warning(f"Tool '{tool_name}' not found in category '{category}'")
        return []
    except Exception as e:
        logger.error(f"Error loading tool parameters for {category}.{tool_name}: {str(e)}")
        return []

# Helper: Wrap MCP Tools
def create_tools(
    tools_config: Dict[str, List[Dict[str, Any]]], mcp_connect_path: Optional[str] = None
) -> List[Any]:
    """
    Create MCP tools from the provided configuration, ensuring proper connection and endpoint handling.

    Args:
        tools_config (Dict[str, List[Dict[str, Any]]]): Tools configuration, grouped by category.
        mcp_connect_path (Optional[str]): Path to MCP connect JSON.

    Returns:
        List[Any]: List of LangChain tools with fully qualified names (e.g., Gmaps.commute_time).
    """
    tools = []
    if mcp_connect_path:
        try:
            connect_mcp(mcp_connect_path)
        except Exception as e:
            logger.error(f"Failed to connect MCP: {str(e)}")
            # Proceed, as some tools may not require MCP connection
    logger.info(f"Creating tools from config:")  
    for category, tool_list in tools_config.items():
        logger.info(f"Processing category '{category}' with {len(tool_list)} tools")
       
        
        for t in tool_list:
            logger.info(f"Setting up tool: {t}")

            # Use attribute access instead of dict access
            action = t.action
            full_tool_name = f"{category}.{action}"
            endpoint = t.endpoint
            tool_description = t.description
            parameters = t.parameters or []
            http_method = getattr(t, "method", "POST").upper()
            @tool
            # @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
           
            def mcp_tool(
                query: Any,
                endpoint: str = endpoint,
                name: str = full_tool_name,
                params: List[Dict] = parameters,
                method: str = http_method
            ) -> Any:
                """
                Executes an MCP tool with the given query, connecting to the specified endpoint.
                """
                # 🩹 Fix: ensure `query` is always a dict
                if isinstance(query, str):
                    try:
                        query = json.loads(query)
                    except json.JSONDecodeError:
                        logger.warning(f"Tool {name} received non-JSON string input: {query}")
                        query = {"raw_input": query}

                payload = {"tool_name": name, "parameters": query}

                try:
                    logger.info(f"Calling tool {name} at {endpoint} with method {method} and payload: {payload}")
                    if method == "POST":
                        response = requests.post(endpoint, json=payload)
                    elif method == "GET":
                        response = requests.get(endpoint, params=payload)
                    else:
                        raise ValueError(f"Unsupported HTTP method: {method}")

                    if (
                        response.status_code == 400
                        and "MCP client not initialized" in response.text
                        and mcp_connect_path
                    ):
                        logger.warning("MCP client not initialized, attempting to reconnect")
                        connect_mcp(mcp_connect_path)
                        if method == "POST":
                            response = requests.post(endpoint, json=payload)
                        elif method == "GET":
                            response = requests.get(endpoint, params=payload)

                    response.raise_for_status()
                    result = response.json().get("result", "Error")
                    logger.info(f"Tool {name} response: {result}")
                    return result
                except Exception as e:
                    logger.error(f"Error calling tool {name}: {str(e)}")
                    return f"Error calling tool {name}: {str(e)}"


            mcp_tool.name = full_tool_name
            mcp_tool.description = tool_description  # Store description for prompt
            tools.append(mcp_tool)

    logger.info(f"Created {len(tools)} tools: {[tool.name for tool in tools]}")
    return tools
def load_knowledge_retriever(
    collection_name: str, config: AgentConfig
) -> Optional[RunnablePassthrough]:
    """
    Load a retriever from a Qdrant collection using the specified collection name.

    Args:
        collection_name (str): Name of the Qdrant collection (e.g., tenant_103_rfq_rules).
        config (AgentConfig): Agent configuration containing the LLM API key.

    Returns:
        Optional[RunnablePassthrough]: A retriever for querying the Qdrant collection, or None if setup fails.
    """
    if not collection_name:
        logger.warning("No collection name provided for Qdrant knowledge base.")
        return None

    logger.info(f"Loading Qdrant knowledge base from collection: {collection_name}")

    try:
        # Initialize Qdrant client
        qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
        qdrant_client = QdrantClient(
            url=qdrant_url,
            timeout=30,
            check_compatibility=False,  # Suppress version mismatch warnings
        )

        # Verify collection exists
        collections_response = qdrant_client.get_collections()
        collection_exists = any(
            collection.name == collection_name
            for collection in collections_response.collections
        )
        if not collection_exists:
            logger.error(f"Collection '{collection_name}' not found in Qdrant.")
            raise ValueError(f"Collection '{collection_name}' does not exist.")

        # Get collection info to verify vector configuration
        collection_info = qdrant_client.get_collection(collection_name)
        vector_config = collection_info.config.params.vectors
        logger.info(f"Collection '{collection_name}' vector config: {vector_config}")

        # Determine vector name and size
        if isinstance(vector_config, dict):
            # Named vectors (e.g., {'embedding': {...}})
            vector_name = list(vector_config.keys())[0] if vector_config else None
            vector_size = vector_config[vector_name].size if vector_name else None
        else:
            # Unnamed vectors (default)
            vector_name = None
            vector_size = vector_config.size if vector_config else None

        logger.info(
            f"Collection '{collection_name}' has vector size: {vector_size}, vector name: {vector_name or 'unnamed'}"
        )

        # Optional: Scroll to inspect collection contents (for debugging)
        response = qdrant_client.scroll(
            collection_name=collection_name,
            limit=10,  # Fetch up to 10 points for inspection
            with_payload=True,  # Include metadata
            with_vectors=False,  # Skip vectors to save bandwidth
        )
        points, next_offset = response
        logger.info(f"Scrolled {len(points)} points from '{collection_name}'")
        for point in points:
            logger.debug(f"Point ID: {point.id}, Payload: {point.payload}")
        if next_offset:
            logger.debug(f"Next offset for pagination: {next_offset}")

        # Initialize embeddings to match collection dimensionality.
        if vector_size == 3072:
            embedding_model_name = "text-embedding-3-large"
        elif vector_size == 1536:
            embedding_model_name = "text-embedding-3-small"
        else:
            embedding_model_name = os.getenv("KB_EMBEDDING_MODEL", "text-embedding-3-large")

        logger.info(
            "Using embedding model '%s' for collection '%s' (vector_size=%s)",
            embedding_model_name,
            collection_name,
            vector_size,
        )
        embeddings = OpenAIEmbeddings(
            model=embedding_model_name,
            openai_api_key=config.llm_api_key,
        )

        # Create Qdrant vector store
        # content_payload_key must match ingestion key ("text", not LangChain's default "page_content")
        vectorstore = Qdrant(
            client=qdrant_client,
            collection_name=collection_name,
            embeddings=embeddings,
            vector_name=None,  # Use None for unnamed vectors
            content_payload_key="text",
        )

        logger.info(f"Successfully connected to Qdrant collection '{collection_name}'")
        retriever = vectorstore.as_retriever(
            search_kwargs={"k": 4}
        )  # Limit to 4 results
        return retriever

    except Exception as e:
        logger.error(f"Failed to load Qdrant collection '{collection_name}': {str(e)}")
        return None


# Helper: Create LLM (unchanged)
def create_llm(config: AgentConfig) -> BaseLanguageModel:
    api_key = config.llm_api_key
    if config.llm_provider == LLMS.OPENAI:
        return ChatOpenAI(model=config.llm_model, api_key=api_key, temperature=0.7)
    elif config.llm_provider == LLMS.ANTHROPIC:
        return ChatAnthropic(model=config.llm_model, api_key=api_key, temperature=0.7)
    else:
        raise ValueError("Unsupported LLM provider")

# Helper: Build ReAct Prompt
def build_react_prompt(config: AgentConfig, task: str, tools: List[Any]) -> PromptTemplate:
    # tool_names = [tool.name for tool in tools] if tools else []
    # tools_description = "\n".join([f"{tool.name}: {tool.description}" for tool in tools]) if tools else "No tools available."
    
    base_prompt = f"""You are {config.name}, a {config.description} agent. Answer the following questions as best you can. You have access to the following tools:

{{tools}}

Your task is: {task}.
Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{{tool_names}}] or 'None' if no tool is needed
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

Begin!

Question: {{input}}
Thought: {{agent_scratchpad}}
"""
    if config.examples:
        example_prompt = PromptTemplate(
            input_variables=["input", "output"],
            template="Question: {input}\nFinal Answer: {output}\n",
        )
        few_shot_prompt = FewShotPromptTemplate(
            examples=config.examples,
            example_prompt=example_prompt,
            prefix="Examples:\n",
            suffix="\n",
            input_variables=[],
        )
        base_prompt = few_shot_prompt.format() + base_prompt
    
    if config.sound_natural:
        base_prompt += "\nRespond in a natural, conversational tone."
    # if config.stay_on_topic and config.topic:
    #     base_prompt += f"\nStay strictly on topic: {config.topic}. Redirect if off-track."
    
    if config.stay_on_topic:
        base_prompt += f"\nStay strictly on topic. Redirect if off-track."
    if config.explain_clearly:
        base_prompt += "\nExplain your reasoning and steps clearly."
    
    logger.info(f"Built ReAct prompt: {base_prompt}")
    return PromptTemplate.from_template(base_prompt)

# Node: ReAct Agent (updated)
def react_node(state: AgentState, agent_executor: AgentExecutor) -> AgentState:
    logger.info(
        f"React node input: messages={[msg.content for msg in state['messages']]}, agent_scratchpad={state.get('agent_scratchpad', [])}"
    )

    # Ensure agent_scratchpad is a list of BaseMessage
    agent_scratchpad = state.get("agent_scratchpad", [])
    if not isinstance(agent_scratchpad, list):
        logger.warning(f"agent_scratchpad is not a list ({type(agent_scratchpad)}). Converting to list.")
        agent_scratchpad = [AIMessage(content=str(agent_scratchpad))] if agent_scratchpad else []
    # Convert any non-message items
    agent_scratchpad = [
        msg if isinstance(msg, BaseMessage) else AIMessage(content=str(msg))
        for msg in agent_scratchpad
    ]

    # Ensure messages are BaseMessage
    messages = state.get("messages", [])
    if not all(isinstance(msg, BaseMessage) for msg in messages):
        logger.error(f"Invalid messages type: {messages}. Converting to BaseMessage list.")
        messages = [
            HumanMessage(content=str(msg)) if not isinstance(msg, BaseMessage) else msg
            for msg in messages
        ]

    try:
        result = agent_executor.invoke(
            {
                "input": messages[-1].content if messages else ""
            }
        )
        logger.info(f"AgentExecutor result: {result}")
        state["messages"].append(AIMessage(content=result["output"]))
        state["agent_scratchpad"] = result.get("intermediate_steps", [])
    except Exception as e:
        logger.error(f"AgentExecutor failed: {str(e)}")
        state["messages"].append(AIMessage(content=f"Error in agent execution: {str(e)}"))
    return state


# Node: RAG Retrieval (if KB)
def rag_node(state: AgentState, retriever: RunnablePassthrough) -> AgentState:
    if not retriever:
        logger.info("No retriever provided, skipping RAG node.")
        return state
    logger.info(f"state messages: {[msg.content for msg in state['messages']]}")
    query = state["messages"][-1].content
    logger.info(f"Entering RAG node with query: type={type(query)}, value={query}")
    if not isinstance(query, str):
        logger.error(f"Expected string query, got {type(query)}: {query}")
        query = json.dumps(query)  # Convert to string if it's a dict
    try:
        relevant_docs = retriever.invoke(query)  # Perform vector similarity search
        logger.info(f"RAG retrieved {len(relevant_docs)} documents")
        context = "\n".join([doc.page_content for doc in relevant_docs])
        logger.info(f"RAG context: {context}")
        state["messages"].append(AIMessage(content=f"Retrieved context: {context}"))
    except Exception as e:
        logger.error(f"RAG retrieval failed: {str(e)}")
        state["messages"].append(
            AIMessage(content="No relevant context retrieved from knowledge base.")
        )
    return state


# Node: Reflection (Think Back)
def reflect_node(state: AgentState, llm: BaseLanguageModel, config) -> AgentState:
    logger.info("Entering reflection node")
    logger.info(f"config.think_back: {config.think_back}")
    if not config.think_back:  # Global config access; in prod, pass as arg
        return state
    prompt = ChatPromptTemplate.from_template(
        "Reflect on your last response: {last}. Improve it."
    )
    reflection = prompt | llm | StrOutputParser()
    state["reflection"] = reflection.invoke({"last": state["messages"][-1].content})
    state["messages"].append(AIMessage(content=state["reflection"]))
    return state


# Node: Topic Guardrail
def guardrail_node(state: AgentState) -> AgentState:
    if not config.stay_on_topic:
        return state
    # Simple heuristic; enhance with LLM
    if "off-topic" in state["messages"][-1].content.lower():  # Placeholder
        state["messages"].append(HumanMessage(content="Stay on topic!"))
    return state


# Agent Builder
# Agent Builder (updated)
class AgentBuilder:
    def __init__(self, config: AgentConfig):
        self.config = config
        self.llm = create_llm(config)
        self.tools = create_tools(config.tools_config, config.mcp_connect_path)  # Updated create_tools
        self.retriever = (
            load_knowledge_retriever(config.knowledge_base, self.config)
            if config.knowledge_base
            else None
        )
        self.memory = self._setup_memory()
    def _setup_memory(self):
        if self.config.remember_long:
            return ConversationSummaryBufferMemory(llm=self.llm, max_token_limit=500)
        elif self.config.remember_now:
            return ConversationBufferMemory()
        return None

    def _classify_agent_type(self, task: str) -> str:
        prompt = PromptTemplate.from_template(
            """
            You are an AI assistant tasked with classifying a user task into one of three agent types:
            - **plan_execute**: For complex tasks requiring planning, multiple steps, or significant analysis/research.
            - **react**: For tasks requiring reasoning and interaction with tools (e.g., APIs or external services).
            - **reflex**: For simple, straightforward tasks needing a direct response without tools or complex reasoning.

            Task: "{task}"

            Analyze the task and determine the most appropriate agent type. Consider:
            - Complexity (e.g., multiple steps, planning, or analysis needed).
            - Tool usage (e.g., does it likely require external APIs or data retrieval).
            - Directness (e.g., can it be answered immediately with minimal processing).

            Return only one of: "plan_execute", "react", or "reflex".
        """
        )
        chain = prompt | self.llm | StrOutputParser()
        try:
            agent_type = chain.invoke({"task": task}).strip()
            if agent_type not in ["plan_execute", "react", "reflex"]:
                logger.error(
                    f"Invalid agent type returned by LLM: {agent_type}. Falling back to 'react'."
                )
                return "react"
            return agent_type
        except Exception as e:
            logger.error(f"Error classifying agent type: {str(e)}. Falling back to 'react'.")
            return "react"

    def build_graph(self, task: str) -> StateGraph:
        agent_type = self._classify_agent_type(task)
        logger.info(f"Classified agent type: {agent_type}")

        graph = StateGraph(AgentState)

        if agent_type == "react":
            # Create ReAct prompt and agent
            prompt = build_react_prompt(self.config, task, self.tools)
            # logger.info(f"tools for react agent: {[tool.name, tool.tools for tool in self.tools]}")
            react_agent = create_react_agent(self.llm, self.tools, prompt)
            global agent_executor  # Define globally for react_node
            agent_executor = AgentExecutor(
                agent=react_agent,
                tools=self.tools,
                memory=self.memory,
                verbose=True
            )
            if self.retriever:
                logger.info("Adding RAG node to graph since knowledge_base is provided.")
                graph.add_node("rag", lambda state: rag_node(state, self.retriever))
                graph.add_node("agent", lambda state: react_node(state, agent_executor))
                graph.add_edge("rag", "agent")
                graph.set_entry_point("rag")
            else:
                logger.info("No knowledge_base provided, skipping RAG node.")
                graph.add_node("agent", lambda state: react_node(state, agent_executor))
                graph.set_entry_point("agent")
        elif agent_type == "plan_execute":
            # [Unchanged plan_execute logic]
            system_prompt = build_react_prompt(self.config, task, self.tools)
            prompt = ChatPromptTemplate.from_messages([
                ("system", system_prompt),
                MessagesPlaceholder(variable_name="messages"),
            ])
            planner = load_chat_planner(self.llm, prompt)
            executor = load_agent_executor(self.llm, self.tools, prompt)
            pne = PlanAndExecute(
                planner=planner, executor=executor, verbose=True, memory=self.memory
            )

            def pne_node(state: AgentState):
                result = pne.invoke({"input": state["messages"][-1].content})
                state["plan"] = result.get("plan", "")
                state["messages"].append(AIMessage(content=result["output"]))
                return state

            if self.retriever:
                graph.add_node("rag", lambda state: rag_node(state, self.retriever))
                graph.add_node("agent", pne_node)
                graph.add_edge("rag", "agent")
                graph.set_entry_point("rag")
            else:
                graph.add_node("agent", pne_node)
                graph.set_entry_point("agent")
        elif agent_type == "reflex":
            # [Unchanged reflex logic]
            system_prompt = build_react_prompt(self.config, task, self.tools)
            prompt = ChatPromptTemplate.from_messages([
                ("system", system_prompt),
                MessagesPlaceholder(variable_name="messages"),
            ])
            chain = prompt | self.llm | StrOutputParser()
            
            def reflex_node(state: AgentState):
                result = chain.invoke({"messages": state["messages"]})
                state["messages"].append(AIMessage(content=result))
                return state

            if self.retriever:
                graph.add_node("rag", lambda state: rag_node(state, self.retriever))
                graph.add_node("agent", reflex_node)
                graph.add_edge("rag", "agent")
                graph.set_entry_point("rag")
            else:
                graph.add_node("agent", reflex_node)
                graph.set_entry_point("agent")

        if self.config.think_back:
            graph.add_node(
                "reflect", lambda state: reflect_node(state, self.llm, self.config)
            )
            graph.add_edge("agent", "reflect")
            graph.add_edge("reflect", END)
        else:
            graph.add_edge("agent", "guardrail" if self.config.stay_on_topic else END)

        if self.config.stay_on_topic:
            graph.add_node("guardrail", guardrail_node)
            graph.add_edge("guardrail", END)

        return graph

    def export_graph_for_react_flow(self, graph: StateGraph) -> Dict:
        # [Unchanged, included for completeness]
        G = nx.DiGraph()
        for node_name in graph.nodes:
            G.add_node(
                node_name, label=node_name.replace("_", " ").title(), type="node"
            )
        for source, target in graph.edges:
            G.add_edge(source, target)
        G.add_node("START", label="Start", type="start")
        G.add_node("END", label="End", type="end")
        if graph.set_entry_point:
            G.add_edge("START", graph.set_entry_point)
        for node in graph.nodes:
            if not any(source == node for source, _ in graph.edges):
                G.add_edge(node, "END")
        graph_data = json_graph.node_link_data(G)
        react_flow_nodes = [
            {
                "id": node["id"],
                "type": node.get("type", "default"),
                "data": {"label": node.get("label", node["id"])},
                "position": {"x": 100 * i, "y": 100},
            }
            for i, node in enumerate(graph_data["nodes"])
        ]
        react_flow_edges = [
            {
                "id": f"e{edge['source']}-{edge['target']}",
                "source": edge["source"],
                "target": edge["target"],
            }
            for edge in graph_data["links"]
        ]
        return {"nodes": react_flow_nodes, "edges": react_flow_edges}

    def execute(
        self, task: str, graph: StateGraph, state: Optional[Dict] = None
    ) -> Dict[str, Any]:
        logger.info(f"Executing task: {task} with type {type(task)}")
        if isinstance(task, dict):
            task = task.get("task", json.dumps(task))
        elif not isinstance(task, str):
            raise ValueError(
                f"Task must be a string or a dictionary with a 'task' key, got {type(task)}"
            )

        if state is None:
            state = {"messages": [HumanMessage(content=task)], "agent_scratchpad": []}

        flow_export = self.export_graph_for_react_flow(graph)
        compiled_graph = graph.compile()
        if self.memory:
            compiled_graph.memory = self.memory

        result = compiled_graph.invoke(state)
        flow_export["result"] = result
        return flow_export


# API Endpoints

# @app.middleware("http")
# async def log_requests(request: Request, call_next):
#     logger.info(f"Incoming request: {request.method} {request.url}")
#     try:
#         body = await request.body()
#         # logger.info(f"Request body: {body.decode('utf-8')}")
#     except Exception as e:
#         logger.warning(f"Could not read request body: {e}")

#     request._body = body
#     response = await call_next(request)
#     logger.info(f"Completed request {request.url} -> {response.status_code}")
#     return response


# @app.post("/decision_agent")
# def decision_agent(input_data: DecisionAgentInput):
#     logger.info(
#         f"Received decision_agent payload: {input_data.model_dump_json(indent=2)}"
#     )
#     try:
#         result = execute_decision_agent(input_data)
#         return result
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


# @app.post("/create_agent")
# def create_agent(input: TaskInput):
#     try:
#         builder = AgentBuilder(input.config)

#         # config = input.config
#         logger.info(
#             f"creating agent for task{input.task} with datatype{type(input.task)}"
#         )

#         graph = builder.build_graph(input.task)
#         logger.info("graph created successfully")
#         initial_state = {
#             "messages": [HumanMessage(content=input.task)],  # task is your user input
#             "agent_scratchpad": [],                     # empty list to start
#             "memory": None,                             # serialized memory (or empty string)
#             "plan": "",                                 # empty plan
#             "topic": "",                                # empty topic
#             "reflection": "",                           # empty reflection
#             "history": [],                              # conversation history
#         }
#         result = builder.execute(input.task, graph, initial_state)
#         logger.info(f"Executed agent {input.config.name} for task: {input.task}")
#         return {
#             "agent_id": input.config.name,
#             "graph": "Compiled",
#             "type": builder._classify_agent_type(input.task),
#             "result": result,
#         }
#     except Exception as e:
#         logger.exception("Error while creating agent:")
#         raise HTTPException(status_code=400, detail=str(e))


# @app.post("/execute")
# def execute_agent(
#     agent_id: str, task: str, state: Optional[str] = None
# ):  # Assume agent cached by ID
#     # In prod, cache builders by ID
#     config = AgentConfig(...)  # Load from DB/cache
#     builder = AgentBuilder(config)
#     graph = builder.build_graph(task)
#     initial_state = json.loads(state) if state else None
#     result = builder.execute(task, graph, initial_state)
#     return result





# ----------------  Flask Routes ---------------

from flask import Flask, request, jsonify, Blueprint
from functools import wraps
import logging
import json

# Create Flask app
app = Flask(__name__)

# Create Blueprint for agent routes
agent_blueprint = Blueprint("agent", __name__)


# Error handler for consistent error responses
def handle_errors(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            logger.exception(f"Error in {f.__name__}:")
            return jsonify({"error": str(e)}), 500
    return decorated_function


# Middleware equivalent for logging requests
@app.before_request
def log_request():
    logger.info(f"Incoming request: {request.method} {request.url}")
    try:
        if request.data:
            logger.info(f"Request body length: {len(request.data)} bytes")
    except Exception as e:
        logger.warning(f"Could not read request body: {e}")


@app.after_request
def log_response(response):
    logger.info(f"Completed request {request.url} -> {response.status_code}")
    return response


# Route 1: Decision Agent
@agent_blueprint.route("/decision_agent", methods=["POST"])
@handle_errors
def decision_agent():
    """
    Execute a decision agent with the provided LLM configuration.
    
    Expected JSON body:
    {
        "llm_provider": "openai",
        "llm_model": "gpt-4-turbo",
        "llm_api_key": "sk-...",
        "prompt": "Your decision prompt",
        "parameters": {...}
    }
    """
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400
    
    input_data = request.get_json()
    logger.info(f"Received decision_agent payload: {json.dumps(input_data, indent=2)}")
    
    # Validate required fields
    required_fields = ["llm_provider", "llm_model", "llm_api_key", "prompt"]
    missing_fields = [field for field in required_fields if field not in input_data]
    if missing_fields:
        return jsonify({"error": f"Missing required fields: {missing_fields}"}), 400
    
    # Convert to Pydantic model for validation (keep your existing validation)
    try:
        validated_input = DecisionAgentInput(**input_data)
        result = execute_decision_agent(validated_input)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": f"Validation error: {str(e)}"}), 400


# Route 2: Create Agent
@agent_blueprint.route("/create_agent", methods=["POST"])
@handle_errors
def create_agent():
    """
    Create and execute an agent with the provided configuration.
    
    Expected JSON body:
    {
        "task": "Your task description",
        "config": {
            "name": "AgentName",
            "description": "Agent description",
            "llm_provider": "openai",
            "llm_model": "gpt-4-turbo",
            "llm_api_key": "sk-...",
            "tools_config": {...},
            ...
        }
    }
    """
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400
    
    input_data = request.get_json()
    
    # Validate required fields
    if "task" not in input_data or "config" not in input_data:
        return jsonify({"error": "Missing 'task' or 'config' in request body"}), 400
    
    try:
        # Convert to Pydantic model for validation
        validated_input = TaskInput(**input_data)
        
        builder = AgentBuilder(validated_input.config)
        
        logger.info(
            f"Creating agent for task: {validated_input.task} with datatype: {type(validated_input.task)}"
        )
        
        graph = builder.build_graph(validated_input.task)
        logger.info("Graph created successfully")
        
        initial_state = {
            "messages": [HumanMessage(content=validated_input.task)],
            "agent_scratchpad": [],
            "memory": None,
            "plan": "",
            "topic": "",
            "reflection": "",
            "history": [],
        }
        
        result = builder.execute(validated_input.task, graph, initial_state)
        logger.info(f"Executed agent {validated_input.config.name} for task: {validated_input.task}")
        
        response_data = {
            "agent_id": validated_input.config.name,
            "graph": "Compiled",
            "type": builder._classify_agent_type(validated_input.task),
            "result": result,
        }
        
        return jsonify(response_data), 200
        
    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        return jsonify({"error": f"Validation error: {str(e)}"}), 400


# Route 3: Execute Agent
@agent_blueprint.route("/execute", methods=["POST"])
@handle_errors
def execute_agent():
    """
    Execute an agent with provided task and optional state.
    
    Expected JSON body or query params:
    {
        "agent_id": "agent_name",
        "task": "Your task",
        "state": "{...}" (optional)
    }
    """
    # Support both JSON body and query parameters
    if request.is_json:
        data = request.get_json()
        agent_id = data.get("agent_id")
        task = data.get("task")
        state = data.get("state")
    else:
        agent_id = request.args.get("agent_id") or request.form.get("agent_id")
        task = request.args.get("task") or request.form.get("task")
        state = request.args.get("state") or request.form.get("state")
    
    # Validate required parameters
    if not agent_id or not task:
        return jsonify({"error": "Missing 'agent_id' or 'task' parameter"}), 400
    
    try:
        # In production, load config from DB/cache based on agent_id
        # For now, this needs to be implemented based on your requirements
        config = AgentConfig(...)  # Load from DB/cache based on agent_id
        
        builder = AgentBuilder(config)
        graph = builder.build_graph(task)
        
        initial_state = json.loads(state) if state else None
        result = builder.execute(task, graph, initial_state)
        
        return jsonify(result), 200
        
    except json.JSONDecodeError as e:
        return jsonify({"error": f"Invalid JSON in state parameter: {str(e)}"}), 400


# Register the blueprint with the app
app.register_blueprint(agent_blueprint)


# Health check endpoint (optional but recommended)
@app.route("/health", methods=["GET"])
def health_check():
    """Simple health check endpoint"""
    return jsonify({"status": "healthy", "service": "AI Agent Backend"}), 200


# Run the Flask app
if __name__ == "__main__":
    # Flask's built-in development server
    app.run(host="0.0.0.0", port=8003, debug=False)
    
    # For production, use a WSGI server like Gunicorn:
    # gunicorn -w 4 -b 0.0.0.0:8003 app:app
    # Or use waitress (cross-platform):
    # from waitress import serve
    # serve(app, host="0.0.0.0", port=8003)
