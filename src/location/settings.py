"""
Location settings application for NetWatcher.

This module provides functions to apply location-specific settings
and manage the overall configuration process.
"""

from pathlib import Path

from ..logging_config import get_logger
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
    get_all_active_services,
    get_default_route_interface,
    update_shell_proxy_configuration,
)
from ..external import get_vpn_details
from ..utils import run_command
from .matching import find_matching_location

# Get module logger
logger = get_logger(__name__)


def apply_location_settings(
    location_config,
    service_name,
    interface_name,
    vpn_active=None,
    skip_dns=False,
    proxy_result=None,
):
    """Applies all settings for a given location."""

    if not skip_dns:
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
    if proxy_result:
        set_proxy(service_name, proxy_result)
    else:
        set_proxy(service_name)  # disable


def check_and_apply_location_settings(
    cfg, apply=True, fetch_details=True, log_level=20  # INFO level
):
    """Determine current location and apply appropriate settings if apply=True.

    Returns:
        tuple: (location_name, vpn_active, vpn_details)
            - location_name: str, name of applied location or "Unknown"
            - vpn_active: bool, whether VPN is currently active
            - vpn_details: str or None, VPN connection details if available
    """
    # Get current network information
    network_info = _get_current_network_info(log_level=log_level)
    if not network_info:
        logger.log(log_level, "Could not determine network configuration")
        return "Unknown", False, None

    service_name, interface, service_id = network_info
    logger.debug(f"Primary interface: {service_name} ({interface})")

    # Get network details for location matching
    current_ssid = get_current_ssid(log_level=log_level)
    current_dns_servers = get_current_dns_servers(interface, log_level=log_level)
    current_search_domains = get_current_search_domains(interface, log_level=log_level)

    logger.log(log_level, f"SSID: {current_ssid}")
    logger.debug(f"DNS servers: {current_dns_servers}")
    logger.debug(f"Search domains: {len(current_search_domains)} found")

    # Check VPN status once
    vpn_active = is_vpn_active(log_level=log_level)
    vpn_details = None

    if vpn_active:
        if fetch_details:
            vpn_details = get_vpn_details()

        # Additional validation for VPN transitions
        if len(current_search_domains) <= 1:
            logger.log(
                log_level,
                "VPN detected but few search domains - network may be transitioning",
            )

    # Find and apply location settings
    location_name = find_matching_location(
        cfg, current_ssid, current_search_domains, vpn_active, log_level=log_level
    )

    available_locations = list(cfg.get("locations", {}).keys())
    logger.debug(f"Available locations: {available_locations}")
    logger.debug(f"Checking if '{location_name}' in available locations")

    if location_name in cfg.get("locations", {}):
        if apply:
            logger.log(log_level, f"Applying settings for location: {location_name}")
            location_config = cfg["locations"][location_name]
            proxy_url = location_config.get("proxy_url", "")

            active_services = get_all_active_services()
            for serv_name, iface in active_services:
                logger.debug(f"Applying to {serv_name} ({iface})")
                skip_dns = vpn_active
                apply_location_settings(
                    location_config,
                    serv_name,
                    iface,
                    vpn_active,
                    skip_dns=skip_dns,
                    proxy_result=proxy_url,
                )

            # System-wide settings
            if "printer" in location_config and location_config["printer"]:
                set_default_printer(location_config["printer"])
            if "ntp_server" in location_config and location_config["ntp_server"]:
                set_ntp_server(location_config["ntp_server"])

            # Shell proxy configuration
            try:
                dns_search_domains = location_config.get("dns_search_domains", [])
                update_shell_proxy_configuration(proxy_url, dns_search_domains)
            except Exception as e:
                logger.warning(f"Failed to update shell proxy configuration: {e}")
    else:
        logger.warning(f"Location '{location_name}' not found in config")
        return "Unknown", vpn_active, vpn_details

    return location_name, vpn_active, vpn_details


def create_vpn_resolver_files(search_domains, vpn_dns_servers=None):
    """Create resolver files for each search domain when VPN is active."""
    resolver_dir = Path("/etc/resolver")
    created_files = []

    try:
        # Ensure directory exists (requires sudo mkdir /etc/resolver)
        run_command(["sudo", "mkdir", "-p", str(resolver_dir)])

        primary_interface = get_default_route_interface()
        current_domains = (
            get_current_search_domains(primary_interface) if primary_interface else []
        )

        for domain in search_domains:
            if domain in current_domains:
                logger.debug(
                    f"Skipping duplicate domain {domain} already in resolv.conf"
                )
                continue

            file_path = resolver_dir / domain
            content = f"search {domain}\n"
            if vpn_dns_servers:
                content += (
                    "\n".join(f"nameserver {dns}" for dns in vpn_dns_servers) + "\n"
                )
                content += "search_order 1\n"  # Prioritize this resolver

            # Write using tee to avoid redirection issues with sudo
            run_command(["sudo", "tee", str(file_path)], input=content)
            created_files.append(file_path)
            logger.debug(f"Created resolver file for {domain}")

        if created_files:
            logger.info(f"Created {len(created_files)} resolver files in /etc/resolver")

        return created_files

    except Exception as e:
        logger.error(f"Failed to create resolver files: {e}")
        return []


def remove_vpn_resolver_files(created_files):
    """Remove previously created resolver files when VPN disconnects."""
    num_files = len(created_files)
    for file_path in created_files:
        try:
            run_command(["sudo", "rm", "-f", str(file_path)])
            logger.debug(f"Removed resolver file: {file_path}")
        except Exception as e:
            logger.error(f"Failed to remove {file_path}: {e}")

    if num_files > 0:
        logger.info(f"Removed {num_files} resolver files from /etc/resolver")


def _get_current_network_info(log_level=20):  # INFO level
    """Get current network service and interface information."""
    try:
        return get_primary_service_interface(log_level=log_level)
    except Exception as e:
        logger.log(log_level, f"Error getting network info: {e}")
        return None
