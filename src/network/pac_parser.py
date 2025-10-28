"""
PAC file parsing utilities for NetWatcher.

This module handles parsing of PAC (Proxy Auto-Configuration) files
to extract actual proxy server information for shell environments.
"""

import urllib.request
import urllib.error
from typing import Optional

from ..logging_config import get_logger

logger = get_logger(__name__)


def parse_pac_file_for_generic_url(
    pac_url: str, test_url: str = "http://effinthing.com"
) -> Optional[str]:
    """
    Parse a PAC file and extract proxy configuration for a generic URL.

    Args:
        pac_url: URL to the PAC file (e.g., "http://wpad/wpad.dat")
        test_url: URL to test against the PAC file logic

    Returns:
        Proxy string (e.g., "http://proxy.company.com:8080") or "DIRECT" or None
    """
    try:
        import pacparser
    except ImportError:
        logger.error(
            "pacparser module not available. Install with: pip install pacparser"
        )
        return None

    try:
        # Download PAC file content
        logger.debug(f"Downloading PAC file from: {pac_url}")

        # Create a proxy handler that bypasses all proxies (equivalent to curl --noproxy '*')
        # ProxyHandler({}) creates a handler with no proxy configuration, forcing direct connection
        proxy_handler = urllib.request.ProxyHandler({})
        opener = urllib.request.build_opener(proxy_handler)

        # Use the opener to download the PAC file directly without any proxy
        request = urllib.request.Request(pac_url)
        with opener.open(request, timeout=10) as response:
            pac_content = response.read().decode("utf-8")

        if not pac_content.strip():
            logger.warning(f"Empty PAC file content from {pac_url}")
            return None

        logger.debug(f"Downloaded PAC file ({len(pac_content)} bytes)")

        # Initialize pacparser
        pacparser.init()

        try:
            # Parse the PAC file content
            pacparser.parse_pac_string(pac_content)

            # Find proxy for the test URL
            proxy_result = pacparser.find_proxy(test_url, "effinthing.com")

            logger.debug(f"PAC result for {test_url}: {proxy_result}")

            # Parse the result - PAC files return strings like:
            # "PROXY proxy.company.com:8080; DIRECT"
            # "DIRECT"
            # "PROXY proxy1.company.com:8080; PROXY proxy2.company.com:8080; DIRECT"

            if not proxy_result or proxy_result == "DIRECT":
                return "DIRECT"

            # Extract first proxy from the result
            proxies = [p.strip() for p in proxy_result.split(";")]
            for proxy in proxies:
                if proxy.startswith("PROXY "):
                    proxy_server = proxy[6:].strip()  # Remove "PROXY " prefix
                    if proxy_server:
                        # Add http:// if not present
                        if not proxy_server.startswith(("http://", "https://")):
                            proxy_server = f"http://{proxy_server}"
                        logger.debug(f"Extracted proxy: {proxy_server}")
                        return proxy_server
                elif proxy == "DIRECT":
                    return "DIRECT"

            # If we get here, no valid proxy was found
            logger.warning(f"No valid proxy found in PAC result: {proxy_result}")
            return "DIRECT"

        finally:
            # Clean up pacparser
            try:
                pacparser.cleanup()
            except Exception:
                pass

    except urllib.error.URLError as e:
        logger.info(f"PAC file not accessible at {pac_url} (network may have changed)")
        return None
    except Exception as e:
        logger.error(f"Error parsing PAC file from {pac_url}: {e}")
        return None


def test_pac_parsing(pac_url: str) -> bool:
    """
    Test PAC file parsing to verify it's working correctly.

    Args:
        pac_url: URL to the PAC file to test

    Returns:
        True if parsing was successful, False otherwise
    """
    try:
        result = parse_pac_file_for_generic_url(pac_url)
        if result is not None:
            logger.info(f"PAC parsing test successful. Result: {result}")
            return True
        else:
            logger.warning("PAC parsing test failed - returned None")
            return False
    except Exception as e:
        logger.error(f"PAC parsing test failed with exception: {e}")
        return False


def extract_proxy_from_result(pac_result: str) -> Optional[str]:
    """
    Extract the first available proxy from a PAC result string.

    Args:
        pac_result: Result string from PAC file (e.g., "PROXY host:port; DIRECT")

    Returns:
        First proxy URL or "DIRECT" or None
    """
    if not pac_result:
        return None

    proxies = [p.strip() for p in pac_result.split(";")]
    for proxy in proxies:
        if proxy.startswith("PROXY "):
            proxy_server = proxy[6:].strip()
            if proxy_server:
                if not proxy_server.startswith(("http://", "https://")):
                    proxy_server = f"http://{proxy_server}"
                return proxy_server
        elif proxy == "DIRECT":
            return "DIRECT"

    return None
