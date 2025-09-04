"""
NetWatcher - Automatic network configuration manager for macOS.

A modern macOS utility that automatically reconfigures system settings
when your network environment changes.
"""

__version__ = "0.1.0"
__author__ = "Don Feliciano"
__email__ = "don@effinthing.com"
__license__ = "MIT"

# Make key components available at package level
from . import config, watcher, logging_config

__all__ = ["config", "watcher", "logging_config"]
