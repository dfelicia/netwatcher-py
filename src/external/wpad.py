"""
WPAD proxy configuration support for NetWatcher.

This module provides functions to fetch and parse WPAD files
and manage curlrc proxy settings.
"""

import logging
import re
import urllib.error
import urllib.request
from pathlib import Path
import pacparser
import tempfile


def get_proxy_from_wpad(wpad_url):
    """Fetch and parse a WPAD file to extract proxy server information."""
    logging.info(f"Fetching proxy configuration from {wpad_url}")
    try:
        # Create request with no proxy to avoid loops
        request = urllib.request.Request(wpad_url)
        proxy_handler = urllib.request.ProxyHandler({})
        opener = urllib.request.build_opener(proxy_handler)

        with opener.open(request, timeout=5) as response:
            wpad_content = response.read().decode("utf-8")

        if not wpad_content:
            logging.warning("WPAD file is empty")
            return None

        # Use pacparser to evaluate the PAC file
        pacparser.init()
        with tempfile.NamedTemporaryFile(
            mode="w+", suffix=".dat", delete=False
        ) as temp_file:
            temp_file.write(wpad_content)
            temp_path = temp_file.name

        pacparser.parse_pac_file(temp_path)

        test_url = "https://brew.sh/"
        test_host = "brew.sh"
        result = pacparser.find_proxy(test_url, test_host)

        pacparser.cleanup()

        import os

        os.unlink(temp_path)

        # Parse the result
        result = result.strip(";").strip()
        if result.startswith("PROXY "):
            proxy_server = result.split(" ")[1]
            logging.info(f"Found proxy server: {proxy_server}")
            return proxy_server
        elif result == "DIRECT":
            logging.info("WPAD returned DIRECT")
            return "DIRECT"
        else:
            logging.info(f"Unexpected WPAD result: {result}")
            return None

    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        logging.error(f"Failed to fetch WPAD file: {e}")
        return None
    except Exception as e:
        logging.error(f"Failed to parse WPAD file: {e}")
        return None
