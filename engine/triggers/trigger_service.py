# services/trigger_service.py

# import  time
# from datetime import datetime
# from typing import List, Dict, Any

# from sqlalchemy.exc import SQLAlchemyError

# from app.database.DatabaseOperationPostgreSQL import db_session
# from app.models.workflow_trigger  import WorkflowTrigger
# from app.models.bot_diagram import BotDiagram

# from engine.workflow_executor import WorkflowExecutor
# from engine.triggers.strategy_registry import TriggerStrategyRegistry
# from logging_config import setup_logging
# from engine.trigger_event_dedup import (
#     is_event_already_processed,
#     mark_event_as_processed,
# )


# logger = setup_logging("TriggerService", level="DEBUG")



# # ---------------------------
# # FLAGS / MODES
# # ---------------------------

# # MODE A (current): let GmailTriggerNode do the Gmail API calls
# USE_GMAIL_NODE_FOR_FETCH = False   # <- set False later when you want the strategy to fetch

# # Simple polling interval (seconds)
# TRIGGER_POLL_INTERVAL = 60


# def _build_strategy(trigger):
#     strategy_cls = TriggerStrategyRegistry.get(trigger.trigger_type)

#     if not strategy_cls:
#         raise ValueError(f"No strategy registered for {trigger.trigger_type}")

#     return strategy_cls(trigger)


# def _load_latest_workflow_for_bot(session, bot_id: int,flow_id: int) -> Dict[str, Any]:
#     """
#     Load latest saved diagram (workflow) for bot.
#     This is exactly what your bot_diagram save logic creates.
#     """
#     diagram = (
#         session.query(BotDiagram)
#         .filter_by(bot_id=bot_id, diagram_id=flow_id)
#         .first()
#     )
#     if not diagram:
#         raise ValueError(f"No workflow diagram found for bot_id={bot_id}, flow_id={flow_id}")


#     import json
#     return json.loads(diagram.diagram_json)


# def _execute_workflow_with_node_fetch(session, trigger: WorkflowTrigger):
#     """
#     MODE A:
#     - Use WorkflowExecutor normally.
#     - GmailTriggerNode will handle fetching emails via its own logic.
#     """
#     bot_id = trigger.bot_id
#     tenant_id = trigger.tenant_id
#     flow_id = trigger.flow_id

#     logger.info(f"[MODE_A] Executing workflow for trigger_id={trigger.id}, bot_id={bot_id}")


#     workflow_json = _load_latest_workflow_for_bot(session, bot_id, flow_id)

#     # ✅ Required injection here
#     workflow_json.update({
#         "bot_id": trigger.bot_id,
#         "tenant_id": trigger.tenant_id,
#         "trigger_id": trigger.id,
#         "trigger_type": trigger.trigger_type,
#     })


#     # For background jobs we don't have JWT here.
#     # We rely on the updated GmailTriggerNode that supports tenant_id fallback.
#     # So we inject tenant_id into trigger_data for that trigger_node.
#     trigger_node_id = trigger.trigger_node_id

#     trigger_data = {
#         trigger_node_id: {
#             "tenant_id": tenant_id
#         }
#     }
#     workflow_json["diagram_id"] = trigger.flow_id
#     executor = WorkflowExecutor(workflow_json)
#     result = executor.execute(
#         trigger_data=trigger_data,
#         return_context=True
#     )

#     logger.info(f"[MODE_A] Workflow execution completed for trigger_id={trigger.id}, "
#                 f"executed_nodes={result.executed_nodes}, status={result.to_dict().get('status')}")




# def _execute_workflow_with_prefetched_events(
#     session,
#     trigger: WorkflowTrigger,
#     events: List[Dict[str, Any]],
# ):
#     """
#     MODE B: Execute workflow with prefetched events
#     Adds DB-backed deduplication (processed_trigger_events)
#     """

#     bot_id = trigger.bot_id
#     flow_id = trigger.flow_id
#     tenant_id = trigger.tenant_id

#     # ------------------------------------------------
#     # 1️⃣ DEDUP EVENTS (BEFORE WORKFLOW EXECUTION)
#     # ------------------------------------------------
#     filtered_events = []

