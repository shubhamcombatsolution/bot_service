"""
Build Tasks Manager for Knowledge Base background processing.
Provides persistent storage, progress tracking, and task history management.
"""

import json
import os
import threading
import uuid
from datetime import datetime
from typing import Optional, Dict, List, Any
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class BuildStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BuildTasksManager:
    """
    Manages background build tasks with persistent JSON file storage.
    Thread-safe for concurrent access.
    """
    
    def __init__(self, storage_path: str = None, max_completed_tasks: int = 100):
        """
        Initialize the BuildTasksManager.
        
        Args:
            storage_path: Path to JSON file for persistent storage
            max_completed_tasks: Maximum number of completed tasks to retain (default: 100)
        """
        if storage_path is None:
            # Default to a location within the bot_builder_service
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            storage_path = os.path.join(base_dir, 'data', 'build_tasks.json')
        
        self.storage_path = storage_path
        self.max_completed_tasks = max_completed_tasks
        self._lock = threading.RLock()
        self._tasks: Dict[str, Dict[str, Any]] = {}
        
        # Ensure storage directory exists
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        
        # Load existing tasks from storage
        self._load_tasks()
    
    def _load_tasks(self) -> None:
        """Load tasks from persistent storage."""
        try:
            if os.path.exists(self.storage_path):
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    self._tasks = json.load(f)
                logger.info(f"Loaded {len(self._tasks)} build tasks from storage")
            else:
                self._tasks = {}
                logger.info("No existing build tasks file found, starting fresh")
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading build tasks: {e}")
            self._tasks = {}
    
    def _reload_tasks(self) -> None:
        """Reload tasks from disk to get latest state across workers."""
        try:
            if os.path.exists(self.storage_path):
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    self._tasks = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error reloading build tasks: {e}")
    
    def _save_tasks(self) -> None:
        """Save tasks to persistent storage."""
        try:
            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump(self._tasks, f, indent=2, default=str)
        except IOError as e:
            logger.error(f"Error saving build tasks: {e}")
    
    def _cleanup_old_tasks(self) -> None:
        """Remove oldest completed tasks if exceeding max_completed_tasks."""
        completed_tasks = [
            (task_id, task) for task_id, task in self._tasks.items()
            if task.get('status') in [BuildStatus.COMPLETED.value, BuildStatus.FAILED.value, BuildStatus.CANCELLED.value]
        ]
        
        if len(completed_tasks) > self.max_completed_tasks:
            # Sort by completion time (oldest first)
            completed_tasks.sort(key=lambda x: x[1].get('completed_at', x[1].get('created_at', '')))
            
            # Remove oldest tasks
            tasks_to_remove = len(completed_tasks) - self.max_completed_tasks
            for i in range(tasks_to_remove):
                task_id = completed_tasks[i][0]
                del self._tasks[task_id]
                logger.debug(f"Removed old completed task: {task_id}")
    
    def create_task(
        self,
        tenant_id: int,
        knowledge_base_name: str,
        knowledge_base_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a new build task.
        
        Args:
            tenant_id: The tenant ID
            knowledge_base_name: Name of the knowledge base being built
            knowledge_base_id: Optional KB ID if already created in DB
            metadata: Optional additional metadata
        
        Returns:
            task_id: Unique identifier for the task
        """
        with self._lock:
            task_id = str(uuid.uuid4())
            
            task = {
                'task_id': task_id,
                'tenant_id': tenant_id,
                'knowledge_base_name': knowledge_base_name,
                'knowledge_base_id': knowledge_base_id,
                'status': BuildStatus.PENDING.value,
                'progress': 0,
                'current_step': 'Initializing...',
                'activity_log': [],
                'created_at': datetime.utcnow().isoformat(),
                'updated_at': datetime.utcnow().isoformat(),
                'started_at': None,
                'completed_at': None,
                'error_message': None,
                'metadata': metadata or {}
            }
            
            self._tasks[task_id] = task
            self._add_activity_log(task_id, 'Task created')
            self._save_tasks()
            
            logger.info(f"Created build task: {task_id} for KB: {knowledge_base_name}")
            return task_id
    
    def _add_activity_log(self, task_id: str, message: str) -> None:
        """Add an entry to the task's activity log."""
        if task_id in self._tasks:
            log_entry = {
                'timestamp': datetime.utcnow().isoformat(),
                'message': message
            }
            self._tasks[task_id]['activity_log'].append(log_entry)
            # Keep only last 50 log entries
            if len(self._tasks[task_id]['activity_log']) > 50:
                self._tasks[task_id]['activity_log'] = self._tasks[task_id]['activity_log'][-50:]
    
    def start_task(self, task_id: str) -> bool:
        """
        Mark a task as started/in-progress.
        
        Args:
            task_id: The task ID
        
        Returns:
            bool: True if successful, False if task not found
        """
        with self._lock:
            if task_id not in self._tasks:
                logger.warning(f"Task not found: {task_id}")
                return False
            
            self._tasks[task_id]['status'] = BuildStatus.IN_PROGRESS.value
            self._tasks[task_id]['started_at'] = datetime.utcnow().isoformat()
            self._tasks[task_id]['updated_at'] = datetime.utcnow().isoformat()
            self._add_activity_log(task_id, 'Build started')
            self._save_tasks()
            
            logger.info(f"Started build task: {task_id}")
            return True
    
    def update_progress(
        self,
        task_id: str,
        progress: int,
        current_step: str,
        log_message: Optional[str] = None
    ) -> bool:
        """
        Update task progress.
        
        Args:
            task_id: The task ID
            progress: Progress percentage (0-100)
            current_step: Description of current step
            log_message: Optional message to add to activity log
        
        Returns:
            bool: True if successful, False if task not found
        """
        with self._lock:
            if task_id not in self._tasks:
                logger.warning(f"Task not found: {task_id}")
                return False
            
            self._tasks[task_id]['progress'] = min(100, max(0, progress))
            self._tasks[task_id]['current_step'] = current_step
            self._tasks[task_id]['updated_at'] = datetime.utcnow().isoformat()
            
            if log_message:
                self._add_activity_log(task_id, log_message)
            
            self._save_tasks()
            return True
    
    def complete_task(
        self,
        task_id: str,
        knowledge_base_id: Optional[int] = None,
        success_message: str = "Build completed successfully",
        build_summary: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Mark a task as completed.
        
        Args:
            task_id: The task ID
            knowledge_base_id: Optional KB ID to update
            success_message: Success message for activity log
            build_summary: Optional summary of build results (chunks, sources, etc.)
        
        Returns:
            bool: True if successful, False if task not found
        """
        with self._lock:
            if task_id not in self._tasks:
                logger.warning(f"Task not found: {task_id}")
                return False
            
            self._tasks[task_id]['status'] = BuildStatus.COMPLETED.value
            self._tasks[task_id]['progress'] = 100
            self._tasks[task_id]['current_step'] = 'Completed'
            self._tasks[task_id]['completed_at'] = datetime.utcnow().isoformat()
            self._tasks[task_id]['updated_at'] = datetime.utcnow().isoformat()
            
            if knowledge_base_id:
                self._tasks[task_id]['knowledge_base_id'] = knowledge_base_id
            
            if build_summary:
                self._tasks[task_id]['build_summary'] = build_summary
            
            self._add_activity_log(task_id, success_message)
            self._cleanup_old_tasks()
            self._save_tasks()
            
            logger.info(f"Completed build task: {task_id}")
            return True
    
    def fail_task(
        self,
        task_id: str,
        error_message: str
    ) -> bool:
        """
        Mark a task as failed.
        
        Args:
            task_id: The task ID
            error_message: Description of the error
        
        Returns:
            bool: True if successful, False if task not found
        """
        with self._lock:
            if task_id not in self._tasks:
                logger.warning(f"Task not found: {task_id}")
                return False
            
            self._tasks[task_id]['status'] = BuildStatus.FAILED.value
            self._tasks[task_id]['current_step'] = 'Failed'
            self._tasks[task_id]['error_message'] = error_message
            self._tasks[task_id]['completed_at'] = datetime.utcnow().isoformat()
            self._tasks[task_id]['updated_at'] = datetime.utcnow().isoformat()
            
            self._add_activity_log(task_id, f'Build failed: {error_message}')
            self._cleanup_old_tasks()
            self._save_tasks()
            
            logger.error(f"Failed build task: {task_id} - {error_message}")
            return True
    
    def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a pending or in-progress task.
        
        Args:
            task_id: The task ID
        
        Returns:
            bool: True if successful, False if task not found or already completed
        """
        with self._lock:
            if task_id not in self._tasks:
                logger.warning(f"Task not found: {task_id}")
                return False
            
            current_status = self._tasks[task_id]['status']
            if current_status in [BuildStatus.COMPLETED.value, BuildStatus.FAILED.value]:
                logger.warning(f"Cannot cancel task {task_id} in status: {current_status}")
                return False
            
            self._tasks[task_id]['status'] = BuildStatus.CANCELLED.value
            self._tasks[task_id]['current_step'] = 'Cancelled'
            self._tasks[task_id]['completed_at'] = datetime.utcnow().isoformat()
            self._tasks[task_id]['updated_at'] = datetime.utcnow().isoformat()
            
            self._add_activity_log(task_id, 'Build cancelled by user')
            self._save_tasks()
            
            logger.info(f"Cancelled build task: {task_id}")
            return True
    
    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a task by ID.
        
        Args:
            task_id: The task ID
        
        Returns:
            Task data or None if not found
        """
        with self._lock:
            self._reload_tasks()  # Reload from disk to get latest state across workers
            return self._tasks.get(task_id)
    
    def get_tasks_by_tenant(self, tenant_id: int) -> List[Dict[str, Any]]:
        """
        Get all tasks for a specific tenant.
        
        Args:
            tenant_id: The tenant ID
        
        Returns:
            List of tasks for the tenant
        """
        with self._lock:
            self._reload_tasks()  # Reload from disk to get latest state across workers
            tasks = [
                task for task in self._tasks.values()
                if task.get('tenant_id') == tenant_id
            ]
            # Sort by created_at descending (newest first)
            tasks.sort(key=lambda x: x.get('created_at', ''), reverse=True)
            return tasks
    
    def get_active_tasks(self, tenant_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get all active (pending or in-progress) tasks.
        
        Args:
            tenant_id: Optional tenant ID filter
        
        Returns:
            List of active tasks
        """
        with self._lock:
            self._reload_tasks()  # Reload from disk to get latest state across workers
            active_statuses = [BuildStatus.PENDING.value, BuildStatus.IN_PROGRESS.value]
            tasks = [
                task for task in self._tasks.values()
                if task.get('status') in active_statuses
                and (tenant_id is None or task.get('tenant_id') == tenant_id)
            ]
            tasks.sort(key=lambda x: x.get('created_at', ''), reverse=True)
            return tasks
    
    def get_all_tasks(
        self,
        tenant_id: Optional[int] = None,
        limit: int = 50,
        include_active: bool = True
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get all tasks grouped by status.
        
        Args:
            tenant_id: Optional tenant ID filter
            limit: Maximum number of completed tasks to return
            include_active: Whether to include active tasks
        
        Returns:
            Dictionary with 'active' and 'completed' task lists
        """
        with self._lock:
            self._reload_tasks()  # Reload from disk to get latest state across workers
            active_statuses = [BuildStatus.PENDING.value, BuildStatus.IN_PROGRESS.value]
            completed_statuses = [BuildStatus.COMPLETED.value, BuildStatus.FAILED.value, BuildStatus.CANCELLED.value]
            
            result = {'active': [], 'completed': []}
            
            for task in self._tasks.values():
                if tenant_id is not None and task.get('tenant_id') != tenant_id:
                    continue
                
                status = task.get('status')
                if include_active and status in active_statuses:
                    result['active'].append(task)
                elif status in completed_statuses:
                    result['completed'].append(task)
            
            # Sort active by created_at ascending (oldest first - queue order)
            result['active'].sort(key=lambda x: x.get('created_at', ''))
            
            # Sort completed by completed_at descending (newest first)
            result['completed'].sort(key=lambda x: x.get('completed_at', ''), reverse=True)
            
            # Limit completed tasks
            result['completed'] = result['completed'][:limit]
            
            return result
    
    def set_knowledge_base_id(self, task_id: str, knowledge_base_id: int) -> bool:
        """
        Update the knowledge_base_id for a task.
        
        Args:
            task_id: The task ID
            knowledge_base_id: The KB ID to set
        
        Returns:
            bool: True if successful, False if task not found
        """
        with self._lock:
            if task_id not in self._tasks:
                return False
            
            self._tasks[task_id]['knowledge_base_id'] = knowledge_base_id
            self._tasks[task_id]['updated_at'] = datetime.utcnow().isoformat()
            self._save_tasks()
            return True


# Singleton instance
_build_tasks_manager: Optional[BuildTasksManager] = None


def get_build_tasks_manager() -> BuildTasksManager:
    """Get the singleton BuildTasksManager instance."""
    global _build_tasks_manager
    if _build_tasks_manager is None:
        _build_tasks_manager = BuildTasksManager()
    return _build_tasks_manager

