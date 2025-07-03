import subprocess
import logging
import re
import shutil
from pathlib import Path
import json
import shlex  # Import shlex

try:
    import CoreWLAN
except ImportError:
    CoreWLAN = None  # Graceful fallback for non-macOS
from . import config


def run_command(command, capture=False, text=True, input=None, shell=False):
    """Runs a command, handling output and errors robustly."""
    # If using shell, the command should be a string.
    if shell and isinstance(command, list):
        # Join the list into a single string, quoting arguments safely.
        command = shlex.join(command)

    logging.debug(f"Running command ({'shell' if shell else 'list'}): {command}")

    try:
        result = subprocess.run(
            command,
            shell=shell,
            check=False,  # We check the return code manually
            capture_output=True,
            text=text,
            encoding="utf-8",
            errors="ignore",
            input=input,
        )

        # Log stderr for debugging, but only as a warning if the command failed.
        if result.stderr and result.returncode != 0:
            logging.warning(
                f"Stderr from failed command '{command}': {result.stderr.strip()}"
            )
        elif result.stderr:
            logging.debug(
                f"Stderr from successful command '{command}': {result.stderr.strip()}"
            )

        if result.returncode != 0:
            logging.warning(
                f"Command '{command}' exited with status {result.returncode}."
            )
            if result.stdout:
                logging.warning(f"Stdout: {result.stdout.strip()}")

            if capture:
                return ((result.stdout or "") + (result.stderr or "")).strip()
            return False

        # Command was successful
        if capture:
            return result.stdout.strip() if result.stdout else ""
        return True

    except FileNotFoundError:
        cmd_name = command.split()[0] if shell else command[0]
        logging.error(f"Command not found: {cmd_name}")
        return False if not capture else None
    except Exception as e:
        logging.error(
            f"An unexpected error occurred in run_command for '{command}': {e}"
        )
        return False if not capture else None


def get_connection_details():
    """Fetches public IP and location details from ipinfo.io."""
    logging.info("Fetching connection details from ipinfo.io")
    details_json = run_command(["curl", "-s", "ipinfo.io"], capture=True)
    if not details_json:
        return {"error": "Could not retrieve connection details."}
    try:
        details = json.loads(details_json)
        return {
            "ip": details.get("ip", "N/A"),
            "city": details.get("city", "N/A"),
            "region": details.get("region", "N/A"),
            "country": details.get("country", "N/A"),
            "org": details.get("org", "N/A"),
        }
    except json.JSONDecodeError:
        logging.error("Failed to parse JSON from ipinfo.io")
        return {"error": "Could not parse connection details."}


def get_proxy_from_wpad(wpad_url):
    """Fetches and parses a wpad.dat file to find the proxy server."""
    logging.info(f"Attempting to get proxy from {wpad_url}")
    try:
        wpad_content = run_command(
            ["curl", "-sL", "--connect-timeout", "3", "--max-time", "5", wpad_url],
            capture=True,
        )
        if not wpad_content:
            return None
        # Simple regex to find a PROXY host:port setting
        match = re.search(r"PROXY\s+([a-zA-Z0-9.-]+:\d+)", wpad_content, re.IGNORECASE)
        if match:
            proxy_server = match.group(1)
            logging.info(f"Found proxy server in wpad.dat: {proxy_server}")
            return proxy_server
    except Exception as e:
        logging.error(f"Failed to parse wpad.dat: {e}")
    return None


def update_curlrc(proxy_server=None):
    """Updates the ~/.curlrc file with the specified proxy server."""
    curlrc_path = Path.home() / ".curlrc"
    lines = []
    try:
        if curlrc_path.exists():
            with open(curlrc_path, "r") as f:
                lines = f.readlines()

        # Remove existing proxy lines
        lines = [
            line
            for line in lines
            if not line.strip().startswith(("proxy=", "httpsproxy_proxy="))
        ]

        # Add new proxy line if a server is provided
        if proxy_server:
            logging.info(f"Updating ~/.curlrc to use proxy: {proxy_server}")
            lines.append(f"proxy = {proxy_server}\n")
        else:
            logging.info("Updating ~/.curlrc to remove proxy settings.")

        with open(curlrc_path, "w") as f:
            f.writelines(lines)
    except IOError as e:
        logging.error(f"Error updating ~/.curlrc: {e}")


