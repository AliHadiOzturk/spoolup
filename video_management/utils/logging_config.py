"""Logging configuration for the video management system."""

import json
import logging
import os
import sys
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path
from typing import Optional


class JSONFormatter(logging.Formatter):
    """Formatter that outputs JSON structured logs."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        if hasattr(record, "extra"):
            log_data.update(record.extra)
        
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, default=str)


def setup_logging(
    log_level: str = "INFO",
    log_format: str = "text",
    log_dir: str = "logs",
    log_rotation_days: int = 30,
    enable_console: bool = True,
) -> None:
    """Set up structured logging for the application.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Output format ("text" or "json")
        log_dir: Directory for log files
        log_rotation_days: Number of days to keep logs
        enable_console: Whether to also log to console
    """
    # Create log directory
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    
    # Determine formatter
    if log_format.lower() == "json":
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    
    # Remove existing handlers
    root_logger.handlers = []
    
    # Main log file - all logs
    main_handler = TimedRotatingFileHandler(
        log_path / "vms.log",
        when="midnight",
        interval=1,
        backupCount=log_rotation_days,
    )
    main_handler.setFormatter(formatter)
    main_handler.setLevel(logging.DEBUG)
    root_logger.addHandler(main_handler)
    
    # Upload logs
    upload_handler = TimedRotatingFileHandler(
        log_path / "vms_uploads.log",
        when="midnight",
        interval=1,
        backupCount=log_rotation_days,
    )
    upload_handler.setFormatter(formatter)
    upload_handler.setLevel(logging.INFO)
    upload_logger = logging.getLogger("uploads")
    upload_logger.addHandler(upload_handler)
    upload_logger.setLevel(logging.INFO)
    
    # Processing logs
    processing_handler = TimedRotatingFileHandler(
        log_path / "vms_processing.log",
        when="midnight",
        interval=1,
        backupCount=log_rotation_days,
    )
    processing_handler.setFormatter(formatter)
    processing_handler.setLevel(logging.INFO)
    processing_logger = logging.getLogger("processing")
    processing_logger.addHandler(processing_handler)
    processing_logger.setLevel(logging.INFO)
    
    # API logs
    api_handler = TimedRotatingFileHandler(
        log_path / "vms_api.log",
        when="midnight",
        interval=1,
        backupCount=log_rotation_days,
    )
    api_handler.setFormatter(formatter)
    api_handler.setLevel(logging.INFO)
    api_logger = logging.getLogger("api")
    api_logger.addHandler(api_handler)
    api_logger.setLevel(logging.INFO)
    
    # Console handler
    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
        root_logger.addHandler(console_handler)
    
    # Reduce noise from third-party libraries
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    
    logging.getLogger(__name__).info(f"Logging configured: level={log_level}, format={log_format}")
