"""Centralized logging configuration using Loguru with rotation, retention, and secret masking."""
import os
import re
import sys
from datetime import datetime
from loguru import logger

# Regex to sanitize sensitive API keys from logs
SECRET_PATTERN = re.compile(r"(sk-[a-zA-Z0-9_-]{10,}|AIzaSy[a-zA-Z0-9_-]{20,}|gsk_[a-zA-Z0-9_-]{10,})")


def mask_secrets(text: str) -> str:
    """Mask sensitive API keys in arbitrary text strings."""
    return SECRET_PATTERN.sub("[MASKED_API_KEY]", text)


def sanitize_secrets(record: dict) -> bool:
    """Filter to mask API keys and secrets from log messages."""
    msg = record["message"]
    if SECRET_PATTERN.search(msg):
        record["message"] = mask_secrets(msg)
    return True


def setup_logger(log_dir: str = "logs", level: str = "DEBUG") -> logger:
    """
    Configure and initialize Loguru logging for console and rotating file sinks.
    
    Log destinations:
    - logs/bug_fixer.log: General application log (rotation: 10 MB, retention: 7 days)
    - logs/debug.log: Deep diagnostic log with line numbers & function names
    - logs/runs/run_{timestamp}.log: Dedicated session log for current execution
    """
    # Remove default handler
    logger.remove()

    os.makedirs(log_dir, exist_ok=True)
    runs_dir = os.path.join(log_dir, "runs")
    os.makedirs(runs_dir, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    session_log_file = os.path.join(runs_dir, f"run_{timestamp}.log")
    main_log_file = os.path.join(log_dir, "bug_fixer.log")
    debug_log_file = os.path.join(log_dir, "debug.log")

    # 1. Main rotating file sink (INFO and above)
    logger.add(
        main_log_file,
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {name}:{function}:{line} - {message}",
        rotation="10 MB",
        retention="7 days",
        compression="zip",
        encoding="utf-8",
        filter=sanitize_secrets,
        enqueue=True
    )

    # 2. Detailed debug file sink (DEBUG and above)
    logger.add(
        debug_log_file,
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {name}:{function}:{line} - {message}",
        rotation="20 MB",
        retention="14 days",
        encoding="utf-8",
        filter=sanitize_secrets,
        enqueue=True
    )

    # 3. Dedicated per-run session file sink
    logger.add(
        session_log_file,
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {name}:{function}:{line} - {message}",
        encoding="utf-8",
        filter=sanitize_secrets,
        enqueue=True
    )

    logger.info(f"Logging initialized. Session log: {session_log_file}")
    return logger


# Initialize default logger instance
default_log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "logs")
app_logger = setup_logger(default_log_dir)

__all__ = ["app_logger", "setup_logger", "logger"]