def set_proxy(service_name, url=None):
    """Sets proxy configuration for a network service (PAC/WPAD, HTTP, or SOCKS)."""
    if url:
        logging.info(f"Setting proxy for '{service_name}' to {url}")

        # Determine proxy type and set accordingly
        if url.startswith(("http://", "https://")) and (
            "/wpad.dat" in url.lower() or ".pac" in url.lower()
        ):
            # PAC/WPAD file
            cmd = [
                "sudo",
                "/usr/sbin/networksetup",
                "-setautoproxyurl",
                service_name,
                url,
            ]
        elif url.startswith("http://"):
            # Manual HTTP proxy
            # Extract host and port from http://host:port
            import urllib.parse

            parsed = urllib.parse.urlparse(url)
            cmd = [
                "sudo",
                "/usr/sbin/networksetup",
                "-setwebproxy",
                service_name,
                parsed.hostname,
                str(parsed.port or 80),
            ]
        elif url.startswith("https://"):
            # Manual HTTPS proxy
            import urllib.parse

            parsed = urllib.parse.urlparse(url)
            cmd = [
                "sudo",
                "/usr/sbin/networksetup",
                "-setsecurewebproxy",
                service_name,
                parsed.hostname,
                str(parsed.port or 443),
            ]
        elif url.startswith("socks://"):
            # Manual SOCKS proxy
            import urllib.parse

            parsed = urllib.parse.urlparse(url)
            cmd = [
                "sudo",
                "/usr/sbin/networksetup",
                "-setsocksfirewallproxy",
                service_name,
                parsed.hostname,
                str(parsed.port or 1080),
            ]
        else:
            # Assume it's a PAC/WPAD URL if no recognized scheme
            cmd = [
                "sudo",
                "/usr/sbin/networksetup",
                "-setautoproxyurl",
                service_name,
                url,
            ]
    else:
        logging.info(f"Disabling all proxies for '{service_name}'")
        # Disable all proxy types
        commands = [
            [
                "sudo",
                "/usr/sbin/networksetup",
                "-setautoproxystate",
                service_name,
                "off",
            ],
            [
                "sudo",
                "/usr/sbin/networksetup",
                "-setwebproxystate",
                service_name,
                "off",
            ],
            [
                "sudo",
                "/usr/sbin/networksetup",
                "-setsecurewebproxystate",
                service_name,
                "off",
            ],
            [
                "sudo",
                "/usr/sbin/networksetup",
                "-setsocksfirewallproxystate",
                service_name,
                "off",
            ],
        ]
        for cmd in commands:
            run_command(cmd, shell=True)
        return

    # Use shell=True to handle service names with spaces correctly.
    run_command(cmd, shell=True)


def set_default_printer(printer_name):
    """Sets the system's default printer."""
    logging.info(f"Setting default printer to {printer_name}")
    run_command(["/usr/sbin/lpadmin", "-d", printer_name])


def set_ntp_server(ntp_server):
    """Sets the system-wide network time protocol (NTP) server robustly."""
    logging.info(f"Setting system-wide NTP server to {ntp_server}")

    # First, turn network time off. This can help clear a stuck state.
    logging.info("Temporarily disabling network time...")
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
    logging.info("Re-enabling network time.")
    cmd_enable_time = ["sudo", "/usr/sbin/systemsetup", "-setusingnetworktime", "on"]
    run_command(cmd_enable_time)

    # Force an immediate time sync
    logging.info("Forcing immediate time synchronization...")
    sntp_result = run_command(["sudo", "/usr/bin/sntp", "-sS", ntp_server])
    if sntp_result:
        logging.info("Time synchronization completed successfully.")
    else:
        logging.warning(
            "Time synchronization may have failed, but NTP server is configured."
        )


# --- Network State Detection ---

# Cache for scutil --dns output to avoid redundant calls
_dns_output_cache = None
_dns_cache_timestamp = 0


