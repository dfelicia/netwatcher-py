"""
Location matching logic for NetWatcher.

This module provides functions to determine the best matching location
based on current network environment.
"""

from ..logging_config import get_logger
from ..network import is_vpn_active

# Get module logger
logger = get_logger(__name__)


def find_matching_location(
    config_data,
    current_ssid,
    current_search_domains,
    vpn_active=None,
    log_level=20,  # INFO level
):
    """Find the best matching location based on network environment."""
    if vpn_active is None:
        vpn_active = is_vpn_active()

    logger.debug(f"Location matching: VPN={vpn_active}, SSID={current_ssid}")

    locations = config_data.get("locations", {})

    # Priority 1: VPN + Proxy configuration
    if vpn_active:
        match = _find_vpn_location(locations, log_level=log_level)
        if match:
            return match

    # Priority 2: SSID matching (non-VPN)
    if not vpn_active and current_ssid:
        match = _find_ssid_location(locations, current_ssid, log_level=log_level)
        if match:
            return match

    # Priority 3: Search domain matching (non-VPN)
    if not vpn_active and current_search_domains:
        match = _find_domain_location(
            locations, current_search_domains, log_level=log_level
        )
        if match:
            return match

    # Priority 4: Corporate vs Home heuristics
    if vpn_active:
        match = _find_corporate_location(locations, log_level=log_level)
        if match:
            return match
    else:
        match = _find_home_location(locations, log_level=log_level)
        if match:
            return match

    logger.log(log_level, "No specific match found, using default")
    return "default"


def _find_vpn_location(locations, log_level=20):  # INFO level
    """Find location with proxy configuration (for VPN scenarios)."""
    for name, settings in locations.items():
        if name != "default" and settings.get("proxy_url"):
            logger.log(log_level, f"VPN active - selected '{name}' (has proxy config)")
            return name
    return None


def _find_ssid_location(locations, ssid, log_level=20):  # INFO level
    """Find location matching current SSID."""
    for name, settings in locations.items():
        if name != "default" and ssid in settings.get("ssids", []):
            logger.debug(f"SSID match - selected '{name}' for SSID '{ssid}'")
            return name
    return None


def _find_corporate_location(locations, log_level=20):  # INFO level
    """Find corporate-like location (has custom NTP)."""
    for name, settings in locations.items():
        if name == "default":
            continue
        ntp_server = settings.get("ntp_server", "")
        if ntp_server and ntp_server != "time.apple.com":
            logger.log(log_level, f"VPN active - selected '{name}' (has corporate NTP)")
            return name
    return None


def _find_domain_location(locations, current_domains, log_level=20):  # INFO level
    """Find location matching current search domains using set intersection."""
    current_set = set(current_domains)
    for name, settings in locations.items():
        if name == "default":
            continue
        config_domains = set(settings.get("dns_search_domains", []))
        if config_domains.intersection(current_set):
            logger.log(log_level, f"Domain match - selected '{name}'")
            return name
    return None


def _find_home_location(locations, log_level=20):  # INFO level
    """Find home-like location (minimal configuration)."""
    for name, settings in locations.items():
        if name == "default":
            continue
        # Home characteristics: no proxy, minimal search domains
        if (
            not settings.get("proxy_url")
            and len(settings.get("dns_search_domains", [])) <= 2
        ):
            logger.log(log_level, f"No VPN - selected '{name}' (home-like config)")
            return name
    return None
