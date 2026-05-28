




# ===== FILE: engine/workflow_executor.py =====
"""Main workflow executor"""
"""Production-grade workflow executor with parallel execution and error handling"""


import requests
from engine.registry import NODE_REGISTRY
from engine.graph_utils import build_graph, compute_dependencies
from engine.load_nodes import load_all_nodes
import asyncio
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Dict, Any, Optional, Set
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
import time
import json
import os
from engine.cache_service_hybrid import HybridCacheService
from app.database.DatabaseOperationPostgreSQL import db_session
from app.models.workflow_runs import WorkflowRun
from app.models.workflow_wait_state import WorkflowWaitState
from engine.generic_agent_node import GenericAgentNode
from logging_config import setup_logging
import threading
from workflow_log_service import WorkflowLogService,LogEmitter
from sqlalchemy.exc import IntegrityError
from collections import OrderedDict

logger = setup_logging("workflow_executor", level="DEBUG")




load_all_nodes()


class NodeStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    TIMEOUT = "timeout"
    WAITING = "waiting"


@dataclass
class NodeExecutionResult:
    """Result of a single node execution"""
    node_id: str
    status: NodeStatus
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[float] = None
    retry_count: int = 0
    
    def to_dict(self):
        """Convert to JSON-serializable dict"""
        return {
            "node_id": self.node_id,
            "status": self.status.value,  # Convert Enum to string
            "output": self.output,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
            "retry_count": self.retry_count
        }
    
    @staticmethod
    def from_dict(data: dict) -> "NodeExecutionResult":
        """Create NodeExecutionResult from dict"""
        return NodeExecutionResult(
            node_id=data.get("node_id"),
            status=NodeStatus(data["status"]) if data.get("status") else NodeStatus.COMPLETED,
            output=data.get("output"),
            error=data.get("error"),
            started_at=datetime.fromisoformat(data["started_at"])
            if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"])
            if data.get("completed_at") else None,
            duration_ms=data.get("duration_ms"),
            retry_count=data.get("retry_count", 0),
        )



@dataclass
class WorkflowExecutionContext:
    """Context for tracking workflow execution state"""
    workflow_id: str
    execution_id: str
    node_results: Dict[str, NodeExecutionResult] = field(default_factory=dict)
    node_outputs: Dict[str, Any] = field(default_factory=dict)
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    total_nodes: int = 0
    executed_nodes: int = 0
    
    def to_dict(self):
        """Convert to JSON-serializable dict"""
        return {
            "workflow_id": self.workflow_id,
            "execution_id": self.execution_id,
            "node_results": {
                node_id: result.to_dict() 
                for node_id, result in self.node_results.items()
            },
            "node_outputs": self.node_outputs,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "total_nodes": self.total_nodes,
            "executed_nodes": self.executed_nodes,
            "status": "completed" if self.executed_nodes == self.total_nodes else "partial"
        }


class WorkflowPausedException(Exception):
    def __init__(self, node_id):
        self.node_id = node_id



