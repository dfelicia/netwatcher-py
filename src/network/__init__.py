"""
Network module for NetWatcher.

This module handles all network-related operations including:
- Network state detection (SSID, DNS, VPN status)
- Network interface management
- Network configuration (DNS servers, proxies, NTP)
"""

# Network constants
VPN_INTERFACE_PREFIX = "utun"  # macOS VPN tunnel interfaces (utun0, utun1, etc.)

from .detection import (
    get_current_ssid,
    get_current_dns_servers,
    get_current_search_domains,
    get_primary_service_interface,
    is_vpn_active,
)

from .interfaces import (
    get_default_route_interface,
    find_configurable_service,
)

from .interfaces import get_all_active_services

from .configuration import (
    set_dns_servers,
    set_search_domains,
    set_proxy,
    set_default_printer,
    set_ntp_server,
)

__all__ = [
    # Constants
    "VPN_INTERFACE_PREFIX",
    # Functions
    "get_current_ssid",
    "get_current_dns_servers",
    "get_current_search_domains",
    "get_primary_service_interface",
    "is_vpn_active",
    "get_default_route_interface",
    "find_configurable_service",
    "get_all_active_services",
    "set_dns_servers",
    "set_search_domains",
    "set_proxy",
    "set_default_printer",
    "set_ntp_server",
]
