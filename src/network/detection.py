"""
Network state detection functions for NetWatcher.

This module provides functions to detect current network state including
DNS servers, search domains, SSID, and VPN status.
"""

import logging
import re

try:
    import CoreWLAN
except ImportError:
    CoreWLAN = None

from . import VPN_INTERFACE_PREFIX
from ..utils import run_command, get_dns_info_native
from .interfaces import get_default_route_interface


def get_dns_output():
    """Get DNS configuration using hybrid approach: native APIs with scutil fallback."""
    # Try native method first
    native_result = get_dns_info_native()
    if (
        native_result
        and "search domain" in native_result
        and "nameserver" in native_result
    ):
        logging.debug("Using native DNS info")
        return native_result

    # Fall back to scutil for complete output
    logging.debug("Using scutil --dns for complete DNS info")
    return run_command(["scutil", "--dns"], capture=True)


def get_active_resolver_block(interface_name):
    """Get the DNS resolver block for a specific network interface."""
    if not interface_name:
        logging.debug("Cannot find resolver block without interface name")
        return None

    dns_output = get_dns_output()
    if not dns_output:
        logging.debug("No DNS output available")
        return None

    # Find the resolver block for this interface
    for block in dns_output.strip().split("resolver #"):
        if block.strip() and f"({interface_name})" in block:
            logging.debug(f"Found resolver block for interface {interface_name}")
            return block

    logging.debug(f"No resolver found for interface {interface_name}")
    return None


def get_current_dns_servers(interface_name):
    """Get current DNS servers for a specific interface."""
    if not interface_name:
        return []

    resolver_block = get_active_resolver_block(interface_name)
    if not resolver_block:
        return []

    # Extract DNS servers from resolver block
    servers = []
    for match in re.finditer(
        r"nameserver\[\s*\d+\s*\]\s*:\s*([\d\.]+)", resolver_block
    ):
        servers.append(match.group(1))

    if servers:
        logging.info(f"Found DNS servers for '{interface_name}': {servers}")
    else:
        logging.debug(f"No DNS servers found for '{interface_name}'")

    return servers


def get_current_search_domains(interface_name):
    """Get current DNS search domains for a specific interface."""
    if not interface_name:
        return []

    resolver_block = get_active_resolver_block(interface_name)
    if not resolver_block:
        return []

    # Extract search domains from resolver block
    domains = []
    for match in re.finditer(r"search domain\[\s*\d+\s*\]\s*:\s*(\S+)", resolver_block):
        domains.append(match.group(1))

    if domains:
        if len(domains) == 1:
            logging.info(f"Found domain '{domains[0]}' for '{interface_name}'")
        else:
            logging.info(
                f"Found domain '{domains[0]}' and {len(domains) - 1} more for '{interface_name}'"
            )
    else:
        logging.debug(f"No search domains found for '{interface_name}'")

    return domains


def get_current_ssid():
    """Gets the SSID of the current Wi-Fi network using CoreWLAN."""
    if not CoreWLAN:
        logging.debug("CoreWLAN not available")
        return None

    try:
        interface = CoreWLAN.CWInterface.interface()
        if interface:
            return interface.ssid()
    except Exception as e:
        logging.error(f"Could not get current SSID using CoreWLAN: {e}")
    return None


def is_vpn_active():
    """Check if VPN is active by examining the default route interface."""
    logging.info("Checking for active VPN connection...")

    try:
        default_interface = get_default_route_interface()

        if not default_interface:
            logging.info("No default route interface found")
            return False

        if default_interface.startswith(VPN_INTERFACE_PREFIX):
            logging.info(f"VPN detected: default route on {default_interface}")
            return True
        else:
            logging.info(f"No VPN: default route on {default_interface}")
            return False

    except Exception as e:
        logging.error(f"Error checking VPN status: {e}")
        return False


def get_primary_service_interface():
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
            logging.debug("Using scutil fallback for primary service info")
            interface, service_id = get_primary_service_scutil()

        if not (interface and service_id):
            logging.debug("Could not determine primary interface and service")
            return None, None, None

        # Get user-friendly service name
        service_name = get_service_display_name(service_id, interface)

        # For VPN interfaces, find the underlying configurable service
        if interface.startswith(VPN_INTERFACE_PREFIX):
            underlying_service = find_configurable_service()
            if underlying_service:
                logging.debug(
                    f"VPN detected, using underlying service: {underlying_service}"
                )
                return underlying_service, interface, service_id

        logging.debug(
            f"Primary service: {service_name} (ID: {service_id}, interface: {interface})"
        )
        return service_name, interface, service_id

    except Exception as e:
        logging.error(f"Error getting primary service: {e}")
        return None, None, None
