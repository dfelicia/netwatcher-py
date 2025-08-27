"""
Location settings application for NetWatcher.

This module provides functions to apply location-specific settings
and manage the overall configuration process.
"""

import logging

from ..network import (
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
from ..external import get_proxy_from_wpad, get_vpn_details
from .matching import find_matching_location


def apply_location_settings(
    location_config, service_name, interface_name, vpn_active=None
):
    """Applies all settings for a given location."""
    # Get domains from two sources:
    # 1. The live system state (from scutil, includes DHCP, VPN, etc.)
    # 2. The domains defined in the location's config
    current_domains = get_current_search_domains(interface_name)
    config_domains = location_config.get("dns_search_domains", [])

    # Determine which domains to use based on VPN status and data freshness
    if vpn_active is None:
        vpn_active = is_vpn_active()

    if config_domains:
        # If location has specific domains configured, use those as primary
        if vpn_active or not current_domains:
            # On VPN or no current domains: combine config + current
            all_domains = list(dict.fromkeys(config_domains + current_domains))
        else:
            # Off VPN with current domains: only use config domains to avoid stale data
            # But preserve any local domains (like .local, .arpa)
            local_domains = [
                d for d in current_domains if d.endswith((".local", ".arpa"))
            ]
            all_domains = list(dict.fromkeys(config_domains + local_domains))
    else:
        # Location has no specific domains: use current system domains
        all_domains = current_domains

    set_search_domains(service_name, all_domains)

    # Set DNS Servers based on the location config
    dns_servers = location_config.get("dns_servers", [])
    set_dns_servers(service_name, dns_servers)

    # Determine proxy
    proxy_url = location_config.get("proxy_url", "")
    proxy_to_use = None
    if proxy_url:
        # If it's a wpad.dat file, we need to parse it to get the actual proxy server
        if "wpad.dat" in proxy_url.lower():
            proxy_result = get_proxy_from_wpad(proxy_url)
            if proxy_result == "DIRECT" or proxy_result is None:
                set_proxy(service_name)  # disable proxy
                proxy_to_use = None
            else:
                proxy_to_use = proxy_result
                set_proxy(service_name, f"http://{proxy_result}")
        else:
            # It's a direct proxy address
            proxy_to_use = proxy_url
            set_proxy(service_name, proxy_to_use)
    else:
        # No proxy URL, so disable proxy settings
        set_proxy(service_name)

    if "printer" in location_config and location_config["printer"]:
        set_default_printer(location_config["printer"])

    # Set NTP server if configured
    if "ntp_server" in location_config and location_config["ntp_server"]:
        set_ntp_server(location_config["ntp_server"])


def check_and_apply_location_settings(cfg):
    """Determine current location and apply appropriate settings.

    Returns:
        tuple: (location_name, vpn_active, vpn_details)
            - location_name: str, name of applied location or "Unknown"
            - vpn_active: bool, whether VPN is currently active
            - vpn_details: str or None, VPN connection details if available
    """
    # Get current network information
    network_info = _get_current_network_info()
    if not network_info:
        logging.debug("Could not determine network configuration")
        return "Unknown", False, None

    service_name, interface, service_id = network_info
    logging.info(f"Primary service: {service_name} ({interface})")

    # Get network details for location matching
    current_ssid = get_current_ssid()
    current_dns_servers = get_current_dns_servers(interface)
    current_search_domains = get_current_search_domains(interface)

    logging.info(f"Current SSID: {current_ssid}")
    logging.info(f"DNS servers: {current_dns_servers}")
    logging.debug(f"Search domains: {current_search_domains}")
    logging.info(f"Search domains: {len(current_search_domains)} found")

    # Check VPN status once
    vpn_active = is_vpn_active()
    vpn_details = None

    if vpn_active:
        vpn_details = get_vpn_details()
        if vpn_details:
            logging.debug(f"VPN details: {vpn_details}")

        # Additional validation for VPN transitions
        if len(current_search_domains) <= 1:
            logging.debug(
                "VPN detected but few search domains - network may be transitioning"
            )

    # Find and apply location settings
    location_name = find_matching_location(
        cfg, current_ssid, current_search_domains, vpn_active
    )

    if location_name in cfg.get("locations", {}):
        logging.info(f"Applying settings for location: {location_name}")
        apply_location_settings(
            cfg["locations"][location_name],
            service_name,
            interface,
            vpn_active,
        )
    else:
        logging.warning(f"Location '{location_name}' not found in config")
        return "Unknown", vpn_active, vpn_details

    return location_name, vpn_active, vpn_details


def _get_current_network_info():
    """Get current network service and interface information."""
    try:
        return get_primary_service_interface()
    except Exception as e:
        logging.error(f"Error getting network info: {e}")
        return None
