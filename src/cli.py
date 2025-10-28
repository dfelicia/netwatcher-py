import copy
import importlib.resources
import platform
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

import click
import objc
import toml

# Use relative imports to avoid module loading conflicts
from . import config
from .network import (
    get_current_ssid,
    get_current_dns_servers,
    get_current_search_domains,
    get_primary_service_interface,
)
from .location import check_and_apply_location_settings
from .utils import run_command


def signal_handler(signum, frame):
    """Handle interrupt signals gracefully."""
    signal_name = signal.Signals(signum).name
    click.echo(f"\n\nReceived {signal_name}. Exiting gracefully...")
    sys.exit(0)


# Set up signal handlers
signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
signal.signal(signal.SIGTERM, signal_handler)  # Termination signal


# --- Location Services / Wi-Fi Scanning Imports ---
try:
    from CoreLocation import (
        CLLocationManager,
        kCLAuthorizationStatusNotDetermined,
        kCLAuthorizationStatusDenied,
        kCLAuthorizationStatusRestricted,
    )
    import CoreWLAN

    CORELOCATION_AVAILABLE = True
except ImportError:
    # This will fail on non-macOS platforms, which is fine.
    CORELOCATION_AVAILABLE = False


if CORELOCATION_AVAILABLE:
    # Only define the delegate class if CoreLocation is available and not already defined
    try:

        class LocationAuthDelegate(objc.lookUpClass("NSObject")):
            """Delegate to handle location authorization callbacks."""

            def locationManagerDidChangeAuthorization_(self, manager):
                """Called when location authorization status changes."""
                # This delegate method is required, but we don't need to do anything with it.
                # The main thread will just poll the status after requesting it.
                pass

    except (objc.error, AttributeError):
        # Class already exists or objc not available
        LocationAuthDelegate = None
else:
    LocationAuthDelegate = None


# --- Helper Functions ---


def ask_yes_no(prompt, default="n"):
    """Asks a yes/no question and returns True for yes, False for no."""
    return click.confirm(prompt, default=(default.lower() == "y"))


# --- Helper Functions for Configuration Wizard ---


def _validate_selection_input(choice_str, items, allow_multiple=True):
    """Validate and parse user selection input."""
    new_selection = []
    if choice_str.strip():
        try:
            indices = [int(i.strip()) - 1 for i in choice_str.split(",")]
            if not allow_multiple and len(indices) > 1:
                click.echo(
                    "Warning: Only one selection is allowed. Taking the first one.",
                    err=True,
                )
                indices = [indices[0]]

            for i in indices:
                if 0 <= i < len(items):
                    new_selection.append(items[i])
                else:
                    click.echo(
                        f"Warning: Invalid selection '{i + 1}' ignored.",
                        err=True,
                    )
        except ValueError:
            click.echo(
                "Warning: Invalid input. Please enter numbers only.",
                err=True,
            )
            return None
    return new_selection


def _handle_manual_entry(current_selection, manual_entry_label, allow_multiple=True):
    """Handle manual entry of items."""
    prompt_text = f"Enter any additional {manual_entry_label} (comma-separated), or press Enter to skip"
    if not allow_multiple:
        prompt_text = f"Enter a {manual_entry_label} manually, or press Enter to skip"

    manual_entry_str = click.prompt(prompt_text, default="", show_default=False)

    if not manual_entry_str:
        return current_selection

    manual_items = [s.strip() for s in manual_entry_str.split(",") if s.strip()]

    if not allow_multiple:
        return [manual_items[0]] if manual_items else current_selection

    # Add new items, avoiding duplicates
    for item in manual_items:
        if item not in current_selection:
            current_selection.append(item)

    return current_selection


def prompt_for_selection(
    prompt_title,
    items,
    selected_items,
    allow_multiple=True,
    show_manual_entry=True,
    manual_entry_label="items",
):
    """
    Generic helper to prompt a user to select from a list of items.

    Args:
        prompt_title (str): The main title for the prompt section.
        items (list): A list of available strings to choose from.
        selected_items (list): A list of strings that are currently selected.
        allow_multiple (bool): Whether to allow multiple selections.
        show_manual_entry (bool): Whether to show a prompt for manual entry.

    Returns:
        list: An updated list of selected items based on user input.
    """
    click.echo(click.style(prompt_title, bold=True))

    # Work with a mutable copy
    current_selection = list(selected_items)

    if not items:
        click.echo("No items were automatically discovered.")
    else:
        if allow_multiple:
            click.echo(
                "Select by number, separated by commas (e.g., 1,3). Press Enter to keep current selection."
            )
        else:
            click.echo("Select one number. Press Enter to keep the current selection.")

        for i, item in enumerate(items, 1):
            is_selected = "x" if item in current_selection else " "
            click.echo(f" [{is_selected}] {i}: {item}")

        default_indices = ",".join(
            [str(i + 1) for i, s in enumerate(items) if s in current_selection]
        )

        prompt_text = "Select by number" if allow_multiple else "Select one number"

        # Make the prompt clearer about what Enter does
        if default_indices:
            prompt_text += " (or press Enter to keep current)"
        else:
            prompt_text += " (or press Enter to skip)"

        choice_str = click.prompt(
            prompt_text, default=default_indices, show_default=True
        )

        # If user entered a new value, parse it. Otherwise, the selection remains as is.
        if choice_str != default_indices:
            parsed_selection = _validate_selection_input(
                choice_str, items, allow_multiple
            )
            if parsed_selection is not None:
                current_selection = parsed_selection

    # Handle manual entry
    if show_manual_entry:
        current_selection = _handle_manual_entry(
            current_selection, manual_entry_label, allow_multiple
        )

    return current_selection


# --- Network Discovery Helper Functions ---