class WorkflowExecutor:
    """
    Production-grade workflow executor with:
    - True parallel execution for independent nodes
    - Proper join node synchronization
    - Comprehensive error handling & retries
    - Execution monitoring & metrics
    - Timeout controls
    - State checkpointing
    - BACKWARD COMPATIBLE: Returns simple dict when called with execute()
    """
    
    def __init__(
        self, 
        workflow_json: Dict[str, Any],
        max_workers: int = 10,
        default_timeout: int = 300,  # 5 minutes
        max_retries: int = 3,
        enable_checkpointing: bool = False,
        enable_parallel: bool = True,  # Can disable for debugging
        cache_service: Optional[HybridCacheService] = None,
        
    ):
        self.workflow = workflow_json
        self.max_workers = max_workers
        self.default_timeout = default_timeout
        self.max_retries = max_retries
        self.enable_checkpointing = enable_checkpointing
        self.enable_parallel = enable_parallel
        
        self.cache_service = cache_service
        self.executor = ThreadPoolExecutor(max_workers=max_workers) if enable_parallel else None
        # Add to WorkflowExecutor.__init__
        self._stop_event = threading.Event()
        try:
            self.agent_execution_delay_seconds = int(
                os.getenv("WORKFLOW_AGENT_DELAY_SECONDS", "5")
            )
        except ValueError:
            self.agent_execution_delay_seconds = 5

    def _resolve_diagram_id(self, trigger_data: Optional[Dict[str, Any]] = None) -> str:
        """
        Resolve diagram id from workflow metadata first, then trigger payload metadata.
        This is important for auto-trigger paths where workflow metadata can be partial.
        """
        diagram_id = self.workflow.get("diagram_id") or self.workflow.get("id")
        if diagram_id:
            return str(diagram_id)

        if isinstance(trigger_data, dict):
            for node_payload in trigger_data.values():
                if not isinstance(node_payload, dict):
                    continue
                metadata = node_payload.get("metadata")
                if isinstance(metadata, dict):
                    candidate = metadata.get("flow_id") or metadata.get("diagram_id")
                    if candidate:
                        return str(candidate)
                candidate = node_payload.get("flow_id") or node_payload.get("diagram_id")
                if candidate:
                    return str(candidate)

        return "unknown"

    def _agent_io_log_path(self, diagram_id: str) -> str:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        log_dir = os.path.join(project_root, "logs", "agent_node_io")
        os.makedirs(log_dir, exist_ok=True)
        return os.path.join(log_dir, f"diagram_{diagram_id}.log")
        
                    
    def resume(self, run_context: dict, new_event_data: dict = None):
        self.context = WorkflowExecutionContext.from_dict(run_context)
    
        # Inject new data (like webhook response / user reply)
        if new_event_data:
            for key, value in new_event_data.items():
                self.context.node_outputs[key] = value
    
        # Mark already executed nodes as complete
        self._mark_completed_nodes(self.context)
    
        # Continue workflow
        return self.execute(trigger_data=None, return_context=True)



    def resume_from_wait_state(
        self,
        wait_state_id: int,
        event_payload: dict,
    ):
        """
        Resume workflow execution from a persisted WaitNode.
        CORE LOGIC UNCHANGED — ONLY SAFETY + LOGS ADDED
        """

        logger.info(
            "[RESUME] ENTER resume_from_wait_state | wait_state_id=%s payload_keys=%s",
            wait_state_id,
            list(event_payload.keys()),
        )

        # =====================================================
        # 🔹 STEP 0: Load wait_state by ID (REQUIRED)
        # =====================================================
        session = next(db_session())

        wait_state = (
            session.query(WorkflowWaitState)
            .filter(WorkflowWaitState.id == wait_state_id)
            .one()
        )

        logger.info(
            "[RESUME] Loaded wait_state | id=%s run_id=%s node_id=%s status=%s",
            wait_state.id,
            wait_state.workflow_run_id,
            wait_state.node_id,
            wait_state.status,
        )

        session.close()

        # =====================================================
        # 🔒 STEP 1: Atomic claim (idempotency guard)
        # =====================================================
        session = next(db_session())

        logger.info(
            "[RESUME] Attempting atomic claim | wait_id=%s expected_status=waiting",
            wait_state.id,
        )

        updated = (
            session.query(WorkflowWaitState)
            .filter(
                WorkflowWaitState.id == wait_state.id,
                WorkflowWaitState.status == "waiting",
            )
            .update(
                {
                    "status": "resuming",
                    "updated_at": datetime.utcnow(),
                },
                synchronize_session=False,
            )
        )

        logger.info(
            "[RESUME] Atomic claim result | wait_id=%s rows_updated=%s",
            wait_state.id,
            updated,
        )

        if updated == 0:
            session.rollback()
            session.close()
            logger.warning(
                "[RESUME] EXIT — wait already claimed or completed | wait_id=%s",
                wait_state.id,
            )
            return None

        session.commit()
        session.close()

        # =====================================================
        # 🔄 STEP 2: Re-hydrate wait_state after commit
        # =====================================================
        session = next(db_session())
        wait_state = session.query(WorkflowWaitState).get(wait_state.id)
        session.close()

        logger.info(
            "[RESUME] Rehydrated wait_state | id=%s status=%s",
            wait_state.id,
            wait_state.status,
        )

        # =====================================================
        # 🔁 STEP 3: Restore workflow context (UNCHANGED)
        # =====================================================
        saved = wait_state.workflow_state or {}

        logger.info(
            "[RESUME] Restoring context | saved_keys=%s",
            list(saved.keys()),
        )

        context = WorkflowExecutionContext(
            workflow_id=self.workflow.get("id"),
            execution_id=saved.get("execution_id"),
        )

        context.node_outputs = saved.get("node_outputs", {})
        context.node_results = {
            k: NodeExecutionResult.from_dict(v)
            for k, v in saved.get("node_results", {}).items()
        }
        context.executed_nodes = saved.get("executed_nodes", 0)
        context.total_nodes = len(self.workflow.get("nodes", []))

        self.execution_db_id = wait_state.workflow_run_id

        logger.info(
            "[RESUME] Context restored | executed=%s total=%s outputs=%s",
            context.executed_nodes,
            context.total_nodes,
            list(context.node_outputs.keys()),
        )

        # =====================================================
        # 🔹 STEP 4: Inject wait completion output
        # =====================================================
        wait_node_id = wait_state.node_id

        logger.info(
            "[RESUME] Injecting wait completion | node_id=%s payload=%s",
            wait_node_id,
            event_payload,
        )

        safe_event_payload = event_payload if isinstance(event_payload, dict) else {}
        wait_output = {
            "status": "completed",
            "event_payload": safe_event_payload,
            "completed_at": datetime.utcnow().isoformat(),
        }

        response_data = self._fetch_wait_webhook_response(wait_state)
        if response_data is not None:
            wait_output["response_data"] = response_data
            wait_output["data"] = response_data
            wait_output["webhook_response"] = response_data

        # Keep WhatsApp and Slack resume payload handling isolated.
        whatsapp_events = []
        payload_whatsapp_events = safe_event_payload.get("whatsapp_events")
        if isinstance(payload_whatsapp_events, list):
            whatsapp_events = [evt for evt in payload_whatsapp_events if isinstance(evt, dict)]

        payload_latest_whatsapp = safe_event_payload.get("latest_whatsapp_event")
        if isinstance(payload_latest_whatsapp, dict):
            whatsapp_events.append(payload_latest_whatsapp)

        slack_events = []
        payload_slack_events = safe_event_payload.get("slack_events")
        if isinstance(payload_slack_events, list):
            slack_events = [evt for evt in payload_slack_events if isinstance(evt, dict)]

        payload_latest_slack = safe_event_payload.get("latest_slack_event")
        if isinstance(payload_latest_slack, dict):
            slack_events.append(payload_latest_slack)

        payload_single_slack = safe_event_payload.get("slack_event")
        if isinstance(payload_single_slack, dict):
            slack_events.append(payload_single_slack)

        if whatsapp_events or safe_event_payload.get("sender_phone") or safe_event_payload.get("from"):
            latest_whatsapp_event = whatsapp_events[-1] if whatsapp_events else {}
            whatsapp_message = str(
                latest_whatsapp_event.get("message")
                or latest_whatsapp_event.get("user_query")
                or (latest_whatsapp_event.get("content") or {}).get("text")
                or safe_event_payload.get("message")
                or safe_event_payload.get("user_query")
                or safe_event_payload.get("text")
                or ""
            ).strip()
            whatsapp_from = str(
                safe_event_payload.get("from")
                or safe_event_payload.get("sender_phone")
                or (latest_whatsapp_event.get("metadata") or {}).get("from_phone")
                or (latest_whatsapp_event.get("metadata") or {}).get("from")
                or latest_whatsapp_event.get("phone")
                or ""
            ).strip()
            whatsapp_message_id = (
                safe_event_payload.get("message_id")
                or (latest_whatsapp_event.get("metadata") or {}).get("message_id")
            )
            whatsapp_timestamp = (
                safe_event_payload.get("timestamp")
                or (latest_whatsapp_event.get("metadata") or {}).get("timestamp")
            )

            if whatsapp_events:
                wait_output["whatsapp_events"] = whatsapp_events
                wait_output["latest_whatsapp_event"] = latest_whatsapp_event
            if whatsapp_message:
                wait_output["message"] = whatsapp_message
                wait_output["user_query"] = whatsapp_message
                wait_output["text"] = whatsapp_message
            if whatsapp_from:
                wait_output["from"] = whatsapp_from
                wait_output["phone"] = whatsapp_from
            if whatsapp_message_id:
                wait_output["message_id"] = str(whatsapp_message_id)
            if whatsapp_timestamp:
                wait_output["timestamp"] = str(whatsapp_timestamp)

        elif slack_events:
            latest_slack_event = slack_events[-1] if slack_events else {}
            slack_message = str(
                latest_slack_event.get("message")
                or latest_slack_event.get("user_query")
                or latest_slack_event.get("text")
                or (latest_slack_event.get("content") or {}).get("text")
                or safe_event_payload.get("message")
                or safe_event_payload.get("user_query")
                or safe_event_payload.get("text")
                or ""
            ).strip()
            slack_channel = str(
                (latest_slack_event.get("metadata") or {}).get("channel")
                or latest_slack_event.get("channel")
                or safe_event_payload.get("channel")
                or safe_event_payload.get("to")
                or ""
            ).strip()
            slack_user = str(
                (latest_slack_event.get("metadata") or {}).get("user")
                or latest_slack_event.get("user")
                or safe_event_payload.get("user")
                or ""
            ).strip()
            slack_thread_ts = str(
                (latest_slack_event.get("metadata") or {}).get("thread_ts")
                or latest_slack_event.get("thread_ts")
                or latest_slack_event.get("ts")
                or safe_event_payload.get("thread_ts")
                or safe_event_payload.get("ts")
                or ""
            ).strip()

            wait_output["slack_events"] = slack_events
            wait_output["latest_slack_event"] = latest_slack_event
            wait_output["slack_event"] = latest_slack_event
            if slack_message:
                wait_output["message"] = slack_message
                wait_output["user_query"] = slack_message
                wait_output["text"] = slack_message
            if slack_channel:
                wait_output["channel"] = slack_channel
            if slack_user:
                wait_output["user"] = slack_user
            if slack_thread_ts:
                wait_output["thread_ts"] = slack_thread_ts

        # Expose webhook response data directly as the wait node output,
        # so downstream nodes can resolve `wait_node_id.field` like a normal node.
        if isinstance(wait_output.get("response_data"), dict):
            context.node_outputs[wait_node_id] = {
                "response": wait_output["response_data"],
                "response_data": wait_output["response_data"],
                "webhook_response": wait_output["response_data"],
                **wait_output["response_data"],
                "_wait_metadata": {
                    "status": wait_output["status"],
                    "completed_at": wait_output["completed_at"],
                    "event_payload": wait_output["event_payload"],
                },
            }
        else:
            context.node_outputs[wait_node_id] = wait_output

        context.executed_nodes += 1

        # =====================================================
        # 🔹 STEP 4B: Restore wait node mapped_data for downstream
        # =====================================================
        # If the wait state has saved node_outputs with wait node data,
        # merge it back so downstream nodes can access resolved variables
        saved_wait_output = saved.get("node_outputs", {}).get(wait_node_id, {})
        if isinstance(saved_wait_output, dict):
            # Merge saved wait output data into current wait_output
            # This includes mapped_data and other resolved fields
            for key, value in saved_wait_output.items():
                if key not in wait_output or wait_output[key] is None:
                    wait_output[key] = value
            
            logger.info(
                "[RESUME] Merged saved wait output | keys_merged=%s",
                list(saved_wait_output.keys()),
            )

        # ✅ NEW: Inject mapped_data into context if available
        # This makes resolved variables accessible to downstream nodes
        if isinstance(saved_wait_output, dict) and "mapped_data" in saved_wait_output:
            mapped_data = saved_wait_output.get("mapped_data", {})
            if isinstance(mapped_data, dict):
                # Store mapped_data in context for downstream resolution
                wait_output["mapped_data"] = mapped_data
                if isinstance(context.node_outputs.get(wait_node_id), dict):
                    context.node_outputs[wait_node_id]["mapped_data"] = mapped_data
                logger.info(
                    "[RESUME] Restored mapped_data for downstream | keys=%s",
                    list(mapped_data.keys()),
                )

        # =====================================================
        # 🔹 STEP 5–8: Downstream execution + finalization
        # Wrapped in try/except so failures move state to 'failed'
        # =====================================================
        try:
            nodes = self.workflow.get("nodes", [])
            edges = self.workflow.get("edges", [])

            graph = build_graph(nodes, edges)
            outgoing = graph["outgoing"]

            logger.info(
                "[RESUME] Graph built | outgoing_from_wait=%s",
                outgoing.get(wait_node_id),
            )

            next_nodes = self._get_next_nodes(
                wait_node_id,
                context.node_outputs[wait_node_id],
                outgoing,
                nodes,
            )

            logger.info(
                "[RESUME] Next nodes computed | wait_node=%s next_nodes=%s",
                wait_node_id,
                next_nodes,
            )

            if not next_nodes:
                logger.warning(
                    "[RESUME] No downstream nodes — finalizing wait only | wait_id=%s",
                    wait_state.id,
                )

                session = next(db_session())
                session.query(WorkflowWaitState).filter(
                    WorkflowWaitState.id == wait_state.id
                ).update(
                    {
                        "status": "completed",
                        "completed_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow(),
                    },
                    synchronize_session=False,
                )
                session.commit()
                session.close()

                return context

            # Validate downstream readiness before resuming execution.
            dependencies = compute_dependencies(graph)[0]
            dependencies = self._prepare_resume_dependencies(graph, context, dependencies)
            ready_start_nodes = [
                node_id
                for node_id in next_nodes
                if node_id not in context.node_outputs
                and self._can_schedule_node(node_id, graph, context, dependencies, running=set())
            ]

            if not ready_start_nodes:
                logger.warning(
                    "[RESUME] No downstream nodes are ready after dependency validation | wait_id=%s next_nodes=%s",
                    wait_state.id,
                    next_nodes,
                )
                session = next(db_session())
                session.query(WorkflowWaitState).filter(
                    WorkflowWaitState.id == wait_state.id
                ).update(
                    {
                        "status": "waiting",
                        "updated_at": datetime.utcnow(),
                    },
                    synchronize_session=False,
                )
                session.commit()
                session.close()
                return None

            # STEP 6: Resume downstream execution
            logger.info(
                "[RESUME] Starting downstream execution | start_nodes=%s",
                ready_start_nodes,
            )

            self._resume_execution_from_nodes(
                start_nodes=ready_start_nodes,
                graph=graph,
                context=context,
            )

            logger.info(
                "[RESUME] Downstream execution finished | executed=%s outputs=%s",
                context.executed_nodes,
                list(context.node_outputs.keys()),
            )

            # STEP 7: Finalize wait node → completed
            session = next(db_session())
            session.query(WorkflowWaitState).filter(
                WorkflowWaitState.id == wait_state.id
            ).update(
                {
                    "status": "completed",
                    "completed_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                },
                synchronize_session=False,
            )
            session.commit()
            session.close()

            logger.info(
                "[RESUME] EXIT resume_from_wait_state SUCCESS | wait_id=%s",
                wait_state.id,
            )

            # STEP 8: Finalize workflow run → completed
            session = next(db_session())
            run = session.query(WorkflowRun).get(self.execution_db_id)
            if run:
                run.status = "completed"
                run.completed_at = datetime.utcnow()
                run.context_json = {
                    "execution_id": context.execution_id,
                    "executed_nodes": context.executed_nodes,
                    "total_nodes": context.total_nodes,
                    "node_outputs": context.node_outputs,
                    "node_results": {
                        k: v.to_dict() for k, v in context.node_results.items()
                    }
                }
                run.current_node_id = None
            session.commit()
            session.close()

            logger.info(
                "[RESUME] WorkflowRun finalized | run_id=%s status=completed",
                self.execution_db_id,
            )

            return context

        except Exception as resume_err:
            logger.exception(
                "[RESUME] Downstream execution failed | wait_id=%s error=%s",
                wait_state.id, resume_err,
            )
            # Move wait_state and run to 'failed' so they are not stuck in 'resuming'
            try:
                session = next(db_session())
                session.query(WorkflowWaitState).filter(
                    WorkflowWaitState.id == wait_state.id
                ).update(
                    {
                        "status": "failed",
                        "updated_at": datetime.utcnow(),
                    },
                    synchronize_session=False,
                )
                session.commit()
                session.close()
            except Exception:
                logger.exception("[RESUME] Could not mark wait_state as failed | wait_id=%s", wait_state.id)

            try:
                session = next(db_session())
                run = session.query(WorkflowRun).get(self.execution_db_id)
                if run:
                    run.status = "failed"
                    run.completed_at = datetime.utcnow()
                    run.context_json = {
                        "execution_id": context.execution_id,
                        "error": str(resume_err),
                        "executed_nodes": context.executed_nodes,
                        "total_nodes": context.total_nodes,
                    }
                    run.current_node_id = None
                session.commit()
                session.close()
            except Exception:
                logger.exception("[RESUME] Could not mark WorkflowRun as failed | run_id=%s", self.execution_db_id)

            raise

    def _resume_execution_from_nodes(self, start_nodes, graph, context):
        """
        Resume execution from specific nodes without restarting workflow.
        LOG-ONLY INSTRUMENTATION
        """

        logger.info(
            "[RESUME] ENTER _resume_execution_from_nodes | start_nodes=%s",
            start_nodes,
        )

        dependencies, _ = compute_dependencies(graph)
        outgoing = graph["outgoing"]

        logger.info(
            "[RESUME] Initial dependencies | %s",
            dependencies,
        )

        dependencies = self._prepare_resume_dependencies(graph, context, dependencies)

        logger.info(
            "[RESUME] Dependencies after cleanup | %s",
            dependencies,
        )

        ready_nodes = []
        running = set()

        for node_id in start_nodes:
            if node_id in context.node_outputs:
                continue
            if self._can_schedule_node(node_id, graph, context, dependencies, running=set()):
                ready_nodes.append(node_id)
            else:
                logger.warning(
                    "[RESUME] Start node %s cannot be scheduled yet due to unmet dependencies",
                    node_id,
                )

        logger.info(
            "[RESUME] Scheduler init | ready_nodes=%s completed=%s",
            ready_nodes,
            list(context.node_outputs.keys()),
        )

        if self.enable_parallel:
            logger.info("[RESUME] Using PARALLEL resume executor")
            self._execute_parallel_resume(
                ready_nodes, graph, outgoing, dependencies, context
            )
        else:
            logger.info("[RESUME] Using SEQUENTIAL resume executor")
            self._execute_sequential_resume(
                ready_nodes, graph, outgoing, dependencies, context
            )

        logger.info(
            "[RESUME] EXIT _resume_execution_from_nodes | executed=%s outputs=%s",
            context.executed_nodes,
            list(context.node_outputs.keys()),
        )

    def _prepare_resume_dependencies(self, graph, context, dependencies):
        """Adjust dependency counts for nodes that already completed before resume."""
        outgoing = graph["outgoing"]
        completed_nodes = set(context.node_outputs.keys())

        for completed_node in completed_nodes:
            for edge in outgoing.get(completed_node, []):
                child_id = edge["target"] if isinstance(edge, dict) else edge
                if child_id in dependencies:
                    dependencies[child_id] = max(0, dependencies[child_id] - 1)

        for node_id in completed_nodes:
            if node_id in dependencies:
                dependencies[node_id] = 0

        return dependencies

    def _execute_parallel_resume(
        self, ready_nodes, graph, outgoing, dependencies, context
    ):
        completed = set(context.node_outputs.keys())
        futures = {}

        while ready_nodes or futures:
            for node_id in list(ready_nodes):
                if node_id in completed:
                    ready_nodes.remove(node_id)
                    continue

                node_def = self._find_node(self.workflow["nodes"], node_id)
                inputs = self._collect_inputs(node_id, graph, context.node_outputs)

                future = self.executor.submit(
                    self._execute_node_wrapper, node_def, inputs, context
                )
                futures[node_id] = future
                ready_nodes.remove(node_id)

            for node_id, future in list(futures.items()):
                if future.done():
                    try:
                        result = future.result()
                    except WorkflowPausedException as e:
                        logger.info("[EXECUTOR] Workflow paused — stopping parallel scheduler")
                        self.executor.shutdown(wait=False)
                        raise
                    context.node_results[node_id] = result

                    if result.status == NodeStatus.COMPLETED:
                        context.node_outputs[node_id] = result.output
                        context.executed_nodes += 1
                        completed.add(node_id)

                        next_nodes = self._get_next_nodes(
                            node_id, result.output, outgoing, self.workflow["nodes"]
                        )

                        for nxt in next_nodes:
                            dependencies[nxt] -= 1
                            if self._can_schedule_node(
                                nxt, graph, context, dependencies, running=set()
                            ):
                                ready_nodes.append(nxt)

                    del futures[node_id]
                    
    def _execute_sequential_resume(
        self, ready_nodes, graph, outgoing, dependencies, context
    ):
        from collections import deque

        queue = deque(ready_nodes)

        while queue:
            node_id = queue.popleft()

            if node_id in context.node_outputs:
                continue

            node_def = self._find_node(self.workflow["nodes"], node_id)
            inputs = self._collect_inputs(node_id, graph, context.node_outputs)

            result = self._execute_node_safe(node_def, inputs, context)
            context.node_results[node_id] = result

            if result.status == NodeStatus.COMPLETED:
                context.node_outputs[node_id] = result.output
                context.executed_nodes += 1

                next_nodes = self._get_next_nodes(
                    node_id, result.output, outgoing, self.workflow["nodes"]
                )

                for nxt in next_nodes:
                    dependencies[nxt] -= 1
                    if self._can_schedule_node(
                        nxt, graph, context, dependencies, running=set()
                    ):
                        queue.append(nxt)

 

    # -------------------
    # EXECUTION FUNCTIONS
    # -------------------
    # (unchanged logic)
    
    def _execute_single_node(self, node, trigger_data, context):
        node_id = node["id"]
        inputs = trigger_data.get(node_id, {}) if trigger_data else {}
        result = self._execute_node_safe(node, inputs, context)
        context.node_results[node_id] = result
        
        if result.status == NodeStatus.COMPLETED:
            context.node_outputs[node_id] = result.output
            context.executed_nodes = 1
    
    
    def execute(
        self, 
        trigger_data: Optional[Dict[str, Any]] = None,
        execution_id: Optional[str] = None,
        return_context: bool = False,
        async_mode: Optional[bool] = False
    ):
        """
        Execute workflow - returns context structure on both success and failure.
        
        ✅ Changes:
        - Always returns context with partial results
        - Failed nodes marked with error in node_outputs
        - Context stored in DB on failure
        """
        
        try:
            # Ensure one per-diagram agent IO log file exists under bb_master/logs.
            diagram_id = self._resolve_diagram_id(trigger_data=trigger_data)
            log_path = self._agent_io_log_path(diagram_id)
            open(log_path, "a", encoding="utf-8").close()
            logger.info("[AGENT_IO] ensured log file path=%s", log_path)

            # 1. Create DB execution record
            run_id = self.create_execution_record(self.workflow, trigger_data)
            execution_id = execution_id or f"exec_{int(time.time() * 1000)}"
            
            workflow_id = self.workflow.get("id") or self.workflow.get("diagram_id") or "unknown"
            
            context = WorkflowExecutionContext(
                workflow_id=workflow_id,
                execution_id=execution_id
            )

            tenant_id = self.workflow.get("tenant_id")
            if tenant_id:
                context.__dict__["tenant_id"] = tenant_id
            
            try:
                nodes = self.workflow.get("nodes", [])
                edges = self.workflow.get("edges", [])
                context.total_nodes = len(nodes)
                
                if not nodes:
                    return context if return_context else {}
                
                # Execute workflow
                if len(nodes) == 1:
                    self._execute_single_node(nodes[0], trigger_data, context)
                else:
                    if self.enable_parallel and len(nodes) > 1:
                        self._execute_parallel_workflow(nodes, edges, trigger_data, context)
                    else:
                        self._execute_sequential_workflow(nodes, edges, trigger_data, context)
                
                # ✅ SUCCESS PATH
                context.status = "completed"
                context.completed_at = datetime.now()
                
                # Update DB with success
                self._finalize_execution_in_db(context, "completed")
                
                mapped_outputs = self._map_node_ids_to_labels(context.node_outputs)

                if return_context:
                    context.node_outputs = mapped_outputs   
                    return context
                
                return mapped_outputs
            
            except WorkflowPausedException:
                raise
                
            except Exception as e:
                # ✅ FAILURE PATH - Return context with error
                logger.error(f"[{execution_id}] Workflow execution failed: {e}", exc_info=True)
                
                context.status = "failed"
                context.completed_at = datetime.now()
                context.error = str(e)
                
                # ✅ Update DB with failed status and full context
                self._finalize_execution_in_db(context, "failed", error=str(e))
                
                # Map outputs for UI (includes partial results + failed node)
                mapped_outputs = self._map_node_ids_to_labels(context.node_outputs)
                
                if return_context:
                    context.node_outputs = mapped_outputs
                    return context
                
                return mapped_outputs
                
        except WorkflowPausedException as e:
            logger.info(f"[EXECUTOR] Workflow paused at node={e.node_id}")
            context.status = "paused"
            return context if return_context else {}


    # ============================================================
    # CHANGE 2: Store failed node in node_outputs
    # ============================================================
    
    def _execute_sequential_workflow(self, nodes, edges, trigger_data, context):
        """Sequential execution - stores failed node output"""
        from collections import deque

        graph = build_graph(nodes, edges)
        dependencies, ready_nodes = compute_dependencies(graph)

        ready_nodes = list(dict.fromkeys(ready_nodes))

        for node in nodes:
            NodeClass = NODE_REGISTRY.get(node["type"])
            if getattr(NodeClass, "is_trigger_node", False):
                if node["id"] not in ready_nodes:
                    ready_nodes.append(node["id"])

        outgoing = graph["outgoing"]
        queue = deque(ready_nodes)
        iteration_guard = 0
        running = set()

        while queue:
            iteration_guard += 1
            if iteration_guard > 10000:
                raise RuntimeError("Possible infinite loop detected in sequential execution")

            node_id = queue.popleft()
            node_def = self._find_node(nodes, node_id)

            logger.debug(f"[SEQUENTIAL] Processing node {node_id}")

            inputs = self._collect_inputs(node_id, graph, context.node_outputs)

            # Handle trigger data injection
            if trigger_data and node_id in trigger_data:
                injected = trigger_data[node_id]
                logger.info(f"[EXECUTOR] Injected data for {node_id}: {injected}")
                inputs.update(injected)

                if injected.get("prefetched_events"):
                    logger.info(f"[EXECUTOR] Skipping execution for {node_id} (AUTO MODE), using prefetched events")
                    _trigger_started_at = datetime.now()
                    LogEmitter.node_started(
                        run_id=self.execution_db_id,
                        node_id=node_id,
                        node_type=node_def.get("type"),
                        inputs={"trigger": "prefetched_events", "events_count": len(injected["prefetched_events"])},
                    )

                    result = NodeExecutionResult(
                        node_id=node_id,
                        status=NodeStatus.COMPLETED,
                        output=injected["prefetched_events"],
                        started_at=_trigger_started_at,
                        completed_at=datetime.now(),
                        duration_ms=0
                    )

                    LogEmitter.node_completed(
                        run_id=self.execution_db_id,
                        node_id=node_id,
                        node_type=node_def.get("type"),
                        outputs={"events_count": len(injected["prefetched_events"])},
                        duration_ms=0,
                        started_at=_trigger_started_at,
                    )

                    context.node_results[node_id] = result
                    context.node_outputs[node_id] = result.output
                    context.executed_nodes += 1

                    next_nodes = self._get_next_nodes(node_id, result.output, outgoing, nodes)
                    logger.debug(f"[SCHEDULER] From {node_id} -> next: {next_nodes} | deps: {dependencies}")

                    for next_node in next_nodes:
                        if next_node in dependencies:
                            dependencies[next_node] -= 1
                            logger.debug(f"[SCHEDULER] Decremented {next_node} dependency to {dependencies[next_node]}")

                        if self._can_schedule_node(
                            next_node, graph, context, dependencies, running=set()
                        ):
                            queue.append(next_node)
                            logger.debug(f"[SCHEDULER] Added {next_node} to queue")

                    continue

            # Execute node
            result = self._execute_node_safe(node_def, inputs, context)
            context.node_results[node_id] = result

            if result.status == NodeStatus.COMPLETED:
                output = result.output or {}
                context.node_outputs[node_id] = output
                context.executed_nodes += 1

                next_nodes = self._get_next_nodes(node_id, output, outgoing, nodes)
                logger.debug(f"[SCHEDULER] From {node_id} -> next: {next_nodes}")

                for next_node in next_nodes:
                    if next_node in dependencies:
                        dependencies[next_node] -= 1
                        logger.debug(f"[SCHEDULER] Decremented {next_node} dependency to {dependencies[next_node]}")

                    if self._can_schedule_node(
                        next_node, graph, context, dependencies, running=set()
                    ):
                        queue.append(next_node)
                        logger.debug(f"[SCHEDULER] Added {next_node} to queue")
            else:
                # ✅ CHANGE: Store failed node in node_outputs
                logger.error(f"[SEQUENTIAL] Node {node_id} failed: {result.error} - STOPPING WORKFLOW")
                
                context.status = "failed"
                
                # ✅ Store failed node output with error
                context.node_outputs[node_id] = {
                    "status": "failed",
                    "error": result.error,
                    "message": f"Node execution failed: {result.error}",
                    "retry_count": result.retry_count if hasattr(result, 'retry_count') else 0
                }
                
                # Raise exception (will be caught in execute())
                raise RuntimeError(f"Workflow stopped due to node failure: {node_id} - {result.error}")

        logger.info(f"[SEQUENTIAL] Workflow completed. Executed: {context.executed_nodes}/{context.total_nodes}")


    def _execute_parallel_workflow(self, nodes, edges, trigger_data, context):
        """Parallel execution - stores failed node output"""
        
        graph = build_graph(nodes, edges)
        dependencies, ready_nodes = compute_dependencies(graph)
        outgoing = graph["outgoing"]

        ready_nodes = list(dict.fromkeys(ready_nodes))

        for node in nodes:
            NodeClass = NODE_REGISTRY.get(node["type"])
            if getattr(NodeClass, "is_trigger_node", False):
                if node["id"] not in ready_nodes:
                    ready_nodes.append(node["id"])

        completed, failed, running = set(), set(), set()
        pending_dependencies = dependencies.copy()
        futures = {}
        iteration_guard = 0

        try:
            while ready_nodes or futures:
                iteration_guard += 1
                if iteration_guard > 10000:
                    raise RuntimeError("Possible infinite graph loop detected")

                current_batch = ready_nodes.copy()
                ready_nodes.clear()

                for node_id in current_batch:
                    if node_id in completed or node_id in failed or node_id in running:
                        continue

                    node_def = self._find_node(nodes, node_id)
                    inputs = self._collect_inputs(node_id, graph, context.node_outputs)

                    if trigger_data and node_id in trigger_data:
                        injected = trigger_data[node_id]
                        logger.info(f"[EXECUTOR] Injected data for {node_id}: {injected}")
                        inputs.update(injected)

                        if injected.get("prefetched_events"):
                            logger.info(
                                f"[EXECUTOR] Skipping execution for {node_id} (AUTO MODE), using prefetched events"
                            )
                            _trigger_started_at = datetime.now()
                            LogEmitter.node_started(
                                run_id=self.execution_db_id,
                                node_id=node_id,
                                node_type=node_def.get("type"),
                                inputs={"trigger": "prefetched_events", "events_count": len(injected["prefetched_events"])},
                            )

                            result = NodeExecutionResult(
                                node_id=node_id,
                                status=NodeStatus.COMPLETED,
                                output=injected["prefetched_events"],
                                started_at=_trigger_started_at,
                                completed_at=datetime.now(),
                                duration_ms=0,
                            )

                            LogEmitter.node_completed(
                                run_id=self.execution_db_id,
                                node_id=node_id,
                                node_type=node_def.get("type"),
                                outputs={"events_count": len(injected["prefetched_events"])},
                                duration_ms=0,
                                started_at=_trigger_started_at,
                            )

                            context.node_results[node_id] = result
                            context.node_outputs[node_id] = result.output
                            context.executed_nodes += 1
                            completed.add(node_id)

                            next_nodes = self._get_next_nodes(
                                node_id, result.output, outgoing, nodes
                            )

                            for next_node in next_nodes:
                                if next_node in pending_dependencies:
                                    pending_dependencies[next_node] -= 1

                                if self._can_schedule_node(
                                    next_node, graph, context, pending_dependencies, running
                                ):
                                    ready_nodes.append(next_node)

                            continue

                    logger.debug(f"[EXECUTOR] Submitting {node_id} for parallel execution")
                    future = self.executor.submit(
                        self._execute_node_wrapper, node_def, inputs, context
                    )
                    futures[node_id] = future
                    running.add(node_id)

                if not futures and not ready_nodes:
                    logger.debug(
                        f"[EXECUTOR] No more futures or ready nodes. "
                        f"Completed: {len(completed)}, Failed: {len(failed)}"
                    )
                    break

                for node_id, future in list(futures.items()):
                    if future.done():
                        try:
                            result = future.result()
                        except WorkflowPausedException:
                            logger.info(
                                "[EXECUTOR] Workflow paused — cancelling remaining parallel tasks"
                            )

                            for f in futures.values():
                                f.cancel()

                            futures.clear()

                            if self.executor:
                                self.executor.shutdown(wait=False, cancel_futures=True)
                                self.executor = ThreadPoolExecutor(max_workers=self.max_workers)

                            raise

                        if not futures:
                            break

                        context.node_results[node_id] = result
                        running.discard(node_id)

                        if result.status == NodeStatus.COMPLETED:
                            completed.add(node_id)
                            context.node_outputs[node_id] = result.output
                            context.executed_nodes += 1

                            next_nodes = self._get_next_nodes(
                                node_id, result.output, outgoing, nodes
                            )

                            for next_node in next_nodes:
                                if next_node in pending_dependencies:
                                    pending_dependencies[next_node] -= 1

                                if self._can_schedule_node(
                                    next_node, graph, context, pending_dependencies, running
                                ):
                                    ready_nodes.append(next_node)
                        else:
                            # ✅ CHANGE: Store failed node in node_outputs
                            failed.add(node_id)
                            logger.error(f"[EXECUTOR] Node {node_id} failed: {result.error} - STOPPING WORKFLOW")
                            
                            # ✅ Store failed node output with error
                            context.node_outputs[node_id] = {
                                "status": "failed",
                                "error": result.error,
                                "message": f"Node execution failed: {result.error}",
                                "retry_count": result.retry_count if hasattr(result, 'retry_count') else 0
                            }
                            
                            # Cancel all pending futures
                            for f in futures.values():
                                f.cancel()
                            
                            futures.clear()
                            
                            # Shutdown executor
                            if self.executor:
                                self.executor.shutdown(wait=False, cancel_futures=True)
                                self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
                            
                            # Mark workflow as failed
                            context.status = "failed"
                            
                            # Raise exception (will be caught in execute())
                            raise RuntimeError(f"Workflow stopped due to node failure: {node_id} - {result.error}")

                        del futures[node_id]

                if futures and not ready_nodes:
                    time.sleep(0.1)

            logger.info(
                f"[EXECUTOR] Parallel workflow completed. "
                f"Executed: {len(completed)}, Failed: {len(failed)}, Total: {len(nodes)}"
            )
        
        except WorkflowPausedException:
            raise
        except Exception as e:
            logger.exception(f"[EXECUTOR] Parallel workflow failed: {e}")
            if self.executor:
                self.executor.shutdown(wait=False, cancel_futures=True)
                self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
            raise

    # -------------------
    # EXECUTOR HELPERS
    # -------------------

    def _execute_node_wrapper(self, node_def, inputs, context):
        try:
            return self._execute_node_safe(node_def, inputs, context)
        except WorkflowPausedException:
            raise  
        except Exception as e:
            return NodeExecutionResult(node_id=node_def["id"], status=NodeStatus.FAILED, error=str(e))


    def _execute_node_safe(self, node_def, inputs, context):
        """
        Execute a single node with comprehensive logging, caching, and retries.
        
        Returns:
            NodeExecutionResult with complete metadata
        """
        node_id = node_def["id"]
        node_type = node_def["type"]
        started_at = datetime.utcnow()

        def _extract_agent_name() -> str:
            node_data = node_def.get("data", {}) if isinstance(node_def, dict) else {}
            form_data = node_data.get("formData", {}) if isinstance(node_data, dict) else {}
            details = node_data.get("details", {}) if isinstance(node_data, dict) else {}
            return (
                form_data.get("agent_name")
                or form_data.get("name")
                or details.get("agent_name")
                or details.get("name")
                or node_data.get("label")
                or node_def.get("label")
                or node_id
            )

        def _write_agent_io_log(agent_name: str, node_input: Any, agent_parameters: Any, agent_output: Any) -> None:
            diagram_id = self._resolve_diagram_id()
            log_path = self._agent_io_log_path(diagram_id)

            record = OrderedDict()
            record["agent_name"] = str(agent_name)
            record["node_input"] = node_input
            record["agent_parameters"] = agent_parameters
            record["agent_output"] = agent_output

            try:
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=True, default=str))
                    f.write("\n")
            except Exception as log_err:
                logger.exception("[AGENT_IO] Failed to write agent IO log to %s: %s", log_path, log_err)
        
        # ──────────────────────────────────────────────────────────────
        # 1. Validate node type exists in registry
        # ──────────────────────────────────────────────────────────────
        NodeClass = NODE_REGISTRY.get(node_type)
        is_generic_agent_alias = False
        if NodeClass:
            try:
                is_generic_agent_alias = issubclass(NodeClass, GenericAgentNode)
            except TypeError:
                is_generic_agent_alias = False
        
        # Hard rule: WaitNode and GenericAgentNode are non-retriable
        if node_type == "WaitNode" or is_generic_agent_alias:
            max_retries = 0
        else:
            max_retries = self.max_retries
        
        if not NodeClass:
            error_msg = f"Unknown node type: {node_type}"
            completed_at = datetime.utcnow()
            duration_ms = (completed_at - started_at).total_seconds() * 1000
            
            LogEmitter.node_failed(
                run_id=self.execution_db_id,
                node_id=node_id,
                node_type=node_type,
                error=error_msg,
                started_at=started_at,
                retry_count=0,
                duration_ms=duration_ms
            )
            
            return NodeExecutionResult(
                node_id=node_id,
                status=NodeStatus.FAILED,
                error=error_msg,
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=duration_ms
            )
        
        # ──────────────────────────────────────────────────────────────
        # 2. Check cache (skip for dynamic/trigger nodes)
        # ──────────────────────────────────────────────────────────────
        DYNAMIC_NODES = {
            "GmailTriggerNode",
            "CalendarTriggerNode",
            "WebhookTriggerNode",
            "WhatsAppTriggerNode",
            "whatsappTriggerNode",
            "SlackTriggerNode",
            "slackTriggerNode",
        }
        is_dynamic = node_type in DYNAMIC_NODES
        
        cache_key = None
        if self.cache_service and not is_dynamic:
            cache_key = self.cache_service.compute_cache_key(node_def, inputs)
            cached_output = self.cache_service.get_cached_output(cache_key)
            
            if cached_output:
                completed_at = datetime.utcnow()
                duration_ms = (completed_at - started_at).total_seconds() * 1000
                
                # ✅ Log cache hit
                LogEmitter.node_cached(
                    run_id=self.execution_db_id,
                    node_id=node_id,
                    node_type=node_type,
                    cache_key=cache_key
                )
                
                return NodeExecutionResult(
                    node_id=node_id,
                    status=NodeStatus.COMPLETED,
                    output=cached_output,
                    started_at=started_at,
                    completed_at=completed_at,
                    duration_ms=duration_ms
                )
        
        # ──────────────────────────────────────────────────────────────
        # 3. Log execution start (only if not cached)
        # ──────────────────────────────────────────────────────────────
        
        # ✅ VERIFY DATA FLOW: Show what data this node receives from where
        logger.info(
            "[%s] 🚀 NODE EXECUTION START | type=%s",
            node_id,
            node_type
        )
        
        # Log all incoming data sources
        all_input_keys = set(inputs.keys())
        upstream_nodes_in_inputs = [k for k in all_input_keys if k in list(inputs.get("node_outputs", {}).keys())]
        
        if upstream_nodes_in_inputs:
            logger.info(
                "[%s] 📊 Received data FROM upstream nodes: %s",
                node_id,
                upstream_nodes_in_inputs
            )
            for upstream_id in upstream_nodes_in_inputs:
                upstream_data = inputs["node_outputs"].get(upstream_id, {})
                if isinstance(upstream_data, dict):
                    logger.debug(
                        "[%s]   ├─ %s provides: %s",
                        node_id,
                        upstream_id,
                        list(upstream_data.keys())
                    )
        
        # Log parameter data
        param_keys = [k for k in inputs.keys() 
                      if k not in ("node_outputs", "workflow", "execution_id", "tenant_id", "whatsapp_events", "latest_whatsapp_event", "slack_events", "latest_slack_event")]
        if param_keys:
            logger.info(
                "[%s] 🔑 Received parameters: %s",
                node_id,
                param_keys
            )
        
        # Log event data
        has_events = any(k.startswith(("whatsapp", "slack", "gmail")) for k in inputs.keys())
        if has_events:
            event_types = []
            if "whatsapp_events" in inputs:
                event_types.append(f"whatsapp({len(inputs.get('whatsapp_events', []))})")
            if "slack_events" in inputs:
                event_types.append(f"slack({len(inputs.get('slack_events', []))})")
            if any(k.startswith("gmail") for k in inputs.keys()):
                event_types.append("gmail")
            logger.info(
                "[%s] 📬 Received events: %s",
                node_id,
                event_types
            )
        
        LogEmitter.node_started(
            run_id=self.execution_db_id,
            node_id=node_id,
            node_type=node_type,
            inputs={k: v for k, v in inputs.items() if k != "node_outputs"}  # Exclude large context
        )
        
        # ──────────────────────────────────────────────────────────────
        # 4. Execute with retry logic
        # ──────────────────────────────────────────────────────────────
        for attempt in range(max_retries + 1):
            try:
                # Execute node
                node_instance = NodeClass(node_id, node_def["data"])
                output = node_instance.execute(inputs)
                
                # Success!
                completed_at = datetime.utcnow()
                duration_ms = (completed_at - started_at).total_seconds() * 1000
                
                # Apply configurable delay after every GenericAgentNode alias
                if is_generic_agent_alias and self.agent_execution_delay_seconds > 0:
                    logger.info(
                        "[EXECUTOR] Agent node %s completed. Applying %ss workflow delay.",
                        node_id,
                        self.agent_execution_delay_seconds,
                    )
                    time.sleep(self.agent_execution_delay_seconds)
                
                # ⏸️ WAIT NODE DETECTION
                if isinstance(output, dict) and output.get("status") == "waiting":
                    logger.info(f"[EXECUTOR] Workflow paused at WaitNode: {node_id}")

                    self._persist_wait_state(
                        node_id=node_id,
                        wait_output=output,
                        context=context
                    )

                    WorkflowLogService.create_node_log(
                        run_id=self.execution_db_id,
                        node_id=node_id,
                        node_type=node_type,
                        event_type="waiting",
                        status="waiting",
                        message="Node is waiting for external event",
                        started_at=started_at,
                        completed_at=datetime.utcnow(),
                        payload={"outputs": output},
                        log_level="INFO",
                    )

                    # STOP workflow execution cleanly
                    raise WorkflowPausedException(node_id=node_id)

                # Treat explicit node-level failures as execution errors so
                # retry/failure handling can return a correct node error.
                if isinstance(output, dict) and str(output.get("status", "")).lower() == "failed":
                    raise RuntimeError(
                        output.get("error")
                        or f"{node_type} returned failed status"
                    )

                # ✅ VERIFY DATA FLOW OUTPUT: Log what this node produces
                logger.info(
                    "[%s] ✅ NODE EXECUTION SUCCESSFUL | output_keys=%s",
                    node_id,
                    list(output.keys()) if isinstance(output, dict) else type(output).__name__
                )

                if is_generic_agent_alias:
                    agent_name = _extract_agent_name()
                    safe_inputs = {k: v for k, v in inputs.items() if k != "node_outputs"}
                    agent_parameters = None
                    if isinstance(output, dict):
                        agent_parameters = output.get("parameters")
                    _write_agent_io_log(
                        agent_name=agent_name,
                        node_input=safe_inputs,
                        agent_parameters=agent_parameters,
                        agent_output=output,
                    )
                
                if isinstance(output, dict):
                    # Categorize output
                    top_level_keys = list(output.keys())
                    logger.debug(
                        "[%s] 📤 OUTPUT DATA AVAILABLE TO DOWNSTREAM | keys=%s",
                        node_id,
                        top_level_keys
                    )
                    
                    # Show what specific data is available
                    if "status" in output and output["status"] != "completed":
                        logger.info(
                            "[%s]   ├─ status: %s",
                            node_id,
                            output["status"]
                        )
                    
                    # Show response/result data
                    if any(k in output for k in ["response", "result", "data", "output", "llm_response"]):
                        logger.debug(
                            "[%s]   ├─ Contains result data: %s",
                            node_id,
                            [k for k in output.keys() if k in ["response", "result", "data", "output", "llm_response"]]
                        )
                
                # ✅ Log success
                LogEmitter.node_completed(
                    run_id=self.execution_db_id,
                    node_id=node_id,
                    node_type=node_type,
                    outputs=output,
                    started_at=started_at,
                    duration_ms=duration_ms
                )
                
                # ✅ Write to cache (if applicable)
                if self.cache_service and cache_key and not is_dynamic:
                    self.cache_service.set_cached_output(cache_key, output)
                
                return NodeExecutionResult(
                    node_id=node_id,
                    status=NodeStatus.COMPLETED,
                    output=output,
                    started_at=started_at,
                    completed_at=completed_at,
                    duration_ms=duration_ms,
                    retry_count=attempt
                )
                
            except WorkflowPausedException:
                raise
            
            except Exception as e:
                # ──────────────────────────────────────────────────────
                # Retry logic
                # ──────────────────────────────────────────────────────
                if attempt < max_retries:
                    # ✅ Log retry attempt
                    LogEmitter.node_retry(
                        run_id=self.execution_db_id,
                        node_id=node_id,
                        node_type=node_type,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        error=e
                    )
                    
                    # Exponential backoff
                    time.sleep(2 ** attempt)
                    continue
                
                # ──────────────────────────────────────────────────────
                # Final failure (all retries exhausted)
                # ──────────────────────────────────────────────────────
                completed_at = datetime.utcnow()
                duration_ms = (completed_at - started_at).total_seconds() * 1000
                
                # ✅ Log final failure
                LogEmitter.node_failed(
                    run_id=self.execution_db_id,
                    node_id=node_id,
                    node_type=node_type,
                    error=e,
                    started_at=started_at,
                    retry_count=attempt,
                    duration_ms=duration_ms
                )
                
                return NodeExecutionResult(
                    node_id=node_id,
                    status=NodeStatus.FAILED,
                    error=str(e),
                    started_at=started_at,
                    completed_at=completed_at,
                    duration_ms=duration_ms,
                    retry_count=attempt
                )
        
        # Should never reach here, but safety fallback
        completed_at = datetime.utcnow()
        duration_ms = (completed_at - started_at).total_seconds() * 1000
        
        return NodeExecutionResult(
            node_id=node_id,
            status=NodeStatus.FAILED,
            error="Maximum retries exceeded",
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
            retry_count=max_retries
        )

    def _get_next_nodes(self, node_id, output, outgoing, nodes):
        """
        Return list of target node IDs (strings) that should run next.
        Handles:
        - Normal edges (now stored as dicts with "target")
        - Decision/Switch/Condition nodes that return "branch" or "route"
        - Old format (strings) for backward compatibility
        """
        node_def = self._find_node(nodes, node_id)
        node_type = node_def["type"].lower()
        print(f"[DEBUG] Node {node_id} output before deciding next: {output}")

        # ──────────────────────────────────────────────────────────────
        # 1. Conditional nodes (Decision, Condition, Switch)
        # ──────────────────────────────────────────────────────────────
        if node_type in ("decisionagentnode", "conditionnode", "switchnode", "decisionrouternode"):
            if isinstance(output, dict):
                branch = (
                    output.get("branch_node_id")
                    or output.get("resolved_branch_id")
                    or output.get("branch")
                    or output.get("route")
                )
                if not branch:
                    logger.info(
                        "[%s] 🔀 Conditional node returned no branch - workflow ends here",
                        node_id
                    )
                    return []
    
                # SwitchNode may return agent name like "SalesAgent-2"
                if node_type in ["switchnode","decisionrouternode"]:
                    resolved = self._resolve_agent_references(branch, nodes)
                    next_nodes = [r for r in resolved if r] if isinstance(resolved, list) else ([resolved] if resolved else [])
                    if next_nodes:
                        selected_agent_bindings = []
                        for next_node_id in next_nodes:
                            node_match = next((n for n in nodes if n.get("id") == next_node_id), {})
                            form_data = ((node_match.get("data") or {}).get("formData") or {}) if isinstance(node_match, dict) else {}
                            selected_agent_bindings.append(
                                {
                                    "node_id": next_node_id,
                                    "node_type": node_match.get("type"),
                                    "agent_name": form_data.get("agent_name"),
                                    "agent_id": form_data.get("agent_id"),
                                }
                            )
                        logger.info(
                            "[FLOW_TRACE][EXECUTOR][BRANCH_RESOLVE] decision_node=%s raw_branch=%s resolved_nodes=%s selected_agent_bindings=%s",
                            node_id,
                            branch,
                            next_nodes,
                            selected_agent_bindings,
                        )
                    else:
                        logger.warning(
                            "[FLOW_TRACE][EXECUTOR][BRANCH_RESOLVE_EMPTY] decision_node=%s raw_branch=%s",
                            node_id,
                            branch,
                        )
                    if next_nodes:
                        logger.info(
                            "[%s] 🔀 Conditional node routes to: %s",
                            node_id,
                            next_nodes
                        )
                    return next_nodes
    
                # Regular Decision/Condition node
                if isinstance(branch, str):
                    logger.info(
                        "[%s] 🔀 Conditional node routes to: %s",
                        node_id,
                        branch
                    )
                    return [branch]
                elif isinstance(branch, list):
                    branch_list = [b for b in branch if b]
                    if branch_list:
                        logger.info(
                            "[%s] 🔀 Conditional node routes to: %s",
                            node_id,
                            branch_list
                        )
                    return branch_list
                else:
                    return []
    
        # ──────────────────────────────────────────────────────────────
        # 2. Normal flow – extract target IDs from edge objects
        # ──────────────────────────────────────────────────────────────
        raw_edges = outgoing.get(node_id, [])
        next_node_ids = []
    
        for item in raw_edges:
            if isinstance(item, dict):
                target = item.get("target")
                if target:
                    next_node_ids.append(target)
            elif isinstance(item, str):
                # Backward compatibility with old graph format
                next_node_ids.append(item)
            # else: ignore invalid
    
        # ✅ Log data flow to downstream nodes
        if next_node_ids:
            logger.info(
                "[%s] 📤 Data flows to downstream: %s",
                node_id,
                next_node_ids
            )
            # Log what data each downstream node will receive
            for next_node_id in next_node_ids:
                logger.debug(
                    "[%s]   └─ %s will receive all output data from %s",
                    node_id,
                    next_node_id,
                    node_id
                )
        else:
            logger.info(
                "[%s] ✅ No downstream nodes - %s is end of this execution path",
                node_id,
                node_id
            )
    
        return next_node_ids

    def _map_node_ids_to_labels(self, node_outputs: dict) -> dict:
        """
        Returns:
        {
        "<label>-[<node_id>]": output
        }
        """
        id_to_label = {}

        for node in self.workflow.get("nodes", []):
            data = node.get("data", {}) or {}
            form_data = data.get("formData", {}) or {}

            label = (
                form_data.get("agent_name")
                or form_data.get("label")
                or data.get("label")
                or node["id"]
            )

            id_to_label[node["id"]] = label

        # ✅ ONLY CHANGE: label-[nodeId]
        return {
            f"{id_to_label.get(nid, nid)}-[{nid}]": output
            for nid, output in node_outputs.items()
        }

    def _resolve_agent_references(self, target, nodes):
        def resolve_single(target_str):
            if not target_str:
                return target_str
            if any(node["id"] == target_str for node in nodes):
                return target_str
            if "-" not in target_str:
                return None
            
            parts = target_str.rsplit("-", 1)
            if len(parts) == 2 and parts[1].strip().isdigit():
                agent_name = parts[0].strip()
                agent_id = int(parts[1].strip())

                for node in nodes:
                    fd = node.get("data", {}).get("formData", {})
                    fd_agent_id = fd.get("agent_id")
                    try:
                        fd_agent_id_int = int(str(fd_agent_id).strip())
                    except (TypeError, ValueError):
                        fd_agent_id_int = None

                    if (
                        fd.get("agent_name") == agent_name
                        and fd_agent_id_int == agent_id
                    ):
                        return node["id"]
                return None
        
        if isinstance(target, str):
            resolved = resolve_single(target)
            return [] if resolved is None else resolved
        elif isinstance(target, list):
            resolved_list = [resolve_single(t) for t in target if t]
            resolved_list = [x for x in resolved_list if x]
            return resolved_list
        return target
        
    def _collect_inputs(self, node_id, graph, node_outputs):
        """
        Supports BOTH:
        - mapping by node ID
        - mapping by node label
        - node_outputs for cross-node lookups
        """

        inputs = {}

        # 1. Parent inputs
        incoming_edges = graph["incoming"].get(node_id, [])
        parent_sources = []
        for edge in incoming_edges:
            source = edge["source"] if isinstance(edge, dict) else edge
            if source in node_outputs:
                inputs[source] = node_outputs[source]
                parent_sources.append(source)
        
        # ✅ Log parent data injection
        if parent_sources:
            logger.info(
                "[%s] 📥 Parent outputs received from: %s",
                node_id,
                parent_sources
            )
            for parent_id in parent_sources:
                parent_output = node_outputs.get(parent_id, {})
                output_keys = list(parent_output.keys()) if isinstance(parent_output, dict) else "N/A"
                logger.debug(
                    "[%s]   ├─ from %s: %s",
                    node_id,
                    parent_id,
                    output_keys
                )

        # 2. Complete node_outputs for deep resolution (all executed nodes available)
        inputs["node_outputs"] = node_outputs.copy()
        inputs["execution_id"] = self.execution_db_id
        
        # ✅ Log all available upstream data
        all_upstream_nodes = list(node_outputs.keys())
        if all_upstream_nodes:
            logger.debug(
                "[%s] 🔗 All upstream nodes available: %s",
                node_id,
                all_upstream_nodes
            )

        # 3. Add label -> id aliases
        for node in self.workflow.get("nodes", []):
            form = node.get("data", {}).get("formData", {}) or {}
            label = (
                form.get("agent_name")
                or form.get("label")
                or node["id"]
            )
            node_id_ref = node["id"]

            if node_id_ref in node_outputs:
                inputs["node_outputs"][label] = node_outputs[node_id_ref]

        # 4. Auto-collect WhatsApp event context for downstream nodes
        def _collect_whatsapp_events(value):
            events = []
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict) and (
                        item.get("trigger_type") == "whatsapp" or item.get("source") == "whatsapp"
                    ):
                        events.append(item)
                return events

            if isinstance(value, dict):
                nested_events = value.get("whatsapp_events")
                if isinstance(nested_events, list):
                    events.extend([evt for evt in nested_events if isinstance(evt, dict)])

                latest_event = value.get("latest_whatsapp_event")
                if isinstance(latest_event, dict):
                    events.append(latest_event)

                event_payload = value.get("event_payload")
                if isinstance(event_payload, dict):
                    payload_events = event_payload.get("whatsapp_events")
                    if isinstance(payload_events, list):
                        events.extend([evt for evt in payload_events if isinstance(evt, dict)])
                    payload_latest = event_payload.get("latest_whatsapp_event")
                    if isinstance(payload_latest, dict):
                        events.append(payload_latest)

                if value.get("trigger_type") == "whatsapp" or value.get("source") == "whatsapp":
                    events.append(value)

            return events

        whatsapp_events = []
        for edge in incoming_edges:
            source = edge["source"] if isinstance(edge, dict) else edge
            whatsapp_events.extend(_collect_whatsapp_events(node_outputs.get(source)))

        if not whatsapp_events:
            for _, output in reversed(list(node_outputs.items())):
                whatsapp_events.extend(_collect_whatsapp_events(output))
                if whatsapp_events:
                    break

        if whatsapp_events:
            latest_whatsapp_event = whatsapp_events[-1]
            inputs.setdefault("whatsapp_events", whatsapp_events)
            inputs.setdefault("latest_whatsapp_event", latest_whatsapp_event)

            message = (
                latest_whatsapp_event.get("message")
                or latest_whatsapp_event.get("user_query")
                or (latest_whatsapp_event.get("content") or {}).get("text")
                or ""
            )
            if isinstance(message, dict):
                message = message.get("body") or ""

            phone = str(
                latest_whatsapp_event.get("phone")
                or (latest_whatsapp_event.get("metadata") or {}).get("from_phone")
                or (latest_whatsapp_event.get("metadata") or {}).get("from")
                or (latest_whatsapp_event.get("parameters") or {}).get("phone")
                or (latest_whatsapp_event.get("parameters") or {}).get("from")
                or ""
            )
            message_id = str(
                (latest_whatsapp_event.get("metadata") or {}).get("message_id")
                or latest_whatsapp_event.get("message_id")
                or ""
            ).strip()

            if isinstance(message, str) and message.strip():
                inputs.setdefault("message", message.strip())
                inputs.setdefault("user_query", message.strip())
            if phone.strip():
                inputs.setdefault("phone", phone.strip())
                inputs.setdefault("from", phone.strip())
            if message_id:
                inputs.setdefault("message_id", message_id)

        # 5. Auto-collect Slack event context for downstream nodes (mirrors WhatsApp logic)
        def _collect_slack_events(value):
            events = []
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict) and (
                        item.get("trigger_type") == "slack" or item.get("source") == "slack"
                    ):
                        events.append(item)
                return events

            if isinstance(value, dict):
                nested_events = value.get("slack_events")
                if isinstance(nested_events, list):
                    events.extend([evt for evt in nested_events if isinstance(evt, dict)])

                latest_event = value.get("latest_slack_event")
                if isinstance(latest_event, dict):
                    events.append(latest_event)

                single_event = value.get("slack_event")
                if isinstance(single_event, dict):
                    events.append(single_event)

                event_payload = value.get("event_payload")
                if isinstance(event_payload, dict):
                    payload_events = event_payload.get("slack_events")
                    if isinstance(payload_events, list):
                        events.extend([evt for evt in payload_events if isinstance(evt, dict)])
                    payload_latest = event_payload.get("latest_slack_event")
                    if isinstance(payload_latest, dict):
                        events.append(payload_latest)
                    payload_single = event_payload.get("slack_event")
                    if isinstance(payload_single, dict):
                        events.append(payload_single)

                inferred_message = (
                    value.get("message")
                    or value.get("user_query")
                    or value.get("text")
                    or (event_payload or {}).get("message")
                    or (event_payload or {}).get("user_query")
                    or (event_payload or {}).get("text")
                )
                inferred_channel = (
                    value.get("channel")
                    or value.get("to")
                    or (event_payload or {}).get("channel")
                    or (event_payload or {}).get("to")
                )
                inferred_user = value.get("user") or (event_payload or {}).get("user")
                inferred_thread_ts = (
                    value.get("thread_ts")
                    or value.get("ts")
                    or (event_payload or {}).get("thread_ts")
                    or (event_payload or {}).get("ts")
                )

                if inferred_message or inferred_channel or inferred_user or inferred_thread_ts:
                    events.append(
                        {
                            "trigger_type": "slack",
                            "source": "slack",
                            "message": inferred_message,
                            "user_query": inferred_message,
                            "text": inferred_message,
                            "channel": inferred_channel,
                            "user": inferred_user,
                            "thread_ts": inferred_thread_ts,
                            "metadata": {
                                "channel": inferred_channel,
                                "user": inferred_user,
                                "thread_ts": inferred_thread_ts,
                            },
                        }
                    )

                if value.get("trigger_type") == "slack" or value.get("source") == "slack":
                    events.append(value)

            return events

        slack_events = []
        for edge in incoming_edges:
            source = edge["source"] if isinstance(edge, dict) else edge
            slack_events.extend(_collect_slack_events(node_outputs.get(source)))

        if not slack_events:
            for _, output in reversed(list(node_outputs.items())):
                slack_events.extend(_collect_slack_events(output))
                if slack_events:
                    break

        if slack_events:
            latest_slack_event = slack_events[-1]
            inputs.setdefault("slack_events", slack_events)
            inputs.setdefault("latest_slack_event", latest_slack_event)
            inputs.setdefault("slack_event", latest_slack_event)

            slack_message = (
                latest_slack_event.get("message")
                or latest_slack_event.get("user_query")
                or latest_slack_event.get("text")
                or (latest_slack_event.get("content") or {}).get("text")
                or ""
            )
            if isinstance(slack_message, dict):
                slack_message = (
                    slack_message.get("text")
                    or slack_message.get("body")
                    or ""
                )
            slack_channel = str(
                (latest_slack_event.get("metadata") or {}).get("channel")
                or latest_slack_event.get("channel")
                or (latest_slack_event.get("parameters") or {}).get("channel")
                or ""
            )
            slack_user = str(
                (latest_slack_event.get("metadata") or {}).get("user")
                or latest_slack_event.get("user")
                or (latest_slack_event.get("parameters") or {}).get("user")
                or ""
            )
            slack_thread_ts = str(
                (latest_slack_event.get("metadata") or {}).get("thread_ts")
                or latest_slack_event.get("thread_ts")
                or latest_slack_event.get("ts")
                or ""
            )

            if isinstance(slack_message, str) and slack_message.strip():
                inputs.setdefault("message", slack_message.strip())
                inputs.setdefault("user_query", slack_message.strip())
            if slack_channel.strip():
                inputs.setdefault("channel", slack_channel.strip())
            if slack_user.strip():
                inputs.setdefault("user", slack_user.strip())
            if slack_thread_ts.strip():
                inputs.setdefault("thread_ts", slack_thread_ts.strip())

        # 6. Auto-collect upstream WAIT NODE outputs for downstream agents
        # This enables any agent downstream of a wait node to access wait output
        # without explicit data_mapping configuration
        upstream_wait_nodes = self._find_upstream_wait_nodes(node_id, graph)
        if upstream_wait_nodes:
            logger.info(
                "[%s] Found upstream wait nodes: %s",
                node_id,
                upstream_wait_nodes
            )
            for wait_node_id in upstream_wait_nodes:
                if wait_node_id in node_outputs:
                    wait_output = node_outputs[wait_node_id]
                    # Store in inputs for direct access
                    inputs[wait_node_id] = wait_output
                    # Also ensure it's in node_outputs for resolution
                    inputs["node_outputs"][wait_node_id] = wait_output
                    logger.info(
                        "[%s] 📨 Auto-injected wait node output | wait_id=%s keys=%s",
                        node_id,
                        wait_node_id,
                        list(wait_output.keys()) if isinstance(wait_output, dict) else "N/A"
                    )

        workflow_meta = {
            "tenant_id": self.workflow.get("tenant_id"),
            "bot_id": self.workflow.get("bot_id"),
            "diagram_id": self.workflow.get("diagram_id"),
            # Expose graph structure for router fallback logic when
            # condition rules are absent in saved workflows.
            "nodes": self.workflow.get("nodes", []),
            "edges": self.workflow.get("edges", []),
        }
        inputs["workflow"] = workflow_meta

        if workflow_meta["tenant_id"] is not None:
            inputs["tenant_id"] = workflow_meta["tenant_id"]

        # ✅ COMPREHENSIVE DATA FLOW SUMMARY
        # Log complete input context for debugging
        logger.info(
            "[%s] ✅ INPUT COLLECTION COMPLETE | total_keys=%d",
            node_id,
            len(inputs)
        )
        
        # Summary of what this node receives
        input_summary = {
            "direct_parents": parent_sources if parent_sources else [],
            "upstream_nodes_accessible": list(node_outputs.keys()),
            "event_data": {
                "has_whatsapp": "whatsapp_events" in inputs,
                "has_slack": "slack_events" in inputs,
                "has_gmail": any(k.startswith("gmailtrigger") for k in inputs.keys()),
            },
            "wait_data": {
                "has_wait_output": any(wait_node_id in inputs for wait_node_id in upstream_wait_nodes) if upstream_wait_nodes else False,
                "wait_nodes": upstream_wait_nodes or [],
            },
            "parameter_keys": [k for k in inputs.keys() if k not in ("node_outputs", "workflow", "execution_id") and not k.startswith("whatsapp") and not k.startswith("slack")],
        }
        
        logger.debug(
            "[%s] 📊 Input Summary:\n%s",
            node_id,
            json.dumps(input_summary, indent=2, default=str)
        )

        return inputs
    
    def _find_node(self, nodes, node_id):
        for node in nodes:
            if node["id"] == node_id:
                return node
        raise Exception(f"Node {node_id} not found")
    
    def _find_upstream_wait_nodes(self, node_id, graph, visited=None):
        """
        Recursively find all upstream wait nodes in the workflow graph.
        Returns a list of wait node IDs that are upstream from the given node.
        
        Used for auto-injecting wait node outputs into downstream agents
        without requiring explicit data_mapping configuration.
        """
        if visited is None:
            visited = set()
        
        if node_id in visited:
            return []
        
        visited.add(node_id)
        wait_nodes = []
        
        # Get all incoming edges for this node
        incoming_edges = graph.get("incoming", {}).get(node_id, [])
        
        for edge in incoming_edges:
            source_node_id = edge["source"] if isinstance(edge, dict) else edge
            
            if source_node_id in visited:
                continue
            
            # Check if source node is a WaitNode
            source_node = None
            for node in self.workflow.get("nodes", []):
                if node["id"] == source_node_id:
                    source_node = node
                    break
            
            if source_node and source_node.get("type") == "WaitNode":
                wait_nodes.append(source_node_id)
            
            # Recursively check upstream nodes
            upstream_wait_nodes = self._find_upstream_wait_nodes(
                source_node_id, graph, visited
            )
            wait_nodes.extend(upstream_wait_nodes)
        
        return list(set(wait_nodes))  # Remove duplicates
    
    
    def _can_schedule_node(
        self,
        node_id,
        graph,
        context,
        pending_dependencies,
        running
    ):
        """
        Generic scheduling rule supporting:
        - AND-join (default)
        - OR-join (fallback)

        OR-join condition:
        - At least one parent completed
        - No parent still running

        This applies to ALL node types without hardcoding.
        """

        # -------------------------
        # AND-JOIN (existing logic)
        # -------------------------
        if pending_dependencies.get(node_id, 0) == 0:
            return True

        # Wait nodes must obey strict AND semantics.
        # Do not resume or schedule a WaitNode until all incoming dependencies are satisfied.
        node_def = None
        try:
            node_def = self._find_node(self.workflow["nodes"], node_id)
        except Exception:
            node_def = None

        if node_def and node_def.get("type") == "WaitNode":
            return False

        # -------------------------
        # OR-JOIN (generic fallback)
        # -------------------------
        incoming = graph.get("incoming", {}).get(node_id, [])
        if not incoming:
            return False

        parent_ids = [
            edge["source"] if isinstance(edge, dict) else edge
            for edge in incoming
        ]

        executed_parents = [
            p for p in parent_ids
            if p in context.node_outputs
        ]

        running_parents = [
            p for p in parent_ids
            if p in running
        ]

        return bool(executed_parents) and not running_parents
      
    def create_execution_record(self, workflow_json, trigger_data, trigger_source=None):
        """
        Create workflow run in an isolated transaction.
        This transaction MUST NEVER be rolled back.
        """

        # 🔒 ALWAYS use a fresh session
        session = next(db_session())

        diagram_id = workflow_json.get("diagram_id") or workflow_json.get("id") or 0

        run = WorkflowRun(
            bot_id=workflow_json.get("bot_id"),
            tenant_id=workflow_json.get("tenant_id"),
            diagram_id=diagram_id,
            status="running",
            trigger_type=trigger_source,
            trigger_data=trigger_data
        )

        session.add(run)
        session.commit()          # ✅ Durable, visible to all threads

        run_id = run.id
        session.close()           # 🔒 Prevent rollback from elsewhere

        self.execution_db_id = run_id

        return run_id

    def update_run_status(self, run_id, new_status, error=None):
        """
        Update workflow run status in database.
        
        ✅ FIX: Creates its own session instead of using non-existent self.session_ref
        """
        try:
            # ✅ Create a fresh session for this update
            session = next(db_session())
            
            run = session.query(WorkflowRun).get(run_id)
            if run:
                run.status = new_status
                if error:
                    run.context_json = {"error": error}
                run.updated_at = datetime.utcnow()
                
                session.commit()  # ✅ Commit immediately
            
            session.close()  # ✅ Clean up
            
        except Exception as e:
            logger.exception(f"Failed to update workflow run status: {e}")

    def _finalize_execution_in_db(self, context: WorkflowExecutionContext, status: str, error: str = None):
        """
        Store full context in database on completion or failure.
        
        ✅ NEW METHOD: Stores complete execution context including:
        - All node outputs (partial results)
        - Node results with timings
        - Error information if failed
        """
        if not hasattr(self, 'execution_db_id'):
            logger.warning("No execution_db_id found - skipping DB update")
            return
        
        try:
            session = next(db_session())
            
            run = session.query(WorkflowRun).get(self.execution_db_id)
            if not run:
                logger.error(f"WorkflowRun {self.execution_db_id} not found")
                session.close()
                return
            
            # Build context JSON with all execution data
            context_json = {
                "execution_id": context.execution_id,
                "workflow_id": context.workflow_id,
                "status": status,
                "executed_nodes": context.executed_nodes,
                "total_nodes": context.total_nodes,
                "started_at": context.started_at.isoformat() if context.started_at else None,
                "completed_at": context.completed_at.isoformat() if context.completed_at else None,
                
                # ✅ Store all node outputs (includes partial results + failed node)
                "node_outputs": context.node_outputs,
                
                # ✅ Store detailed node results
                "node_results": {
                    node_id: {
                        "status": result.status.value if hasattr(result.status, 'value') else str(result.status),
                        "duration_ms": result.duration_ms,
                        "retry_count": result.retry_count if hasattr(result, 'retry_count') else 0,
                        "error": result.error if hasattr(result, 'error') else None,
                        "started_at": result.started_at.isoformat() if result.started_at else None,
                        "completed_at": result.completed_at.isoformat() if result.completed_at else None
                    }
                    for node_id, result in context.node_results.items()
                }
            }
            
            # Add error if failed
            if error:
                context_json["error"] = error
            
            # Update workflow run
            run.status = status
            run.context_json = context_json
            run.completed_at = datetime.utcnow()
            run.updated_at = datetime.utcnow()
            
            session.commit()
            session.close()
            
            logger.info(f"✅ Finalized execution in DB | run_id={self.execution_db_id} status={status}")
            
        except Exception as e:
            logger.exception(f"Failed to finalize execution in DB: {e}")
            # Don't re-raise - this is best-effort logging


    def _fetch_wait_webhook_response(self, wait_state: WorkflowWaitState) -> Optional[dict]:
        """Fetch the wait node webhook response JSON for resumed execution."""
        try:
            headers = wait_state.headers or {}
            response = requests.get(wait_state.webhook_url, headers=headers, timeout=30)
            logger.info(
                "[RESUME] Fetched wait webhook response | url=%s status=%s",
                wait_state.webhook_url,
                response.status_code,
            )
            if response.status_code != 200:
                logger.warning(
                    "[RESUME] Non-200 wait webhook response | status=%s body=%s",
                    response.status_code,
                    response.text[:200],
                )
                return None

            try:
                return response.json()
            except ValueError as e:
                logger.error("[RESUME] Failed to parse wait webhook response JSON: %s", e)
                return None
        except Exception as e:
            logger.exception("[RESUME] Failed to fetch wait webhook response: %s", e)
            return None

    def _persist_wait_state(self, node_id: str, wait_output: dict, context):
        """Save wait state with all tracking information"""
        session = next(db_session())

        try:
            
            tracking_key = wait_output.get("tracking_key") or f"node:{node_id}"
            tracking_type = wait_output.get("tracking_type", "custom")

            existing = (
                session.query(WorkflowWaitState)
                .filter(
                    WorkflowWaitState.workflow_run_id == self.execution_db_id,
                    WorkflowWaitState.node_id == node_id,
                    WorkflowWaitState.status == "waiting",
                )
                .one_or_none()
            )

            if existing:
                logger.warning(
                    f"⚠️ Wait already exists for run={self.execution_db_id}, node={node_id}. Skipping insert."
                )
                return existing


            wait_state = WorkflowWaitState(
                # Workflow identifiers
                workflow_run_id=getattr(self, 'execution_db_id', None),
                execution_id=context.execution_id,
                bot_id=str(self.workflow.get("bot_id")),
                tenant_id=str(self.workflow.get("tenant_id")),
                diagram_id=int(self.workflow.get("diagram_id", 0)),
                node_id=node_id,
                trigger_id=self.workflow.get("trigger_id"),

                # ✅ NEW: Tracking fields
                tracking_key=tracking_key,
                tracking_type=tracking_type,

                # Configuration
                webhook_url=wait_output["config"]["webhook_url"],
                success_path=wait_output["config"]["success_path"],
                success_value=wait_output["config"].get("success_value"),
                backoff_minutes=wait_output["config"]["backoff_minutes"],
                max_retries=wait_output["config"]["max_retries"],
                fetch_url_on_success=wait_output["config"].get("fetch_url_on_success"),
                headers=wait_output["config"].get("headers"),
                timeout_at=datetime.fromisoformat(
                    wait_output["config"]["timeout_at"].replace("Z", "")
                ),

                # State
                status="waiting",
                retry_count=0,
                next_poll_at=datetime.fromisoformat(
                    wait_output["state"]["next_poll_at"].replace("Z", "")
                ),

                # Context - ✅ Store everything including wait_output
                workflow_state={
                    "node_outputs": {
                        **context.node_outputs,
                        # ✅ CRITICAL: Include wait_output with mapped_data for resume
                        node_id: wait_output
                    },
                    "node_results": {
                        k: v.to_dict()
                        for k, v in context.node_results.items()
                    },
                    "executed_nodes": context.executed_nodes,
                    "execution_id": context.execution_id
                },
                
                
                created_at=datetime.utcnow()
            )

            session.add(wait_state)

            run = session.query(WorkflowRun).get(self.execution_db_id)
            if run:
                run.status = "waiting"
                run.current_node_id = node_id
                run.context_json = {
                    "execution_id": context.execution_id,
                    "status": "waiting",
                    "waiting_node_id": node_id,
                    "node_outputs": context.node_outputs,
                    "node_results": {
                        key: value.to_dict()
                        for key, value in context.node_results.items()
                    },
                    "executed_nodes": context.executed_nodes,
                    "total_nodes": context.total_nodes,
                }
                run.updated_at = datetime.utcnow()

            session.commit()
            return wait_state
            
        except IntegrityError as e:
            session.rollback()
            if "unique constraint" in str(e).lower():
                # Another thread already created it
                existing = session.query(WorkflowWaitState).filter_by(
                    workflow_run_id=self.execution_db_id,
                    node_id=node_id
                ).one()
                return existing
            raise
        finally:
            session.close()
    
    def shutdown(self):
        if self.executor:
            self.executor.shutdown(wait=True)
        
        # ✅ Only close session if we created it
        if hasattr(self, 'should_close_session') and self.should_close_session:
            if hasattr(self, 'session_ref') and self.session_ref:
                self.session_ref.close()

    def _checkpoint(self, context):
        pass

    def _log_execution_summary(self, context):
        pass
    
  
