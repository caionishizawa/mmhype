"""
Logging configuration for the trading system.
"""
import logging
import sys
from pathlib import Path
import structlog
from structlog.processors import JSONRenderer
from structlog.stdlib import add_log_level, add_logger_name

from .config import LoggingConfig


def setup_logging(config: LoggingConfig):
    """
    Configure structlog for structured logging.

    Args:
        config: Logging configuration
    """
    # Create log directory if it doesn't exist
    if config.file_enabled:
        log_path = Path(config.file_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)

    # Configure standard logging
    log_level = getattr(logging, config.level.upper(), logging.INFO)

    # Create handlers
    handlers = []

    if config.console_enabled:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        handlers.append(console_handler)

    if config.file_enabled:
        file_handler = logging.FileHandler(config.file_path)
        file_handler.setLevel(log_level)
        handlers.append(file_handler)

    # Configure root logger
    logging.basicConfig(
        format="%(message)s",
        level=log_level,
        handlers=handlers,
    )

    # Configure structlog
    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if config.format == "json":
        processors.append(JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logger = structlog.get_logger(__name__)
    logger.info(
        "logging_configured",
        level=config.level,
        format=config.format,
        console_enabled=config.console_enabled,
        file_enabled=config.file_enabled,
    )
