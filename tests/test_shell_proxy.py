"""
Unit tests for src/network/shell_proxy.py

Tests shell proxy configuration, especially the critical bug fix
where user-configured PAC URLs were being ignored.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open


@pytest.mark.unit
class TestParseProxyConfig:
    """Tests for parse_proxy_config function - CRITICAL for bug prevention."""

    def test_user_configured_pac_url_is_used(self):
        """
        CRITICAL: Test that user-configured PAC URL from config is used.

        This test catches the bug we fixed where parse_proxy_config was
        calling get_proxy_url_for_shell() which queried system proxy,
        instead of using the provided proxy_url parameter.
        """
        from src.network.shell_proxy import parse_proxy_config

        user_pac_url = "http://my-custom-proxy.company.com/custom.pac"

        with patch(
            "src.network.pac_parser.parse_pac_file_for_generic_url"
        ) as mock_parse:
            # User's PAC file returns a specific proxy
            mock_parse.return_value = "http://custom-proxy.company.com:9000"

            result = parse_proxy_config(user_pac_url)

            # CRITICAL: Must call parse_pac_file_for_generic_url with USER'S PAC URL
            mock_parse.assert_called_once_with(user_pac_url)

            # Verify result uses the parsed proxy
            assert result is not None
            assert result["http_proxy"] == "http://custom-proxy.company.com:9000"

    def test_pac_file_returning_direct(self):
        """Test PAC file returning DIRECT."""
        from src.network.shell_proxy import parse_proxy_config

        with patch(
            "src.network.pac_parser.parse_pac_file_for_generic_url"
        ) as mock_parse:
            mock_parse.return_value = "DIRECT"

            result = parse_proxy_config("http://proxy.pac")

            assert result is None

    def test_manual_http_proxy(self):
        """Test manual HTTP proxy configuration."""
        from src.network.shell_proxy import parse_proxy_config

        result = parse_proxy_config("http://proxy.company.com:8080")

        assert result is not None
        assert result["http_proxy"] == "http://proxy.company.com:8080"
        assert result["https_proxy"] == "http://proxy.company.com:8080"
        assert result["ftp_proxy"] == "http://proxy.company.com:8080"
        assert result["all_proxy"] == "http://proxy.company.com:8080"
        assert result["rsync_proxy"] == "proxy.company.com:8080"  # No protocol
        assert "no_proxy" in result

    def test_proxy_without_protocol(self):
        """Test proxy URL without protocol prefix."""
        from src.network.shell_proxy import parse_proxy_config

        result = parse_proxy_config("proxy.company.com:8080")

        assert result is not None
        assert result["http_proxy"] == "http://proxy.company.com:8080"

    def test_empty_proxy_url(self):
        """Test empty proxy URL returns None."""
        from src.network.shell_proxy import parse_proxy_config

        result = parse_proxy_config("")
        assert result is None

    def test_none_proxy_url(self):
        """Test 'none' proxy URL returns None."""
        from src.network.shell_proxy import parse_proxy_config

        result = parse_proxy_config("none")
        assert result is None

    def test_additional_bypass_domains(self):
        """Test that additional bypass domains are included."""
        from src.network.shell_proxy import parse_proxy_config

        with patch("src.network.shell_proxy.get_shell_bypass_domains") as mock_bypass:
            mock_bypass.return_value = "localhost,127.0.0.1"

            result = parse_proxy_config(
                "http://proxy:8080",
                additional_bypass_domains=["custom.com", "internal.local"],
            )

            assert result is not None
            # Additional domains should be in no_proxy
            assert "custom.com" in result["no_proxy"]
            assert "internal.local" in result["no_proxy"]


@pytest.mark.unit
class TestGetShellBypassDomains:
    """Tests for get_shell_bypass_domains function."""

    def test_standard_bypass_domains_included(self):
        """Test that standard bypass domains are included."""
        from src.network.shell_proxy import get_shell_bypass_domains

        with patch(
            "src.network.shell_proxy.get_bypass_domains_from_resolver_files"
        ) as mock_resolver:
            mock_resolver.return_value = []

            result = get_shell_bypass_domains()

            assert "localhost" in result
            assert "127.0.0.1" in result
            assert "*.local" in result

    def test_resolver_domains_included(self):
        """Test that /etc/resolver domains are included."""
        from src.network.shell_proxy import get_shell_bypass_domains

        with patch(
            "src.network.shell_proxy.get_bypass_domains_from_resolver_files"
        ) as mock_resolver:
            mock_resolver.return_value = ["corp.company.com", "internal.local"]

            result = get_shell_bypass_domains()

            assert "corp.company.com" in result
            assert "internal.local" in result


@pytest.mark.unit
class TestWriteShellProxyFiles:
    """Tests for shell proxy file writing functions."""

    def test_write_bash_proxy_env_with_proxy(self, temp_config_dir):
        """Test writing bash proxy environment file."""
        from src.network.shell_proxy import write_bash_proxy_env

        proxy_config = {
            "http_proxy": "http://proxy:8080",
            "https_proxy": "http://proxy:8080",
            "ftp_proxy": "http://proxy:8080",
            "all_proxy": "http://proxy:8080",
            "rsync_proxy": "proxy:8080",
            "no_proxy": "localhost,127.0.0.1",
        }

        cache_file = temp_config_dir / "proxy.env.sh"

        with patch("pathlib.Path.home", return_value=temp_config_dir.parent.parent):
            write_bash_proxy_env(proxy_config)

            assert cache_file.exists()
            content = cache_file.read_text()
            assert 'export http_proxy="http://proxy:8080"' in content
            assert 'export no_proxy="localhost,127.0.0.1"' in content

    def test_write_bash_proxy_env_without_proxy(self, temp_config_dir):
        """Test removing bash proxy environment file when no proxy."""
        from src.network.shell_proxy import write_bash_proxy_env

        cache_file = temp_config_dir / "proxy.env.sh"
        cache_file.write_text("# Old proxy config")

        with patch("pathlib.Path.home", return_value=temp_config_dir.parent.parent):
            write_bash_proxy_env(None)

            assert not cache_file.exists()

    def test_write_csh_proxy_env_with_proxy(self, temp_config_dir):
        """Test writing csh proxy environment file."""
        from src.network.shell_proxy import write_csh_proxy_env

        proxy_config = {
            "http_proxy": "http://proxy:8080",
            "https_proxy": "http://proxy:8080",
            "ftp_proxy": "http://proxy:8080",
            "all_proxy": "http://proxy:8080",
            "rsync_proxy": "proxy:8080",
            "no_proxy": "localhost,127.0.0.1",
        }

        cache_file = temp_config_dir / "proxy.env.csh"

        with patch("pathlib.Path.home", return_value=temp_config_dir.parent.parent):
            write_csh_proxy_env(proxy_config)

            assert cache_file.exists()
            content = cache_file.read_text()
            assert 'setenv http_proxy "http://proxy:8080"' in content

    def test_write_fish_proxy_env_with_proxy(self, temp_config_dir):
        """Test writing fish proxy environment file."""
        from src.network.shell_proxy import write_fish_proxy_env

        proxy_config = {
            "http_proxy": "http://proxy:8080",
            "https_proxy": "http://proxy:8080",
            "ftp_proxy": "http://proxy:8080",
            "all_proxy": "http://proxy:8080",
            "rsync_proxy": "proxy:8080",
            "no_proxy": "localhost,127.0.0.1",
        }

        cache_file = temp_config_dir / "proxy.env.fish"

        with patch("pathlib.Path.home", return_value=temp_config_dir.parent.parent):
            write_fish_proxy_env(proxy_config)

            assert cache_file.exists()
            content = cache_file.read_text()
            assert 'set -x http_proxy "http://proxy:8080"' in content


@pytest.mark.unit
class TestDetectUserShells:
    """Tests for detect_user_shells function."""

    def test_detect_bash_shell(self, tmp_path):
        """Test detecting bash shell."""
        from src.network.shell_proxy import detect_user_shells

        bash_profile = tmp_path / ".bash_profile"
        bash_profile.touch()

        with (
            patch("pathlib.Path.home", return_value=tmp_path),
            patch("pwd.getpwuid") as mock_pwd,
        ):

            mock_user = MagicMock()
            mock_user.pw_shell = "/bin/bash"
            mock_pwd.return_value = mock_user

            shells, primary = detect_user_shells()

            assert "bash" in shells
            assert primary == "bash"

    def test_detect_zsh_shell(self, tmp_path):
        """Test detecting zsh shell."""
        from src.network.shell_proxy import detect_user_shells

        zshrc = tmp_path / ".zshrc"
        zshrc.touch()

        with (
            patch("pathlib.Path.home", return_value=tmp_path),
            patch("pwd.getpwuid") as mock_pwd,
        ):

            mock_user = MagicMock()
            mock_user.pw_shell = "/bin/zsh"
            mock_pwd.return_value = mock_user

            shells, primary = detect_user_shells()

            assert "zsh" in shells
            assert primary == "zsh"
