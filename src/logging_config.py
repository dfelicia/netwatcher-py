"""
Centralized logging configuration for NetWatcher.

This module provides a single point of configuration for all logging in the
NetWatcher application, ensuring consistent formatting, handlers, and levels
across all modules.
"""

import logging
import sys
from typing import Optional

from . import config


class NetWatcherLogger:
    """Centralized logger configuration for NetWatcher."""

    _initialized = False
    _debug_enabled = False

    @classmethod
    def setup(cls, debug: bool = False, force_reinit: bool = False) -> None:
        """
        Set up centralized logging for the entire application.

        Args:
            debug: If True, enable DEBUG level logging
            force_reinit: If True, reinitialize even if already set up
        """
        if cls._initialized and not force_reinit:
            return

        # Clear any existing handlers to avoid duplication
        root_logger = logging.getLogger()
        if root_logger.hasHandlers():
            root_logger.handlers.clear()

        # Set up logging level
        cls._debug_enabled = debug
        log_level = logging.DEBUG if debug else logging.INFO
        root_logger.setLevel(log_level)

        # Create formatter
        formatter = logging.Formatter(config.LOG_FORMAT, datefmt=config.LOG_DATE_FORMAT)

        # Always add file handler
        cls._add_file_handler(root_logger, formatter)

        # Add console handler (for services, stdout/stderr are redirected so no duplication)
        cls._add_console_handler(root_logger, formatter)

        cls._initialized = True

        # Log the initialization
        logger = logging.getLogger(__name__)
        logger.debug(f"NetWatcher logging initialized (debug={'on' if debug else 'off'})")

    @classmethod
    def _add_file_handler(cls, logger: logging.Logger, formatter: logging.Formatter) -> None:
        """Add file handler for persistent logging."""
        try:
            # Ensure log directory exists
            config.LOG_DIR.mkdir(parents=True, exist_ok=True)

            file_handler = logging.FileHandler(config.LOG_FILE)
            file_handler.setFormatter(formatter)
            file_handler.setLevel(logging.DEBUG)  # File always gets debug
            logger.addHandler(file_handler)
        except Exception as e:
            # If file logging fails, at least log to console
            print(f"Warning: Could not set up file logging: {e}", file=sys.stderr)

    @classmethod
    def _add_console_handler(cls, logger: logging.Logger, formatter: logging.Formatter) -> None:
        """Add console handler for interactive feedback."""
        try:
            console_handler = logging.StreamHandler(sys.stderr)
            console_handler.setFormatter(formatter)
            # Console handler respects the debug setting
            console_handler.setLevel(logging.DEBUG if cls._debug_enabled else logging.INFO)
            logger.addHandler(console_handler)
        except Exception as e:
            print(f"Warning: Could not set up console logging: {e}", file=sys.stderr)

    @classmethod
    def get_logger(cls, name: Optional[str] = None) -> logging.Logger:
        """
        Get a logger instance, ensuring NetWatcher logging is initialized.

        Args:
            name: Logger name (typically __name__)

        Returns:
            Configured logger instance
        """
        if not cls._initialized:
            cls.setup()

        return logging.getLogger(name)

    @classmethod
    def is_debug_enabled(cls) -> bool:
        """Check if debug logging is currently enabled."""
        return cls._debug_enabled

    @classmethod
    def set_debug(cls, debug: bool) -> None:
        """
        Change debug level at runtime.

        Args:
            debug: If True, enable DEBUG level logging
        """
        if debug != cls._debug_enabled:
            cls.setup(debug=debug, force_reinit=True)


# Convenience functions for easy import
def setup_logging(debug: bool = False, force_reinit: bool = False) -> None:
    """Set up centralized logging. Wrapper for NetWatcherLogger.setup()."""
    NetWatcherLogger.setup(debug=debug, force_reinit=force_reinit)


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Get a logger instance. Wrapper for NetWatcherLogger.get_logger()."""
    return NetWatcherLogger.get_logger(name)


def is_debug_enabled() -> bool:
    """Check if debug logging is enabled. Wrapper for NetWatcherLogger.is_debug_enabled()."""
    return NetWatcherLogger.is_debug_enabled()


def set_debug(debug: bool) -> None:
    """Change debug level at runtime. Wrapper for NetWatcherLogger.set_debug()."""
    NetWatcherLogger.set_debug(debug)
