from abc import ABC, abstractmethod
from datetime import datetime
from sqlalchemy.orm import Session
from typing import List, Dict, Any
import logging
from engine import langgraph_urls

from engine.triggers.strategy_registry import TriggerStrategyRegistry


logger = logging.getLogger("TriggerStrategies")

CREDENTIALS_URL = langgraph_urls.GMAIL_CREDENTIALS_URL


# services/base_strategy.py


class BaseTriggerStrategy(ABC):
    trigger_type = None  # override in child

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.trigger_type:
            TriggerStrategyRegistry.register(cls.trigger_type, cls)

    def __init__(self, trigger_row):
        self.trigger = trigger_row


    @abstractmethod
    def should_run(self, now: datetime) -> bool:
        """Return True if this trigger should fire at 'now'."""
        pass

    @abstractmethod
    def fetch_events(self, db_session: Session) -> List[Dict[str, Any]]:
        """
        Fetch raw events (emails, webhook payloads, etc.)
        For Gmail: each event will look similar to GmailTriggerNode output item.
        """
        pass
