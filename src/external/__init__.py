"""
External services module for NetWatcher.

This module handles interactions with external services including:
- Connection details from ip-api.com
- WPAD proxy configuration
- VPN client integrations
"""

from .ipinfo import get_connection_details
from .wpad import get_proxy_from_wpad, update_curlrc
from .vpn import get_vpn_details

__all__ = [
    "get_connection_details",
    "get_proxy_from_wpad",
    "update_curlrc",
    "get_vpn_details",
]