def _check_python_signature():
    """Check if Python interpreter has ad-hoc signature that might prevent Wi-Fi scanning."""
    try:
        codesign_output = run_command(["codesign", "-dv", sys.executable], capture=True)
        if codesign_output and "flags=0x2(adhoc)" in codesign_output:
            click.echo(
                click.style(
                    "Warning: This script is running on a Python interpreter with an ad-hoc "
                    "signature (e.g., from Homebrew).",
                    fg="yellow",
                )
            )
            click.echo(
                click.style(
                    "Wi-Fi scanning may fail or return an empty list. For best results, "
                    "create a virtual environment using the system Python:",
                    fg="yellow",
                )
            )
            click.echo(
                click.style("  /usr/bin/python3 -m venv <path_to_venv>", fg="yellow")
            )
    except Exception:
        # Ignore if codesign isn't available or fails.
        pass


def _request_location_authorization():
    """Request and check Location Services authorization. Returns True if authorized."""
    try:
        if not CORELOCATION_AVAILABLE or LocationAuthDelegate is None:
            click.echo("Location services not available - using manual SSID entry")
            return False

        manager = CLLocationManager.alloc().init()
        delegate = LocationAuthDelegate.alloc().init()
        manager.setDelegate_(delegate)
        status = manager.authorizationStatus()

        if status == kCLAuthorizationStatusNotDetermined:
            click.echo(
                "Requesting Location Services access to scan for Wi-Fi networks..."
            )
            manager.requestWhenInUseAuthorization()
            # Poll for a few seconds for the user to respond to the dialog
            for _ in range(config.LOCATION_AUTH_POLL_COUNT):
                time.sleep(config.LOCATION_AUTH_POLL_INTERVAL)
                status = manager.authorizationStatus()
                if status != kCLAuthorizationStatusNotDetermined:
                    break

        if status in [kCLAuthorizationStatusDenied, kCLAuthorizationStatusRestricted]:
            click.echo(
                click.style(
                    "Error: Location Services access is denied or restricted.",
                    fg="red",
                ),
                err=True,
            )
            click.echo(
                "Please enable Location Services for your terminal application in "
                "System Settings > Privacy & Security > Location Services.",
                err=True,
            )
            return False

        return True

    except Exception as e:
        click.echo(f"Could not check Location Services status: {e}", err=True)
        return False


def _perform_wifi_scan():
    """Perform the actual Wi-Fi network scan. Returns list of SSIDs."""
    try:
        interface = CoreWLAN.CWInterface.interface()
        if not interface:
            click.echo("No Wi-Fi interface found.", err=True)
            return []

        click.echo("Scanning for Wi-Fi networks... (this may take a moment)")
        # The scan can sometimes fail if the resource is busy, so we retry.
        networks = None
        for i in range(config.WIFI_SCAN_RETRY_COUNT):
            networks, error = interface.scanForNetworksWithName_error_(None, None)
            if networks is not None:
                break
            if error and "Busy" in str(error):
                time.sleep(
                    config.WIFI_SCAN_RETRY_DELAY_BASE * (i + 1)
                )  # Exponential backoff
            else:
                break  # A non-busy error occurred

        if networks is None:
            click.echo(f"Failed to scan for networks. Error: {error}", err=True)
            return []

        # Filter out networks with no SSID (redacted by OS) and return unique names
        ssids = sorted(list({n.ssid() for n in networks if n.ssid()}))
        click.echo(f"Found {len(ssids)} available networks.")
        return ssids

    except Exception as e:
        click.echo(f"An unexpected error occurred during Wi-Fi scan: {e}", err=True)
        return []


def get_available_ssids():
    """
    Attempts to get a list of available Wi-Fi SSIDs using CoreWLAN.
    Requires Location Services to be enabled for the terminal/script.
    """
    _check_python_signature()

    if not _request_location_authorization():
        return []

    return _perform_wifi_scan()


def get_available_printers():
    """Gets a list of available printer names."""
    try:
        printers_raw = run_command(["lpstat", "-p"], capture=True)
        if printers_raw:
            # Use splitlines() to avoid issues with newline characters
            return [
                line.split()[1]
                for line in printers_raw.splitlines()
                if line.startswith("printer")
            ]
    except Exception:
        pass  # Fail silently
    return []


# --- CLI Commands ---


class OrderedGroup(click.Group):
    """Custom Click group that preserves command order."""

    def list_commands(self, ctx):
        return list(self.commands.keys())


@click.group(cls=OrderedGroup)
def cli():
    """
    NetWatcher - Automatic network configuration management for macOS.

    NetWatcher automatically detects your network location and applies appropriate
    settings like DNS servers, search domains, proxy configuration, and default
    printer based on your current Wi-Fi network or other network characteristics.
    """
    pass


# --- Configuration Wizard Helper Functions ---


def _discover_current_network_settings():
    """Discover and return current network settings."""
    primary_service, primary_interface, primary_service_id = (
        get_primary_service_interface()
    )
    if not primary_service:
        click.echo("Could not determine primary network service. Exiting.", err=True)
        return None

    click.echo(f"Primary network service detected: {primary_service}")

    current_settings = {
        "ssid": get_current_ssid(),
        "dns_servers": get_current_dns_servers(primary_interface),
        "dns_search_domains": get_current_search_domains(primary_interface),
        "proxy_url": "",  # Default to empty
        "ntp_server": "time.apple.com",  # Default
    }

    # Get proxy URL
    proxy_out = run_command(
        ["networksetup", "-getautoproxyurl", primary_service], capture=True
    )
    if proxy_out and "No Auto Proxy URL is set" not in proxy_out:
        match = re.search(r"URL: (.*)", proxy_out)
        if match:
            url_value = match.group(1).strip()
            if url_value != "(null)":
                current_settings["proxy_url"] = url_value

    # Get NTP server
    ntp_out = run_command(["systemsetup", "-getnetworktimeserver"], capture=True)
    if ntp_out and "is not currently set" not in ntp_out:
        match = re.search(r"Network Time Server: (.*)", ntp_out)
        if match:
            current_settings["ntp_server"] = match.group(1).strip()

    return current_settings


