from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt,get_jwt_identity
from sqlalchemy import text, cast, Integer
from app.database.DatabaseOperationPostgreSQL import db_session
import json
import logging
from logging.handlers import RotatingFileHandler   # <-- ADD THIS
import os
from flask_jwt_extended import decode_token
from logging_config import setup_logging
from app.models import WorkflowRun,WorkflowNodeLog,WorkflowAgentStepLog
from app.models.bot_diagram import BotDiagram

workflow_blueprint = Blueprint("workflow", __name__)


logger = setup_logging("workflow_routes", level="DEBUG")



# ---------------------- Workflow Executor API --------------------
from engine.workflow_executor import WorkflowExecutor,WorkflowExecutionContext,NodeStatus
from engine.cache_service_hybrid import HybridCacheService

REDIS_URL = "redis://127.0.0.1:6379/0"

def _compute_overall_status(node_outputs):
    """
    Return False if any node failed, True otherwise.
    node_outputs can be dict from WorkflowExecutionContext.node_results or simple dict.
    """
    for node_id, node in node_outputs.items():
        # node might be NodeExecutionResult or dict
        status = getattr(node, "status", None) or node.get("status") if isinstance(node, dict) else None
        if status == "failed" or status == NodeStatus.FAILED.value:
            return False
    return True


def _resolve_bot_id_from_diagram(session, tenant_id, diagram_id):
    if tenant_id is None:
        return None

    diagram = (
        session.query(BotDiagram)
        .filter(
            BotDiagram.diagram_id == diagram_id,
            BotDiagram.tenant_id == tenant_id,
            BotDiagram.del_flg.is_(False),
        )
        .first()
    )
    if not diagram:
        return None
    return diagram.bot_id


def _find_workflow_run(session, tenant_id, diagram_id, bot_id=None, run_id=None, statuses=None):
    """
    Try to find a workflow run using:
    1. the requested bot_id
    2. the bot_id resolved from the diagram
    3. any bot_id for the same tenant + diagram
    """
    bot_candidates = []
    if bot_id is not None:
        bot_candidates.append(bot_id)

    resolved_bot_id = _resolve_bot_id_from_diagram(session, tenant_id, diagram_id)
    if resolved_bot_id is not None:
        bot_candidates.append(resolved_bot_id)

    bot_candidates.append(None)

    seen = set()
    for candidate_bot_id in bot_candidates:
        if candidate_bot_id in seen:
            continue
        seen.add(candidate_bot_id)

        filters = [
            WorkflowRun.tenant_id == tenant_id,
            WorkflowRun.diagram_id == diagram_id,
        ]

        if candidate_bot_id is not None:
            filters.append(WorkflowRun.bot_id == candidate_bot_id)

        if statuses:
            filters.append(WorkflowRun.status.in_(statuses))

        if run_id:
            filters.append(WorkflowRun.id == run_id)
            run = session.query(WorkflowRun).filter(*filters).first()
        else:
            run = (
                session.query(WorkflowRun)
                .filter(*filters)
                .order_by(WorkflowRun.started_at.desc())
                .first()
            )

        if run:
            return run

    return None

