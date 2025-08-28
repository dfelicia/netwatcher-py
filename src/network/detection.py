"""
Network state detection functions for NetWatcher.

This module provides functions to detect current network state including
DNS servers, search domains, SSID, and VPN status.
"""

import re

try:
    import CoreWLAN
except ImportError:
    CoreWLAN = None

from . import VPN_INTERFACE_PREFIX
from ..logging_config import get_logger
from ..utils import run_command, get_dns_info_native
from .interfaces import get_default_route_interface

# Get module logger
logger = get_logger(__name__)


def get_dns_output():
    """Get DNS configuration using scutil for complete info including scoped."""
    logger.debug("Using scutil --dns for DNS info")
    return run_command(["scutil", "--dns"], capture=True)


def get_active_resolver_block(interface_name):
    """Get the DNS resolver block for a specific network interface from scoped section."""
    if not interface_name:
        logger.debug("Cannot find resolver block without interface name")
        return None

    dns_output = get_dns_output()
    if not dns_output:
        logger.debug("No DNS output available")
        return None

    # Find the scoped DNS configuration section
    scoped_start = dns_output.find("DNS configuration (for scoped queries)")
    if scoped_start == -1:
        logger.debug("No scoped DNS configuration found")
        return None

    scoped_section = dns_output[scoped_start:]

    # Split into resolver blocks
    blocks = scoped_section.strip().split("resolver #")

    for block in blocks:
        if block.strip() and f"({interface_name})" in block:
            logger.debug(f"Found scoped resolver block for {interface_name}")
            return block

    logger.debug(f"No scoped resolver found for {interface_name}")
    return None


def get_current_dns_servers(interface_name, log_level=20):  # INFO level
    """Get current DNS servers for a specific interface."""
    if not interface_name:
        return []

    resolver_block = get_active_resolver_block(interface_name)
    if not resolver_block:
        return []

    # Extract DNS servers from resolver block
    servers = []
    for match in re.finditer(r"nameserver\[\d+\]\s*:\s*([\d\.]+)", resolver_block):
        servers.append(match.group(1))

    if servers:
        logger.log(log_level, f"Found DNS servers for '{interface_name}': {servers}")
    else:
        logger.log(log_level, f"No DNS servers found for '{interface_name}'")

    return servers


def get_current_search_domains(interface_name, log_level=20):  # INFO level
    """Get current DNS search domains for a specific interface."""
    if not interface_name:
        return []

    resolver_block = get_active_resolver_block(interface_name)
    if not resolver_block:
        return []

    # Extract search domains from resolver block
    domains = []
    for match in re.finditer(r"search domain\[\d+\]\s*:\s*(\S+)", resolver_block):
        domains.append(match.group(1))

    if domains:
        if len(domains) == 1:
            logger.log(log_level, f"Found domain '{domains[0]}' for '{interface_name}'")
        else:
            logger.log(
                log_level,
                f"Found domain '{domains[0]}' and {len(domains) - 1} more for '{interface_name}'",
            )
    else:
        logger.log(log_level, f"No search domains found for '{interface_name}'")

    return domains


def get_current_ssid(log_level=20):  # INFO level
    """Gets the SSID of the current Wi-Fi network using CoreWLAN."""
    if not CoreWLAN:
        logger.log(log_level, "CoreWLAN not available")
        return None

    try:
        interface = CoreWLAN.CWInterface.interface()
        if interface:
            return interface.ssid()
    except Exception as e:
        logger.log(log_level, f"Could not get current SSID using CoreWLAN: {e}")
    return None


def is_vpn_active(log_level=20):  # INFO level
    """Check if VPN is active by examining the default route interface."""
    logger.log(log_level, "Checking for active VPN connection")

    try:
        default_interface = get_default_route_interface()

        if not default_interface:
            logger.log(log_level, "No default route interface found")
            return False

        if default_interface.startswith(VPN_INTERFACE_PREFIX):
            logger.log(log_level, f"VPN detected: default route on {default_interface}")
            return True
        else:
            logger.log(log_level, f"No VPN: default route on {default_interface}")
            return False

    except Exception as e:
        logger.log(log_level, f"Error checking VPN status: {e}")
        return False


def get_primary_service_interface(log_level=20):  # INFO level
    """Get the primary network service and interface information."""
    from .interfaces import (
        get_primary_service_id,
        get_primary_service_scutil,
        get_service_display_name,
        find_configurable_service,
    )
    from ..utils import get_default_route_interface_native

    try:
        # Try native method first
        interface = get_default_route_interface_native()
        service_id = None

        if interface:
            service_id = get_primary_service_id()

        # Fall back to scutil if native method incomplete
        if not interface or not service_id:
            logger.log(log_level, "Using scutil fallback for primary service info")
            interface, service_id = get_primary_service_scutil()

        if not (interface and service_id):
            logger.log(log_level, "Could not determine primary interface and service")
            return None, None, None

        # Get user-friendly service name
        service_name = get_service_display_name(service_id, interface)

        # For VPN interfaces, find the underlying configurable service
        if interface.startswith(VPN_INTERFACE_PREFIX):
            underlying_service = find_configurable_service()
            if underlying_service:
                logger.log(
                    log_level,
                    f"VPN detected, using underlying service: {underlying_service}",
                )
                return underlying_service, interface, service_id

        logger.log(
            log_level,
            f"Primary service: {service_name} (ID: {service_id}, interface: {interface})",
        )
        return service_name, interface, service_id

    except Exception as e:
        logger.log(log_level, f"Error getting primary service: {e}")
        return None, None, None