def _get_location_name(cfg, location_name):
    """Get location name from user input or prompt."""
    if not location_name:
        existing_locations = [
            loc for loc in cfg.get("locations", {}) if loc != "default"
        ]
        click.echo(
            click.style("\n--- Location Selection ---", bold=True, underline=True)
        )
        if existing_locations:
            click.echo("Existing locations: " + ", ".join(existing_locations))
        location_name = click.prompt(
            "Enter the name for this new or existing location (e.g., 'Home', 'Office')"
        )

    if not location_name:
        click.echo("Error: Location name cannot be empty.", err=True)
        return None

    if location_name.lower() == "default":
        click.echo(
            "Error: The 'default' location is reserved for fallback settings and cannot be configured directly.",
            err=True,
        )
        return None

    return location_name


def _configure_ssids(location_cfg, current_settings, available_ssids):
    """Configure SSIDs for the location."""
    # If SSIDs are not set for the location, suggest the current one if available.
    if not location_cfg.get("ssids") and current_settings.get("ssid"):
        if ask_yes_no(
            f'Do you want to associate the current Wi-Fi network "{current_settings["ssid"]}" with this location?',
            "y",
        ):
            location_cfg["ssids"] = [current_settings["ssid"]]

    location_cfg["ssids"] = prompt_for_selection(
        "\n--- Wi-Fi Networks (SSIDs) ---",
        items=available_ssids,
        selected_items=location_cfg.get("ssids", []),
        allow_multiple=True,
        manual_entry_label="SSIDs",
    )


def _configure_dns(location_cfg, current_settings):
    """Configure DNS settings for the location."""
    # Configure DNS Search Domains
    location_cfg["dns_search_domains"] = prompt_for_selection(
        "\n--- DNS Search Domains ---",
        items=current_settings.get("dns_search_domains", []),
        selected_items=[],  # Never pre-select, always start fresh
        allow_multiple=True,
        manual_entry_label="domains",
    )

    # Configure DNS Servers
    click.echo(click.style("\n--- DNS Servers ---", bold=True))
    click.echo(
        "By default, NetWatcher uses the DNS servers provided by your network (DHCP)."
    )

    if ask_yes_no("Do you want to specify custom DNS servers for this location?", "n"):
        if not location_cfg.get("dns_servers") and current_settings.get("dns_servers"):
            click.echo(
                "\nCurrent DNS servers detected: "
                + ", ".join(current_settings["dns_servers"])
            )
            if ask_yes_no(
                "Do you want to start with these DNS servers for this location?", "y"
            ):
                location_cfg["dns_servers"] = current_settings["dns_servers"]

        location_cfg["dns_servers"] = prompt_for_selection(
            "Custom DNS Servers",
            items=current_settings.get("dns_servers", []),
            selected_items=location_cfg.get("dns_servers", []),
            allow_multiple=True,
            manual_entry_label="DNS servers",
        )
    else:
        location_cfg["dns_servers"] = []
        click.echo("DNS servers will be managed by DHCP for this location.")


def _configure_wpad_proxy():
    """Handle WPAD proxy configuration."""
    wpad_auto = ask_yes_no("\nTry to auto-detect WPAD URL (http://wpad/wpad.dat)?", "n")

    if not wpad_auto:
        return click.prompt(
            "Enter Auto Proxy Configuration URL", default="", show_default=False
        )

    click.echo(
        "\n⚠️  WARNING: WPAD auto-discovery can be a security risk on untrusted networks."
    )
    click.echo(
        "   Malicious networks could intercept your traffic via a rogue WPAD server."
    )

    if not ask_yes_no("Continue with WPAD auto-detection?", "n"):
        return click.prompt(
            "Enter Auto Proxy Configuration URL", default="", show_default=False
        )

    click.echo("Checking for WPAD auto-configuration...")
    wpad_url = "http://wpad/wpad.dat"

    try:
        import urllib.request

        req = urllib.request.Request(wpad_url)
        with urllib.request.urlopen(req, timeout=5) as response:
            wpad_content = response.read().decode("utf-8")
            if "function FindProxyForURL" in wpad_content:
                click.echo(f"✓ Found WPAD configuration at {wpad_url}")
                if ask_yes_no(f"Use {wpad_url}?", "y"):
                    return wpad_url
                else:
                    return click.prompt(
                        "Enter Auto Proxy Configuration URL",
                        default="",
                        show_default=False,
                    )
            else:
                click.echo("✗ No valid WPAD configuration found")
                return click.prompt(
                    "Enter Auto Proxy Configuration URL", default="", show_default=False
                )
    except Exception as e:
        click.echo(f"✗ Failed to fetch WPAD: {e}")
        return click.prompt(
            "Enter Auto Proxy Configuration URL", default="", show_default=False
        )


def _get_proxy_configuration():
    """Get proxy configuration from user."""
    click.echo("\nProxy configuration options:")
    click.echo("1. Auto-configuration URL (PAC/WPAD file)")
    click.echo("2. Manual HTTP/HTTPS proxy")
    click.echo("3. Manual SOCKS proxy")
    click.echo("4. No proxy")

    proxy_choice = click.prompt(
        "Choose proxy type", type=click.Choice(["1", "2", "3", "4"]), default="4"
    )

    if proxy_choice == "1":
        click.echo("\nCommon PAC/WPAD URLs:")
        click.echo("  • http://wpad/wpad.dat")
        click.echo("  • http://proxy.company.com/proxy.pac")
        click.echo("  • http://example.com/wpad.dat")
        return _configure_wpad_proxy()

    elif proxy_choice == "2":
        proxy_host = click.prompt("Enter HTTP proxy hostname or IP")
        proxy_port = click.prompt(
            "Enter HTTP proxy port", type=int, default=config.DEFAULT_PROXY_PORT
        )
        return f"http://{proxy_host}:{proxy_port}"

    elif proxy_choice == "3":
        proxy_host = click.prompt("Enter SOCKS proxy hostname or IP")
        proxy_port = click.prompt(
            "Enter SOCKS proxy port", type=int, default=config.DEFAULT_SOCKS_PORT
        )
        return f"socks://{proxy_host}:{proxy_port}"

    else:
        return ""


