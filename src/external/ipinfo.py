"""
Connection information from ip-api.com for NetWatcher.

This module provides functions to fetch public IP and location details
from ip-api.com with proxy support.
"""

import json
import urllib.error
import urllib.request

from .. import config
from ..logging_config import get_logger
from ..network.proxy_detection import get_urllib_proxy_handler

# Get module logger
logger = get_logger(__name__)


def get_connection_details(silent=False):
    """
    Fetch public IP and location details from ip-api.com.

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
        Uses system proxy settings automatically via urllib.
        Uses ip-api.com as the primary service for connection details.
    """
    logger.debug(f"get_connection_details called (silent={silent})")

    if not silent:
        logger.info("Fetching connection details from ip-api.com")

    try:
        # Get system proxy if configured
        proxy_handler = get_urllib_proxy_handler()

        # Build opener with or without proxy
        if proxy_handler:
            opener = urllib.request.build_opener(proxy_handler)
        else:
            opener = urllib.request.build_opener()

        # urllib automatically uses system proxy settings from environment (http_proxy, https_proxy)
        # but when running as LaunchAgent, those aren't set, so we check system settings above
        request = urllib.request.Request(config.IPINFO_API_URL)
        request.add_header("User-Agent", "NetWatcher/1.0")

        logger.debug(f"Making request to {config.IPINFO_API_URL}")
        with opener.open(request, timeout=config.IPINFO_TIMEOUT) as response:
            data = json.loads(response.read().decode("utf-8"))
            logger.debug(f"Received response from ip-api.com: {data}")

            # Map ip-api.com response fields to our standard format
            result = {
                "ip": data.get("query", "N/A"),  # ip-api.com uses 'query' for IP
                "city": data.get("city", "N/A"),
                "region": data.get("regionName", "N/A"),  # ip-api.com uses 'regionName'
                "country": data.get(
                    "countryCode", "N/A"
                ),  # ip-api.com uses 'countryCode'
                "isp": data.get("isp", "N/A"),  # ip-api.com provides 'isp' directly
            }
            logger.debug(f"Returning connection details: {result}")
            return result
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as e:
        logger.debug(f"Network/JSON error fetching connection details: {e}")
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
        logger.debug(f"Unexpected error fetching connection details: {e}")
        if not silent:
            logger.error(f"Unexpected error fetching connection details: {e}")
        return {
            "ip": "N/A",
            "city": "N/A",
            "region": "N/A",
            "country": "N/A",
            "isp": "N/A",
        }