#     for e in events:
#         event_id = e.get("metadata", {}).get("message_id")
#         if not event_id:
#             continue

#         if is_event_already_processed(
#             session=session,
#             tenant_id=tenant_id,
#             trigger_id=trigger.id,
#             event_id=event_id,
#         ):
#             logger.info(
#                 f"[DEDUP] Skipping already processed event "
#                 f"trigger_id={trigger.id}, event_id={event_id}"
#             )
#             continue

#         filtered_events.append(e)

#     if not filtered_events:
#         logger.info(
#             f"[MODE_B] No new events after dedup for trigger_id={trigger.id}"
#         )
#         return

#     # ------------------------------------------------
#     # 2️⃣ LOAD WORKFLOW JSON
#     # ------------------------------------------------
#     workflow_json = _load_latest_workflow_for_bot(
#         session,
#         bot_id,
#         flow_id,
#     )

#     workflow_json.update({
#         "bot_id": trigger.bot_id,
#         "tenant_id": tenant_id,
#         "trigger_id": trigger.id,
#         "trigger_type": trigger.trigger_type,
#         "diagram_id": trigger.flow_id,
#     })

#     trigger_node_id = trigger.trigger_node_id

#     trigger_data = {
#         trigger_node_id: {
#             "tenant_id": tenant_id,
#             "prefetched_events": filtered_events,
#         }
#     }

#     logger.info(
#         f"[MODE_B] Executing workflow with "
#         f"{len(filtered_events)} event(s) for trigger_id={trigger.id}"
#     )

#     # ------------------------------------------------
#     # 3️⃣ EXECUTE WORKFLOW
#     # ------------------------------------------------
#     executor = WorkflowExecutor(workflow_json)
#     executor.session_ref = session  # reuse same session

#     try:
#         result = executor.execute(
#             trigger_data=trigger_data,
#             return_context=True,
#         )

#     except Exception as e:
#         logger.exception(
#             f"[MODE_B] Workflow execution failed for trigger_id={trigger.id}"
#         )
#         session.rollback()
#         raise

#     # ------------------------------------------------
#     # 4️⃣ MARK EVENTS AS PROCESSED (AFTER SUCCESS)
#     # ------------------------------------------------
#     for e in filtered_events:
#         mark_event_as_processed(
#             session=session,
#             tenant_id=tenant_id,
#             trigger_id=trigger.id,
#             event_id=e["metadata"]["message_id"],
#             event_source=e.get("source", "gmail"),
#         )

#     # ------------------------------------------------
#     # 5️⃣ FINALIZE + COMMIT
#     # ------------------------------------------------
#     if hasattr(executor, "execution_db_id"):
#         executor.finalize_execution_record(result)

#     session.commit()

#     logger.info(
#         f"[MODE_B] Completed workflow & marked "
#         f"{len(filtered_events)} event(s) processed "
#         f"for trigger_id={trigger.id}"
#     )


# def start_trigger_service():
#     """
#     Long-running polling loop.
#     """
#     logger.info("🚀 TriggerService started (polling mode)")

#     while True:
#         session = None
#         try:
#             now = datetime.now()
#             session = next(db_session())

#             triggers: List[WorkflowTrigger] = (
#                 session.query(WorkflowTrigger)
#                 .filter_by(status="active")
#                 .all()
#             )

#             logger.debug(f"[TRIGGER_SERVICE] Found {len(triggers)} active trigger(s)")

#             for trigger in triggers:
#                 try:
#                     strategy = _build_strategy(trigger)

#                     if not strategy.should_run(now):
#                         logger.debug(f"[TRIGGER_SERVICE] Trigger_id={trigger.id} not due yet")
#                         continue

#                     logger.info(f"[TRIGGER_SERVICE] Trigger_id={trigger.id} is due, type={trigger.trigger_type}")

#                     if USE_GMAIL_NODE_FOR_FETCH:
#                         _execute_workflow_with_node_fetch(session, trigger)
#                     else:
#                         events = strategy.fetch_events(session)
#                         if not events:
#                             logger.info(f"[TRIGGER_SERVICE] No new events for trigger_id={trigger.id}")
#                             continue

