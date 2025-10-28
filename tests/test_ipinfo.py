"""
Unit tests for src/external/ipinfo.py

Tests the ip-api.com integration with proxy support.
"""

import pytest
import json
from unittest.mock import patch, MagicMock, Mock
import urllib.error


@pytest.mark.unit
class TestGetConnectionDetails:
    """Tests for get_connection_details function."""

    def test_successful_request_with_proxy(self, mock_ipapi_response):
        """Test successful request through proxy."""
        from src.external.ipinfo import get_connection_details

        mock_handler = MagicMock()
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(mock_ipapi_response).encode(
            "utf-8"
        )
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)

        with (
            patch("src.external.ipinfo.get_urllib_proxy_handler") as mock_get_handler,
            patch("urllib.request.build_opener") as mock_build_opener,
        ):

            mock_get_handler.return_value = mock_handler
            mock_opener = MagicMock()
            mock_opener.open.return_value = mock_response
            mock_build_opener.return_value = mock_opener

            result = get_connection_details(silent=True)

            assert result["ip"] == "203.0.113.42"
            assert result["city"] == "San Francisco"
            assert result["region"] == "California"
            assert result["country"] == "US"
            assert result["isp"] == "Example ISP Inc"

            # Verify proxy handler was used
            mock_get_handler.assert_called_once()
            mock_build_opener.assert_called_once_with(mock_handler)

    def test_successful_request_without_proxy(self, mock_ipapi_response):
        """Test successful request without proxy."""
        from src.external.ipinfo import get_connection_details

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(mock_ipapi_response).encode(
            "utf-8"
        )
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)

        with (
            patch("src.external.ipinfo.get_urllib_proxy_handler") as mock_get_handler,
            patch("urllib.request.build_opener") as mock_build_opener,
        ):

            mock_get_handler.return_value = None  # No proxy
            mock_opener = MagicMock()
            mock_opener.open.return_value = mock_response
            mock_build_opener.return_value = mock_opener

            result = get_connection_details(silent=True)

            assert result["ip"] == "203.0.113.42"
            # Verify no proxy handler was passed
            mock_build_opener.assert_called_once_with()

    def test_timeout_error(self):
        """Test timeout returns N/A values."""
        from src.external.ipinfo import get_connection_details

        with (
            patch("src.external.ipinfo.get_urllib_proxy_handler") as mock_get_handler,
            patch("urllib.request.build_opener") as mock_build_opener,
        ):

            mock_get_handler.return_value = None
            mock_opener = MagicMock()
            mock_opener.open.side_effect = urllib.error.URLError("timed out")
            mock_build_opener.return_value = mock_opener

            result = get_connection_details(silent=True)

            assert result["ip"] == "N/A"
            assert result["city"] == "N/A"
            assert result["region"] == "N/A"
            assert result["country"] == "N/A"
            assert result["isp"] == "N/A"

    def test_http_error(self):
        """Test HTTP error returns N/A values."""
        from src.external.ipinfo import get_connection_details

        with (
            patch("src.external.ipinfo.get_urllib_proxy_handler") as mock_get_handler,
            patch("urllib.request.build_opener") as mock_build_opener,
        ):

            mock_get_handler.return_value = None
            mock_opener = MagicMock()
            mock_opener.open.side_effect = urllib.error.HTTPError(
                "http://ip-api.com/json", 500, "Internal Server Error", {}, None
            )
            mock_build_opener.return_value = mock_opener

            result = get_connection_details(silent=True)

            assert result["ip"] == "N/A"

    def test_json_decode_error(self):
        """Test invalid JSON returns N/A values."""
        from src.external.ipinfo import get_connection_details

        mock_response = MagicMock()
        mock_response.read.return_value = b"Invalid JSON"
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)

        with (
            patch("src.external.ipinfo.get_urllib_proxy_handler") as mock_get_handler,
            patch("urllib.request.build_opener") as mock_build_opener,
        ):

            mock_get_handler.return_value = None
            mock_opener = MagicMock()
            mock_opener.open.return_value = mock_response
            mock_build_opener.return_value = mock_opener

            result = get_connection_details(silent=True)

            assert result["ip"] == "N/A"

    def test_missing_fields_in_response(self):
        """Test response with missing fields uses N/A."""
        from src.external.ipinfo import get_connection_details

        partial_response = {"query": "1.2.3.4"}  # Missing other fields
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(partial_response).encode("utf-8")
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)

        with (
            patch("src.external.ipinfo.get_urllib_proxy_handler") as mock_get_handler,
            patch("urllib.request.build_opener") as mock_build_opener,
        ):

            mock_get_handler.return_value = None
            mock_opener = MagicMock()
            mock_opener.open.return_value = mock_response
            mock_build_opener.return_value = mock_opener

            result = get_connection_details(silent=True)

            assert result["ip"] == "1.2.3.4"
            assert result["city"] == "N/A"
            assert result["region"] == "N/A"

    def test_debug_logging_output(self, mock_ipapi_response):
        """Test that debug logging works correctly."""
        from src.external.ipinfo import get_connection_details

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(mock_ipapi_response).encode(
            "utf-8"
        )
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)

        with (
            patch("src.external.ipinfo.get_urllib_proxy_handler") as mock_get_handler,
            patch("urllib.request.build_opener") as mock_build_opener,
            patch("src.external.ipinfo.logger") as mock_logger,
        ):

            mock_get_handler.return_value = None
            mock_opener = MagicMock()
            mock_opener.open.return_value = mock_response
            mock_build_opener.return_value = mock_opener

            result = get_connection_details(silent=True)

            # Verify debug logging was called
            assert mock_logger.debug.called
            debug_calls = [call[0][0] for call in mock_logger.debug.call_args_list]
            assert any("get_connection_details called" in call for call in debug_calls)
            assert any("Making request to" in call for call in debug_calls)