@workflow_blueprint.route('/execute', methods=['POST'])
def execute_workflow():
    try:
        logger.debug("======== /execute REQUEST START ========")

        # Log headers safely
        try:
            headers_dict = dict(request.headers)
            if "Authorization" in headers_dict:
                headers_dict["Authorization"] = headers_dict["Authorization"][:20] + "...(truncated)"
            logger.debug(f"Incoming Headers: {headers_dict}")
        except Exception as e:
            logger.error(f"Failed to log headers: {e}")

        # Log body safely
        try:
            raw_body = request.get_data(as_text=True)
            logger.debug(f"Incoming Raw Body: {raw_body[:10000]}")
        except Exception as e:
            logger.error(f"Failed to log raw body: {e}")

        # Parse JSON
        data = request.get_json()
        logger.debug(f"Parsed JSON keys: {list(data.keys()) if data else 'None'}")

        

        # Extract JWT
        auth_header = request.headers.get("Authorization", "")
        jwt_token = None
        if auth_header and auth_header.startswith("Bearer "):
            jwt_token = auth_header.replace("Bearer ", "").strip()

        if not jwt_token:
            logger.error("JWT token is missing from Authorization header")
            return jsonify({"status": False, "error": "JWT token is required in Authorization header"}), 401

        # Prepare trigger data
        trigger_data = (
            data.get("trigger_data")
            or data.get("inputData", {}).get("trigger_data")
            or {}
        )
        logger.debug(f"Initial trigger_data: {trigger_data}")


        # ---- Extract tenant_id from JWT once ----
        decoded = decode_token(jwt_token)
        tenant_id = decoded.get("tenant_id")
        
        if not tenant_id:
            return jsonify({"error": "tenant_id missing in JWT"}), 401


        workflow = data.get('workflow')
        if not workflow:
            logger.error("Missing workflow in request")
            return jsonify({"status": False, "error": "Missing workflow"}), 400
        
        # Ensure required metadata is present
        # ---- Normalize workflow metadata ----
        workflow.setdefault("bot_id", None)
        workflow.setdefault("tenant_id", None)
        workflow.setdefault("diagram_id", None)

        # Apply fallback priority
        workflow["bot_id"] = (
            workflow.get("bot_id")
            or decoded.get("bot_id")
            or data.get("bot_id")
            or 981  # default
        )

        workflow["tenant_id"] = (
            workflow.get("tenant_id")
            or tenant_id   
            or data.get("tenant_id")
        )

        workflow["diagram_id"] = (
            workflow.get("diagram_id")
            or data.get("diagram_id")
            or 1216  # default for testing
        )

        
        # ---- Prepare trigger data ----
        if not trigger_data:
            for node in workflow["nodes"]:
                if node["type"] == "GenralInputNode":
                    trigger_data[node["id"]] = {
                        "tenant_id": tenant_id,
                        "inputs": {}   # default empty
                    }
                elif node["type"] in (
                    "GmailTriggerNode",
                    "WhatsAppTriggerNode",
                    "whatsappTriggerNode",
                    "ExportNode",
                    "whatsappSendMessageNode",
                    "whatsappSendAndWaitNode",
                    "whatsappSendTemplateNode",
                    "whatsappUploadMediaNode",
                    "whatsappDownloadMediaNode",
                    "whatsappDeleteMediaNode",
                    # Slack nodes — must receive tenant_id so credential/channel
                    # resolution works without raising Missing tenant_id errors.
                    "SlackTriggerNode",
                    "slackTriggerNode",
                    "slackSendMessageNode",
                    "slackSendAndWaitNode",
                ):
                    trigger_data[node["id"]] = {
                        "tenant_id": tenant_id,      
                        "formData": node.get("data", {}).get("formData", {})
                    }
        else:
            for node in workflow["nodes"]:
                node_id = node["id"]
                if node_id in trigger_data and "tenant_id" not in trigger_data[node_id]:
                    trigger_data[node_id]["tenant_id"] = tenant_id
        
        
        logger.info(f"Prepared trigger data for {len(trigger_data)} nodes")
        logger.debug(f"Final trigger_data: {trigger_data}")

        # Initialize cache
        # cache_service = HybridCacheService(
        #     redis_url=REDIS_URL,
        #     db_session=db_session,
        #     redis_ttl=3600,
        #     debug=True
        # )
        # logger.debug("Initialized HybridCacheService")

        # Create executor
        executor = WorkflowExecutor(
            workflow,
            enable_parallel=data.get('enable_parallel', True),
            max_retries=data.get('max_retries', 3),
        )
        logger.debug("WorkflowExecutor created")

        # Execute
        result = executor.execute(
            trigger_data=trigger_data,
            return_context=data.get('detailed', True)
        )
        # logger.info(f"Workflow execution successfullllllllllllllllllllllllllllllllllll{result}")

        # Compute status
        # if data.get('detailed', True):
        #     overall_status = _compute_overall_status(result.node_results)
        # else:
        #     overall_status = _compute_overall_status(result)

        # if data.get('detailed', True):
        #     execution_dict = result.to_dict()
        #     execution_dict["workflow_status"] = "failed" if not overall_status else "success"
        #     return jsonify({
        #         "status": overall_status,
        #         "execution": execution_dict
        #     })
        # else:
        #     return jsonify({
        #         "status": overall_status,
        #         "node_outputs": result
        #     })
        
        if data.get('detailed', True):
            # Result is a WorkflowExecutionContext
            execution_dict = result.to_dict()
            
            # Determine overall status from context
            if result.status == "failed":
                overall_status = False
                execution_dict["workflow_status"] = "failed"
            else:
                overall_status = _compute_overall_status(result.node_results)
                execution_dict["workflow_status"] = "success" if overall_status else "failed"
            
            return jsonify({
                "status": overall_status,
                "execution": execution_dict
            })
        else:
            # Result is mapped node_outputs dict
            # For non-detailed mode, check if any node failed
            overall_status = True
            for node_output in result.values():
                if isinstance(node_output, dict) and node_output.get("status") == "failed":
                    overall_status = False
                    break
            
            return jsonify({
                "status": overall_status,
                "node_outputs": result
            })

    except Exception as e:
        logger.exception(f"Workflow execution failed: {e}")
        return jsonify({"status": False, "error": str(e)}), 500


# ------------------ FOR TETING THE NODES ---------------------
from nodes.decision_agent import DecisionRouterNode