#                         _execute_workflow_with_prefetched_events(session, trigger, events)

#                 except ValueError as ve:
#                     logger.error(f"[TRIGGER_SERVICE] Config error for trigger_id={trigger.id}: {ve}")
#                 except Exception as e:
#                     logger.exception(f"[TRIGGER_SERVICE] Error processing trigger_id={trigger.id}: {e}")

#         except SQLAlchemyError as db_err:
#             logger.error(f"[TRIGGER_SERVICE] Database error: {db_err}", exc_info=True)
#             if session:
#                 session.rollback()
#         except Exception as e:
#             logger.exception(f"[TRIGGER_SERVICE] Fatal error in main loop: {e}")
#         finally:
#             if session is not None:
#                 session.close()

#         time.sleep(TRIGGER_POLL_INTERVAL)
        
        




# services/trigger_service.py

import os
import time
import json
import redis
from datetime import datetime, timedelta
from typing import List, Dict, Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func, or_

from app.database.DatabaseOperationPostgreSQL import db_session
from app.models.workflow_trigger import WorkflowTrigger
from app.models.bot_diagram import BotDiagram
from engine.triggers.strategy_registry import TriggerStrategyRegistry
from logging_config import setup_logging
from engine.trigger_event_dedup import (
    is_event_already_processed,
    mark_event_as_processed,
)

logger = setup_logging("TriggerService", level="DEBUG")


# ---------------------------
# FLAGS / MODES
# ---------------------------
USE_GMAIL_NODE_FOR_FETCH = False
TRIGGER_POLL_INTERVAL = 60
REDIS_TRIGGER_QUEUE = "trigger_queue"
TRIGGER_CONSUMER_THREADS = max(1, int(os.environ.get("TRIGGER_CONSUMER_THREADS", "1")))


# ---------------------------
# STANDALONE REDIS CLIENT
# (No Flask app context needed)
# ---------------------------

def _get_redis_client() -> redis.Redis:
    """
    Build a Redis client directly from environment variables.
    Safe to call outside Flask app context (e.g. in trigger worker process).
    """
    return redis.Redis(
        host=os.environ.get("REDIS_HOST", "redis"),
        port=int(os.environ.get("REDIS_PORT", 6379)),
        db=int(os.environ.get("REDIS_DB", 0)),
        decode_responses=True,
    )


def enqueue_trigger(trigger_payload: Dict[str, Any]) -> None:
    """
    Push a trigger payload onto the Redis queue.
    Can be called from Flask routes (no app context issue since we use env vars).
    """
    client = _get_redis_client()
    client.rpush(REDIS_TRIGGER_QUEUE, json.dumps(trigger_payload))
    logger.info(
        "[QUEUE] job queued trigger_id=%s workflow_id=%s trigger_node_id=%s",
        trigger_payload.get("trigger_id"),
        trigger_payload.get("flow_id"),
        trigger_payload.get("trigger_node_id"),
    )


def _dequeue_trigger(client: redis.Redis, timeout: int = 0) -> Dict[str, Any] | None:
    """
    Blocking pop from the Redis queue.
    Returns parsed payload or None on timeout.
    """
    result = client.blpop(REDIS_TRIGGER_QUEUE, timeout=timeout)
    if result is None:
        return None
    _, data = result
    return json.loads(data)


# ---------------------------
# HELPERS
# ---------------------------

def _build_strategy(trigger: WorkflowTrigger):
    strategy_cls = TriggerStrategyRegistry.get(trigger.trigger_type)
    if not strategy_cls:
        raise ValueError(f"No strategy registered for {trigger.trigger_type}")
    return strategy_cls(trigger)


