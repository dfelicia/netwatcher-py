"""
Configuration management for NetWatcher.

This module handles loading, validation, and default configuration values
for the NetWatcher application.
"""

import toml
from pathlib import Path

# --- App Constants ---
APP_NAME = "netwatcher"
PLIST_FILENAME = f"com.user.{APP_NAME}.plist"
LAUNCH_AGENT_LABEL = f"com.user.{APP_NAME}"
LAUNCH_AGENT_DIR = Path.home() / "Library/LaunchAgents"
LAUNCH_AGENT_PLIST_PATH = LAUNCH_AGENT_DIR / PLIST_FILENAME
LOG_DIR = Path.home() / "Library" / "Logs"
LOG_FILE = LOG_DIR / "netwatcher.log"

# --- Logging Constants ---
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# --- Network Constants ---
DEFAULT_NTP_SERVER = "time.apple.com"
DEFAULT_DEBOUNCE_SECONDS = 5
DEFAULT_DEBUG = False

# --- External Service Constants ---
IPINFO_TIMEOUT = 10  # seconds
DNS_RESOLUTION_TIMEOUT = 5  # seconds
IPINFO_API_URL = "http://ip-api.com/json"  # Primary IP info service

# --- Network Operation Constants ---
WIFI_SCAN_RETRY_COUNT = 5  # Number of times to retry Wi-Fi scanning
LOCATION_AUTH_POLL_COUNT = 10  # Number of times to poll for location authorization
LOCATION_AUTH_POLL_INTERVAL = 1  # Seconds between location authorization polls
WIFI_SCAN_RETRY_DELAY_BASE = 2  # Base delay for exponential backoff in Wi-Fi scanning

# --- Default Port Numbers ---
DEFAULT_HTTP_PORT = 80
DEFAULT_HTTPS_PORT = 443
DEFAULT_SOCKS_PORT = 1080
DEFAULT_PROXY_PORT = 8080

# Default configuration for a single location. Used for creating new locations.
DEFAULT_LOCATION_CONFIG = {
    "ssids": [],
    "dns_search_domains": [],
    "dns_servers": [],
    "proxy_url": "",
    "printer": "",
    "ntp_server": DEFAULT_NTP_SERVER,
}

# Default configuration for the application
DEFAULT_CONFIG = {
    "settings": {
        "debug": DEFAULT_DEBUG,
        "debounce_seconds": DEFAULT_DEBOUNCE_SECONDS,
    },
    "locations": {
        # The 'default' location acts as a fallback and a template.
        "default": DEFAULT_LOCATION_CONFIG.copy()
    },
}


def get_config_path():
    """Gets the path to the configuration file."""
    return Path.home() / ".config" / "netwatcher" / "config.toml"


def load_config():
    """Loads the configuration from the TOML file."""
    path = get_config_path()
    if not path.exists():
        # Create a default config if one doesn't exist
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            toml.dump(DEFAULT_CONFIG, f)
        return DEFAULT_CONFIG

    with open(path, "r") as f:
        config = toml.load(f)

    # Import logging from our centralized module
    from .logging_config import get_logger

    logger = get_logger(__name__)
    logger.debug(f"Loaded locations: {list(config.get('locations', {}).keys())}")
    return config


if __name__ == "__main__":
    config = load_config()
    import json

    print(json.dumps(config, indent=4))