@workflow_blueprint.route('/test/decision_router', methods=['POST'])
def test_decision_router():
    """
    Test endpoint for executing DecisionRouterNode.

    Example Request Body:
    {
        "node_id": "router-1",
        "node_data": {
            "formData": {
                "task": "Classify the email intent:\nSubject: {email.subject}\nBody: {email.body}\nReturn only one key: `decision`",
                
                "data_mapping": {
                    "subject": "email.subject",
                    "body": "email.body"
                },

                "conditions": [
                    { "value": "RFQ", "target": "rfq_agent" },
                    { "value": "FOLLOWUP", "target": "followup_agent" },
                    { "value": "SUPPORT", "target": "support_agent" }
                ],

                "default_target": "fallback_agent"
            }
        },

        "context": {
            "email": {
                "subject": "Request for quotation: Samsung SSD",
                "body": "Hello, can you share price and availability for 1TB SSD?"
            }
        }
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": False, "error": "Invalid request"}), 400

        node_id = data.get("node_id", "decision-router")
        node_data = data.get("node_data", {})
        context = data.get("context", {})

        router_node = DecisionRouterNode(node_id, node_data)
        result = router_node.execute(context)

        return jsonify({
            "status": True,
            "node_id": node_id,
            "result": result
        }), 200

    except Exception as e:
        logger.error(f"[DecisionRouter Test] Failed: {e}", exc_info=True)
        return jsonify({
            "status": False,
            "error": str(e),
            "trace": traceback.format_exc()
        }), 500





import traceback
import time 
from engine.utils import prepare_agent_input
from engine.generic_agent_node import GenericAgentNode



@workflow_blueprint.route('/test/agent_node', methods=['POST'])
def test_agent_node():
    data = request.get_json()

    node_id = data.get("node_id", "test-generic-agent")
    node_data = data.get("node_data", {})
    context = data.get("context", {})
    parameters = data.get("parameters", {})   # ✅ ADD THIS

    agent_node = GenericAgentNode(node_id, node_data)
    result = agent_node.execute(
        context=context,
        parameters=parameters                  # ✅ AND THIS
    )

    return jsonify({
        "status": True,
        "node_id": node_id,
        "result": result
    }), 200


@workflow_blueprint.route("/test/config/<int:agent_id>", methods=["GET"])
def test_agent_config(agent_id):
    """
    Test endpoint to fetch agent configuration.
    
    Usage:
        GET /api/agent/test/config/101?use_temp_llm=true
    
    Query Parameters:
        - use_temp_llm: true/false (optional, defaults to true)
    
    Returns:
        Agent configuration from database
    """
    try:
        use_temp_llm = request.args.get("use_temp_llm", "true").lower() == "true"
        
        logger.info(f"Fetching config for agent_id={agent_id}, use_temp_llm={use_temp_llm}")
        
        # Fetch configuration
        agent_input = prepare_agent_input(
            agent_id=agent_id,
            task="",
            use_temp_llm=use_temp_llm
        )
        
        return jsonify({
            "status": True,
            "agent_id": agent_id,
            "config": agent_input["config"],
            "use_temp_llm": use_temp_llm
        }), 200
        
    except ValueError as e:
        logger.error(f"Agent not found: {e}")
        return jsonify({
            "status": False,
            "error": f"Agent with id={agent_id} not found"
        }), 404
        
    except Exception as e:
        logger.error(f"Error fetching config: {e}", exc_info=True)
        return jsonify({
            "status": False,
            "error": str(e)
        }), 500




# Import your GmailTriggerNode
from nodes.gmail_trigger_node import GmailTriggerNode

@workflow_blueprint.route("/test/gmail_trigger", methods=["POST"])
@jwt_required()
def test_gmail_trigger():
    """
    Route to test the GmailTriggerNode using JWT to fetch tenant_id.
    No payload required.
    """
    try:
        # Extract tenant_id from JWT claims
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")
        if not tenant_id:
            return jsonify({"error": "Missing tenant_id in token"}), 401

        # Use a default flow_id since no payload is expected
        flow_id = "rfq_quotation_flow_v1"

        # Extract JWT token from Authorization header
        raw_auth = request.headers.get("Authorization", "")
        if raw_auth.startswith("Bearer "):
            jwt_token = raw_auth.split(" ", 1)[1]
        else:
            jwt_token = raw_auth

        if not jwt_token:
            return jsonify({"error": "Authorization header missing or malformed"}), 401

        # Prepare inputs as executor would pass
        inputs = {
            "tenant_id": tenant_id,
            "jwt": jwt_token
        }

        # Initialize GmailTriggerNode
        node = GmailTriggerNode(
            node_id="gmail_trigger_test",
            node_data={"flow_id": flow_id, "tool_name": "GmailTool"}
        )

        output = node.execute(inputs)

        return jsonify({"status": True, "output": output}), 200

    except Exception as e:
        return jsonify({
            "status": False,
            "error": str(e),
            "trace": traceback.format_exc()
        }), 500




from nodes.export_node import ExportNode


@workflow_blueprint.route("/test/export_gmail", methods=["POST"])
def test_export_gmail():
    """
    Test endpoint for ExportNode using GmailStrategy.
    Passes tenant_id, form_data, and JWT token (Authorization header).
    The JWT is required by GmailStrategy to fetch credentials securely.
    """
    import traceback
    from nodes.export_node import ExportNode  # adjust import if needed

    try:
        # Extract JWT from Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid Authorization header"}), 401

        jwt_token = auth_header.replace("Bearer ", "").strip()

        # Parse JSON body
        data = request.get_json() or {}
        tenant_id = data.get("tenant_id")
        form_data = data.get("form_data", {})

        # Validate inputs
        if not tenant_id:
            return jsonify({"error": "Missing tenant_id"}), 400
        if not form_data:
            return jsonify({"error": "Missing form_data in request"}), 400
        if not form_data.get("type"):
            return jsonify({"error": "Missing 'type' field in form_data"}), 400

        # Create ExportNode dynamically based on export type
        node = ExportNode(
            node_id="export_gmail_test",
            node_data={"export_type": form_data["type"]}
        )

        # Construct the input payload for node execution
        inputs = {
            "tenant_id": tenant_id,
            "form_data": form_data,
            "jwt": jwt_token  # pass token so strategy can fetch credentials
        }

        # Execute node
        output = node.execute(inputs)

        return jsonify({"status": True, "output": output}), 200

    except Exception as e:
        return jsonify({
            "status": False,
            "error": str(e),
            "trace": traceback.format_exc()
        }), 500

from nodes.set_node import SetNode

@workflow_blueprint.route('/test/set_node', methods=['POST'])
def execute_set_node():
    """
    Execute SetNode with trigger data and mapping configuration
    
    Request Body:
    {
        "trigger_data": {
            "gmail-trigger-1": [...],  // Your Gmail trigger output
        },
        "config": {
            "mappings": [...]
        },
        "debug": true  // Optional: enable detailed debug logging
    }
    
    Response:
    {
        "status": true,
        "output": {...},
        "debug_info": {...}  // Only included if debug=true
    }
    """
    request_start_time = time.time()
    debug_mode = False
    
    try:
        logger.info("=" * 100)
        logger.info("SET NODE TEST ENDPOINT - REQUEST RECEIVED")
        logger.info("=" * 100)
        
        # Get and validate request data
        logger.info(f"Request method: {request.method}")
        logger.info(f"Content-Type: {request.content_type}")
        logger.info(f"Request URL: {request.url}")
        
        data = request.get_json()
        
        if not data:
            logger.error("✗ No JSON data in request body")
            return jsonify({
                'status': False,
                'error': 'Request body is required'
            }), 400
        
        logger.info(f"✓ JSON data received successfully")
        logger.info(f"Top-level keys in request: {list(data.keys())}")
        
        # Check for debug flag
        debug_mode = data.get('debug', False)
        logger.info(f"Debug mode: {debug_mode}")
        
        # Validate required fields
        if 'trigger_data' not in data:
            logger.error("✗ Missing 'trigger_data' field")
            return jsonify({
                'status': False,
                'error': "Missing required field: 'trigger_data'"
            }), 400
        
        if 'config' not in data:
            logger.error("✗ Missing 'config' field")
            return jsonify({
                'status': False,
                'error': "Missing required field: 'config'"
            }), 400
        
        logger.info("✓ All required top-level fields present")
        
        trigger_data = data['trigger_data']
        config = data['config']
        
        # Log trigger_data structure
        logger.info("\n" + "-" * 80)
        logger.info("TRIGGER DATA ANALYSIS")
        logger.info("-" * 80)
        logger.info(f"Trigger data type: {type(trigger_data)}")
        
        if isinstance(trigger_data, dict):
            logger.info(f"Trigger data keys: {list(trigger_data.keys())}")
            
            for key, value in trigger_data.items():
                logger.info(f"\n  Key: '{key}'")
                logger.info(f"    Type: {type(value)}")
                
                if isinstance(value, list):
                    logger.info(f"    List length: {len(value)}")
                    if len(value) > 0:
                        logger.info(f"    First item type: {type(value[0])}")
                        if isinstance(value[0], dict):
                            logger.info(f"    First item keys: {list(value[0].keys())}")
                elif isinstance(value, dict):
                    logger.info(f"    Dict keys: {list(value.keys())}")
                else:
                    preview = str(value)[:100]
                    logger.info(f"    Value preview: {preview}...")
        else:
            logger.warning(f"⚠ Trigger data is not a dict: {type(trigger_data)}")
        
        # Log config structure
        logger.info("\n" + "-" * 80)
        logger.info("CONFIG ANALYSIS")
        logger.info("-" * 80)
        logger.info(f"Config type: {type(config)}")
        logger.info(f"Config keys: {list(config.keys())}")
        
        # Validate config
        if 'mappings' not in config:
            logger.error("✗ Missing 'mappings' field in config")
            return jsonify({
                'status': False,
                'error': 'Config must contain mappings array'
            }), 400
        
        mappings = config.get('mappings', [])
        logger.info(f"Number of mappings: {len(mappings)}")
        
        # Log each mapping
        for idx, mapping in enumerate(mappings):
            logger.info(f"\n  Mapping {idx + 1}:")
            logger.info(f"    Field: {mapping.get('field', 'NOT SET')}")
            logger.info(f"    Source: {mapping.get('source', 'NOT SET')}")
            logger.info(f"    Transform: {mapping.get('transform', 'None')}")
            
            # Validate mapping structure
            if not mapping.get('field'):
                logger.warning(f"    ⚠ Warning: Missing 'field' in mapping {idx + 1}")
            if not mapping.get('source'):
                logger.warning(f"    ⚠ Warning: Missing 'source' in mapping {idx + 1}")
        
        logger.info("\n" + "-" * 80)
        logger.info("CREATING SET NODE INSTANCE")
        logger.info("-" * 80)
        
        # Create SetNode instance
        node_id = "test-set-node"
        logger.info(f"Node ID: {node_id}")
        logger.info(f"Config being passed to SetNode: {json.dumps(config, indent=2)}")
        
        try:
            set_node = SetNode(node_id, config)
            logger.info("✓ SetNode instance created successfully")
        except Exception as e:
            logger.error(f"✗ Failed to create SetNode instance: {e}")
            logger.error(traceback.format_exc())
            raise
        
        # Set debug mode
        if hasattr(set_node, 'DEBUG_EXTRACTION'):
            set_node.DEBUG_EXTRACTION = debug_mode
            logger.info(f"✓ Debug mode set to: {debug_mode}")
        else:
            logger.warning("⚠ SetNode doesn't have DEBUG_EXTRACTION attribute")
        
        logger.info("\n" + "-" * 80)
        logger.info("EXECUTING SET NODE")
        logger.info("-" * 80)
        
        execution_start = time.time()
        
        try:
            output = set_node.execute(trigger_data)
            execution_time = time.time() - execution_start
            
            logger.info(f"✓ SetNode execution completed in {execution_time:.3f}s")
            logger.info(f"Output type: {type(output)}")
            logger.info(f"Output keys: {list(output.keys()) if isinstance(output, dict) else 'Not a dict'}")
            
            # Log output details
            if isinstance(output, dict):
                logger.info("\n" + "-" * 80)
                logger.info("OUTPUT DETAILS")
                logger.info("-" * 80)
                
                for key, value in output.items():
                    logger.info(f"\n  Field: '{key}'")
                    logger.info(f"    Type: {type(value)}")
                    
                    if isinstance(value, str):
                        preview = value[:200] if len(value) > 200 else value
                        logger.info(f"    Length: {len(value)}")
                        logger.info(f"    Preview: {preview}{'...' if len(value) > 200 else ''}")
                    elif isinstance(value, (list, dict)):
                        logger.info(f"    Length/Size: {len(value)}")
                    else:
                        logger.info(f"    Value: {value}")
                
                if len(output) == 0:
                    logger.warning("⚠ WARNING: Output dictionary is EMPTY!")
                    logger.warning("This means no mappings were successfully processed")
            else:
                logger.warning(f"⚠ Output is not a dictionary: {type(output)}")
            
        except Exception as e:
            execution_time = time.time() - execution_start
            logger.error(f"✗ SetNode execution failed after {execution_time:.3f}s")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error message: {str(e)}")
            logger.error(f"Traceback:\n{traceback.format_exc()}")
            raise
        
        # Prepare response
        total_time = time.time() - request_start_time
        
        logger.info("\n" + "=" * 100)
        logger.info("SET NODE TEST ENDPOINT - REQUEST COMPLETED SUCCESSFULLY")
        logger.info(f"Total request time: {total_time:.3f}s")
        logger.info(f"Execution time: {execution_time:.3f}s")
        logger.info(f"Output fields count: {len(output) if isinstance(output, dict) else 0}")
        logger.info("=" * 100 + "\n")
        
        response_data = {
            'status': True,
            'output': output
        }
        
        # Add debug info if debug mode is enabled
        if debug_mode:
            response_data['debug_info'] = {
                'execution_time_ms': round(execution_time * 1000, 2),
                'total_time_ms': round(total_time * 1000, 2),
                'mappings_count': len(mappings),
                'output_fields_count': len(output) if isinstance(output, dict) else 0,
                'trigger_data_keys': list(trigger_data.keys()) if isinstance(trigger_data, dict) else [],
                'successful_mappings': list(output.keys()) if isinstance(output, dict) else []
            }
        
        return jsonify(response_data)
    
    except Exception as e:
        total_time = time.time() - request_start_time
        
        logger.error("\n" + "=" * 100)
        logger.error("SET NODE TEST ENDPOINT - REQUEST FAILED")
        logger.error("=" * 100)
        logger.error(f"Total request time: {total_time:.3f}s")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Error message: {str(e)}")
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
        logger.error("=" * 100 + "\n")
        
        error_response = {
            'status': False,
            'error': str(e),
            'error_type': type(e).__name__
        }
        
        # Add debug info in error response if debug mode was enabled
        if debug_mode:
            error_response['debug_info'] = {
                'total_time_ms': round(total_time * 1000, 2),
                'traceback': traceback.format_exc()
            }
        
        return jsonify(error_response), 500

from engine.utils import prepare_agent_input

@workflow_blueprint.route("/agents/<int:agent_id>/input", methods=["GET"])
def get_agent_input(agent_id: int):
    """
    Test endpoint to fetch agent input payload (Flask version).
    Pass ?task=...&use_temp_llm=true|false in query params.
    """
    try:
        task = request.args.get("task", "")
        use_temp_llm_str = request.args.get("use_temp_llm", "true").lower()
        use_temp_llm = use_temp_llm_str == "true"

        agent_input = prepare_agent_input(agent_id, task, use_temp_llm)
        return jsonify({"status": True, "data": agent_input})

    except Exception as e:
        return jsonify({"status": False, "error": str(e)}), 500








# ----------- Logs Routes -------------------

@workflow_blueprint.route("/logs", methods=["GET"])
@jwt_required()
def get_latest_workflow_logs():
    bot_id = request.args.get("bot_id", type=int)
    diagram_id = request.args.get("diagram_id", type=int)

    session = next(db_session())

    run = _find_workflow_run(session, tenant_id=None, diagram_id=diagram_id, bot_id=bot_id)

    if not run:
        return jsonify([]), 200

    logs = (
        session.query(WorkflowNodeLog)
        .filter(WorkflowNodeLog.run_id == run.id)
        .order_by(WorkflowNodeLog.created_at.asc())
        .all()
    )

    response = {
        "run": {
            "run_id": run.id,
            "status": run.status,
            "started_at": run.started_at,
            "completed_at": run.completed_at
        },
        "logs": [
            {
                "node_id": l.node_id,
                "node_type": l.node_type,
                "event_type": l.event_type,
                "status": l.status,
                "message": l.message,
                "duration_ms": l.duration_ms
            }
            for l in logs
        ]
    }

    session.close()
    return jsonify(response), 200


@workflow_blueprint.route("/logs/node", methods=["GET"])
@jwt_required()
def get_node_logs_by_context():
 
    # -------------------------
    # Extract tenant_id safely
    # -------------------------
    claims = get_jwt() or {}
    tenant_id = claims.get("tenant_id")

    if not tenant_id:
        logger.warning("tenant_id missing in JWT claims")
        return jsonify({
            "status": False,
            "error": "tenant_id missing in JWT"
        }), 401


    # 📥 Query params (tenant_id REMOVED)
    bot_id = request.args.get("bot_id", type=int)
    diagram_id = request.args.get("diagram_id", type=int)
    node_id = request.args.get("node_id", type=str)
    node_type = request.args.get("node_type", type=str)
    run_id = request.args.get("run_id", type=int)  # ✅ OPTIONAL

    if not all([diagram_id, node_id]):
        return jsonify({
            "error": "diagram_id and node_id are required"
        }), 400

    logger.info(
        "[LOGS] Fetching node logs | tenant=%s bot=%s diagram=%s node=%s run_id=%s",
        tenant_id, bot_id, diagram_id, node_id, run_id
    )

    session = next(db_session())

    try:
        # 1️⃣ Resolve workflow run
        run = _find_workflow_run(
            session=session,
            tenant_id=tenant_id,
            diagram_id=diagram_id,
            bot_id=bot_id,
            run_id=run_id,
        )

        if not run:
            logger.warning(
                "[LOGS] No workflow run found | tenant=%s bot=%s diagram=%s",
                tenant_id, bot_id, diagram_id
            )
            return jsonify({"run": None, "logs": []}), 200

        # 2️⃣ Build log query
        log_query = (
            session.query(WorkflowNodeLog)
            .filter(
                WorkflowNodeLog.run_id == run.id,
                WorkflowNodeLog.node_id == node_id
            )
            .order_by(WorkflowNodeLog.created_at.asc())
        )

        if node_type:
            log_query = log_query.filter(
                WorkflowNodeLog.node_type == node_type
            )

        logs = log_query.all()

        # 2.1️⃣ Fallback for node-level visibility:
        # If latest run has no logs for this node (common with branchy flows),
        # pick the most recent run that actually logged this node.
        if not logs and not run_id:
            fallback_query = (
                session.query(WorkflowNodeLog, WorkflowRun)
                .join(WorkflowRun, WorkflowRun.id == WorkflowNodeLog.run_id)
                .filter(
                    WorkflowRun.tenant_id == tenant_id,
                    WorkflowRun.diagram_id == diagram_id,
                    WorkflowNodeLog.node_id == node_id,
                )
            )

            if bot_id:
                fallback_query = fallback_query.filter(WorkflowRun.bot_id == bot_id)

            if node_type:
                fallback_query = fallback_query.filter(WorkflowNodeLog.node_type == node_type)

            fallback_row = fallback_query.order_by(WorkflowNodeLog.created_at.desc()).first()

            if fallback_row:
                _, fallback_run = fallback_row
                run = fallback_run

                log_query = (
                    session.query(WorkflowNodeLog)
                    .filter(
                        WorkflowNodeLog.run_id == run.id,
                        WorkflowNodeLog.node_id == node_id,
                    )
                    .order_by(WorkflowNodeLog.created_at.asc())
                )

                if node_type:
                    log_query = log_query.filter(WorkflowNodeLog.node_type == node_type)

                logs = log_query.all()
                logger.info(
                    "[LOGS] Fallback run selected | run_id=%s node=%s count=%s",
                    run.id,
                    node_id,
                    len(logs),
                )

        logger.info(
            "[LOGS] Returned %d logs | run_id=%s node=%s",
            len(logs), run.id, node_id
        )

        return jsonify({
            "run": {
                "run_id": run.id,
                "workflow_id": run.diagram_id,
                "diagram_id": run.diagram_id,
                "bot_id": run.bot_id,
                "status": run.status,
                "started_at": run.started_at,
                "completed_at": run.completed_at
            },
            "logs": [
                {
                    "id": l.id,
                    "run_id": l.run_id,
                    "workflow_id": run.diagram_id,
                    "timestamp": l.created_at,
                    "node_id": l.node_id,
                    "node_type": l.node_type,
                    "event_type": l.event_type,
                    "status": l.status,
                    "log_level": l.log_level,
                    "message": l.message,
                    "duration_ms": l.duration_ms
                }
                for l in logs
            ]
        }), 200

    finally:
        session.close()

@workflow_blueprint.route("/runs/<int:run_id>/logs", methods=["GET"])
@jwt_required()
def get_logs_by_run(run_id):
    session = next(db_session())

    logs = (
        session.query(WorkflowNodeLog)
        .filter(WorkflowNodeLog.run_id == run_id)
        .order_by(WorkflowNodeLog.id.asc())
        .all()
    )

    response = [
        {
            "id": l.id,
            "node_id": l.node_id,
            "node_type": l.node_type,
            "event_type": l.event_type,
            "status": l.status,
            "message": l.message,
            "duration_ms": l.duration_ms,
            "created_at": l.created_at
        }
        for l in logs
    ]

    session.close()
    return jsonify(response), 200



# ----------------- Workflwo runs routes --------------------
@workflow_blueprint.route("/runs", methods=["GET"])
@jwt_required()
def list_workflow_runs():
    bot_id = request.args.get("bot_id", type=int)
    diagram_id = request.args.get("diagram_id", type=int)
    limit = request.args.get("limit", 20, type=int)
    offset = request.args.get("offset", 0, type=int)

    session = next(db_session())

    query = session.query(WorkflowRun).filter(
        WorkflowRun.bot_id == bot_id,
        WorkflowRun.diagram_id == diagram_id
    )

    total = query.count()

    runs = (
        query.order_by(WorkflowRun.started_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    response = {
        "total": total,
        "runs": [
            {
                "run_id": r.id,
                "status": r.status,
                "started_at": r.started_at,
                "completed_at": r.completed_at
            }
            for r in runs
        ]
    }

    session.close()
    return jsonify(response), 200

@workflow_blueprint.route("/runs/latest", methods=["GET"])
@jwt_required()
def get_latest_workflow_run():
    session = None
    try:
        logger.debug("======== /runs/latest REQUEST START ========")

        # -------------------------
        # Extract tenant_id safely
        # -------------------------
        claims = get_jwt() or {}
        tenant_id = claims.get("tenant_id")

        if not tenant_id:
            logger.warning("tenant_id missing in JWT claims")
            return jsonify({
                "status": False,
                "error": "tenant_id missing in JWT"
            }), 401

        # -------------------------
        # Query params
        # detailed = TRUE by default
        # -------------------------
        bot_id = request.args.get("bot_id", type=int)
        diagram_id = request.args.get("diagram_id", type=int)
        detailed = request.args.get("detailed", "true").lower() == "true"

        if not bot_id or not diagram_id:
            logger.warning(
                f"Missing params | tenant_id={tenant_id}, "
                f"bot_id={bot_id}, diagram_id={diagram_id}"
            )
            return jsonify({
                "status": False,
                "error": "bot_id and diagram_id are required"
            }), 400

        logger.debug(
            f"Fetching latest run | tenant_id={tenant_id}, "
            f"bot_id={bot_id}, diagram_id={diagram_id}, detailed={detailed}"
        )

        # -------------------------
        # DB query
        # -------------------------
        session = next(db_session())

        latest_run = _find_workflow_run(
            session=session,
            tenant_id=tenant_id,
            diagram_id=diagram_id,
            bot_id=bot_id,
            statuses=["completed", "partial", "failed"],
        )

        if not latest_run:
            logger.info(
                f"No runs found | tenant_id={tenant_id}, "
                f"bot_id={bot_id}, diagram_id={diagram_id}"
            )
            return jsonify({
                "status": False,
                "error": "No workflow runs found"
            }), 404

        logger.debug(
            f"Latest run found | run_id={latest_run.id}, status={latest_run.status}"
        )

        # -------------------------
        # Read stored execution data
        # -------------------------
        execution_dict = latest_run.context_json or {}

        # NEVER recompute execution status here
        workflow_status = execution_dict.get("workflow_status") or latest_run.status

        # -------------------------
        # Response
        # -------------------------
        if detailed:
            response = {
                "status": workflow_status == "success",
                "run_id": latest_run.id,
                "execution": execution_dict,
                "meta": {
                    "run_status": latest_run.status,
                    "trigger_type": latest_run.trigger_type,
                    "started_at": latest_run.started_at,
                    "completed_at": latest_run.completed_at
                }
            }
        else:
            response = {
                "status": workflow_status == "success",
                "run_id": latest_run.id,
                "node_outputs": execution_dict.get("node_outputs", {}),
                "meta": {
                    "run_status": latest_run.status,
                    "trigger_type": latest_run.trigger_type,
                    "completed_at": latest_run.completed_at
                }
            }

        logger.debug(
            f"/runs/latest SUCCESS | run_id={latest_run.id}, detailed={detailed}"
        )

        return jsonify(response), 200

    except Exception as e:
        logger.exception("Failed to fetch latest workflow run")
        return jsonify({
            "status": False,
            "error": "Failed to fetch latest workflow run",
            "details": str(e)
        }), 500

    finally:
        if session:
            session.close()
            
            
            

#--------------- Agent Step Logs ---------------

@workflow_blueprint.route("/agent-logs", methods=["POST"])
@jwt_required(optional=True)
def ingest_agent_step_log():

    data = request.get_json()

    required_fields = ["run_id", "node_id", "agent_id", "step_type", "status"]

    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing field: {field}"}), 400

    session = next(db_session())

    try:
        log = WorkflowAgentStepLog(
            run_id=data["run_id"],
            node_id=data["node_id"],
            agent_id=data["agent_id"],
            bot_id=data.get("bot_id"),
            diagram_id=data.get("diagram_id"),
            step_index=data.get("step_index", 0),
            step_type=data["step_type"],
            tool_name=data.get("tool_name"),
            status=data["status"],
            message=data.get("message"),
            data=data.get("data"),  # ✅ single JSON field
            log_level=data.get("log_level", "INFO")
        )

        session.add(log)
        session.commit()

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        session.rollback()
        return jsonify({"error": str(e)}), 500

    finally:
        session.close()
@workflow_blueprint.route("/logs/agent_node", methods=["GET"])
@jwt_required()
def get_agent_step_logs():

    bot_id = request.args.get("bot_id", type=int)
    diagram_id = request.args.get("diagram_id", type=int)
    node_id = request.args.get("node_id", type=str)
    run_id = request.args.get("run_id", type=int)

    if not diagram_id or not node_id:
        return jsonify({
            "error": "diagram_id and node_id are required"
        }), 400

    session = next(db_session())

    try:
        # -------------------------------------------------------
        # 1️⃣ Resolve Run
        # -------------------------------------------------------
        run_query = session.query(WorkflowRun).filter(WorkflowRun.diagram_id == diagram_id)
        if bot_id:
            run_query = run_query.filter(WorkflowRun.bot_id == bot_id)

        if run_id:
            run_query = run_query.filter(WorkflowRun.id == run_id)

        run = run_query.order_by(WorkflowRun.started_at.desc()).first()

        if not run:
            return jsonify({
                "run": None,
                "node": {
                    "node_id": node_id,
                    "status": "not_found",
                    "steps": []
                }
            }), 200

        # -------------------------------------------------------
        # 2️⃣ Fetch Logs
        # -------------------------------------------------------
        logs = (
            session.query(WorkflowAgentStepLog)
            .filter(
                cast(WorkflowAgentStepLog.run_id, Integer) == run.id,
                WorkflowAgentStepLog.node_id == node_id
            )
            .order_by(
                WorkflowAgentStepLog.step_index.asc(),
                WorkflowAgentStepLog.created_at.asc()
            )
            .all()
        )

        # -------------------------------------------------------
        # 3️⃣ Group Start/End/Error into UI Steps
        # -------------------------------------------------------
        steps = []
        current_step = None

        for log in logs:

            base_type = log.step_type.split("_")[0]  # llm / tool / chain

            # ---------- START ----------
            if log.step_type.endswith("start"):
                current_step = {
                    "type": base_type,
                    "tool_name": log.tool_name,
                    "status": "running",
                    "started_at": log.created_at,
                    "ended_at": None,
                    "duration_ms": None,
                    "message": log.message,
                    "log_level": log.log_level,
                    "data": log.data or {},
                }

            # ---------- END ----------
            elif log.step_type.endswith("end") and current_step:
                current_step["ended_at"] = log.created_at
                current_step["status"] = log.status
                current_step["log_level"] = log.log_level
                current_step["data"] = log.data or {}

                # Compute duration dynamically
                if current_step["started_at"]:
                    current_step["duration_ms"] = int(
                        (log.created_at - current_step["started_at"]).total_seconds() * 1000
                    )

                steps.append(current_step)
                current_step = None

            # ---------- ERROR ----------
            elif log.step_type.endswith("error"):
                error_step = {
                    "type": base_type,
                    "tool_name": log.tool_name,
                    "status": "failed",
                    "started_at": log.created_at,
                    "ended_at": log.created_at,
                    "duration_ms": 0,
                    "message": log.message,
                    "log_level": log.log_level,
                    "data": log.data or {},
                }
                steps.append(error_step)

        # If something still running
        if current_step:
            steps.append(current_step)

        # -------------------------------------------------------
        # Fallback: use node-level logs when agent-step logs are missing
        # -------------------------------------------------------
        if not steps:
            node_logs = (
                session.query(WorkflowNodeLog)
                .filter(
                    WorkflowNodeLog.run_id == run.id,
                    WorkflowNodeLog.node_id == node_id
                )
                .order_by(WorkflowNodeLog.created_at.asc())
                .all()
            )

            if node_logs:
                current_step = None
                for log in node_logs:
                    base_type = log.node_type or "node"
                    event_type = (log.event_type or "").lower()

                    if event_type.endswith("started"):
                        current_step = {
                            "type": base_type,
                            "tool_name": None,
                            "status": "running",
                            "started_at": log.started_at or log.created_at,
                            "ended_at": None,
                            "duration_ms": None,
                            "message": log.message,
                            "log_level": log.log_level,
                            "data": log.payload or {},
                        }

                    elif event_type.endswith("completed") and current_step:
                        current_step["ended_at"] = log.completed_at or log.created_at
                        current_step["status"] = log.status or "completed"
                        current_step["log_level"] = log.log_level
                        current_step["data"] = log.payload or {}
                        if current_step["started_at"] and current_step["ended_at"]:
                            current_step["duration_ms"] = int(
                                (current_step["ended_at"] - current_step["started_at"]).total_seconds() * 1000
                            )
                        steps.append(current_step)
                        current_step = None

                    elif event_type == "failed":
                        steps.append({
                            "type": base_type,
                            "tool_name": None,
                            "status": "failed",
                            "started_at": log.started_at or log.created_at,
                            "ended_at": log.completed_at or log.created_at,
                            "duration_ms": 0,
                            "message": log.message,
                            "log_level": log.log_level,
                            "data": log.payload or {},
                        })

                if current_step:
                    steps.append(current_step)

                if not steps:
                    for log in node_logs:
                        steps.append({
                            "type": log.node_type or "node",
                            "tool_name": None,
                            "status": log.status,
                            "started_at": log.started_at or log.created_at,
                            "ended_at": log.completed_at or log.created_at,
                            "duration_ms": 0,
                            "message": log.message,
                            "log_level": log.log_level,
                            "data": log.payload or {},
                        })

        # -------------------------------------------------------
        # 4️⃣ Compute Node Status
        # -------------------------------------------------------
        node_status = "completed"

        for step in steps:
            if step["status"] == "failed":
                node_status = "failed"
                break
            if step["ended_at"] is None:
                node_status = "running"

        # If this run failed and we have no agent step logs for the node,
        # report the node as failed rather than silently completed.
        if not steps and run.status == "failed":
            node_status = "failed"

        # -------------------------------------------------------
        # 5️⃣ Final Response (UI Ready)
        # -------------------------------------------------------
        response = {
            "run": {
                "run_id": run.id,
                "status": run.status,
                "started_at": run.started_at,
                "completed_at": run.completed_at
            },
            "node": {
                "node_id": node_id,
                "status": node_status,
                "total_steps": len(steps),
                "steps": steps
            }
        }

        return jsonify(response), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    finally:
        session.close()