def _load_latest_workflow_for_bot(
    session,
    diagram_id: int,
    tenant_id: int | None = None,
    trigger_bot_id: int | None = None,
) -> Dict[str, Any]:
    logger.info(
        "[FLOW_TRACE][TRIGGER_WORKER][DIAGRAM_LOAD_REQUEST] diagram_id=%s tenant_id=%s bot_id=%s",
        diagram_id,
        tenant_id,
        trigger_bot_id,
    )
    query = session.query(BotDiagram).filter(
        BotDiagram.diagram_id == diagram_id,
        BotDiagram.del_flg.is_(False),
        func.lower(func.coalesce(BotDiagram.status, "")) != "deleted",
    )
    if tenant_id is not None:
        query = query.filter(BotDiagram.tenant_id == tenant_id)
    if trigger_bot_id is not None:
        # Prefer exact bot binding; allow legacy null bot_id rows.
        query = query.filter(
            or_(BotDiagram.bot_id == trigger_bot_id, BotDiagram.bot_id.is_(None))
        )

    diagram = query.first()

    if not diagram:
        raise ValueError(
            f"No workflow diagram found for diagram_id={diagram_id}, "
            f"tenant_id={tenant_id}, bot_id={trigger_bot_id}"
        )

    logger.info(
        "[FLOW_TRACE][TRIGGER_WORKER][DIAGRAM_SELECTED] diagram_id=%s tenant_id=%s trigger_bot_id=%s db_bot_id=%s status=%s del_flg=%s",
        diagram.diagram_id,
        diagram.tenant_id,
        trigger_bot_id,
        diagram.bot_id,
        getattr(diagram, "status", None),
        getattr(diagram, "del_flg", None),
    )

    if diagram.bot_id is None and trigger_bot_id is not None:
        logger.info(
            "[TRIGGER_SERVICE_BINDING] diagram_id=%s has null bot_id; using trigger bot_id=%s at runtime only",
            diagram_id,
            trigger_bot_id,
        )

    return json.loads(diagram.diagram_json)


# ---------------------------
# EXECUTION MODES
# ---------------------------

def _execute_workflow_with_node_fetch(session, trigger: WorkflowTrigger) -> None:
    """
    MODE A: WorkflowExecutor runs normally; GmailTriggerNode handles fetching.
    """
    from engine.workflow_executor import WorkflowExecutor

    bot_id = trigger.bot_id
    tenant_id = trigger.tenant_id
    flow_id = trigger.flow_id

    logger.info(f"[MODE_A] Executing workflow for trigger_id={trigger.id}, bot_id={bot_id}")

    workflow_json = _load_latest_workflow_for_bot(
        session,
        flow_id,
        tenant_id,
        bot_id,
    )
    workflow_json.update({
        "bot_id": trigger.bot_id,
        "tenant_id": trigger.tenant_id,
        "trigger_id": trigger.id,
        "trigger_type": trigger.trigger_type,
        "diagram_id": trigger.flow_id,
    })

    trigger_data = {
        trigger.trigger_node_id: {"tenant_id": tenant_id}
    }

    executor = WorkflowExecutor(workflow_json)
    result = executor.execute(trigger_data=trigger_data, return_context=True)

    logger.info(
        f"[MODE_A] Workflow completed for trigger_id={trigger.id}, "
        f"executed_nodes={result.executed_nodes}, status={result.to_dict().get('status')}"
    )


