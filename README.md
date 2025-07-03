# NetWatcher

A modern macOS utility that automatically reconfigures system settings when your network environment changes. It runs as a menu bar application and background service, monitoring for network changes and applying predefined settings for different locations.

## How It Works

NetWatcher is built with Python and uses native macOS frameworks for reliable, event-driven network automation:

- **Core Engine**: Leverages the `SystemConfiguration` framework to receive real-time notifications from macOS whenever network settings change. This is highly efficient and avoids the need for constant polling.
- **Menu Bar App**: A `rumps`-based application provides a simple icon in the macOS menu bar, showing current connection status and location, with the ability to manually trigger settings re-application.
- **Configuration**: All settings are defined in a simple `config.toml` file, making it easy to manage different network profiles for home, office, or public Wi-Fi.
- **Background Service**: The application runs as a persistent `LaunchAgent`, ensuring it starts automatically at login and runs silently in the background.
- **CLI Management**: A comprehensive command-line interface provides easy installation, uninstallation, configuration, and service management.

## Features

- **Real-time network monitoring** using macOS SystemConfiguration framework
- **Menu bar integration** with current location and connection status display
- **Automatic network configuration** including:
  - DNS servers and search domains
  - Proxy settings (PAC/WPAD files, HTTP/HTTPS/SOCKS proxies)
  - Default printer selection
  - Network Time Protocol (NTP) server configuration
- **Command-line tool integration** with `~/.curlrc` proxy configuration
- **VPN detection and status display** (configurable for various VPN clients)
- **One-click testing** from the menu bar with log file integration
- **Comprehensive logging** for debugging and monitoring

## Prerequisites

Before you begin, ensure you have the following:

1. **macOS**: This tool is designed exclusively for macOS (tested on macOS 10.15+)
2. **Python**: Version 3.9 or higher recommended for full compatibility
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
   Cmnd_Alias NETWATCHER_CMDS = /usr/sbin/networksetup, /usr/sbin/systemsetup, /usr/sbin/lpadmin, /usr/bin/sntp
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

The configuration will be saved to `~/.config/netwatcher/config.toml`.

### Step 5: Install the Service

Install the LaunchAgent to have NetWatcher run automatically in the background:

```bash
netwatcher service install
```

The application will start automatically and you'll see the NetWatcher icon in your menu bar. You can monitor its activity in the log file at `~/Library/Logs/netwatcher/netwatcher.log`.

## Using the CLI

NetWatcher provides a command-line interface for configuration and service management:

- **Configure network locations**: `netwatcher configure`
- **Test current network detection**: `netwatcher test`
- **Check system permissions**: `netwatcher check`
- **Install the background service**: `netwatcher service install`
- **Uninstall the background service**: `netwatcher service uninstall`
- **Start the background service**: `netwatcher service start`
- **Stop the background service**: `netwatcher service stop`
- **Check service status**: `netwatcher service status`

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

### VPN Configuration (Optional)

Configure VPN client status checking by adding a `[vpn]` section:

```toml
[vpn]
client_name = "Cisco Secure Client"
client_path = "/opt/cisco/secureclient/bin/vpn"
```

**Note**: VPN status is only checked when the active network interface is a VPN (utun) interface.

### Example Configuration

```toml
[vpn]
client_name = "Cisco Secure Client"
client_path = "/opt/cisco/secureclient/bin/vpn"

[locations.Home]
ssids = ["HomeWiFi", "HomeWiFi_5G"]
dns_servers = []  # Use DHCP
dns_search_domains = ["home.local"]
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

## Architecture

NetWatcher consists of several modular components:

- **`src/cli.py`**: Command-line interface and service management
- **`src/watcher.py`**: Menu bar application and network monitoring
- **`src/actions.py`**: Network detection and system configuration logic
- **`src/config.py`**: Configuration file handling and constants
- **`src/com.user.netwatcher.plist`**: macOS LaunchAgent configuration template

## Troubleshooting

### Permission Issues
- Ensure passwordless sudo is configured correctly: `netwatcher check`
- Verify the sudoers file syntax with `sudo visudo -c`

### Service Not Starting
- Check the log file: `~/Library/Logs/netwatcher/netwatcher.log`
- Verify the LaunchAgent is loaded: `launchctl list | grep netwatcher`
- Try restarting: `netwatcher service stop && netwatcher service start`

### Network Settings Not Applying
- Ensure your `config.toml` is correctly configured
- Check that SSIDs, domains, and other settings match your network
- Use "Test Configuration" from the menu bar to trigger manual application
- Test manually: `netwatcher test`

### Wi-Fi Scanning Issues
- **You must use system Python**: `/usr/bin/python3 -m venv .venv`
- Ensure location services are enabled for Terminal/iTerm in System Settings
- This is not optional - Wi-Fi scanning will not work with other Python versions

### VPN Detection Issues
- VPN status is only checked when on a VPN (utun) interface
- Verify the VPN client path in your configuration
- Check that the VPN client supports the `stats` command

## Contributing

Contributions are welcome! Please read the [CONTRIBUTING.md](CONTRIBUTING.md) for more information on how to contribute to this project.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
