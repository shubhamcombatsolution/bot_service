# from queue import Queue, Full
# from threading import Thread
# from datetime import datetime
# import logging

# from app.database.DatabaseOperationPostgreSQL import db_session
# from app.models.workflow_node_logs import WorkflowNodeLog

# logger = logging.getLogger("workflow_log_service")


# class WorkflowLogService:
#     """
#     In-process async log writer.
#     Non-blocking, fire-and-forget.
#     """

#     _queue = Queue(maxsize=10000)
#     _started = False

#     @classmethod
#     def start(cls):
#         """Start background writer thread once per process"""
#         if cls._started:
#             return

#         cls._started = True
#         t = Thread(target=cls._writer, daemon=True)
#         t.start()
#         logger.info("[WorkflowLogService] Async log writer started")

#     @classmethod
#     def emit(cls, **kwargs):
#         """
#         Non-blocking log emit.
#         If queue is full, log is dropped (execution must continue).
#         """
#         try:
#             cls._queue.put_nowait(WorkflowNodeLog(**kwargs))
#         except Full:
#             logger.warning("[WorkflowLogService] Log queue full, dropping log")

#     @classmethod
#     def _writer(cls):
#         """Background DB writer"""
#         session = next(db_session())

#         while True:
#             log_row = cls._queue.get()

#             try:
#                 session.add(log_row)
#                 session.commit()
#             except Exception as e:
#                 session.rollback()
#                 logger.exception("Failed to write workflow log")



from queue import Queue, Full, Empty
from threading import Thread, Lock
from datetime import datetime
import logging
import atexit

from app.database.DatabaseOperationPostgreSQL import db_session
from app.models.workflow_node_logs import WorkflowNodeLog

logger = logging.getLogger("workflow_log_service")


class WorkflowLogService:
    """
    Production-grade async log writer with:
    - Batch writes for performance
    - Graceful shutdown
    - Thread-safe initialization
    - Session lifecycle management
    - Error recovery
    """

    _queue = Queue(maxsize=10000)
    _started = False
    _shutdown = False
    _start_lock = Lock()
    _writer_thread = None
    
    # Configuration
    BATCH_SIZE = 100
    BATCH_TIMEOUT_SEC = 5  # Flush batch after this time
    QUEUE_POLL_TIMEOUT = 1
    
    ALLOWED_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}

    @classmethod
    def start(cls):
        """Start background writer thread (called once per process)"""
        with cls._start_lock:
            if cls._started:
                return

            cls._started = True
            cls._writer_thread = Thread(target=cls._writer, daemon=False, name="WorkflowLogWriter")
            cls._writer_thread.start()
            
            # Register shutdown handler
            atexit.register(cls.shutdown)
            
            logger.info("[WorkflowLogService] Started with batch_size=%d", cls.BATCH_SIZE)

    @classmethod
    def emit(cls, **kwargs):
        """
        Non-blocking log emit.
        
        Args:
            run_id (int): Workflow run ID
            node_id (str): Node identifier
            node_type (str): Node type
            event_type (str): started|completed|failed|cached|retry
            status (str): running|completed|failed
            message (str, optional): Human-readable message
            payload (dict, optional): Structured data (inputs/outputs/errors)
            started_at (datetime, optional)
            completed_at (datetime, optional)
            duration_ms (float, optional)
        """
        if not cls._started:
            cls.start()
        
        try:
            level = kwargs.get("log_level", "INFO")
            if level not in cls.ALLOWED_LEVELS:
                kwargs["log_level"] = "INFO"
            cls._queue.put_nowait(WorkflowNodeLog(**kwargs))
        except Full:
            logger.warning("[WorkflowLogService] Queue full, dropping log for node_id=%s", kwargs.get("node_id"))

    @classmethod
    def create_node_log(cls, **kwargs):
        """Backward-compatible explicit API for node log creation."""
        cls.emit(**kwargs)

    @classmethod
    def shutdown(cls, timeout=10):
        """
        Graceful shutdown: flush remaining logs before exit
        
        Args:
            timeout (int): Max seconds to wait for queue to drain
        """
        if not cls._started or cls._shutdown:
            return
        
        logger.info("[WorkflowLogService] Shutting down, flushing queue...")
        cls._shutdown = True
        
        if cls._writer_thread:
            cls._writer_thread.join(timeout=timeout)
        
        remaining = cls._queue.qsize()
        if remaining > 0:
            logger.warning("[WorkflowLogService] Shutdown with %d logs remaining", remaining)
        else:
            logger.info("[WorkflowLogService] Clean shutdown")

    @classmethod
    def _writer(cls):
        """
        Background DB writer with:
        - Batching for performance
        - Time-based flush
        - Error recovery
        - Proper session lifecycle
        """
        batch = []
        last_flush = datetime.utcnow()
        
        while not cls._shutdown or not cls._queue.empty():
            try:
                # Get log with timeout
                log_row = cls._queue.get(timeout=cls.QUEUE_POLL_TIMEOUT)
                batch.append(log_row)
                
                # Flush conditions
                time_elapsed = (datetime.utcnow() - last_flush).total_seconds()
                should_flush = (
                    len(batch) >= cls.BATCH_SIZE or
                    cls._queue.empty() or
                    time_elapsed >= cls.BATCH_TIMEOUT_SEC
                )
                
                if should_flush:
                    cls._flush_batch(batch)
                    batch.clear()
                    last_flush = datetime.utcnow()
                
            except Empty:
                # Timeout - flush partial batch if exists
                if batch:
                    cls._flush_batch(batch)
                    batch.clear()
                    last_flush = datetime.utcnow()
                continue
            
            except Exception as e:
                logger.exception("[WorkflowLogService] Unexpected error in writer loop")
                batch.clear()  # Drop corrupted batch
        
        # Final flush on shutdown
        if batch:
            cls._flush_batch(batch)

    @classmethod
    def _flush_batch(cls, batch):
        """
        Write batch to database with proper session management
        
        Args:
            batch (list): List of WorkflowNodeLog objects
        """
        if not batch:
            return
        
        session = None
        try:
            session = next(db_session())
            session.bulk_save_objects(batch)
            session.commit()
            
            logger.debug("[WorkflowLogService] Flushed %d logs", len(batch))
            
        except Exception as e:
            if session:
                session.rollback()
            logger.exception("[WorkflowLogService] Failed to write batch of %d logs", len(batch))
            
        finally:
            if session:
                session.close()



