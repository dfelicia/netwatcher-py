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

        # Extract proxy server from WPAD content
        match = re.search(r"PROXY\s+([a-zA-Z0-9.-]+:\d+)", wpad_content, re.IGNORECASE)
        if match:
            proxy_server = match.group(1)
            logging.info(f"Found proxy server: {proxy_server}")
            return proxy_server
        else:
            logging.info("No PROXY directive found in WPAD content")
            logging.debug(f"WPAD content preview: {wpad_content[:200]}...")
            return None

    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        logging.error(f"Failed to fetch WPAD file: {e}")
        return None
    except Exception as e:
        logging.error(f"Failed to parse WPAD file: {e}")
        return None


def update_curlrc(proxy_server=None):
    """Update ~/.curlrc with proxy settings."""
    curlrc_path = Path.home() / ".curlrc"

    try:
        # Read existing content
        lines = []
        if curlrc_path.exists():
            lines = curlrc_path.read_text(encoding="utf-8").splitlines(keepends=True)

        # Remove existing proxy lines
        lines = [
            line
            for line in lines
            if not (
                line.strip().lower().startswith("proxy")
                and ("=" in line or ":" in line)
            )
        ]

        # Add new proxy configuration if specified
        if proxy_server:
            lines.append(f"proxy = {proxy_server}\n")

        # Write updated content
        curlrc_path.write_text("".join(lines), encoding="utf-8")

    except IOError as e:
        logging.error(f"Error updating ~/.curlrc: {e}")