def _execute_workflow_with_prefetched_events(
    session,
    trigger: WorkflowTrigger,
    events: List[Dict[str, Any]],
    runtime_fields: Dict[str, Any] | None = None,
) -> None:
    """
    MODE B: Execute workflow with prefetched events + DB-backed deduplication.
    """
    from engine.workflow_executor import WorkflowExecutor

    bot_id = trigger.bot_id
    flow_id = trigger.flow_id
    tenant_id = trigger.tenant_id

    # ── 1. DEDUP ──────────────────────────────────────────
    def _event_dedup_id(event: Dict[str, Any]) -> str:
        metadata = event.get("metadata") or {}
        return str(metadata.get("message_id") or metadata.get("event_id") or "").strip()

    filtered_events = []
    for e in events:
        event_id = _event_dedup_id(e)
        if not event_id:
            continue
        if is_event_already_processed(
            session=session,
            tenant_id=tenant_id,
            trigger_id=trigger.id,
            event_id=event_id,
        ):
            logger.info(f"[DEDUP] Skipping event trigger_id={trigger.id}, event_id={event_id}")
            continue
        filtered_events.append(e)

    if not filtered_events:
        logger.info(f"[MODE_B] No new events after dedup for trigger_id={trigger.id}")
        return

    # ── 2. LOAD WORKFLOW ──────────────────────────────────
    workflow_json = _load_latest_workflow_for_bot(
        session,
        flow_id,
        tenant_id,
        bot_id,
    )
    workflow_json.update({
        "bot_id": trigger.bot_id,
        "tenant_id": tenant_id,
        "trigger_id": trigger.id,
        "trigger_type": trigger.trigger_type,
        "diagram_id": trigger.flow_id,
    })

    trigger_payload = {
        "tenant_id": tenant_id,
        "prefetched_events": filtered_events,
    }
    if isinstance(runtime_fields, dict):
        trigger_payload.update(runtime_fields)

    trigger_data = {
        trigger.trigger_node_id: trigger_payload
    }
    logger.info(
        "[FLOW_TRACE][TRIGGER_WORKER][EXECUTE_PREP] trigger_id=%s trigger_node_id=%s flow_id=%s tenant_id=%s bot_id=%s event_count=%s runtime_keys=%s",
        trigger.id,
        trigger.trigger_node_id,
        flow_id,
        tenant_id,
        bot_id,
        len(filtered_events),
        list((runtime_fields or {}).keys()) if isinstance(runtime_fields, dict) else [],
    )

    logger.info(
        "[WORKFLOW] resolved workflow_id=%s trigger_id=%s trigger_node_id=%s",
        trigger.flow_id,
        trigger.id,
        trigger.trigger_node_id,
    )
    logger.info(f"[MODE_B] Executing workflow with {len(filtered_events)} event(s) for trigger_id={trigger.id}")
    logger.info("[WORKFLOW] started workflow_id=%s trigger_id=%s", trigger.flow_id, trigger.id)

    # ── 3. EXECUTE ────────────────────────────────────────
    executor = WorkflowExecutor(workflow_json)
    executor.session_ref = session

    try:
        result = executor.execute(trigger_data=trigger_data, return_context=True)
    except Exception:
        logger.exception(f"[MODE_B] Workflow execution failed for trigger_id={trigger.id}")
        session.rollback()
        raise

    # ── 4. MARK PROCESSED ─────────────────────────────────
    for e in filtered_events:
        event_id = _event_dedup_id(e)
        if not event_id:
            continue
        mark_event_as_processed(
            session=session,
            tenant_id=tenant_id,
            trigger_id=trigger.id,
            event_id=event_id,
            event_source=e.get("source", trigger.trigger_type or "trigger"),
        )

    # ── 5. FINALIZE ───────────────────────────────────────
    finalize_fn = getattr(executor, "finalize_execution_record", None)
    if callable(finalize_fn):
        finalize_fn(result)

    session.commit()
    logger.info(
        f"[MODE_B] Completed & marked {len(filtered_events)} event(s) processed "
        f"for trigger_id={trigger.id}"
    )


# ---------------------------
# REDIS QUEUE CONSUMER
# ---------------------------