def _get_dns_output():
    """
    Gets the output of `scutil --dns` with simple caching to avoid redundant calls.
    Cache expires after 5 seconds.
    """
    global _dns_output_cache, _dns_cache_timestamp
    import time

    current_time = time.time()
    if _dns_output_cache is None or (current_time - _dns_cache_timestamp) > 5:
        _dns_output_cache = run_command(["scutil", "--dns"], capture=True)
        _dns_cache_timestamp = current_time
        logging.debug("Fetched fresh scutil --dns output")
    else:
        logging.debug("Using cached scutil --dns output")

    return _dns_output_cache


def _get_active_resolver_block(interface_name):
    """
    Gets the specific resolver block from `scutil --dns` that is associated
    with the given network interface.
    """
    if not interface_name:
        logging.warning("Cannot find resolver block without an interface name.")
        return None

    dns_output = _get_dns_output()
    if not dns_output:
        logging.warning("`scutil --dns` returned no output.")
        return None

    # Split the output into blocks for each resolver
    resolver_blocks = dns_output.strip().split("resolver #")

    for block in resolver_blocks:
        if not block.strip():
            continue

        # Check if the block corresponds to our interface by name
        # The format is like: 'if_index : 7 (en0)'
        if f"({interface_name})" in block:
            logging.info(f"Found active resolver block for interface {interface_name}.")
            return block

    logging.warning(f"No active resolver found for interface {interface_name}.")
    return None


def get_current_dns_servers(interface_name):
    """
    Gets the current DNS servers from the active resolver for a specific interface.
    Returns a list of IP addresses.
    """
    if not interface_name:
        return []
    resolver_block = _get_active_resolver_block(interface_name)
    if not resolver_block:
        return []

    servers = []
    # The regex now looks for `nameserver[ <index> ] : <ip_address>`
    for match in re.finditer(
        r"nameserver\[\s*\d+\s*\]\s*:\s*([\d\.]+)", resolver_block
    ):
        servers.append(match.group(1))

    if not servers:
        logging.warning(
            f"Could not find DNS servers for interface '{interface_name}' in its resolver block."
        )
    else:
        logging.info(f"Discovered DNS servers for '{interface_name}': {servers}")
    return servers


def get_current_search_domains(interface_name):
    """
    Gets the current DNS search domains from the active resolver for a specific interface.
    Returns a list of domain names.
    """
    if not interface_name:
        return []
    resolver_block = _get_active_resolver_block(interface_name)
    if not resolver_block:
        return []

    domains = []
    # The regex looks for `search domain[ <index> ] : <domain>` (note the space)
    for match in re.finditer(r"search domain\[\s*\d+\s*\]\s*:\s*(\S+)", resolver_block):
        domains.append(match.group(1))

    if not domains:
        logging.warning(
            f"Could not find search domains for interface '{interface_name}' in its resolver block."
        )
    else:
        logging.info(f"Discovered search domains for '{interface_name}': {domains}")
    return domains


def set_dns_servers(service_name, dns_servers):
    """Sets the DNS servers for a network service."""
    if not dns_servers:
        # Use "Empty" to clear the DNS servers
        dns_list = ["Empty"]
        logging.info(f"Clearing DNS servers for '{service_name}'.")
    else:
        dns_list = [str(d) for d in dns_servers]
        logging.info(f"Setting DNS servers for '{service_name}' to: {dns_list}")

    try:
        cmd = [
            "sudo",
            "/usr/sbin/networksetup",
            "-setdnsservers",
            service_name,
        ] + dns_list
        # Use shell=True to handle service names with spaces correctly.
        run_command(cmd, shell=True)
    except Exception as e:
        logging.error(f"Failed to set DNS servers: {e}")


def set_search_domains(service_name, domains):
    """Sets the DNS search domains for a network service."""
    if not domains:
        # Use "Empty" to clear the search domains
        domains_list = ["Empty"]
        logging.info(f"Clearing search domains for '{service_name}'.")
    else:
        domains_list = [str(d) for d in domains]
        logging.info(f"Setting search domains for '{service_name}' to: {domains_list}")

    try:
        cmd = [
            "sudo",
            "/usr/sbin/networksetup",
            "-setsearchdomains",
            service_name,
        ] + domains_list
        # Use shell=True to handle service names with spaces correctly.
        run_command(cmd, shell=True)
    except Exception as e:
        logging.error(f"Failed to set search domains: {e}")


