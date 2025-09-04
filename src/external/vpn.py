"""
VPN detection and status retrieval for NetWatcher.

This module provides functions to detect VPN connections and get details
from specific VPN clients like Cisco AnyConnect.
"""

import re
from pathlib import Path

from ..logging_config import get_logger
from ..utils import run_command

# Get module logger
logger = get_logger(__name__)


def get_vpn_details():
    """Get VPN details using auto-detection for known VPN types."""
    try:
        # Import here to avoid circular import
        from ..network.detection import get_primary_service_interface

        _, _, service_id = get_primary_service_interface()
        if service_id and "com.cisco" in service_id.lower():
            return get_cisco_vpn_details(service_id)
    except Exception as e:
        logger.debug(f"Failed to get service ID for VPN detection: {e}")

    logger.debug("No VPN client auto-detection available")
    return None


def find_cisco_vpn_binary():
    """Find Cisco VPN binary in common installation locations."""
    common_paths = [
        "/opt/cisco/secureclient/bin/vpn",
        "/opt/cisco/anyconnect/bin/vpn",
        "/Applications/Cisco/Cisco AnyConnect Secure Mobility Client.app/Contents/MacOS/Cisco AnyConnect Secure Mobility Client",
        "/Applications/Cisco/Cisco Secure Client.app/Contents/MacOS/Cisco Secure Client",
    ]

    for path in common_paths:
        if Path(path).exists():
            logger.debug(f"Found Cisco VPN binary: {path}")
            return path

    logger.debug("No Cisco VPN binary found")
    return None


def get_cisco_vpn_details(service_id):
    """Get Cisco VPN connection details if available."""
    if not service_id or "com.cisco" not in service_id.lower():
        return None

    vpn_binary = find_cisco_vpn_binary()
    if not vpn_binary:
        logger.debug("Cisco VPN detected but no CLI binary found")
        return None

    logger.debug("Retrieving Cisco VPN status")
    try:
        stats = run_command([vpn_binary, "stats"], capture=True)
        if not stats or "state: Disconnected" in stats:
            logger.info("Cisco VPN is disconnected")
            return None

        # Parse connection details
        logger.debug(f"Cisco VPN stats output: {stats}")

        # Match Bash logic: look for "Server Address:" and "Protocol:" fields
        server_match = re.search(r"server address:\s*(.+)", stats, re.IGNORECASE)
        server = server_match.group(1).strip() if server_match else "Unknown"

        protocol_match = re.search(r"protocol:\s*(.+)", stats, re.IGNORECASE)
        protocol = protocol_match.group(1).strip() if protocol_match else None

        # Also try to get client IP if available
        ip_match = re.search(r"client address \(ipv4\):\s*(.+)", stats, re.IGNORECASE)
        vpn_ip = (
            ip_match.group(1).strip() if ip_match else "N/A"
        )  # Format details on separate lines for better readability
        details_parts = [f"VPN Connected to {server}"]
        details_parts.append(f"IP: {vpn_ip}")
        if protocol:
            details_parts.append(f"Protocol: {protocol}")

        details = "\n".join(details_parts)  # Use newlines for menu display
        # Log details on a single line to avoid line breaks in logs
        details_single_line = ", ".join(details_parts)
        logger.info(f"Cisco VPN details: {details_single_line}")
        return details

    except Exception as e:
        logger.debug(f"Cisco VPN stats lookup failed: {e}")
        return None
