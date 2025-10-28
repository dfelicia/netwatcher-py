"""
Unit tests for src/network/proxy_detection.py

These tests verify the centralized proxy detection logic, including
the critical bugs we fixed during refactoring.
"""

import pytest
from unittest.mock import patch, MagicMock
import urllib.request


@pytest.mark.unit
class TestGetSystemProxyConfig:
    """Tests for get_system_proxy_config function."""

    def test_pac_proxy_detection(self, mock_networksetup_outputs, mock_primary_service):
        """Test detection of PAC proxy configuration."""
        from src.network.proxy_detection import get_system_proxy_config

        with (
            patch(
                "src.network.proxy_detection.get_primary_service_interface"
            ) as mock_get_primary,
            patch("src.network.proxy_detection.run_command") as mock_run,
        ):

            mock_get_primary.return_value = mock_primary_service
            mock_run.return_value = mock_networksetup_outputs["pac_proxy"]

            proxy_type, proxy_value = get_system_proxy_config()

            assert proxy_type == "pac"
            assert proxy_value == "http://wpad.company.com/wpad.dat"
            mock_run.assert_called_once()

    def test_http_proxy_detection(
        self, mock_networksetup_outputs, mock_primary_service
    ):
        """Test detection of manual HTTP proxy configuration."""
        from src.network.proxy_detection import get_system_proxy_config

        with (
            patch(
                "src.network.proxy_detection.get_primary_service_interface"
            ) as mock_get_primary,
            patch("src.network.proxy_detection.run_command") as mock_run,
        ):

            mock_get_primary.return_value = mock_primary_service

            # Mock returns: first call for PAC (none), second call for HTTP (found)
            mock_run.side_effect = [
                mock_networksetup_outputs["no_proxy"],  # PAC check
                mock_networksetup_outputs["http_proxy"],  # HTTP check
            ]

            proxy_type, proxy_value = get_system_proxy_config()

            assert proxy_type == "http"
            assert proxy_value == "proxy.company.com:8080"

    def test_https_proxy_detection(
        self, mock_networksetup_outputs, mock_primary_service
    ):
        """Test detection of manual HTTPS proxy configuration."""
        from src.network.proxy_detection import get_system_proxy_config

        with (
            patch(
                "src.network.proxy_detection.get_primary_service_interface"
            ) as mock_get_primary,
            patch("src.network.proxy_detection.run_command") as mock_run,
        ):

            mock_get_primary.return_value = mock_primary_service

            # Mock returns: PAC (none), HTTP (none), HTTPS (found)
            mock_run.side_effect = [
                mock_networksetup_outputs["no_proxy"],  # PAC
                mock_networksetup_outputs["no_proxy"],  # HTTP
                mock_networksetup_outputs["https_proxy"],  # HTTPS
            ]

            proxy_type, proxy_value = get_system_proxy_config()

            assert proxy_type == "https"
            assert proxy_value == "proxy-secure.company.com:8443"

    def test_socks_proxy_detection(
        self, mock_networksetup_outputs, mock_primary_service
    ):
        """Test detection of SOCKS proxy configuration."""
        from src.network.proxy_detection import get_system_proxy_config

        with (
            patch(
                "src.network.proxy_detection.get_primary_service_interface"
            ) as mock_get_primary,
            patch("src.network.proxy_detection.run_command") as mock_run,
        ):

            mock_get_primary.return_value = mock_primary_service

            # Mock returns: all checks return none until SOCKS
            mock_run.side_effect = [
                mock_networksetup_outputs["no_proxy"],  # PAC
                mock_networksetup_outputs["no_proxy"],  # HTTP
                mock_networksetup_outputs["no_proxy"],  # HTTPS
                mock_networksetup_outputs["socks_proxy"],  # SOCKS
            ]

            proxy_type, proxy_value = get_system_proxy_config()

            assert proxy_type == "socks"
            assert proxy_value == "socks.company.com:1080"

    def test_no_proxy_configured(self, mock_networksetup_outputs, mock_primary_service):
        """Test when no proxy is configured."""
        from src.network.proxy_detection import get_system_proxy_config

        with (
            patch(
                "src.network.proxy_detection.get_primary_service_interface"
            ) as mock_get_primary,
            patch("src.network.proxy_detection.run_command") as mock_run,
        ):

            mock_get_primary.return_value = mock_primary_service
            mock_run.return_value = mock_networksetup_outputs["no_proxy"]

            proxy_type, proxy_value = get_system_proxy_config()

            assert proxy_type is None
            assert proxy_value is None

    def test_no_primary_service(self):
        """Test when no primary service is available."""
        from src.network.proxy_detection import get_system_proxy_config

        with patch(
            "src.network.proxy_detection.get_primary_service_interface"
        ) as mock_get_primary:
            mock_get_primary.return_value = (None, None, None)

            proxy_type, proxy_value = get_system_proxy_config()

            assert proxy_type is None
            assert proxy_value is None