def is_vpn_active():
    """
    Checks for an active VPN connection by verifying if the default route is a
    `utun` interface and if that interface is actively used by a DNS resolver.
    This is more reliable than just checking for a `utun` interface, which can
    be used by non-VPN macOS services (e.g., iCloud Private Relay).
    """
    logging.info("Checking for active VPN connection...")
    default_interface = None
    try:
        # 1. Find the default network interface
        netstat_output = run_command(["netstat", "-rn"], capture=True)
        if netstat_output:
            for line in netstat_output.split("\n"):
                if line.startswith("default"):
                    # The interface is the last column
                    default_interface = line.split()[-1]
                    break

        if not default_interface or not default_interface.startswith("utun"):
            logging.info("Default route is not on a utun (VPN) interface.")
            return False

        logging.info(f"Default route is on interface: {default_interface}")

        # 2. Check if a DNS resolver is using that specific utun interface
        dns_output = _get_dns_output()
        if not dns_output:
            logging.warning("`scutil --dns` returned no output. Cannot verify VPN.")
            return False

        # Split the output into blocks for each resolver
        resolver_blocks = dns_output.strip().split("resolver #")

        for block in resolver_blocks:
            if not block.strip():
                continue

            # Check if the block corresponds to our default interface
            if f"if_index" in block and f"({default_interface})" in block:
                # Check if it actually has a nameserver configured
                if "nameserver[" in block:
                    logging.info(
                        f"Confirmed active VPN: DNS resolver is using interface {default_interface}."
                    )
                    return True

        logging.info(
            f"Interface {default_interface} is default, but no active DNS resolver found for it. Not a user VPN."
        )
        return False

    except Exception as e:
        logging.error(f"Error checking for VPN connection: {e}")
        return False


def get_vpn_details():
    """Checks for a configured VPN client's status and returns details if connected."""
    app_config = config.load_config()
    vpn_config = app_config.get("vpn", {})
    client_path = vpn_config.get("client_path")
    client_name = vpn_config.get("client_name", "VPN")

    if not client_path or not Path(client_path).exists():
        logging.info(
            f"{client_name} command not found at '{client_path}', skipping VPN check."
        )
        return None

    logging.info(f"Checking {client_name} status.")
    stats = run_command([client_path, "stats"], capture=True)
    if not stats or "state: Disconnected" in stats:
        logging.info(f"{client_name} is not connected.")
        return None

    try:
        vpn_server_match = re.search(r"server: (.*)", stats, re.IGNORECASE)
        vpn_server = (
            vpn_server_match.group(1).strip() if vpn_server_match else "Unknown"
        )

        ip_match = re.search(r"client address \(ipv4\): (.*)", stats, re.IGNORECASE)
        vpn_ip = ip_match.group(1).strip() if ip_match else "N/A"

        details = f"VPN Connected to {vpn_server}\\nVPN IP: {vpn_ip}"
        logging.info(details)
        return details
    except Exception as e:
        logging.error(f"Failed to parse VPN stats: {e}")
        return "VPN status could not be determined."


def apply_location_settings(
    location_name, location_config, service_name, interface_name
):
    """Applies all settings for a given location."""
    logging.info(f"Applying settings for location: {location_name}")

    # Get domains from two sources:
    # 1. The live system state (from scutil, includes DHCP, VPN, etc.)
    # 2. The domains defined in the location's config
    current_domains = get_current_search_domains(interface_name)
    config_domains = location_config.get("dns_search_domains", [])

    # Combine all domains and remove duplicates, preserving order.
    # The location's configured domains are given precedence.
    all_domains = list(dict.fromkeys(config_domains + current_domains))
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
            proxy_to_use = get_proxy_from_wpad(proxy_url)
            # We still set the system to the autodiscovery URL
            set_proxy(service_name, proxy_url)
        else:
            # It's a direct proxy address
            proxy_to_use = proxy_url
            set_proxy(service_name, proxy_to_use)
    else:
        # No proxy URL, so disable proxy settings
        set_proxy(service_name)

    # Update curlrc with the specific proxy server address, or remove it
    # Only pass a proxy to curlrc if we have a real proxy server, not None or empty strings
    if proxy_to_use and proxy_to_use.strip() and proxy_to_use != "(null)":
        update_curlrc(proxy_to_use)
    else:
        update_curlrc(None)  # This will remove proxy settings

    if "printer" in location_config and location_config["printer"]:
        set_default_printer(location_config["printer"])

    # Set NTP server if configured
    if "ntp_server" in location_config and location_config["ntp_server"]:
        set_ntp_server(location_config["ntp_server"])


