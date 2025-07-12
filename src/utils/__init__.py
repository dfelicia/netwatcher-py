"""
Utility functions for NetWatcher.

This module provides common utility functions used throughout the application.
"""

from .commands import run_command
from .native import (
    get_dns_info_native,
    get_service_name_native,
    get_default_route_interface_native,
    get_interface_ip_native,
)

__all__ = [
    "run_command",
    "get_dns_info_native",
    "get_service_name_native",
    "get_default_route_interface_native",
    "get_interface_ip_native",
]
