# NetWatcher

A macOS utility that automatically reconfigures system settings when your network environment changes. It runs as a menu bar application and background service, monitoring for network changes and applying predefined settings for different locations.

📖 **[Visual Guide: How NetWatcher Works](https://dfelicia.github.io/netwatcher-py/netwatcher_visual_guide.html)** - Interactive visual explanation of the architecture and flow

## How It Works

NetWatcher is built with Python and uses native macOS frameworks for reliable, event-driven network automation:

- **Core Engine**: Leverages the `SystemConfiguration` framework to receive real-time notifications from macOS whenever network settings change.
- **Menu Bar App**: A `rumps`-based application provides a simple icon in the macOS menu bar, showing current connection status and location, with the ability to manually trigger settings re-application.
- **Configuration**: All settings are defined in a simple `config.toml` file, making it easy to manage different network profiles for home, office, or public Wi-Fi.
- **Background Service**: The application runs as a persistent `LaunchAgent`, ensuring it starts automatically at login and runs silently in the background.
- **CLI Management**: A comprehensive command-line interface provides easy installation, uninstallation, configuration, and service management.

## Features

- **Real-time network monitoring** using macOS SystemConfiguration framework
- **Menu bar integration** with current location and connection status display
- **Automatic network configuration** including multi-interface support and dynamic /etc/resolver for VPN search domains:
  - DNS servers and search domains
  - Proxy settings (PAC/WPAD files, HTTP/HTTPS/SOCKS proxies) with advanced parsing via pacparser for precise detection
  - **Shell proxy configuration** - Automatic proxy setup for terminal applications (bash, zsh, tcsh/csh, fish)
  - Default printer selection
  - Network Time Protocol (NTP) server configuration
- **VPN detection and status display** (configurable for various VPN clients)
- **One-click testing** from the menu bar with log file integration
- **Comprehensive logging** for debugging and monitoring

## Prerequisites

Before you begin, ensure you have the following:

1. **macOS**: This tool is designed exclusively for macOS (tested on macOS 10.15+)
2. **Python**: Only Apple's shipped version of Python 3 can be used (due to code signing requirements for location services)
3. **Administrator access**: Required for network configuration changes

## Setup and Installation

### Step 1: Clone the Repository

```bash
git clone https://github.com/dfelicia/netwatcher-py.git
cd netwatcher-py
```

### Step 2: Create a Virtual Environment & Install Dependencies

**Important: Wi-Fi Scanning Requires System Python**

For Wi-Fi network discovery to work during configuration, you **must** use the system Python interpreter provided by Apple. This is the only version with the proper code signature that macOS trusts for Wi-Fi scanning.

```bash
# Create and activate a virtual environment using Apple's system Python
/usr/bin/python3 -m venv .venv
source .venv/bin/activate

# Install the project and dependencies
pip install --upgrade pip setuptools
pip install --editable .
```

This ensures that Wi-Fi scanning during the `netwatcher configure` step works correctly.

### Step 3: Configure Passwordless Sudo

NetWatcher requires elevated privileges to modify system network settings. Configure passwordless execution for required commands:

1. Create a new sudoers file for your user (replace `your_username`):
   ```bash
   sudo touch /etc/sudoers.d/your_username
   ```

2. Edit the file with `visudo` to ensure syntax validation:
   ```bash
   sudo visudo -f /etc/sudoers.d/your_username
   ```

3. Add the following lines (replace `your_username` with your actual macOS username):
   ```
   # Allow NetWatcher to run required network commands without a password
   Cmnd_Alias NETWATCHER_CMDS = /usr/sbin/networksetup, /usr/sbin/systemsetup, /usr/sbin/lpadmin, /usr/bin/sntp, /bin/mkdir /etc/resolver, /bin/rm /etc/resolver/*, /usr/bin/tee /etc/resolver/*, /usr/bin/dscacheutil -flushcache
   your_username ALL=(ALL) NOPASSWD: NETWATCHER_CMDS
   ```

4. Verify the configuration:
   ```bash
   netwatcher check
   ```

### Step 4: Configure Your Network Locations

Run the interactive configuration wizard to create your `config.toml` file:

```bash
netwatcher configure
```

The configuration wizard will guide you through setting up network locations and will offer to configure shell proxy integration for terminal applications.

The configuration will be saved to `~/.config/netwatcher/config.toml`.

### Step 5: Install the Service

Install the LaunchAgent to have NetWatcher run automatically in the background:

```bash
netwatcher service install
```

The application will start automatically and you'll see the NetWatcher icon in your menu bar. You can monitor its activity in the log file at `~/Library/Logs/netwatcher.log`.

## Upgrading NetWatcher

To update to the latest version:

```bash
# Navigate to your NetWatcher directory and pull changes
cd /path/to/netwatcher-py && git pull origin main

# Activate virtual environment and reinstall
source .venv/bin/activate
pip install --editable .

# Restart the service to apply changes
netwatcher service stop
netwatcher service start
```

## Using the CLI

NetWatcher provides a command-line interface for configuration and service management:

- **Configure network locations**: `netwatcher configure`
- **Test current network detection**: `netwatcher test` (use `--debug` for verbose output)
- **Install the background service**: `netwatcher service install`
- **Start the background service**: `netwatcher service start`
- **Stop the background service**: `netwatcher service stop`
- **Check service status**: `netwatcher service status`
- **Uninstall the background service**: `netwatcher service uninstall`
- **Set up shell proxy integration**: `netwatcher shell-proxy setup`
- **Check shell proxy status**: `netwatcher shell-proxy status`
- **Remove shell proxy integration**: `netwatcher shell-proxy remove`
- **Check system permissions**: `netwatcher check`

## Using the Menu Bar App

Once installed, NetWatcher runs as a menu bar application showing:

- **Current location**: The matched network profile
- **Connection details**: IP address, city, region, ISP
- **VPN status**: If configured and connected
- **Test Configuration**: Manually trigger settings application
- **Logs**: Click notifications to open log files in Console.app

## Configuration File Explained

Your settings are stored in `~/.config/netwatcher/config.toml`. Here's what each setting does:

### Location Settings

- `ssids = ["MyWiFi", "AnotherWiFi"]`: Wi-Fi network names (SSIDs) for this location
- `dns_servers = ["8.8.8.8", "1.1.1.1"]`: DNS servers to use (empty list uses DHCP)
- `dns_search_domains = ["mycompany.com"]`: DNS search domains for this location (these domains are used for both location detection and network configuration)
- `proxy_url = "http://proxy.company.com/proxy.pac"`: Proxy configuration - supports PAC/WPAD URLs, HTTP proxies (http://host:port), HTTPS proxies (https://host:port), or SOCKS proxies (socks://host:port)

⚠️ **Security Note**: WPAD (Web Proxy Auto-Discovery) should only be used on trusted networks. On untrusted networks, malicious actors could provide rogue WPAD configurations to intercept your traffic. NetWatcher will warn you before using WPAD auto-detection.
- `printer = "Office_Printer"`: Default printer name (must match System Settings)
- `ntp_server = "time.company.com"`: Network Time Protocol (NTP) server

### VPN Detection

NetWatcher automatically detects VPN connections and can provide status information for supported VPN clients:

- **Cisco VPN**: Auto-detected when service ID contains "com.cisco" and VPN binary is found
- **Generic VPN**: Detected via utun interface routing
- **Status Display**: Shows connection details in menu bar when available

No manual VPN configuration is required - the tool will automatically detect and display VPN status when active.

### Global Settings

The `[settings]` section in your config.toml controls application-wide behavior:

- `debug = false`: Enables DEBUG logging for the background service (set to true for detailed logs)
- `debounce_seconds = 5`: Wait time before applying settings after network change
- `shell_proxy_enabled = true`: Enable shell proxy integration (added by `netwatcher shell-proxy setup`)

**To enable debug logging:**
1. Set `debug = true` in `~/.config/netwatcher/config.toml`
2. Restart the service: `netwatcher service stop && netwatcher service start`
3. Monitor logs: `tail -f ~/Library/Logs/netwatcher.log`

For CLI commands, you can also use the `--debug` flag: `netwatcher test --debug`

### Example Configuration

Complete example showing multiple locations:

```toml
[settings]
debug = false
debounce_seconds = 5
shell_proxy_enabled = true

[locations.Home]
dns_servers = []  # Use DHCP
dns_search_domains = ["home.arpa"]
proxy_url = ""
printer = "Home_Printer"
ntp_server = "time.apple.com"

[locations.Office]
ssids = ["CorpWiFi"]
dns_servers = ["10.1.1.10", "10.1.1.11"]
dns_search_domains = ["corp.company.com"]
proxy_url = "http://proxy.company.com/proxy.pac"  # PAC file
printer = "Office_MFP"
ntp_server = "time.company.com"

[locations.RemoteOffice]
ssids = ["RemoteWiFi"]
dns_servers = ["8.8.8.8", "1.1.1.1"]
dns_search_domains = ["remote.company.com"]
proxy_url = "http://proxy.remote.com:8080"  # Manual HTTP proxy
printer = ""
ntp_server = "pool.ntp.org"

[locations.default]
dns_servers = ["8.8.8.8", "1.1.1.1"]
dns_search_domains = []
proxy_url = ""
printer = ""
ntp_server = "time.apple.com"
```

**Note**: VPN detection and status display is automatic - no manual configuration required.

## Shell Proxy Integration

NetWatcher can automatically configure proxy environment variables for terminal applications, eliminating the need to manually set proxy variables in your shell configuration files.

### Setup Commands

```bash
# Set up shell proxy integration for all detected shells
netwatcher shell-proxy setup

# Check the status of shell proxy integration
netwatcher shell-proxy status

# Remove shell proxy integration if needed
netwatcher shell-proxy remove
```

### How It Works

Shell proxy integration provides:
- **Automatic proxy configuration** for terminal applications (`curl`, `wget`, `pip`, `npm`, `brew`, etc.)
- **PAC/WPAD file parsing** to extract actual proxy servers automatically
- **Multi-shell support** for bash, zsh, tcsh/csh, and fish shells
- **Smart bypass domains** including localhost and domains managed by NetWatcher
- **Interactive-only activation** - proxy settings only apply to interactive shell sessions
- **Location-aware cleanup** - proxy settings are automatically removed when switching to locations without proxies

### Environment Variables Set

- `http_proxy`, `https_proxy`, `ftp_proxy`, `all_proxy` - Standard proxy variables
- `HTTP_PROXY`, `HTTPS_PROXY`, `FTP_PROXY`, `ALL_PROXY` - Legacy uppercase versions
- `rsync_proxy` - Special format for rsync (host:port without protocol)
- `no_proxy`, `NO_PROXY` - Bypass addresses for local and corporate domains

You can optionally specify which shells to configure by adding `shell_proxy_shells = ["bash", "zsh", "fish"]` to the `[settings]` section in your config.toml.

## Architecture

NetWatcher uses a modular architecture for maintainability and clarity:

### Core Components
- **`src/cli.py`**: Command-line interface and service management
- **`src/watcher.py`**: Menu bar application and network monitoring
- **`src/config.py`**: Configuration file handling and constants
- **`src/com.user.netwatcher.plist`**: macOS LaunchAgent configuration template

### Modular Structure
NetWatcher is organized into focused modules:

#### **`src/network/`** - Network Operations
- **`detection.py`**: Network state detection (SSID, DNS, VPN status)
- **`interfaces.py`**: Network interface and service management
- **`configuration.py`**: Network settings application (DNS, proxy, NTP)
- **`proxy_detection.py`**: Centralized system proxy detection (PAC, HTTP, HTTPS, SOCKS)
- **`pac_parser.py`**: PAC file parsing and proxy extraction
- **`shell_proxy.py`**: Shell environment proxy configuration management
- **`cache.py`**: Network state caching for performance optimization

#### **`src/external/`** - External Service Integrations
- **`ipinfo.py`**: Connection details from ip-api.com with proxy support
- **`vpn.py`**: VPN client integrations (Cisco, generic utun detection)

#### **`src/location/`** - Location Logic
- **`matching.py`**: Network environment to location profile matching
- **`settings.py`**: Location-specific settings application

#### **`src/utils/`** - Utility Functions
- **`commands.py`**: Command execution with error handling
- **`native.py`**: Native macOS SystemConfiguration APIs

#### **`src/logging_config.py`** - Centralized Logging
- Unified logging configuration for the entire application
- Supports both DEBUG and INFO levels via config.toml or CLI flags

This modular design makes the codebase easier to understand, maintain, and extend. New developers can focus on specific functionality without needing to understand the entire system.

### Development and Imports

Import directly from specific modules:

```python
# Network operations
from src.network import (
    get_current_ssid,
    is_vpn_active,
    set_dns_servers,
    get_system_proxy_config,
    get_urllib_proxy_handler
)

# External services
from src.external import get_connection_details

# Location logic
from src.location import find_matching_location, apply_location_settings

# Utilities
from src.utils import run_command

# Logging
from src.logging_config import get_logger, setup_logging
```

## Troubleshooting

### Permission Issues
- Ensure passwordless sudo is configured correctly: `netwatcher check`
- Verify the sudoers file syntax with `sudo visudo -c`

### Service Not Starting
- Check the log file: `~/Library/Logs/netwatcher.log`
- Verify the LaunchAgent is loaded: `launchctl list | grep netwatcher`
- Try restarting: `netwatcher service stop && netwatcher service start`

### Network Settings Not Applying
- Ensure your `config.toml` is correctly configured
- Check that SSIDs, domains, and other settings match your network
- Use "Test Configuration" from the menu bar to trigger manual application
- Test manually: `netwatcher test`

### Wi-Fi Scanning Issues
- **You must use system Python**: `/usr/bin/python3 -m venv .venv`
- Ensure Location Services are enabled for Terminal/iTerm and Python in System Settings > Privacy and Security
- This is not optional - Wi-Fi scanning will not work with other Python versions

### VPN Detection Issues
- VPN status is only displayed when on a VPN (utun) interface
- Cisco VPN details require the VPN CLI binary to be installed
- Detection is automatic for all VPN clients using standard utun interfaces

### Menu Bar App Issues
- **Do not click the menu bar icon while network changes are being processed** - this can cause the app to crash and automatically respawn
- If the menu bar app becomes unresponsive, it will automatically restart
- Check `~/Library/Logs/netwatcher.log` for any error details

## Contributing

Contributions are welcome! Please read the [CONTRIBUTING.md](CONTRIBUTING.md) for more information on how to contribute to this project.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
