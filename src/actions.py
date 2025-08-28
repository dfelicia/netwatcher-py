"""
NetWatcher Actions Module

This module provides the main API for NetWatcher network operations.
It serves as a compatibility layer for the existing interface while
using the new modular structure underneath.

The module re-exports functions from specialized submodules:
- network.*: Network detection and configuration
- external.*: External service integrations
- location.*: Location matching and settings
- utils.*: Utility functions

Example usage:
    from src import actions

    # Network detection
    ssid = actions.get_current_ssid()
    vpn_active = actions.is_vpn_active()

    # Configuration
    actions.set_dns_servers("Wi-Fi", ["8.8.8.8", "1.1.1.1"])
    actions.set_proxy("Wi-Fi", "http://proxy.company.com:8080")

    # Location management
    location = actions.find_matching_location(config_data)
    actions.apply_location_settings(location, config_data[location])

For new code, consider importing directly from specific modules:
    from .network import get_current_ssid, is_vpn_active
    from .external import get_connection_details
    from .location import find_matching_location
"""

# Re-export the main functions to maintain compatibility
from .location import (
    find_matching_location,
    apply_location_settings,
    check_and_apply_location_settings,
)

from .network import (
    get_current_ssid,
    get_current_dns_servers,
    get_current_search_domains,
    get_primary_service_interface,
    is_vpn_active,
    set_dns_servers,
    set_search_domains,
    set_proxy,
    set_default_printer,
    set_ntp_server,
)

from .external import (
    get_connection_details,
    get_vpn_details,
)

from .utils import run_command

# Maintain the original API
__all__ = [
    # Main functions
    "check_and_apply_location_settings",
    "find_matching_location",
    "apply_location_settings",
    # Network detection
    "get_current_ssid",
    "get_current_dns_servers",
    "get_current_search_domains",
    "get_primary_service_interface",
    "is_vpn_active",
    # Network configuration
    "set_dns_servers",
    "set_search_domains",
    "set_proxy",
    "set_default_printer",
    "set_ntp_server",
    # External services
    "get_connection_details",
    "get_vpn_details",
    # Utilities
    "run_command",
]
