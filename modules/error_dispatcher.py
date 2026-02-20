"""Centralized error handling and dispatching for the application.

This module provides a singleton ErrorDispatcher that routes errors to appropriate
handlers based on severity level. It replaces scattered try/except blocks with
a consistent, centralized error management system.

Architecture:
- All errors bubble up from features → modules → tabs → app
- App can subscribe to errors and handle UI display
- Different severity levels (INFO, WARNING, ERROR, CRITICAL)
- Supports both synchronous and deferred error handling
"""

from __future__ import annotations

import logging
from typing import Callable, Optional
from enum import Enum
from datetime import datetime


class ErrorLevel(Enum):
    """Severity levels for error dispatch."""
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ErrorEvent:
    """Represents a single error event."""
    
    def __init__(
        self,
        level: ErrorLevel,
        message: str,
        context: str = "unknown",
        exception: Optional[Exception] = None,
        data: Optional[dict] = None,
    ) -> None:
        self.level = level
        self.message = message
        self.context = context
        self.exception = exception
        self.data = data or {}
        self.timestamp = datetime.now()
    
    def __str__(self) -> str:
        return f"[{self.level.value}] {self.context}: {self.message}"
    
    def to_dict(self) -> dict:
        """Convert to dictionary for logging/storage."""
        return {
            "level": self.level.value,
            "message": self.message,
            "context": self.context,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
            "exception_type": type(self.exception).__name__ if self.exception else None,
            "exception_message": str(self.exception) if self.exception else None,
        }


class ErrorDispatcher:
    """Centralized error dispatcher for the application.
    
    Manages error routing, filtering, and handler invocation.
    Implements singleton pattern to ensure single instance across app.
    
    Usage:
        dispatcher = ErrorDispatcher.get_instance()
        dispatcher.subscribe(ErrorLevel.ERROR, my_error_handler)
        dispatcher.emit(ErrorLevel.WARNING, "Operation failed", "module_name", exception=e)
    """
    
    _instance: Optional[ErrorDispatcher] = None
    
    def __init__(self) -> None:
        """Initialize error dispatcher with logging setup."""
        self._handlers: dict[ErrorLevel, list[Callable[[ErrorEvent], None]]] = {
            level: [] for level in ErrorLevel
        }
        self._error_history: list[ErrorEvent] = []
        self._max_history = 100
        self._logger = self._setup_logging()
    
    @classmethod
    def get_instance(cls) -> ErrorDispatcher:
        """Get or create singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def reset(cls) -> None:
        """Reset singleton (useful for testing)."""
        cls._instance = None
    
    def _setup_logging(self) -> logging.Logger:
        """Set up Python logging for error dispatch."""
        logger = logging.getLogger("HPGeGUI")
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.DEBUG)
        return logger
    
    def subscribe(
        self,
        level: ErrorLevel,
        handler: Callable[[ErrorEvent], None],
    ) -> None:
        """Subscribe a handler to errors of a specific level.
        
        Args:
            level: ErrorLevel to listen for
            handler: Callable that receives ErrorEvent
        """
        if handler not in self._handlers[level]:
            self._handlers[level].append(handler)
    
    def unsubscribe(
        self,
        level: ErrorLevel,
        handler: Callable[[ErrorEvent], None],
    ) -> None:
        """Unsubscribe a handler from a specific level."""
        if handler in self._handlers[level]:
            self._handlers[level].remove(handler)
    
    def emit(
        self,
        level: ErrorLevel,
        message: str,
        context: str = "unknown",
        exception: Optional[Exception] = None,
        data: Optional[dict] = None,
    ) -> ErrorEvent:
        """Emit an error event and invoke registered handlers.
        
        Args:
            level: ErrorLevel for this event
            message: Human-readable error message
            context: Where the error occurred (module/class name)
            exception: Optional exception object
            data: Optional dictionary with additional context
        
        Returns:
            The ErrorEvent that was emitted
        """
        event = ErrorEvent(level, message, context, exception, data)
        
        # Log to Python logger
        self._log_event(event)
        
        # Store in history
        self._store_in_history(event)
        
        # Invoke handlers for this level
        for handler in self._handlers[level]:
            try:
                handler(event)
            except Exception as handler_error:
                # Prevent handler errors from breaking dispatch
                self._logger.error(
                    f"Error in error handler: {handler_error}",
                    exc_info=True
                )
        
        return event
    
    def _log_event(self, event: ErrorEvent) -> None:
        """Log event to Python logger."""
        log_level = {
            ErrorLevel.INFO: logging.INFO,
            ErrorLevel.WARNING: logging.WARNING,
            ErrorLevel.ERROR: logging.ERROR,
            ErrorLevel.CRITICAL: logging.CRITICAL,
        }[event.level]
        
        log_message = str(event)
        if event.exception:
            self._logger.log(log_level, log_message, exc_info=event.exception)
        else:
            self._logger.log(log_level, log_message)
    
    def _store_in_history(self, event: ErrorEvent) -> None:
        """Store event in history buffer."""
        self._error_history.append(event)
        # Keep history size bounded
        if len(self._error_history) > self._max_history:
            self._error_history = self._error_history[-self._max_history:]
    
    def get_history(self, level: Optional[ErrorLevel] = None) -> list[ErrorEvent]:
        """Get error history, optionally filtered by level."""
        if level is None:
            return self._error_history.copy()
        return [e for e in self._error_history if e.level == level]
    
    def clear_history(self) -> None:
        """Clear error history."""
        self._error_history.clear()
    
    def safe_execute(
        self,
        func: Callable,
        *args,
        context: str = "unknown",
        on_error: Optional[Callable[[Exception], None]] = None,
        **kwargs,
    ):
        """Execute a function with automatic error handling.
        
        Useful for wrapping operations that might fail.
        
        Args:
            func: Function to execute
            context: Context name for error reporting
            on_error: Optional callback if error occurs
            *args, **kwargs: Arguments to pass to func
        
        Returns:
            Result of func, or None if error occurred
        """
        try:
            return func(*args, **kwargs)
        except Exception as e:
            self.emit(
                ErrorLevel.ERROR,
                f"Operation failed: {str(e)}",
                context=context,
                exception=e,
            )
            if on_error:
                on_error(e)
            return None


# Module-level convenience function for getting singleton
def get_dispatcher() -> ErrorDispatcher:
    """Get the global error dispatcher instance."""
    return ErrorDispatcher.get_instance()
