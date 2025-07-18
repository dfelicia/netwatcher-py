"""
Network configuration functions for NetWatcher.

This module provides functions to configure network settings including
DNS servers, search domains, proxies, printers, and NTP servers.
"""

import logging
import urllib.parse
from pathlib import Path

from .. import config
from ..utils import run_command


def set_dns_servers(service_name, dns_servers):
    """Sets the DNS servers for a network service."""
    if not dns_servers:
        # Don't set anything - let DHCP handle DNS
        logging.info(
            f"No DNS servers configured for '{service_name}', leaving DHCP in control"
        )
        return

    dns_list = [str(d) for d in dns_servers]
    logging.info(f"Setting DNS servers for '{service_name}' to: {dns_list}")

    try:
        cmd = [
            "sudo",
            "/usr/sbin/networksetup",
            "-setdnsservers",
            service_name,
        ] + dns_list
        # Use list form (not shell=True) for security - networksetup handles service names with spaces
        run_command(cmd)
    except Exception as e:
        logging.error(f"Failed to set DNS servers: {e}")


def set_search_domains(service_name, domains):
    """Sets the DNS search domains for a network service."""
    if not domains:
        # Use "Empty" to clear the search domains
        domains_list = ["Empty"]
        logging.info(f"Clearing search domains for '{service_name}'")
    else:
        domains_list = [str(d) for d in domains]
        logging.info(f"Setting {len(domains_list)} search domains for '{service_name}'")
        logging.debug(f"Search domains for '{service_name}': {domains_list}")

    try:
        cmd = [
            "sudo",
            "/usr/sbin/networksetup",
            "-setsearchdomains",
            service_name,
        ] + domains_list
        # Use list form (not shell=True) for security - networksetup handles service names with spaces
        run_command(cmd)
    except Exception as e:
        logging.error(f"Failed to set search domains: {e}")


def set_proxy(service_name, url=None):
    """Set proxy configuration for a network service."""
    if not url:
        logging.info(f"Disabling all proxies for '{service_name}'")
        _disable_all_proxies(service_name)
        return

    logging.info(f"Setting proxy for '{service_name}' to {url}")

    # Determine proxy type and construct command
    cmd = _build_proxy_command(service_name, url)
    if cmd:
        run_command(cmd)


def _disable_all_proxies(service_name):
    """Disable all proxy types for a network service."""
    proxy_types = [
        ("-setautoproxystate", "off"),
        ("-setwebproxystate", "off"),
        ("-setsecurewebproxystate", "off"),
        ("-setsocksfirewallproxystate", "off"),
    ]

    for proxy_type, state in proxy_types:
        cmd = ["sudo", "/usr/sbin/networksetup", proxy_type, service_name, state]
        run_command(cmd)


def _build_proxy_command(service_name, url):
    """Build the appropriate networksetup command for the given proxy URL."""
    # PAC/WPAD file
    if url.startswith(("http://", "https://")) and (
        "/wpad.dat" in url.lower() or ".pac" in url.lower()
    ):
        return ["sudo", "/usr/sbin/networksetup", "-setautoproxyurl", service_name, url]

    # Parse URL for manual proxy configuration
    try:
        parsed = urllib.parse.urlparse(url)
        if not parsed.hostname:
            # Assume it's a PAC/WPAD URL if no hostname parsed
            return [
                "sudo",
                "/usr/sbin/networksetup",
                "-setautoproxyurl",
                service_name,
                url,
            ]

        # Manual proxy configuration
        if parsed.scheme == "http":
            return [
                "sudo",
                "/usr/sbin/networksetup",
                "-setwebproxy",
                service_name,
                parsed.hostname,
                str(parsed.port or config.DEFAULT_HTTP_PORT),
            ]
        elif parsed.scheme == "https":
            return [
                "sudo",
                "/usr/sbin/networksetup",
                "-setsecurewebproxy",
                service_name,
                parsed.hostname,
                str(parsed.port or config.DEFAULT_HTTPS_PORT),
            ]
        elif parsed.scheme == "socks":
            return [
                "sudo",
                "/usr/sbin/networksetup",
                "-setsocksfirewallproxy",
                service_name,
                parsed.hostname,
                str(parsed.port or config.DEFAULT_SOCKS_PORT),
            ]
        else:
            # Unknown scheme, try as PAC/WPAD
            return [
                "sudo",
                "/usr/sbin/networksetup",
                "-setautoproxyurl",
                service_name,
                url,
            ]

    except Exception as e:
        logging.debug(f"Proxy URL parsing failed for {url}: {e}")
        # Try as PAC/WPAD URL
        return ["sudo", "/usr/sbin/networksetup", "-setautoproxyurl", service_name, url]


def set_default_printer(printer_name):
    """Sets the system's default printer."""
    logging.info(f"Setting default printer to {printer_name}")
    run_command(["/usr/sbin/lpadmin", "-d", printer_name])


def set_ntp_server(ntp_server):
    """Sets the system-wide network time protocol (NTP) server robustly."""
    logging.info(f"Setting NTP server to {ntp_server}")

    # First, turn network time off. This can help clear a stuck state.
    logging.debug("Temporarily disabling network time")
    run_command(["sudo", "/usr/sbin/systemsetup", "-setusingnetworktime", "off"])

    # Set the new NTP server.
    cmd_set_server = [
        "sudo",
        "/usr/sbin/systemsetup",
        "-setnetworktimeserver",
        ntp_server,
    ]
    run_command(cmd_set_server)

    # Re-enable network time.
    logging.debug("Re-enabling network time")
    cmd_enable_time = ["sudo", "/usr/sbin/systemsetup", "-setusingnetworktime", "on"]
    run_command(cmd_enable_time)

    # Force an immediate time sync with shorter timeout
    logging.debug("Triggering time synchronization")
    # Use shorter timeout for VPN scenarios where NTP might be blocked
    sntp_result = run_command(
        ["sudo", "/usr/bin/sntp", "-t", "3", "-sS", ntp_server], capture=True
    )
    if sntp_result:
        logging.info("Time synchronization completed successfully")
    else:
        # If direct sync fails, the system will still use the configured NTP server
        # for automatic synchronization when network allows it
        logging.info(
            "Immediate time sync failed (may be blocked by VPN/firewall), "
            "but NTP server is configured for automatic synchronization"
        )
