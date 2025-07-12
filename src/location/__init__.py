"""
Location matching and settings application for NetWatcher.

This module handles matching network conditions to location profiles
and applying location-specific settings.
"""

from .matching import find_matching_location
from .settings import apply_location_settings, check_and_apply_location_settings

__all__ = [
    "find_matching_location",
    "apply_location_settings",
    "check_and_apply_location_settings",
]