class LogEmitter:
    """Convenience class for structured log emission"""
    
    @staticmethod
    def node_started(run_id, node_id, node_type, inputs=None):
        WorkflowLogService.create_node_log(
            run_id=run_id,
            node_id=node_id,
            node_type=node_type,
            event_type="started",
            status="running",
            message="Node execution started",
            started_at=datetime.utcnow(),
            payload={"inputs": inputs} if inputs else None,
            log_level="INFO"
        )
    
    @staticmethod
    def node_completed(run_id, node_id, node_type, outputs=None, duration_ms=None, started_at=None):
        completed_at = datetime.utcnow()
        
        WorkflowLogService.create_node_log(
            run_id=run_id,
            node_id=node_id,
            node_type=node_type,
            event_type="completed",
            status="completed",
            message="Node execution completed",
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms or (completed_at - started_at).total_seconds() * 1000 if started_at else None,
            payload={"outputs": outputs} if outputs else None,
            log_level="INFO"
        )
    
    @staticmethod
    def node_failed(run_id, node_id, node_type, error, duration_ms=None, started_at=None, retry_count=0):
        completed_at = datetime.utcnow()
        
        WorkflowLogService.create_node_log(
            run_id=run_id,
            node_id=node_id,
            node_type=node_type,
            event_type="failed",
            status="failed",
            message=str(error),
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms or (completed_at - started_at).total_seconds() * 1000 if started_at else None,
            payload={"error": str(error), "retry_count": retry_count},
            log_level="ERROR"
        )
    
    @staticmethod
    def node_cached(run_id, node_id, node_type, cache_key):
        WorkflowLogService.create_node_log(
            run_id=run_id,
            node_id=node_id,
            node_type=node_type,
            event_type="cached",
            status="completed",
            message="Cache hit",
            duration_ms=0,
            payload={"cache_key": cache_key},
            log_level="INFO"
        )
    
    @staticmethod
    def node_retry(run_id, node_id, node_type, attempt, max_retries, error):
        WorkflowLogService.create_node_log(
            run_id=run_id,
            node_id=node_id,
            node_type=node_type,
            event_type="retry",
            status="running",
            message=f"Retry {attempt}/{max_retries}",
            payload={"attempt": attempt, "max_retries": max_retries, "error": str(error)},
            log_level="WARNING"
        )