def _process_trigger_payload(payload: Dict[str, Any]) -> None:
    """
    Process a single trigger payload popped from Redis.

    Expected payload shape (produced by enqueue_trigger):
        {
            "trigger_id": <int>,   # look up from DB, or pass full data
            ...
        }

    The worker re-queries the DB so we always act on fresh state.
    """
    trigger_id = payload.get("trigger_id")
    if not trigger_id:
        logger.warning(f"[REDIS_WORKER] Payload missing trigger_id, skipping: {payload}")
        return

    session = None
    try:
        logger.info(
            "[FLOW_TRACE][TRIGGER_WORKER][PAYLOAD_RECEIVED] keys=%s trigger_id=%s flow_id=%s bot_id=%s tenant_id=%s trigger_node_id=%s",
            list(payload.keys()),
            payload.get("trigger_id"),
            payload.get("flow_id"),
            payload.get("bot_id"),
            payload.get("tenant_id"),
            payload.get("trigger_node_id"),
        )
        session = next(db_session())

        trigger: WorkflowTrigger | None = (
            session.query(WorkflowTrigger)
            .filter_by(id=trigger_id, status="active")
            .first()
        )

        if not trigger:
            logger.warning(f"[REDIS_WORKER] No active trigger found for trigger_id={trigger_id}")
            return

        logger.info(
            "[WORKFLOW] resolved workflow_id=%s trigger_id=%s trigger_node_id=%s",
            trigger.flow_id,
            trigger.id,
            trigger.trigger_node_id,
        )

        # Webhook-driven payloads can include already parsed events.
        prefetched_events = payload.get("prefetched_events")
        runtime_fields = payload.get("input_data")
        if isinstance(prefetched_events, list):
            _execute_workflow_with_prefetched_events(
                session,
                trigger,
                prefetched_events,
                runtime_fields=runtime_fields if isinstance(runtime_fields, dict) else None,
            )
            return

        strategy = _build_strategy(trigger)

        if USE_GMAIL_NODE_FOR_FETCH:
            _execute_workflow_with_node_fetch(session, trigger)
        else:
            events = strategy.fetch_events(session)
            if not events:
                logger.info(f"[REDIS_WORKER] No new events for trigger_id={trigger_id}")
                return
            _execute_workflow_with_prefetched_events(session, trigger, events)

    except ValueError as ve:
        logger.error(f"[REDIS_WORKER] Config error for trigger_id={trigger_id}: {ve}")
    except SQLAlchemyError as db_err:
        logger.error(f"[REDIS_WORKER] DB error for trigger_id={trigger_id}: {db_err}", exc_info=True)
        if session:
            session.rollback()
    except Exception:
        logger.exception(f"[REDIS_WORKER] Unexpected error for trigger_id={trigger_id}")
        if session:
            session.rollback()
    finally:
        if session:
            session.close()


def _run_redis_consumer() -> None:
    """
    Blocking Redis queue consumer.
    Runs in its own thread (started by start_trigger_service).
    Uses blpop with a timeout so the thread can be interrupted cleanly.
    """
    import threading
    logger.info("[REDIS_CONSUMER] Starting Redis queue consumer thread")
    client = _get_redis_client()

    while not getattr(threading.current_thread(), "_stop_event", None):
        try:
            # timeout=5 means blpop returns None every 5 s if queue is empty,
            # allowing the loop to check for shutdown signals.
            payload = _dequeue_trigger(client, timeout=5)
            if payload is None:
                continue  # queue was empty, loop again
            logger.info(
                "[QUEUE] dequeued trigger_id=%s workflow_id=%s trigger_node_id=%s",
                payload.get("trigger_id"),
                payload.get("flow_id"),
                payload.get("trigger_node_id"),
            )
            _process_trigger_payload(payload)
        except redis.exceptions.ConnectionError as e:
            logger.error(f"[REDIS_CONSUMER] Redis connection error: {e}. Retrying in 5s…")
            time.sleep(5)
            client = _get_redis_client()  # reconnect
        except Exception:
            logger.exception("[REDIS_CONSUMER] Unexpected error in consumer loop")
            time.sleep(1)


# ---------------------------
# MAIN POLLING LOOP
# ---------------------------

