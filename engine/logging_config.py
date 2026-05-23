import logging
import os
import sys
from logging.handlers import RotatingFileHandler

LOG_FORMAT = (
    "[%(asctime)s] [%(levelname)s] [%(name)s] "
    "[%(filename)s:%(lineno)d] - %(message)s"
)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(
    name: str,
    level=logging.INFO,
    log_dir: str = "logs",
    filename: str | None = None,
    max_size_mb: int = 5,
):
    """
    Create a single log file per module.
    File overwrites when size exceeds limit. No backups are kept.
    """

    if isinstance(level, str):
        level = logging.getLevelName(level.upper())

    os.makedirs(log_dir, exist_ok=True)

    if filename is None:
        filename = f"{name}.log"

    log_path = os.path.join(log_dir, filename)

    formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)

    # ---- File Handler (Overwrites older logs) ----
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=max_size_mb * 1024 * 1024,
        backupCount=0,  # <---- THIS ENSURES ONLY ONE FILE EXISTS
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    # ---- Console Handler ----
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    # ---- Create Logger ----
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid duplicate handler registration
    if not logger.handlers:
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)

    logger.propagate = False

    return logger
