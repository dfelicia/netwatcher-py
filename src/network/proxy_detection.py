"""
System proxy detection utilities for NetWatcher.

This module provides centralized proxy detection that can be used by
multiple components (ipinfo.py, shell_proxy.py, etc.) to avoid code duplication.
"""

import re
import urllib.request
from typing import Optional, Tuple

from ..logging_config import get_logger
from ..utils import run_command
from .detection import get_primary_service_interface
from .pac_parser import parse_pac_file_for_generic_url

# Get module logger
logger = get_logger(__name__)


def get_system_proxy_config() -> Tuple[Optional[str], Optional[str]]:
    """
    Get system proxy configuration from networksetup.

    Returns:
        Tuple of (proxy_type, proxy_value) where:
        - proxy_type: "pac", "http", "https", "socks", or None
        - proxy_value: URL for PAC or host:port for manual proxy, or None
    """
    try:
        # Get the primary service
        primary_service, _, _ = get_primary_service_interface(log_level=10)  # DEBUG
        if not primary_service:
            logger.debug("No primary service found for proxy detection")
            return None, None

        # Check for PAC (auto proxy) configuration first
        pac_output = run_command(
            ["networksetup", "-getautoproxyurl", primary_service],
            capture=True,
            quiet_on_error=True,
        )

        if pac_output and "URL:" in pac_output:
            url_match = re.search(r"URL:\s*(.+)", pac_output)
            if url_match:
                pac_url = url_match.group(1).strip()
                if pac_url and pac_url != "(null)":
                    logger.debug(f"Found PAC proxy: {pac_url}")
                    return "pac", pac_url

        # Check for manual HTTP proxy
        http_output = run_command(
            ["networksetup", "-getwebproxy", primary_service],
            capture=True,
            quiet_on_error=True,
        )

        if http_output and "Enabled: Yes" in http_output:
            server_match = re.search(r"Server:\s*(.+)", http_output)
            port_match = re.search(r"Port:\s*(\d+)", http_output)
            if server_match and port_match:
                server = server_match.group(1).strip()
                port = port_match.group(1).strip()
                proxy_value = f"{server}:{port}"
                logger.debug(f"Found HTTP proxy: {proxy_value}")
                return "http", proxy_value

        # Check for manual HTTPS proxy
        https_output = run_command(
            ["networksetup", "-getsecurewebproxy", primary_service],
            capture=True,
            quiet_on_error=True,
        )

        if https_output and "Enabled: Yes" in https_output:
            server_match = re.search(r"Server:\s*(.+)", https_output)
            port_match = re.search(r"Port:\s*(\d+)", https_output)
            if server_match and port_match:
                server = server_match.group(1).strip()
                port = port_match.group(1).strip()
                proxy_value = f"{server}:{port}"
                logger.debug(f"Found HTTPS proxy: {proxy_value}")
                return "https", proxy_value

        # Check for SOCKS proxy
        socks_output = run_command(
            ["networksetup", "-getsocksfirewallproxy", primary_service],
            capture=True,
            quiet_on_error=True,
        )

        if socks_output and "Enabled: Yes" in socks_output:
            server_match = re.search(r"Server:\s*(.+)", socks_output)
            port_match = re.search(r"Port:\s*(\d+)", socks_output)
            if server_match and port_match:
                server = server_match.group(1).strip()
                port = port_match.group(1).strip()
                proxy_value = f"{server}:{port}"
                logger.debug(f"Found SOCKS proxy: {proxy_value}")
                return "socks", proxy_value

        logger.debug("No system proxy configured")
        return None, None

    except Exception as e:
        logger.debug(f"Error detecting system proxy: {e}")
        return None, None


def get_urllib_proxy_handler() -> Optional[urllib.request.ProxyHandler]:
    """
    Get urllib ProxyHandler based on system proxy configuration.

    This function detects system proxy settings and returns an appropriate
    ProxyHandler for urllib. PAC files are automatically parsed to extract
    the actual proxy server.

    Returns:
        urllib.request.ProxyHandler or None for direct connection
    """
    proxy_type, proxy_value = get_system_proxy_config()

    if not proxy_type or not proxy_value:
        logger.debug("No proxy configured, using direct connection")
        return None

    if proxy_type == "pac":
        # Parse PAC file to get actual proxy
        logger.debug(f"Parsing PAC file: {proxy_value}")
        actual_proxy = parse_pac_file_for_generic_url(proxy_value)

        if actual_proxy and actual_proxy != "DIRECT":
            # pac_parser returns URLs like "http://proxy.com:8080" already formatted
            logger.debug(f"Using proxy from PAC file: {actual_proxy}")
            return urllib.request.ProxyHandler(
                {"http": actual_proxy, "https": actual_proxy}
            )
        else:
            logger.debug("PAC file returned DIRECT, using direct connection")
            return None

    elif proxy_type in ("http", "https"):
        # Manual HTTP/HTTPS proxy
        proxy_url = f"http://{proxy_value}"
        logger.debug(f"Using manual {proxy_type.upper()} proxy: {proxy_url}")
        return urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})

    elif proxy_type == "socks":
        # SOCKS proxy
        proxy_url = f"socks://{proxy_value}"
        logger.debug(f"Using SOCKS proxy: {proxy_url}")
        return urllib.request.ProxyHandler(
            {"http": proxy_url, "https": proxy_url, "socks": proxy_url}
        )

    return None


def get_proxy_url_for_shell(resolve_pac: bool = True) -> Optional[str]:
    """
    Get proxy URL suitable for shell environment variables (http_proxy, etc.).

    Args:
        resolve_pac: If True, parse PAC files to get actual proxy. If False,
                     return None for PAC configurations.

    Returns:
        Proxy URL string or None
    """
    proxy_type, proxy_value = get_system_proxy_config()

    if not proxy_type or not proxy_value:
        return None

    if proxy_type == "pac":
        if not resolve_pac:
            logger.debug("PAC proxy found but resolve_pac=False, returning None")
            return None

        # Parse PAC file
        logger.debug(f"Parsing PAC file for shell: {proxy_value}")
        actual_proxy = parse_pac_file_for_generic_url(proxy_value)

        if actual_proxy and actual_proxy != "DIRECT":
            # pac_parser already returns formatted URLs like "http://proxy.com:8080"
            return actual_proxy
        else:
            return None

    elif proxy_type in ("http", "https"):
        return f"http://{proxy_value}"

    elif proxy_type == "socks":
        return f"socks://{proxy_value}"

    return None