def start_trigger_service() -> None:
    """
    1. Starts a background thread that consumes on-demand triggers from Redis.
    2. Runs the original time-based polling loop on the main thread.

    The two mechanisms are complementary:
    - Redis consumer  → instant execution when something enqueues a trigger.
    - Polling loop    → scheduled / periodic trigger checks (every 60 s).
    """
    import threading

    logger.info("🚀 TriggerService starting (Redis consumer + polling loop)")

    # ── Start Redis consumer threads ──────────────────────
    consumer_threads = []
    for i in range(TRIGGER_CONSUMER_THREADS):
        consumer_thread = threading.Thread(
            target=_run_redis_consumer,
            name=f"redis-trigger-consumer-{i + 1}",
            daemon=True,   # dies automatically when the main process exits
        )
        consumer_thread.start()
        consumer_threads.append(consumer_thread)

    logger.info(
        "[TRIGGER_SERVICE] Redis consumer threads started count=%s",
        TRIGGER_CONSUMER_THREADS,
    )

    # ── Polling loop (main thread) ────────────────────────
    while True:
        session = None
        try:
            now = datetime.now()
            session = next(db_session())

            triggers: List[WorkflowTrigger] = (
                session.query(WorkflowTrigger)
                .filter_by(status="active")
                .all()
            )

            logger.debug(f"[TRIGGER_SERVICE] Found {len(triggers)} active trigger(s)")

            for trigger in triggers:
                try:
                    # Queue-driven triggers are executed via webhook enqueue path.
                    if trigger.trigger_type in {"whatsapp", "webhook", "slack"}:
                        continue

                    strategy = _build_strategy(trigger)

                    if not strategy.should_run(now):
                        logger.debug(f"[TRIGGER_SERVICE] Trigger_id={trigger.id} not due yet")
                        continue

                    logger.info(
                        f"[TRIGGER_SERVICE] Trigger_id={trigger.id} is due, "
                        f"type={trigger.trigger_type}"
                    )

                    if USE_GMAIL_NODE_FOR_FETCH:
                        _execute_workflow_with_node_fetch(session, trigger)
                    else:
                        events = strategy.fetch_events(session)
                        if not events:
                            logger.info(f"[TRIGGER_SERVICE] No new events for trigger_id={trigger.id}")
                            continue
                        _execute_workflow_with_prefetched_events(session, trigger, events)

                except ValueError as ve:
                    logger.error(f"[TRIGGER_SERVICE] Config error for trigger_id={trigger.id}: {ve}")
                except Exception:
                    logger.exception(f"[TRIGGER_SERVICE] Error processing trigger_id={trigger.id}")

        except SQLAlchemyError as db_err:
            logger.error(f"[TRIGGER_SERVICE] Database error: {db_err}", exc_info=True)
            if session:
                session.rollback()
        except Exception:
            logger.exception("[TRIGGER_SERVICE] Fatal error in main loop")
        finally:
            if session is not None:
                session.close()

        # ── Gmail wait-state tick ─────────────────────────
        try:
            _tick_gmail_wait_states()
        except Exception:
            logger.exception("[TRIGGER_SERVICE] Error in gmail wait-state tick")

        time.sleep(TRIGGER_POLL_INTERVAL)


# ---------------------------
# GMAIL WAIT-STATE TICKER
# ---------------------------

GMAIL_RECHECK_MINUTES = 5


def _tick_gmail_wait_states() -> None:
    """
    Check gmail_thread wait states that are due for polling.
    For each: query Gmail API for replies. Resume on reply or timeout.
    """
    from app.models.workflow_wait_state import WorkflowWaitState
    from engine.workflow_executor import WorkflowExecutor

    session = None
    try:
        session = next(db_session())
        now = datetime.utcnow()

        due_states = (
            session.query(WorkflowWaitState)
            .filter(
                WorkflowWaitState.status == "waiting",
                WorkflowWaitState.tracking_type == "gmail_thread",
                WorkflowWaitState.next_poll_at <= now,
            )
            .all()
        )

        if not due_states:
            return

        logger.info("[GMAIL_TICK] Found %d due gmail_thread wait state(s)", len(due_states))

        for ws in due_states:
            try:
                _check_gmail_wait_state(session, ws, now)
            except Exception:
                logger.exception(
                    "[GMAIL_TICK] Error checking wait_state id=%s thread=%s",
                    ws.id, ws.tracking_key,
                )
        session.commit()
    except Exception:
        logger.exception("[GMAIL_TICK] Fatal error in tick loop")
        if session:
            session.rollback()
    finally:
        if session:
            session.close()


