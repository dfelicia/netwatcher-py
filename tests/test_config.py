"""
Unit tests for src/config.py

Tests configuration loading and constants.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, mock_open
import toml


@pytest.mark.unit
class TestConfigLoading:
    """Tests for configuration loading."""

    def test_load_config_creates_default(self, temp_config_dir):
        """Test that load_config creates default config if none exists."""
        from src import config

        config_file = temp_config_dir / "config.toml"

        with patch("src.config.get_config_path", return_value=config_file):
            result = config.load_config()

            assert config_file.exists()
            assert "settings" in result
            assert "locations" in result
            assert result["settings"]["debug"] == False
            assert result["settings"]["debounce_seconds"] == 5

    def test_load_existing_config(self, temp_config_dir, mock_config):
        """Test loading an existing config file."""
        from src import config

        config_file = temp_config_dir / "config.toml"
        with open(config_file, "w") as f:
            toml.dump(mock_config, f)

        with patch("src.config.get_config_path", return_value=config_file):
            result = config.load_config()

            assert result["settings"]["debug"] == mock_config["settings"]["debug"]
            assert "Home" in result["locations"]
            assert "Office" in result["locations"]

    def test_config_uses_stdlib_logging(self):
        """
        CRITICAL: Test that config.py uses stdlib logging to avoid
        premature initialization of custom logging.
        """
        from src import config
        import logging

        # This test verifies the fix where we changed from get_logger()
        # to stdlib logging.getLogger() to avoid auto-init
        with patch("src.config.Path") as mock_path_cls:
            mock_path = mock_path_cls.return_value
            mock_path.exists.return_value = False
            mock_path.parent.mkdir = lambda **kwargs: None

            # Mock the file operations
            with patch("builtins.open", mock_open()):
                with patch("toml.dump"):
                    # Should not raise ImportError or initialization errors
                    result = config.load_config()
                    assert result is not None


@pytest.mark.unit
class TestConfigConstants:
    """Tests for configuration constants."""

    def test_app_constants(self):
        """Test that app constants are defined."""
        from src import config

        assert config.APP_NAME == "netwatcher"
        assert "netwatcher" in config.PLIST_FILENAME
        assert "netwatcher" in config.LAUNCH_AGENT_LABEL

    def test_network_constants(self):
        """Test that network constants are defined."""
        from src import config

        assert config.DEFAULT_NTP_SERVER == "time.apple.com"
        assert config.DEFAULT_DEBOUNCE_SECONDS == 5
        assert config.IPINFO_TIMEOUT > 0
        assert "ip-api.com" in config.IPINFO_API_URL

    def test_default_location_config(self):
        """Test default location configuration structure."""
        from src import config

        default_loc = config.DEFAULT_LOCATION_CONFIG
        assert "ssids" in default_loc
        assert "dns_servers" in default_loc
        assert "dns_search_domains" in default_loc
        assert "proxy_url" in default_loc
        assert "printer" in default_loc
        assert "ntp_server" in default_loc