def _configure_proxy(location_cfg, current_settings):
    """Configure proxy settings for the location."""
    click.echo(click.style("\n--- Proxy Settings ---", bold=True))

    just_set_from_detection = False

    # Suggest current proxy if detected and not set
    if not location_cfg.get("proxy_url") and current_settings.get("proxy_url"):
        click.echo(f"Current proxy URL detected: {current_settings['proxy_url']}")
        if ask_yes_no("Use this proxy URL?", "y"):
            location_cfg["proxy_url"] = current_settings["proxy_url"]
            just_set_from_detection = True

    # If still not set, show choice menu to set one
    if not location_cfg.get("proxy_url"):
        location_cfg["proxy_url"] = _get_proxy_configuration()
    # If already set and not just from detection, prompt to change
    elif not just_set_from_detection:
        current_proxy = location_cfg.get("proxy_url", "")
        click.echo(f"Current proxy configuration: {current_proxy}")
        if ask_yes_no("Change proxy configuration?", "n"):
            location_cfg["proxy_url"] = _get_proxy_configuration()


def _configure_printer(location_cfg, available_printers):
    """Configure printer settings for the location."""
    click.echo(click.style("\n--- Default Printer ---", bold=True))
    selected_printer = location_cfg.get("printer")

    if not available_printers:
        click.echo("No printers found on this system.")
        location_cfg["printer"] = ""
    else:
        # Add a "None" option to the list for explicit de-selection
        printer_choices = available_printers + ["None"]

        try:
            default_idx = printer_choices.index(selected_printer) + 1
        except ValueError:
            default_idx = printer_choices.index("None") + 1

        click.echo("Select one printer from the list below:")
        for i, p in enumerate(printer_choices, 1):
            click.echo(f"  {i}: {p}")

        choice = click.prompt("Select by number", type=int, default=default_idx)

        if 1 <= choice <= len(available_printers):
            chosen_printer = available_printers[choice - 1]
            location_cfg["printer"] = chosen_printer
            click.echo(f"Printer set to: {chosen_printer}")
        elif choice == len(printer_choices):  # This is the "None" option
            location_cfg["printer"] = ""
            click.echo("No default printer will be set for this location.")
        else:
            click.echo("Invalid selection. Printer setting unchanged.", err=True)


def _configure_ntp(location_cfg):
    """Configure NTP server for the location."""
    click.echo(click.style("\n--- NTP Server ---", bold=True))
    location_cfg["ntp_server"] = click.prompt(
        "Enter NTP Server", default=location_cfg.get("ntp_server", "time.apple.com")
    )


def _configure_shell_proxy(cfg):
    """Configure shell proxy integration settings."""
    click.echo(click.style("\n--- Shell Proxy Integration ---", bold=True))
    click.echo(
        "Shell proxy integration automatically configures proxy environment variables\n"
        "for terminal applications when NetWatcher switches locations."
    )

    current_enabled = cfg.get("settings", {}).get("shell_proxy_enabled", True)
    shell_proxy_enabled = ask_yes_no(
        "Enable shell proxy integration?", "y" if current_enabled else "n"
    )

    return shell_proxy_enabled


def _save_configuration(
    cfg, location_name, location_cfg, shell_proxy_enabled, config_path
):
    """Save the configuration to file."""
    # Ensure the configuration always has the complete default structure
    if "settings" not in cfg:
        cfg["settings"] = config.DEFAULT_CONFIG["settings"].copy()

    # Update shell proxy setting
    cfg["settings"]["shell_proxy_enabled"] = shell_proxy_enabled

    if "locations" not in cfg:
        cfg["locations"] = {}

    # Ensure the default location exists for fallback settings
    if "default" not in cfg["locations"]:
        cfg["locations"]["default"] = config.DEFAULT_CONFIG["locations"][
            "default"
        ].copy()

    # Ensure SSIDs are strings before TOML serialization (prevents character array bug)
    if "ssids" in location_cfg:
        location_cfg["ssids"] = [str(ssid) for ssid in location_cfg["ssids"]]

    cfg["locations"][location_name] = location_cfg

    try:
        with open(config_path, "w") as f:
            toml.dump(cfg, f)
        click.echo(
            click.style(
                f"\nConfiguration saved successfully for location '{location_name}'!",
                fg="green",
            )
        )

        # If shell proxy was enabled, inform user how to set it up
        if shell_proxy_enabled:
            click.echo(
                "\nTo complete shell proxy setup, run: netwatcher shell-proxy setup"
            )

        return True
    except Exception as e:
        click.echo(f"Error saving configuration file: {e}", err=True)
        return False