def _check_gmail_wait_state(session, ws, now: datetime) -> None:
    """Check a single gmail_thread wait state for reply or timeout."""
    from app.models.workflow_wait_state import WorkflowWaitState
    from engine.workflow_executor import WorkflowExecutor

    thread_id = ws.tracking_key
    tenant_id = int(ws.tenant_id)
    created_at = ws.created_at

    logger.info(
        "[GMAIL_TICK] Checking wait_state id=%s thread=%s tenant=%s",
        ws.id, thread_id, tenant_id,
    )

    reply = _find_gmail_reply(tenant_id, thread_id, created_at)

    if reply:
        logger.info(
            "[GMAIL_TICK] Reply found for wait_state id=%s from=%s",
            ws.id, reply.get("from", ""),
        )
        _resume_gmail_wait_state(session, ws, {
            "reply_received": True,
            "timed_out": False,
            "gmail_reply": reply,
        })
        return

    is_timed_out = ws.timeout_at and now >= ws.timeout_at
    if is_timed_out:
        logger.info("[GMAIL_TICK] Timeout for wait_state id=%s", ws.id)
        _resume_gmail_wait_state(session, ws, {
            "reply_received": False,
            "timed_out": True,
        })
        return

    next_check = now + timedelta(minutes=GMAIL_RECHECK_MINUTES)
    ws.next_poll_at = next_check
    ws.retry_count = (ws.retry_count or 0) + 1
    session.add(ws)
    logger.debug(
        "[GMAIL_TICK] No reply yet for wait_state id=%s, next_poll_at=%s",
        ws.id, next_check.isoformat(),
    )


def _find_gmail_reply(tenant_id: int, thread_id: str, since: datetime) -> dict | None:
    """Query Gmail API for new messages in thread from someone other than the sender."""
    try:
        from Tools.GmailTool import GmailTool

        gmail = GmailTool(tenant_id=tenant_id, auth_mode="manual")
        gmail.authenticate()
        if not gmail.service:
            logger.error("[GMAIL_TICK] Auth failed for tenant %s", tenant_id)
            return None

        messages = gmail.get_thread_messages(thread_id)
        if not messages:
            return None

        sender_email = (gmail.authenticated_email or "").lower().strip()

        for msg in messages:
            headers = {
                h["name"].lower(): h["value"]
                for h in msg.get("payload", {}).get("headers", [])
            }
            msg_from = (headers.get("from") or "").lower()
            msg_date_str = headers.get("date", "")

            if sender_email and sender_email in msg_from:
                continue

            msg_epoch_ms = int(msg.get("internalDate", 0))
            if msg_epoch_ms > 0:
                msg_time = datetime.utcfromtimestamp(msg_epoch_ms / 1000)
                if msg_time <= since:
                    continue

            return {
                "message_id": msg.get("id"),
                "thread_id": msg.get("threadId"),
                "from": headers.get("from", ""),
                "to": headers.get("to", ""),
                "subject": headers.get("subject", ""),
                "date": msg_date_str,
            }

        return None
    except Exception:
        logger.exception("[GMAIL_TICK] Error querying Gmail for thread %s", thread_id)
        return None


def _resume_gmail_wait_state(session, ws, event_payload: dict) -> None:
    """Load workflow and resume execution from the gmail wait state."""
    from engine.workflow_executor import WorkflowExecutor

    try:
        workflow_json = _load_latest_workflow_for_bot(
            session,
            int(ws.diagram_id),
            int(ws.tenant_id),
            int(ws.bot_id),
        )
        workflow_json.update({
            "bot_id": int(ws.bot_id),
            "tenant_id": int(ws.tenant_id),
            "diagram_id": int(ws.diagram_id),
            "trigger_id": ws.trigger_id,
        })

        executor = WorkflowExecutor(workflow_json)
        executor.session_ref = session

        result = executor.resume_from_wait_state(
            wait_state_id=ws.id,
            event_payload=event_payload,
        )

        if result is None:
            logger.info("[GMAIL_TICK] Wait state id=%s already claimed", ws.id)
        else:
            logger.info("[GMAIL_TICK] Resumed wait_state id=%s successfully", ws.id)

    except Exception:
        logger.exception("[GMAIL_TICK] Failed to resume wait_state id=%s", ws.id)

