"""
Native macOS API utilities for NetWatcher.

This module provides functions that use native macOS SystemConfiguration APIs
and socket operations for network information gathering.
It serves as the central location for all native API calls to avoid duplication.
"""

import fcntl
import logging
import socket
import struct

try:
    import SystemConfiguration
except ImportError:
    SystemConfiguration = None


def get_dns_info_native():
    """
    Get DNS configuration using SystemConfiguration framework.

    Returns:
        str: Formatted DNS resolver information similar to 'scutil --dns' output,
             or None if SystemConfiguration is unavailable or no DNS info found.

    Note:
        This provides a native alternative to parsing 'scutil --dns' output.
        The format mimics scutil for compatibility with existing parsing code.
    """
    if not SystemConfiguration:
        return None

    try:
        store = SystemConfiguration.SCDynamicStoreCreate(None, "NetWatcher", None, None)
        if not store:
            return None

        # Get all DNS service keys
        dns_pattern = "State:/Network/Service/.*/DNS"
        dns_keys = SystemConfiguration.SCDynamicStoreCopyKeyList(store, dns_pattern)

        if not dns_keys:
            logging.debug("No DNS service keys found, checking global DNS")
            return _get_global_dns_info(store)

        # Process each DNS service
        result = []
        for dns_key in dns_keys:
            dns_dict = SystemConfiguration.SCDynamicStoreCopyValue(store, dns_key)
            if dns_dict:
                resolver_info = _format_dns_resolver_info(
                    dns_dict, dns_key, len(result) + 1
                )
                if resolver_info:
                    result.extend(resolver_info)

        return "\n".join(result) if result else None

    except Exception as e:
        logging.debug(f"Native DNS info failed: {e}")
        return None


def _get_global_dns_info(store):
    """Get global DNS configuration as fallback."""
    try:
        global_dns_key = "State:/Network/Global/DNS"
        global_dns_dict = SystemConfiguration.SCDynamicStoreCopyValue(
            store, global_dns_key
        )

        if not global_dns_dict:
            return None

        dns_servers = global_dns_dict.get("ServerAddresses", [])
        search_domains = global_dns_dict.get("SearchDomains", [])

        if not (dns_servers or search_domains):
            return None

        result = ["resolver #1"]
        for i, server in enumerate(dns_servers):
            result.append(f"  nameserver[{i}] : {server}")
        if search_domains:
            result.append(f"  search domain[0] : {' '.join(search_domains)}")

        return "\n".join(result)

    except Exception as e:
        logging.debug(f"Failed to get global DNS info: {e}")
        return None


def _format_dns_resolver_info(dns_dict, dns_key, resolver_num):
    """Format DNS resolver information for display."""
    dns_servers = dns_dict.get("ServerAddresses", [])
    search_domains = dns_dict.get("SearchDomains", [])
    interface = dns_dict.get("InterfaceName", "unknown")

    if not (dns_servers or search_domains):
        return None

    result = [f"resolver #{resolver_num}"]
    if interface != "unknown":
        result.append(f"  interface: {interface}")

    for i, server in enumerate(dns_servers):
        result.append(f"  nameserver[{i}] : {server}")

    if search_domains:
        result.append(f"  search domain[0] : {' '.join(search_domains)}")

    return result


def get_service_name_native(service_id):
    """Get service name using SystemConfiguration instead of scutil."""
    if not SystemConfiguration:
        return None

    try:
        # Create a dynamic store
        store = SystemConfiguration.SCDynamicStoreCreate(None, "NetWatcher", None, None)
        if not store:
            return None

        # Get service configuration
        service_key = f"Setup:/Network/Service/{service_id}"
        service_dict = SystemConfiguration.SCDynamicStoreCopyValue(store, service_key)

        if service_dict:
            user_defined_name = service_dict.get("UserDefinedName")
            if user_defined_name:
                logging.debug(f"Native API found service name: {user_defined_name}")
                return user_defined_name

        return None

    except Exception as e:
        logging.debug(f"Native service name lookup failed: {e}")
        return None


def get_default_route_interface_native():
    """Get the default route interface using native APIs instead of netstat."""
    if not SystemConfiguration:
        return None

    try:
        # Create a dynamic store
        store = SystemConfiguration.SCDynamicStoreCreate(None, "NetWatcher", None, None)
        if not store:
            return None

        # Get global IPv4 state
        ipv4_key = "State:/Network/Global/IPv4"
        ipv4_dict = SystemConfiguration.SCDynamicStoreCopyValue(store, ipv4_key)

        if not ipv4_dict:
            logging.debug("No global IPv4 configuration found")
            return None

        # Get the primary interface
        primary_interface = ipv4_dict.get("PrimaryInterface")
        if primary_interface:
            logging.debug(f"Native API found primary interface: {primary_interface}")
            return primary_interface

        return None

    except Exception as e:
        logging.debug(f"Native default route interface lookup failed: {e}")
        return None


def get_interface_ip_native(interface):
    """Get IP address for an interface using native socket APIs."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Use SIOCGIFADDR ioctl to get interface IP
            interface_bytes = interface.encode("utf-8")[:15]  # IFNAMSIZ is 16
            ifreq = struct.pack("16s16x", interface_bytes)

            result = fcntl.ioctl(sock.fileno(), 0x8915, ifreq)  # SIOCGIFADDR
            ip_bytes = result[20:24]  # sockaddr_in.sin_addr offset
            ip = socket.inet_ntoa(ip_bytes)

            logging.debug(f"Native API found IP {ip} for interface {interface}")
            return ip

        except OSError as e:
            logging.debug(f"Interface {interface} has no IP address: {e}")
            return None
        finally:
            sock.close()

    except Exception as e:
        logging.debug(f"Native IP lookup failed for interface {interface}: {e}")
        return None