@cli.command()
@click.option(
    "--location",
    "location_name",
    default=None,
    help="Name of the location to configure (e.g. 'Home', 'Office'). If not specified, you'll be prompted to enter one.",
)
def configure(location_name):
    """
    Interactively configure network settings for a location.

    This wizard guides you through setting up network configurations that will
    be automatically applied when NetWatcher detects you're connected to specific
    networks. You can configure:

    \b
    • Wi-Fi networks (SSIDs) that identify this location
    • DNS servers and search domains
    • Proxy settings (including auto-discovery)
    • Default printer
    • NTP server

    For best results, run this command while connected to the network you want
    to configure. NetWatcher will detect your current settings and offer to use
    them as defaults.

    Examples:
      netwatcher configure --location Home
      netwatcher configure  # Will prompt for location name
    """
    # --- Initial Setup & Config Loading ---
    config_path = config.get_config_path()
    cfg = config.load_config()

    click.echo(
        click.style(
            "--- NetWatcher Configuration Wizard ---", bold=True, underline=True
        )
    )

    if not config_path.exists():
        click.echo(
            f"No configuration file found. A new one will be created at: \n{config_path}"
        )
        if not ask_yes_no("Do you want to continue?", "y"):
            return
        config_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        click.echo(f"Loaded existing configuration from:\n{config_path}")

    click.echo(
        "\nTip: For best results, run this wizard while connected to the network you wish to configure."
    )

    # --- Discover Network Settings ---
    click.echo("\nDiscovering current network environment...")
    current_settings = _discover_current_network_settings()
    if current_settings is None:
        return

    available_ssids = get_available_ssids()
    available_printers = get_available_printers()

    # --- Location Selection ---
    location_name = _get_location_name(cfg, location_name)
    if location_name is None:
        return

    # --- Get or Create Location Config ---
    location_cfg = copy.deepcopy(
        cfg.get("locations", {}).get(location_name, config.DEFAULT_LOCATION_CONFIG)
    )

    click.echo(
        click.style(
            f"\n--- Configuring Location: {location_name} ---",
            bold=True,
            underline=True,
        )
    )

    # --- Configure each section ---
    _configure_ssids(location_cfg, current_settings, available_ssids)
    _configure_dns(location_cfg, current_settings)
    _configure_proxy(location_cfg, current_settings)
    _configure_printer(location_cfg, available_printers)
    _configure_ntp(location_cfg)
    shell_proxy_enabled = _configure_shell_proxy(cfg)

    # --- Save Configuration ---
    _save_configuration(
        cfg, location_name, location_cfg, shell_proxy_enabled, config_path
    )


@cli.command()
@click.option(
    "--debug",
    is_flag=True,
    help="Enable verbose debug logging to see detailed network detection and setting application.",
)
def test(debug):
    """
    Test network detection and apply settings for the current location.

    This command performs the same network detection and settings application
    that the background service does automatically. It will:

    \b
    1. Detect your current network (Wi-Fi SSID, DNS servers, search domains)
    2. Find a matching location in your configuration
    3. Apply the appropriate settings for that location
    4. Show detailed logging of what actions were taken

    This is useful for:
    • Testing your configuration after making changes
    • Troubleshooting network detection issues
    • Manually triggering settings application
    • Seeing exactly what NetWatcher would do automatically

    Use --debug for verbose output showing network detection details.
    """
    # Import watcher here to avoid circular dependency issues at startup
    from .logging_config import setup_logging

    # Setup logging to show INFO messages, and DEBUG if the flag is passed.
    # Force reinit to ensure debug setting takes effect even if logging was already initialized
    setup_logging(debug=debug, force_reinit=True)

    click.echo("Running test...")
    click.echo("Evaluating current network state and applying settings.")

    # This function now contains the core logic
    # It will log its actions, which is what we want for a test command.
    try:
        # Clear network cache for fresh test data
        from .network import clear_cache

        clear_cache()

        cfg = config.load_config()
        if not cfg.get("locations"):
            click.echo(
                click.style(
                    "Configuration is empty. Run `netwatcher configure` first.",
                    fg="yellow",
                )
            )
            return

        location_name, vpn_active, vpn_details = check_and_apply_location_settings(cfg)

        # Also fetch and display connection details (for completeness)
        try:
            from .external import get_connection_details

            connection_info = get_connection_details(silent=False)
            click.echo(
                f"\nConnection Details: IP={connection_info['ip']}, "
                f"Location={connection_info['city']}, {connection_info['region']}, "
                f"ISP={connection_info['isp']}"
            )
        except Exception as e:
            click.echo(f"Note: Could not fetch connection details: {e}")

        if location_name:
            click.echo(
                click.style(
                    f"Test complete. Settings applied for location: '{location_name}'",
                    fg="green",
                )
            )
        else:
            click.echo(
                click.style(
                    "Test complete. No matching location found for the current network.",
                    fg="yellow",
                )
            )
    except Exception as e:
        click.echo(click.style(f"An error occurred during the test: {e}", fg="red"))


# --- Service Management Commands ---


@cli.group()
def service():
    """
    Manage the NetWatcher background service (launchd agent).

    The background service automatically monitors network changes and applies
    appropriate settings when you connect to different networks. Commands:

    \b
    • install  - Install and start the background service
    • uninstall - Stop and remove the background service
    • start    - Start the background service
    • stop     - Stop the background service
    • status   - Check if the service is running

    The service runs as a macOS Launch Agent, so it starts automatically when
    you log in and runs in the background monitoring network changes.
    """
    if platform.system() != "Darwin":
        click.echo("Service management is only supported on macOS.", err=True)
        sys.exit(1)


def _check_config_and_install_status(expect_installed):
    """Helper to check if config exists and if service is installed."""
    plist_path = config.LAUNCH_AGENT_PLIST_PATH
    config_path = config.get_config_path()

    if not config_path.exists():
        click.echo(
            "Configuration file not found. Please run `netwatcher configure` first.",
            err=True,
        )
        return False

    if expect_installed and not plist_path.exists():
        click.echo(
            "Service is not installed. Please run `netwatcher service install` first.",
            err=True,
        )
        return False
    elif not expect_installed and plist_path.exists():
        click.echo("Service is already installed.", err=True)
        return False

    return True


