import logging
import os
import sys
from datetime import datetime
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
    group: str | None = None,          # NEW
    filename: str | None = None,
    max_size_mb: int = 5,
    use_date_folder: bool = False,     # NEW
):
    """
    Creates a logger with:
    logs/<group>/<date>/<name>.log

    - One log file per module
    - Rotates by size
    - No backups
    """

    if isinstance(level, str):
        level = logging.getLevelName(level.upper())

    # ---- Build directory path ----
    path_parts = [log_dir]

    if group:
        path_parts.append(group)

    if use_date_folder:
        path_parts.append(datetime.now().strftime("%Y-%m-%d"))

    final_log_dir = os.path.join(*path_parts)
    os.makedirs(final_log_dir, exist_ok=True)

    # ---- File name ----
    if filename is None:
        filename = f"{name}.log"

    log_path = os.path.join(final_log_dir, filename)

    formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)

    # ---- File Handler ----
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=max_size_mb * 1024 * 1024,
        backupCount=0,      # Only ONE file
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    # ---- Console Handler ----
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    # ---- Logger ----
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Prevent duplicate handlers
    if not logger.handlers:
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    logger.propagate = False
    return logger
