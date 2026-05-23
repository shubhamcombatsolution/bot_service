import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

import logging
from logging_config import setup_logging


logger = setup_logging("TriggerWorker", level="INFO")
# Just add project root to PATH if not already present
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
    
print("✔ PYTHONPATH Loaded:", sys.path)

from engine.triggers.trigger_service import start_trigger_service

if __name__ == "__main__":
    print("🔄 Trigger Worker Starting...")
    logger.info("[Trigger Worker] Starting the trigger service...")
    start_trigger_service()
    logger.info("[Trigger Worker] Trigger service stopped.")