@service.command()
def start():
    """
    Start the NetWatcher background service.

    This loads and starts the macOS Launch Agent that monitors network changes.
    The service will automatically detect network changes and apply appropriate
    settings based on your configured locations.

    Requires the service to already be installed.
    """
    if not _check_config_and_install_status(expect_installed=True):
        return
    click.echo("Starting NetWatcher service...")
    plist_path = config.LAUNCH_AGENT_PLIST_PATH
    run_command(["launchctl", "load", "-w", str(plist_path)])
    click.echo("Service started.")


@service.command()
def stop():
    """
    Stop the NetWatcher background service.

    This stops the background service from monitoring network changes, but
    leaves it installed. You can restart it later with 'netwatcher service start'.

    Your network settings will remain as they were when the service stopped.
    """
    if not _check_config_and_install_status(expect_installed=True):
        return
    click.echo("Stopping NetWatcher service...")
    plist_path = config.LAUNCH_AGENT_PLIST_PATH
    run_command(["launchctl", "unload", "-w", str(plist_path)])
    click.echo("Service stopped.")


@service.command()
def status():
    """
    Check the status of the NetWatcher background service.

    Shows whether the service is installed, loaded, and currently running.
    Also provides information about where to find logs if the service has
    encountered any issues.
    """
    if not _check_config_and_install_status(expect_installed=True):
        return
    click.echo("Checking service status...")
    label = config.LAUNCH_AGENT_LABEL
    output = run_command(["launchctl", "list"], capture=True)
    if output and label in output:
        # The output of `launchctl list` is complex. A simple string search is a good indicator.
        # A more robust check could parse the output line for the specific service.
        click.echo(f"Service '{label}' is loaded.")
        # We can't easily get the PID and status from `launchctl list` anymore.
        # A simple check is to see if the process is running.
        try:
            # pgrep returns 0 if a process is found, 1 otherwise.
            # Look for the specific command pattern that matches our watcher
            subprocess.run(
                ["pgrep", "-f", "src.watcher"], check=True, capture_output=True
            )
            click.echo(click.style("Process is RUNNING.", fg="green"))
        except subprocess.CalledProcessError:
            click.echo(click.style("Process is STOPPED.", fg="yellow"))
            click.echo("The service is loaded but the process is not running.")
            click.echo("It may have crashed. Check logs for details:")
            click.echo(f"  tail -f {config.LOG_FILE}")

    else:
        click.echo(f"Service '{label}' is not loaded.")


@service.command()
def install():
    """
    Install and start the NetWatcher background service.

    This creates a macOS Launch Agent that automatically:
    • Starts when you log in
    • Monitors network changes in the background
    • Applies appropriate settings when you connect to configured networks

    The service will be installed to ~/Library/LaunchAgents/ and started
    immediately. Logs are written to ~/Library/Logs/netwatcher.log.

    Requires a valid configuration (run 'netwatcher configure' first).
    """
    if not _check_config_and_install_status(expect_installed=False):
        return

    click.echo("Installing NetWatcher service...")
    plist_path = config.LAUNCH_AGENT_PLIST_PATH
    plist_path.parent.mkdir(parents=True, exist_ok=True)

    # Find the path to the currently running Python executable
    python_executable = sys.executable
    # Find the path to the root of the netwatcher-py project
    # This assumes cli.py is in src/
    project_root = Path(__file__).parent.parent

    # The command should run the watcher main function directly to avoid module import warnings
    command_to_run = [python_executable, "-c", "from src.watcher import main; main()"]

    try:
        with importlib.resources.path(
            "src", "com.user.netwatcher.plist"
        ) as template_path:
            with open(template_path, "r") as f:
                plist_template = f.read()

        # Replace placeholders
        plist_content = plist_template.replace(
            "{{PYTHON_EXECUTABLE}}", python_executable
        )
        plist_content = plist_content.replace(
            "{{COMMAND_TO_RUN}}",
            " ".join(f"<string>{c}</string>" for c in command_to_run),
        )
        plist_content = plist_content.replace(
            "{{WORKING_DIRECTORY}}", str(project_root)
        )
        plist_content = plist_content.replace(
            "{{LAUNCH_AGENT_LABEL}}", config.LAUNCH_AGENT_LABEL
        )

        with open(plist_path, "w") as f:
            f.write(plist_content)

        click.echo(f"Created launch agent plist at: {plist_path}")

        # Load the service
        run_command(["launchctl", "load", "-w", str(plist_path)])
        click.echo(
            click.style("Service installed and started successfully.", fg="green")
        )

    except FileNotFoundError:
        click.echo(
            "Error: com.user.netwatcher.plist template not found.",
            err=True,
        )
    except Exception as e:
        click.echo(f"An error occurred during installation: {e}", err=True)


# --- Service Management Helper Functions ---


def _unload_and_remove_service():
    """Unload and remove the LaunchAgent service. Returns True if successful."""
    plist_path = config.LAUNCH_AGENT_PLIST_PATH

    try:
        # Unload the service first
        run_command(["launchctl", "unload", "-w", str(plist_path)])
        click.echo("Service stopped.")

        # Remove the plist file
        plist_path.unlink()
        click.echo("Removed launch agent plist file.")
        click.echo(click.style("Service uninstalled successfully.", fg="green"))
        return True

    except FileNotFoundError:
        click.echo("Service was not installed (plist not found).", err=True)
        return False
    except Exception as e:
        click.echo(f"An error occurred during uninstallation: {e}", err=True)
        return False


