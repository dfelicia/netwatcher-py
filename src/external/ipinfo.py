"""
Connection information from ip-api.com for NetWatcher.

This module provides functions to fetch public IP and location details
from ip-api.com with proxy support.
"""

import json
import urllib.error
import urllib.request
from pathlib import Path

from .. import config
from ..logging_config import get_logger

# Get module logger
logger = get_logger(__name__)


def get_connection_details(silent=False):
    """
    Fetch public IP and location details from ip-api.com with proxy support.

    Args:
        silent: If True, suppress info-level logging

    Returns:
        dict: Connection details with keys:
            - ip: Public IP address
            - city: City name
            - region: State/region
            - country: Country code
            - isp: Internet Service Provider name

    Note:
        Automatically detects proxy settings from ~/.curlrc if present.
        Uses ip-api.com as the primary service for connection details.
    """
    if not silent:
        logger.info("Fetching connection details from ip-api.com")

    try:
        # Check if we have an active proxy configuration via curlrc
        curlrc_path = Path.home() / ".curlrc"
        proxy_url = None

        if curlrc_path.exists():
            try:
                curlrc_content = curlrc_path.read_text(encoding="utf-8")
                # Find the first proxy line using a more Pythonic approach
                proxy_lines = (
                    line.split("=", 1)[1].strip()
                    for line in curlrc_content.splitlines()
                    if line.strip().lower().startswith("proxy") and "=" in line
                )
                proxy_url = next(proxy_lines, None)
            except Exception:
                pass  # Ignore curlrc parsing errors

        # Create request with appropriate proxy configuration
        if proxy_url:
            # Use proxy configuration
            proxy_handler = urllib.request.ProxyHandler({"http": f"http://{proxy_url}", "https": f"http://{proxy_url}"})
            opener = urllib.request.build_opener(proxy_handler)
        else:
            # No proxy configuration found, use default
            opener = urllib.request.build_opener()

        request = urllib.request.Request(config.IPINFO_API_URL)
        request.add_header("User-Agent", "NetWatcher/1.0")

        with opener.open(request, timeout=config.IPINFO_TIMEOUT) as response:
            data = json.loads(response.read().decode("utf-8"))

            # Map ip-api.com response fields to our standard format
            return {
                "ip": data.get("query", "N/A"),  # ip-api.com uses 'query' for IP
                "city": data.get("city", "N/A"),
                "region": data.get("regionName", "N/A"),  # ip-api.com uses 'regionName'
                "country": data.get("countryCode", "N/A"),  # ip-api.com uses 'countryCode'
                "isp": data.get("isp", "N/A"),  # ip-api.com provides 'isp' directly
            }
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as e:
        if not silent:
            logger.error(f"Failed to fetch connection details: {e}")
        return {
            "ip": "N/A",
            "city": "N/A",
            "region": "N/A",
            "country": "N/A",
            "isp": "N/A",
        }
    except Exception as e:
        if not silent:
            logger.error(f"Unexpected error fetching connection details: {e}")
        return {
            "ip": "N/A",
            "city": "N/A",
            "region": "N/A",
            "country": "N/A",
            "isp": "N/A",
        }
