"""
Network state caching for NetWatcher.

This module provides a simple caching mechanism to avoid repeated network
queries during a single evaluation cycle. The cache is designed to be
short-lived and cleared between evaluations.
"""

import time
from threading import Lock
from typing import Any, Dict, Optional

from ..logging_config import get_logger

logger = get_logger(__name__)

# Global cache state
_cache: Dict[str, Any] = {}
_cache_timestamp: Optional[float] = None
_cache_lock = Lock()

# Cache timeout in seconds (should be longer than any single evaluation)
CACHE_TIMEOUT = 30


def _is_cache_valid() -> bool:
    """Check if the current cache is still valid."""
    if _cache_timestamp is None:
        return False
    return time.time() - _cache_timestamp < CACHE_TIMEOUT


def get_cached(key: str, default=None) -> Any:
    """Get a value from the cache."""
    with _cache_lock:
        if not _is_cache_valid():
            return default
        return _cache.get(key, default)


def set_cached(key: str, value: Any) -> None:
    """Set a value in the cache."""
    global _cache_timestamp
    with _cache_lock:
        if not _is_cache_valid():
            # Cache is stale, clear it first
            _cache.clear()
            _cache_timestamp = time.time()
            logger.debug("Network state cache initialized")

        _cache[key] = value
        logger.debug(f"Cached network state: {key}")


def clear_cache() -> None:
    """Manually clear the cache."""
    global _cache_timestamp
    with _cache_lock:
        if _cache:
            logger.debug("Network state cache cleared")
        _cache.clear()
        _cache_timestamp = None


def cache_network_function(cache_key: str):
    """Decorator to cache network function results."""

    def decorator(func):
        def wrapper(*args, **kwargs):
            # Create a cache key that includes function name and relevant args
            # For network functions, we typically only care about interface name
            key_parts = [cache_key]

            # Only add first arg if it exists and is not a log_level parameter
            if args and not (isinstance(args[0], int) and len(args) == 1):
                # First arg is usually interface name or similar
                key_parts.append(str(args[0]) if args[0] else "none")

            full_key = ":".join(key_parts)

            # Try to get from cache first
            cached_result = get_cached(full_key)
            if cached_result is not None:
                logger.debug(f"Using cached result for {cache_key}")
                return cached_result

            # Call the actual function
            result = func(*args, **kwargs)

            # Cache the result
            set_cached(full_key, result)

            return result

        return wrapper

    return decorator