def _cleanup_user_files():
    """Offer to clean up configuration and log files."""
    config_dir = config.get_config_path().parent
    log_file = config.LOG_FILE

    cleanup_items = []
    if config_dir.exists():
        cleanup_items.append(f"Configuration directory: {config_dir}")
    if log_file.exists():
        cleanup_items.append(f"Log file: {log_file}")

    if not cleanup_items:
        click.echo("No additional files to clean up.")
        return

    click.echo("\nThe following NetWatcher files remain on your system:")
    for item in cleanup_items:
        click.echo(f"  • {item}")

    if not ask_yes_no(
        "\nWould you like to remove these files for a complete cleanup?", default="n"
    ):
        click.echo("Configuration and log files preserved.")
        return

    import shutil

    try:
        removed_items = []
        if config_dir.exists():
            shutil.rmtree(config_dir)
            removed_items.append("Configuration directory")
        if log_file.exists():
            log_file.unlink()
            removed_items.append("Log file")

        if removed_items:
            click.echo(f"Removed: {', '.join(removed_items)}")
            click.echo(click.style("Complete cleanup finished.", fg="green"))

    except Exception as e:
        click.echo(f"Warning: Could not remove some files: {e}", err=True)


@service.command()
def uninstall():
    """
    Stop and completely remove the NetWatcher background service.

    This stops the background service and removes the Launch Agent plist file.
    Optionally removes configuration files and logs for a complete cleanup.

    To temporarily stop the service without removing it, use 'netwatcher service stop' instead.
    """
    if not _check_config_and_install_status(expect_installed=True):
        return

    click.echo("Uninstalling NetWatcher service...")

    if _unload_and_remove_service():
        _cleanup_user_files()


# --- Shell Proxy Management Commands ---


@cli.group()
def shell_proxy():
    """
    Manage shell proxy integration for terminal applications.

    Shell proxy integration automatically configures proxy environment variables
    for terminal applications when NetWatcher switches between locations. Commands:

    \b
    • setup  - Set up shell proxy integration for detected shells
    • remove - Remove shell proxy integration from all shells
    • status - Show current shell proxy integration status

    The integration works by:
    • Adding source commands to your shell configuration files
    • Creating proxy environment files when proxies are active
    • Automatically parsing PAC/WPAD files when needed
    • Cleaning up proxy settings when switching locations
    """
    pass


@shell_proxy.command()
@click.option(
    "--config-file",
    default=None,
    help="Path to configuration file (default: ~/.config/netwatcher/config.toml)",
)
def setup(config_file):
    """Set up shell proxy integration for detected shells."""
    try:
        from .network.shell_proxy import (
            setup_all_shell_integrations,
            detect_user_shells,
            ensure_shell_proxy_config,
        )

        # Load config to check if shell proxy is enabled
        if config_file:
            click.echo(f"Custom config file not supported yet: {config_file}")
            click.echo("Using default config location")

        cfg = config.load_config()

        # Ensure config options are set up
        if not ensure_shell_proxy_config():
            click.echo(
                click.style("❌ Failed to set up shell proxy configuration", fg="red")
            )
            return

        # Reload config after ensuring options are set up
        cfg = config.load_config()

        if not cfg.get("settings", {}).get("shell_proxy_enabled", True):
            click.echo("Shell proxy integration is disabled in configuration.")
            click.echo("To enable: set shell_proxy_enabled = true in config.toml")
            return

        detected_shells, primary_shell = detect_user_shells()
        click.echo(f"Detected shells: {', '.join(detected_shells)}")
        click.echo(f"Primary shell: {primary_shell}")

        if setup_all_shell_integrations(cfg):
            click.echo(
                click.style(
                    "✅ Shell proxy integration set up successfully", fg="green"
                )
            )
            click.echo("\nShell proxy integration will:")
            click.echo("• Automatically configure proxy variables for terminal apps")
            click.echo("• Parse PAC/WPAD files when needed")
            click.echo("• Apply settings based on your current location")
            click.echo("• Clean up proxy settings when switching locations")
            click.echo("\nConfiguration added to ~/.config/netwatcher/config.toml")
            click.echo("To disable: set shell_proxy_enabled = false in config.toml")
            click.echo("\nRestart your shell or open a new terminal to apply changes.")
        else:
            click.echo(
                click.style("❌ Failed to set up shell proxy integration", fg="red")
            )

    except Exception as e:
        click.echo(f"Error setting up shell proxy integration: {e}", err=True)


@shell_proxy.command()
def remove():
    """Remove shell proxy integration from all shells."""
    try:
        from .network.shell_proxy import (
            remove_all_shell_integrations,
            cleanup_shell_proxy_files,
            detect_user_shells,
        )

        detected_shells, _ = detect_user_shells()
        click.echo(
            f"Removing NetWatcher proxy integration from: {', '.join(detected_shells)}"
        )

        # This now automatically disables shell_proxy_enabled in config
        remove_all_shell_integrations()
        cleanup_shell_proxy_files()

        click.echo(
            click.style("✅ Shell proxy integration removed successfully", fg="green")
        )
        click.echo("• Disabled shell_proxy_enabled in configuration")
        click.echo("• Removed integration from shell config files")
        click.echo("• Cleaned up proxy environment files")
        click.echo(
            "Restart your shell or open a new terminal for changes to take effect."
        )

    except Exception as e:
        click.echo(f"Error removing shell proxy integration: {e}", err=True)