def get_primary_service_interface():
    """Gets the primary network service and its interface (e.g., Wi-Fi, Ethernet)."""
    try:
        # Use scutil to get the primary interface and service ID
        scutil_output = run_command(
            ["scutil"], capture=True, input="show State:/Network/Global/IPv4\n"
        )
        primary_interface = re.search(r"PrimaryInterface\s*:\s*(\S+)", scutil_output)
        primary_service_id = re.search(r"PrimaryService\s*:\s*(\S+)", scutil_output)

        if not (primary_interface and primary_service_id):
            logging.warning("Could not determine PrimaryInterface and PrimaryService.")
            return None, None

        interface = primary_interface.group(1)
        service_id = primary_service_id.group(1)

        # Get the user-friendly service name from the service ID
        service_name_output = run_command(
            ["scutil"],
            capture=True,
            input=f"show Setup:/Network/Service/{service_id}\n",
        )
        user_defined_name = re.search(
            r"UserDefinedName\s*:\s*(.+)", service_name_output
        )

        if user_defined_name:
            return user_defined_name.group(1).strip(), interface
        else:
            logging.warning(
                f"Could not find UserDefinedName for service ID {service_id}."
            )
            return "Unknown Service", interface

    except Exception as e:
        logging.error(f"An error occurred while getting the primary service: {e}")
        return None, None


def get_current_ssid():
    """Gets the SSID of the current Wi-Fi network using CoreWLAN."""
    if CoreWLAN is None:
        logging.warning("CoreWLAN framework not available. Cannot get SSID.")
        return None
    try:
        interface = CoreWLAN.CWInterface.interface()
        if interface:
            return interface.ssid()
    except Exception as e:
        logging.error(f"Could not get current SSID using CoreWLAN: {e}")
    return None


def find_matching_location(
    config_data, current_ssid, current_dns_servers, current_search_domains
):
    """Finds a matching location in the config based on network properties."""
    for loc, settings in config_data.get("locations", {}).items():
        if loc == "default":
            continue

        # Match by SSID
        if current_ssid and current_ssid in settings.get("ssids", []):
            return loc

        # Match by DNS servers (if any of the current servers are in the location's list)
        if current_dns_servers and any(
            s in settings.get("dns_servers", []) for s in current_dns_servers
        ):
            return loc

        # Match by search domains
        if current_search_domains and any(
            d in settings.get("dns_search_domains", []) for d in current_search_domains
        ):
            return loc

    return "default"


def check_and_apply_location_settings(cfg):
    """Determine location and apply settings. Returns the location name."""
    primary_service, primary_interface = get_primary_service_interface()
    if not primary_service:
        logging.warning("Could not determine the primary network service.")
        return "Unknown"

    current_ssid = get_current_ssid()
    current_dns_servers = get_current_dns_servers(primary_interface)
    current_search_domains = get_current_search_domains(primary_interface)

    logging.info(f"Primary Service: {primary_service} ({primary_interface})")
    logging.info(f"Current SSID: {current_ssid}")
    logging.info(f"Current DNS Servers: {current_dns_servers}")
    logging.info(f"Current Search Domains: {current_search_domains}")

    location_name = find_matching_location(
        cfg,
        current_ssid,
        current_dns_servers,
        current_search_domains,
    )

    if location_name and location_name in cfg.get("locations", {}):
        logging.info(f"Matched location: '{location_name}'. Applying settings.")
        apply_location_settings(
            location_name,
            cfg["locations"][location_name],
            primary_service,
            primary_interface,
        )
    else:
        logging.info("No matching location found. Applying default settings.")
        if "default" in cfg.get("locations", {}):
            apply_location_settings(
                "default",
                cfg["locations"]["default"],
                primary_service,
                primary_interface,
            )
            location_name = "default"
        else:
            logging.warning("No 'default' location configured. Cannot apply settings.")
            return "Unknown"

    return location_name
