"""
Location matching logic for NetWatcher.

This module provides functions to determine the best matching location
based on current network environment.
"""

import logging

from ..network import is_vpn_active


def find_matching_location(
    config_data,
    current_ssid,
    current_search_domains,
    vpn_active=None,
):
    """Find the best matching location based on network environment."""
    if vpn_active is None:
        vpn_active = is_vpn_active()

    logging.info(f"Location matching: VPN={vpn_active}, SSID={current_ssid}")
    logging.info(f"Search domains: {len(current_search_domains)} found")

    locations = config_data.get("locations", {})

    # Priority 1: VPN + Proxy configuration
    if vpn_active:
        match = _find_vpn_location(locations)
        if match:
            return match

    # Priority 2: SSID matching (non-VPN)
    if not vpn_active and current_ssid:
        match = _find_ssid_location(locations, current_ssid)
        if match:
            return match

    # Priority 3: Corporate vs Home heuristics
    if vpn_active:
        match = _find_corporate_location(locations)
        if match:
            return match
    else:
        match = _find_home_location(locations)
        if match:
            return match

    logging.info("No specific match found, using default")
    return "default"


def _find_vpn_location(locations):
    """Find location with proxy configuration (for VPN scenarios)."""
    for name, settings in locations.items():
        if name != "default" and settings.get("proxy_url"):
            logging.info(f"VPN active - selected '{name}' (has proxy config)")
            return name
    return None


def _find_ssid_location(locations, ssid):
    """Find location matching current SSID."""
    for name, settings in locations.items():
        if name != "default" and ssid in settings.get("ssids", []):
            logging.info(f"SSID match - selected '{name}' for SSID '{ssid}'")
            return name
    return None


def _find_corporate_location(locations):
    """Find corporate-like location (has custom NTP)."""
    for name, settings in locations.items():
        if name == "default":
            continue
        ntp_server = settings.get("ntp_server", "")
        if ntp_server and ntp_server != "time.apple.com":
            logging.info(f"VPN active - selected '{name}' (has corporate NTP)")
            return name
    return None


def _find_home_location(locations):
    """Find home-like location (minimal configuration)."""
    for name, settings in locations.items():
        if name == "default":
            continue
        # Home characteristics: no proxy, minimal search domains
        if (
            not settings.get("proxy_url")
            and len(settings.get("dns_search_domains", [])) <= 2
        ):
            logging.info(f"No VPN - selected '{name}' (home-like config)")
            return name
    return None