@shell_proxy.command()
@click.option(
    "--config-file",
    default=None,
    help="Path to configuration file (default: ~/.config/netwatcher/config.toml)",
)
def show_status(config_file):
    """Show shell proxy integration status."""
    try:
        from .network.shell_proxy import detect_user_shells
        from pathlib import Path

        # Load config
        if config_file:
            click.echo(f"Custom config file not supported yet: {config_file}")
            click.echo("Using default config location")

        cfg = config.load_config()

        detected_shells, primary_shell = detect_user_shells()
        click.echo(f"Detected shells: {', '.join(detected_shells)}")
        click.echo(f"Primary shell: {primary_shell}")

        # Check configuration
        shell_proxy_enabled = cfg.get("settings", {}).get("shell_proxy_enabled", True)
        configured_shells = cfg.get("settings", {}).get(
            "shell_proxy_shells", detected_shells
        )

        click.echo("\nConfiguration:")
        click.echo(f"• shell_proxy_enabled: {shell_proxy_enabled}")
        click.echo(f"• shell_proxy_shells: {configured_shells}")

        # Check integration status
        click.echo("\nIntegration Status:")
        home = Path.home()
        shell_configs = {
            "bash": home / ".bash_profile",
            "zsh": home / ".zshrc",
            "tcsh": home / ".tcshrc",
            "csh": home / ".cshrc",
            "fish": home / ".config/fish/config.fish",
        }

        for shell in detected_shells:
            config_file = shell_configs.get(shell)
            if config_file and config_file.exists():
                content = config_file.read_text()
                if "NetWatcher proxy configuration" in content:
                    click.echo(f"• {shell}: ✅ Integrated")
                else:
                    click.echo(f"• {shell}: ❌ Not integrated")
            else:
                click.echo(f"• {shell}: ❓ Config file not found")

        # Check proxy environment files
        click.echo("\nProxy Environment Files:")
        cache_dir = Path.home() / ".config/netwatcher"
        proxy_files = {
            "bash/zsh": cache_dir / "proxy.env.sh",
            "tcsh/csh": cache_dir / "proxy.env.csh",
            "fish": cache_dir / "proxy.env.fish",
        }

        for name, proxy_file in proxy_files.items():
            if proxy_file.exists():
                click.echo(f"• {name}: ✅ {proxy_file}")
            else:
                click.echo(f"• {name}: ❌ Not found")

    except Exception as e:
        click.echo(f"Error checking shell proxy status: {e}", err=True)


@cli.command()
def check():
    """
    Check if passwordless sudo is configured for network commands.

    NetWatcher requires passwordless sudo access to run networksetup, systemsetup,
    lpadmin, and sntp commands that modify DNS, proxy, printer, and time settings.
    This command verifies that sudo is properly configured without prompting for a password.

    If this check fails, you'll need to configure sudo privileges for your user.
    """
    click.echo("Checking sudo permissions for NetWatcher commands...")

    # Commands that NetWatcher needs to run with sudo
    required_commands = [
        ("/usr/sbin/networksetup", ["-listallnetworkservices"]),
        ("/usr/sbin/systemsetup", ["-getnetworktimeserver"]),
        ("/usr/sbin/lpadmin", ["-h"]),  # Help option doesn't modify anything
        ("/usr/bin/sntp", ["-h"]),  # Help option doesn't modify anything
        ("/bin/mkdir", ["/etc/resolver"]),
        ("/usr/bin/tee", ["/etc/resolver/netwatcher-test.tmp"]),
        ("/bin/rm", ["-f", "/etc/resolver/netwatcher-test.tmp"]),
        ("/usr/bin/dscacheutil", ["-flushcache"]),
        ("/usr/bin/killall", ["-HUP", "mDNSResponder"]),
    ]

    all_passed = True

    for cmd_path, test_args in required_commands:
        cmd_name = cmd_path.split("/")[-1]
        click.echo(f"  Testing {cmd_name}...", nl=False)

        input_content = None
        if cmd_path == "/usr/bin/tee":
            input_content = (
                "# This is a test file created by NetWatcher check. Safe to remove.\n"
            )

        try:
            result = subprocess.run(
                ["sudo", "-n"] + [cmd_path] + test_args,
                capture_output=True,
                text=True,
                timeout=config.IPINFO_TIMEOUT,  # Use consistent timeout
                input=input_content,
            )

            # For most commands, return code 0 means success
            # For lpadmin -h and sntp -h, they might return non-zero but that's OK if no password was required
            if result.returncode == 0 or (
                "a password is required" not in result.stderr.lower()
                and "sudo:" not in result.stderr.lower()
            ):
                click.echo(click.style(" ✓", fg="green"))
            else:
                click.echo(click.style(" ✗", fg="red"))
                if "a password is required" in result.stderr.lower():
                    click.echo(f"    Error: {cmd_name} requires a password")
                else:
                    click.echo(f"    Error: {result.stderr.strip()}")
                all_passed = False

        except subprocess.TimeoutExpired:
            click.echo(click.style(" ✗ (timeout)", fg="red"))
            click.echo(
                f"    Error: {cmd_name} check timed out (likely requires password)"
            )
            all_passed = False
        except FileNotFoundError:
            click.echo(click.style(" ✗ (not found)", fg="red"))
            click.echo(f"    Error: {cmd_path} not found")
            all_passed = False
        except Exception as e:
            click.echo(click.style(" ✗ (error)", fg="red"))
            click.echo(f"    Error: {e}")
            all_passed = False

    click.echo()  # Blank line

    if all_passed:
        click.echo(
            click.style("✓ All sudo permissions are correctly configured!", fg="green")
        )
        click.echo("NetWatcher should work without password prompts.")
    else:
        click.echo(click.style("✗ Sudo configuration needs to be updated.", fg="red"))
        click.echo("\nTo fix this, add the following to your sudo configuration:")
        click.echo("  1. Run: sudo visudo -f /etc/sudoers.d/$USER")
        click.echo("  2. Add these lines:")
        click.echo(
            "     # Allow NetWatcher to run required network commands without a password"
        )
        click.echo(
            "     Cmnd_Alias NETWATCHER_CMDS = /usr/sbin/networksetup, /usr/sbin/systemsetup, /usr/sbin/lpadmin, /usr/bin/sntp, /bin/mkdir /etc/resolver, /bin/rm /etc/resolver/*, /usr/bin/tee /etc/resolver/*, /usr/bin/dscacheutil -flushcache, /usr/bin/killall -HUP mDNSResponder"
        )
        click.echo("     $USER ALL=(ALL) NOPASSWD: NETWATCHER_CMDS")
        click.echo("\nSee the README for detailed setup instructions.")


if __name__ == "__main__":
    cli()