@pytest.mark.unit
class TestGetUrllibProxyHandler:
    """Tests for get_urllib_proxy_handler function - CRITICAL for bug prevention."""

    def test_pac_proxy_handler_no_double_http(self, mock_primary_service):
        """
        CRITICAL: Test that PAC proxy doesn't add double 'http://' prefix.

        This test catches the bug we fixed where pac_parser returns
        'http://proxy:8080' but we were adding 'http://' again.
        """
        from src.network.proxy_detection import get_urllib_proxy_handler

        with (
            patch("src.network.proxy_detection.get_system_proxy_config") as mock_config,
            patch(
                "src.network.proxy_detection.parse_pac_file_for_generic_url"
            ) as mock_parse,
        ):

            mock_config.return_value = ("pac", "http://wpad/wpad.dat")
            # pac_parser returns URL with http:// already
            mock_parse.return_value = "http://proxy.company.com:8080"

            handler = get_urllib_proxy_handler()

            assert handler is not None
            assert isinstance(handler, urllib.request.ProxyHandler)
            # CRITICAL: Should NOT have double http://
            assert handler.proxies["http"] == "http://proxy.company.com:8080"
            assert handler.proxies["https"] == "http://proxy.company.com:8080"
            # Make sure we don't have http://http://
            assert "http://http://" not in handler.proxies["http"]

    def test_pac_proxy_returns_direct(self, mock_primary_service):
        """Test that PAC file returning DIRECT results in no proxy."""
        from src.network.proxy_detection import get_urllib_proxy_handler

        with (
            patch("src.network.proxy_detection.get_system_proxy_config") as mock_config,
            patch(
                "src.network.proxy_detection.parse_pac_file_for_generic_url"
            ) as mock_parse,
        ):

            mock_config.return_value = ("pac", "http://wpad/wpad.dat")
            mock_parse.return_value = "DIRECT"

            handler = get_urllib_proxy_handler()

            assert handler is None

    def test_http_proxy_handler(self):
        """Test manual HTTP proxy handler creation."""
        from src.network.proxy_detection import get_urllib_proxy_handler

        with patch(
            "src.network.proxy_detection.get_system_proxy_config"
        ) as mock_config:
            mock_config.return_value = ("http", "proxy.company.com:8080")

            handler = get_urllib_proxy_handler()

            assert handler is not None
            assert handler.proxies["http"] == "http://proxy.company.com:8080"
            assert handler.proxies["https"] == "http://proxy.company.com:8080"

    def test_socks_proxy_handler(self):
        """Test SOCKS proxy handler creation."""
        from src.network.proxy_detection import get_urllib_proxy_handler

        with patch(
            "src.network.proxy_detection.get_system_proxy_config"
        ) as mock_config:
            mock_config.return_value = ("socks", "socks.company.com:1080")

            handler = get_urllib_proxy_handler()

            assert handler is not None
            assert handler.proxies["http"] == "socks://socks.company.com:1080"
            assert handler.proxies["socks"] == "socks://socks.company.com:1080"

    def test_no_proxy_returns_none(self):
        """Test that no proxy configuration returns None."""
        from src.network.proxy_detection import get_urllib_proxy_handler

        with patch(
            "src.network.proxy_detection.get_system_proxy_config"
        ) as mock_config:
            mock_config.return_value = (None, None)

            handler = get_urllib_proxy_handler()

            assert handler is None


@pytest.mark.unit
class TestGetProxyUrlForShell:
    """Tests for get_proxy_url_for_shell function."""

    def test_pac_proxy_resolved(self):
        """Test PAC proxy is resolved for shell use."""
        from src.network.proxy_detection import get_proxy_url_for_shell

        with (
            patch("src.network.proxy_detection.get_system_proxy_config") as mock_config,
            patch(
                "src.network.proxy_detection.parse_pac_file_for_generic_url"
            ) as mock_parse,
        ):

            mock_config.return_value = ("pac", "http://wpad/wpad.dat")
            mock_parse.return_value = "http://proxy.company.com:8080"

            result = get_proxy_url_for_shell(resolve_pac=True)

            assert result == "http://proxy.company.com:8080"

    def test_pac_proxy_not_resolved_when_disabled(self):
        """Test PAC proxy returns None when resolve_pac=False."""
        from src.network.proxy_detection import get_proxy_url_for_shell

        with patch(
            "src.network.proxy_detection.get_system_proxy_config"
        ) as mock_config:
            mock_config.return_value = ("pac", "http://wpad/wpad.dat")

            result = get_proxy_url_for_shell(resolve_pac=False)

            assert result is None

    def test_http_proxy_for_shell(self):
        """Test manual HTTP proxy for shell."""
        from src.network.proxy_detection import get_proxy_url_for_shell

        with patch(
            "src.network.proxy_detection.get_system_proxy_config"
        ) as mock_config:
            mock_config.return_value = ("http", "proxy.company.com:8080")

            result = get_proxy_url_for_shell()

            assert result == "http://proxy.company.com:8080"

    def test_socks_proxy_for_shell(self):
        """Test SOCKS proxy for shell."""
        from src.network.proxy_detection import get_proxy_url_for_shell

        with patch(
            "src.network.proxy_detection.get_system_proxy_config"
        ) as mock_config:
            mock_config.return_value = ("socks", "socks.company.com:1080")

            result = get_proxy_url_for_shell()

            assert result == "socks://socks.company.com:1080"
