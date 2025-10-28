"""
Pytest configuration and shared fixtures for NetWatcher tests.

This module provides reusable fixtures and configuration for all tests.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, Mock


@pytest.fixture
def mock_config():
    """Provide a mock configuration dictionary."""
    return {
        "settings": {
            "debug": False,
            "debounce_seconds": 5,
            "shell_proxy_enabled": True,
        },
        "locations": {
            "Home": {
                "ssids": ["HomeWiFi"],
                "dns_servers": ["192.168.1.1"],
                "dns_search_domains": ["home.local"],
                "proxy_url": "",
                "printer": "Home_Printer",
                "ntp_server": "time.apple.com",
            },
            "Office": {
                "ssids": ["CorpWiFi"],
                "dns_servers": ["10.1.1.10", "10.1.1.11"],
                "dns_search_domains": ["corp.company.com"],
                "proxy_url": "http://proxy.company.com/proxy.pac",
                "printer": "Office_Printer",
                "ntp_server": "time.company.com",
            },
            "default": {
                "ssids": [],
                "dns_servers": ["8.8.8.8", "1.1.1.1"],
                "dns_search_domains": [],
                "proxy_url": "",
                "printer": "",
                "ntp_server": "time.apple.com",
            },
        },
    }


@pytest.fixture
def mock_networksetup_outputs():
    """Provide mock outputs from networksetup commands."""
    return {
        "pac_proxy": """Enabled: Yes
URL: http://wpad.company.com/wpad.dat
""",
        "http_proxy": """Enabled: Yes
Server: proxy.company.com
Port: 8080
Authenticated Proxy Enabled: 0
""",
        "https_proxy": """Enabled: Yes
Server: proxy-secure.company.com
Port: 8443
Authenticated Proxy Enabled: 0
""",
        "socks_proxy": """Enabled: Yes
Server: socks.company.com
Port: 1080
Authenticated Proxy Enabled: 0
""",
        "no_proxy": """Enabled: No
Server:
Port: 0
Authenticated Proxy Enabled: 0
""",
    }


@pytest.fixture
def mock_pac_file_content():
    """Provide a mock PAC file content."""
    return """
function FindProxyForURL(url, host) {
    // Internal domains go direct
    if (shExpMatch(host, "*.company.com") ||
        shExpMatch(host, "*.local") ||
        isInNet(host, "10.0.0.0", "255.0.0.0")) {
        return "DIRECT";
    }

    // Everything else goes through proxy
    return "PROXY proxy.company.com:8080; DIRECT";
}
"""


@pytest.fixture
def mock_ipapi_response():
    """Provide a mock response from ip-api.com."""
    return {
        "query": "203.0.113.42",
        "city": "San Francisco",
        "regionName": "California",
        "countryCode": "US",
        "isp": "Example ISP Inc",
    }


@pytest.fixture
def temp_config_dir(tmp_path):
    """Provide a temporary config directory."""
    config_dir = tmp_path / ".config" / "netwatcher"
    config_dir.mkdir(parents=True)
    return config_dir


@pytest.fixture
def mock_run_command():
    """Provide a mock for run_command function."""
    mock = MagicMock()
    mock.return_value = True
    return mock


@pytest.fixture
def mock_primary_service():
    """Provide a mock for get_primary_service_interface."""
    return ("USB 10/100/1000 LAN", "en0", "12345678-1234-1234-1234-123456789012")


@pytest.fixture(autouse=True)
def reset_logging():
    """Reset logging configuration between tests."""
    import logging

    # Clear all handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    # Reset to default level
    root_logger.setLevel(logging.WARNING)
    yield
    # Cleanup after test
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
