"""
Shell proxy configuration management for NetWatcher.

This module handles automatic proxy configuration for terminal applications
by managing shell environment variables across multiple shell types.
"""

import os
import pwd
import socket
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..logging_config import get_logger
from .. import config

logger = get_logger(__name__)


def detect_user_shells() -> Tuple[List[str], str]:
    """
    Detect shells the user might be using.

    Returns:
        Tuple of (detected_shells, primary_shell)
    """
    # Get primary shell from /etc/passwd
    primary_shell = pwd.getpwuid(os.getuid()).pw_shell
    primary_name = os.path.basename(primary_shell)

    # Check for existing shell config files
    home = Path.home()
    detected_shells = []

    shell_configs = {
        "bash": [home / ".bash_profile", home / ".bashrc"],
        "zsh": [home / ".zshrc"],
        "tcsh": [home / ".tcshrc"],
        "csh": [home / ".cshrc"],
        "fish": [home / ".config/fish/config.fish"],
    }

    # Add primary shell
    if primary_name in shell_configs:
        detected_shells.append(primary_name)

    # Check for other shells with existing config files
    for shell, configs in shell_configs.items():
        if shell not in detected_shells:
            if any(config.exists() for config in configs):
                detected_shells.append(shell)

    return detected_shells, primary_name


def get_bypass_domains_from_resolver_files() -> List[str]:
    """Get bypass domains from /etc/resolver files we created."""
    resolver_dir = Path("/etc/resolver")
    if resolver_dir.exists():
        try:
            return [f.name for f in resolver_dir.iterdir() if f.is_file()]
        except PermissionError:
            logger.debug("Cannot read /etc/resolver directory (permission denied)")
            return []
    return []


def get_standard_bypass_domains() -> List[str]:
    """Get standard bypass domains for shell proxy."""
    standard = [
        "localhost",
        "127.0.0.1",
        "*.local",
        "169.254/16",  # Link-local
    ]

    try:
        hostname = socket.gethostname()
        if hostname:
            standard.append(hostname)
    except Exception:
        pass

    return standard


def get_shell_bypass_domains() -> str:
    """Get complete bypass domain list for shell proxy."""
    standard = get_standard_bypass_domains()
    resolver_domains = get_bypass_domains_from_resolver_files()
    all_bypasses = standard + resolver_domains
    return ",".join(all_bypasses)


def parse_proxy_config(
    proxy_url: str, additional_bypass_domains: Optional[List[str]] = None
) -> Optional[Dict[str, str]]:
    """
    Parse proxy configuration from proxy_url.

    Args:
        proxy_url: Proxy URL from config (can be PAC file, direct proxy, or empty)
        additional_bypass_domains: Additional domains to add to no_proxy list (e.g., DNS search domains)

    Returns:
        Dictionary with proxy configuration or None if no proxy
    """
    if not proxy_url or proxy_url == "none":
        return None

    if proxy_url.endswith((".pac", ".dat")):
        # PAC/WPAD file - parse it to get actual proxy
        logger.debug(f"Parsing PAC file: {proxy_url}")
        from .pac_parser import parse_pac_file_for_generic_url

        actual_proxy = parse_pac_file_for_generic_url(proxy_url)
        if actual_proxy and actual_proxy != "DIRECT":
            proxy_url = actual_proxy
        else:
            logger.debug("PAC file returned DIRECT or failed to parse")
            return None

    # Parse proxy URL
    if "://" not in proxy_url:
        proxy_url = f"http://{proxy_url}"

    # Extract host and port for rsync_proxy
    try:
        from urllib.parse import urlparse

        parsed = urlparse(proxy_url)
        if parsed.hostname and parsed.port:
            rsync_proxy = f"{parsed.hostname}:{parsed.port}"
        elif parsed.hostname:
            # Default to port 80 if not specified
            rsync_proxy = f"{parsed.hostname}:80"
        else:
            # Fallback: strip protocol
            rsync_proxy = proxy_url.replace("http://", "").replace("https://", "")
    except Exception:
        # Fallback: strip protocol
        rsync_proxy = proxy_url.replace("http://", "").replace("https://", "")

    # Build bypass domains list
    standard_bypasses = get_shell_bypass_domains().split(",")
    all_bypasses = standard_bypasses.copy()

    # Add additional bypass domains (e.g., DNS search domains from location config)
    if additional_bypass_domains:
        added_domains = []
        for domain in additional_bypass_domains:
            if domain and domain not in all_bypasses:
                all_bypasses.append(domain)
                added_domains.append(domain)
        if added_domains:
            logger.debug(f"Added DNS search domains to no_proxy: {added_domains}")

    bypass_domains = ",".join(all_bypasses)

    return {
        "http_proxy": proxy_url,
        "https_proxy": proxy_url,
        "ftp_proxy": proxy_url,
        "all_proxy": proxy_url,
        "rsync_proxy": rsync_proxy,
        "no_proxy": bypass_domains,
    }


def write_bash_proxy_env(proxy_config: Optional[Dict[str, str]]):
    """Write bash/zsh compatible proxy environment file."""
    cache_file = Path.home() / ".config/netwatcher/proxy.env.sh"
    cache_file.parent.mkdir(parents=True, exist_ok=True)

    if proxy_config:
        content = f"""# Generated by NetWatcher - Auto-generated, will be overwritten
# To disable: set shell_proxy_enabled = false in ~/.config/netwatcher/config.toml

# Standard proxy variables
export http_proxy="{proxy_config["http_proxy"]}"
export https_proxy="{proxy_config["https_proxy"]}"
export ftp_proxy="{proxy_config["ftp_proxy"]}"
export all_proxy="{proxy_config["all_proxy"]}"

# Special case: rsync (no protocol)
export rsync_proxy="{proxy_config["rsync_proxy"]}"

# Bypass addresses
export no_proxy="{proxy_config["no_proxy"]}"
"""
        # Write atomically
        temp_file = cache_file.with_suffix(".tmp")
        with open(temp_file, "w") as f:
            f.write(content)
        temp_file.rename(cache_file)

        logger.debug(f"Updated bash/zsh proxy environment: {cache_file}")
    else:
        # No proxy needed - delete the file
        if cache_file.exists():
            cache_file.unlink()
            logger.debug(f"Removed bash/zsh proxy environment file: {cache_file}")
        else:
            logger.debug("No bash/zsh proxy environment file to remove")


def write_csh_proxy_env(proxy_config: Optional[Dict[str, str]]):
    """Write tcsh/csh compatible proxy environment file."""
    cache_file = Path.home() / ".config/netwatcher/proxy.env.csh"
    cache_file.parent.mkdir(parents=True, exist_ok=True)

    if proxy_config:
        content = f"""# Generated by NetWatcher - Auto-generated, will be overwritten
# To disable: set shell_proxy_enabled = false in ~/.config/netwatcher/config.toml

# Standard proxy variables
setenv http_proxy "{proxy_config["http_proxy"]}"
setenv https_proxy "{proxy_config["https_proxy"]}"
setenv ftp_proxy "{proxy_config["ftp_proxy"]}"
setenv all_proxy "{proxy_config["all_proxy"]}"

# Legacy uppercase versions
setenv HTTP_PROXY "{proxy_config["http_proxy"]}"
setenv HTTPS_PROXY "{proxy_config["https_proxy"]}"
setenv FTP_PROXY "{proxy_config["ftp_proxy"]}"
setenv ALL_PROXY "{proxy_config["all_proxy"]}"

# Special case: rsync (no protocol)
setenv rsync_proxy "{proxy_config["rsync_proxy"]}"

# Bypass addresses
setenv no_proxy "{proxy_config["no_proxy"]}"
setenv NO_PROXY "{proxy_config["no_proxy"]}"
"""
        # Write atomically
        temp_file = cache_file.with_suffix(".tmp")
        with open(temp_file, "w") as f:
            f.write(content)
        temp_file.rename(cache_file)

        logger.debug(f"Updated tcsh/csh proxy environment: {cache_file}")
    else:
        # No proxy needed - delete the file
        if cache_file.exists():
            cache_file.unlink()
            logger.debug(f"Removed tcsh/csh proxy environment file: {cache_file}")
        else:
            logger.debug("No tcsh/csh proxy environment file to remove")


def write_fish_proxy_env(proxy_config: Optional[Dict[str, str]]):
    """Write fish shell compatible proxy environment file."""
    cache_file = Path.home() / ".config/netwatcher/proxy.env.fish"
    cache_file.parent.mkdir(parents=True, exist_ok=True)

    if proxy_config:
        content = f"""# Generated by NetWatcher - Auto-generated, will be overwritten
# To disable: set shell_proxy_enabled = false in ~/.config/netwatcher/config.toml

# Standard proxy variables
set -x http_proxy "{proxy_config["http_proxy"]}"
set -x https_proxy "{proxy_config["https_proxy"]}"
set -x ftp_proxy "{proxy_config["ftp_proxy"]}"
set -x all_proxy "{proxy_config["all_proxy"]}"

# Legacy uppercase versions
set -x HTTP_PROXY "{proxy_config["http_proxy"]}"
set -x HTTPS_PROXY "{proxy_config["https_proxy"]}"
set -x FTP_PROXY "{proxy_config["ftp_proxy"]}"
set -x ALL_PROXY "{proxy_config["all_proxy"]}"

# Special case: rsync (no protocol)
set -x rsync_proxy "{proxy_config["rsync_proxy"]}"

# Bypass addresses
set -x no_proxy "{proxy_config["no_proxy"]}"
set -x NO_PROXY "{proxy_config["no_proxy"]}"
"""
        # Write atomically
        temp_file = cache_file.with_suffix(".tmp")
        with open(temp_file, "w") as f:
            f.write(content)
        temp_file.rename(cache_file)

        logger.debug(f"Updated fish proxy environment: {cache_file}")
    else:
        # No proxy needed - delete the file
        if cache_file.exists():
            cache_file.unlink()
            logger.debug(f"Removed fish proxy environment file: {cache_file}")
        else:
            logger.debug("No fish proxy environment file to remove")


def write_all_shell_proxy_files(proxy_config: Optional[Dict[str, str]]):
    """Write proxy environment files for all supported shells."""
    write_bash_proxy_env(proxy_config)
    write_csh_proxy_env(proxy_config)
    write_fish_proxy_env(proxy_config)


def get_shell_config_file(shell_name: str) -> Optional[Path]:
    """Get the appropriate shell config file for a given shell."""
    home = Path.home()

    shell_configs = {
        "bash": home / ".bash_profile",
        "zsh": home / ".zshrc",
        "tcsh": home / ".tcshrc",
        "csh": home / ".cshrc",
        "fish": home / ".config/fish/config.fish",
    }

    return shell_configs.get(shell_name)


def get_shell_integration_block(shell_name: str) -> Optional[str]:
    """Get the integration block for a specific shell."""

    integrations = {
        "bash": """# NetWatcher proxy configuration - Auto-generated, will be overwritten
# To disable: set shell_proxy_enabled = false in ~/.config/netwatcher/config.toml
if [[ -f ~/.config/netwatcher/proxy.env.sh ]]; then
    source ~/.config/netwatcher/proxy.env.sh
fi
# End NetWatcher proxy configuration""",
        "zsh": """# NetWatcher proxy configuration - Auto-generated, will be overwritten
# To disable: set shell_proxy_enabled = false in ~/.config/netwatcher/config.toml
if [[ -f ~/.config/netwatcher/proxy.env.sh ]]; then
    source ~/.config/netwatcher/proxy.env.sh
fi
# End NetWatcher proxy configuration""",
        "tcsh": """# NetWatcher proxy configuration - Auto-generated, will be overwritten
# To disable: set shell_proxy_enabled = false in ~/.config/netwatcher/config.toml
if (-f ~/.config/netwatcher/proxy.env.csh) then
    source ~/.config/netwatcher/proxy.env.csh
endif
# End NetWatcher proxy configuration""",
        "csh": """# NetWatcher proxy configuration - Auto-generated, will be overwritten
# To disable: set shell_proxy_enabled = false in ~/.config/netwatcher/config.toml
if (-f ~/.config/netwatcher/proxy.env.csh) then
    source ~/.config/netwatcher/proxy.env.csh
endif
# End NetWatcher proxy configuration""",
        "fish": """# NetWatcher proxy configuration - Auto-generated, will be overwritten
# To disable: set shell_proxy_enabled = false in ~/.config/netwatcher/config.toml
if test -f ~/.config/netwatcher/proxy.env.fish
    source ~/.config/netwatcher/proxy.env.fish
end
# End NetWatcher proxy configuration""",
    }

    return integrations.get(shell_name)


def setup_shell_integration(shell_name: str) -> bool:
    """Set up NetWatcher integration for a specific shell."""
    config_file = get_shell_config_file(shell_name)
    if not config_file:
        logger.warning(f"Unknown shell: {shell_name}")
        return False

    integration_block = get_shell_integration_block(shell_name)
    if not integration_block:
        logger.warning(f"No integration block defined for shell: {shell_name}")
        return False

    # For bash, create .bash_profile if it doesn't exist
    if shell_name == "bash" and not config_file.exists():
        config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(config_file, "w") as f:
            f.write(
                """# Created by NetWatcher
# Source .bashrc for interactive shells
if [[ "${-}" =~ i ]] && [[ -f ~/.bashrc ]]; then
    source ~/.bashrc
fi

"""
            )
        logger.info(f"Created {config_file}")

    # For fish, create config directory if it doesn't exist
    if shell_name == "fish":
        config_file.parent.mkdir(parents=True, exist_ok=True)

    # Check if already integrated
    content = config_file.read_text() if config_file.exists() else ""
    if "NetWatcher proxy configuration" in content:
        logger.debug(f"Shell proxy integration already present in {config_file}")
        return True

    # Add integration block
    try:
        with open(config_file, "a") as f:
            f.write(f"\n{integration_block}\n")
        logger.info(f"Added NetWatcher proxy integration to {config_file}")
        return True
    except Exception as e:
        logger.error(f"Failed to add integration to {config_file}: {e}")
        return False


def remove_shell_integration(shell_name: str) -> bool:
    """Remove NetWatcher proxy integration from a specific shell."""
    config_file = get_shell_config_file(shell_name)
    if not config_file or not config_file.exists():
        return True

    try:
        content = config_file.read_text()

        # Remove NetWatcher block
        lines = content.splitlines()
        filtered_lines = []
        skip_block = False

        for line in lines:
            if "NetWatcher proxy configuration" in line:
                skip_block = True
            elif "End NetWatcher proxy configuration" in line:
                skip_block = False
                continue
            elif not skip_block:
                filtered_lines.append(line)

        if len(filtered_lines) != len(lines):
            config_file.write_text("\n".join(filtered_lines) + "\n")
            logger.info(f"Removed NetWatcher proxy integration from {config_file}")

        return True
    except Exception as e:
        logger.error(f"Failed to remove integration from {config_file}: {e}")
        return False


def ensure_shell_proxy_config():
    """Ensure shell proxy configuration options exist in config.toml."""
    config_path = config.get_config_path()

    if not config_path.exists():
        logger.warning("Config file doesn't exist - run 'netwatcher configure' first")
        return False

    try:
        import toml

        # Read current config
        with open(config_path, "r") as f:
            config_data = toml.load(f)

        # Ensure [settings] section exists
        if "settings" not in config_data:
            config_data["settings"] = {}

        settings_changed = False

        # Add shell_proxy_enabled if missing
        if "shell_proxy_enabled" not in config_data["settings"]:
            config_data["settings"]["shell_proxy_enabled"] = True
            settings_changed = True
            logger.info("Added shell_proxy_enabled = true to config")
            logger.debug(
                f"DEBUG: shell_proxy_enabled value type: {type(config_data['settings']['shell_proxy_enabled'])}"
            )
            logger.debug(
                f"DEBUG: shell_proxy_enabled value: {repr(config_data['settings']['shell_proxy_enabled'])}"
            )

        # Add shell_proxy_shells if missing (commented example)
        if "shell_proxy_shells" not in config_data["settings"]:
            # We can't add comments with toml library, but we can note it in logs
            logger.info(
                'Note: You can optionally add shell_proxy_shells = ["bash", "zsh"] to limit which shells are configured'
            )

        # Write back if changed
        if settings_changed:
            with open(config_path, "w") as f:
                toml.dump(config_data, f)
            logger.info(f"Updated configuration file: {config_path}")

            # DEBUG: Read back the file to verify what was written
            with open(config_path, "r") as f:
                verification_data = toml.load(f)
            logger.debug(
                f"DEBUG: Verification - shell_proxy_enabled after write: {verification_data.get('settings', {}).get('shell_proxy_enabled', 'NOT_FOUND')}"
            )

        return True

    except Exception as e:
        logger.error(f"Failed to update config file: {e}")
        return False


def disable_shell_proxy_in_config():
    """Disable shell proxy in configuration file."""
    config_path = config.get_config_path()

    if not config_path.exists():
        logger.warning("Config file doesn't exist")
        return False

    try:
        import toml

        # Read current config
        with open(config_path, "r") as f:
            config_data = toml.load(f)

        # Ensure [settings] section exists
        if "settings" not in config_data:
            config_data["settings"] = {}

        # Disable shell proxy
        if config_data["settings"].get("shell_proxy_enabled", True):
            config_data["settings"]["shell_proxy_enabled"] = False

            # Write back
            with open(config_path, "w") as f:
                toml.dump(config_data, f)

            logger.info("Disabled shell_proxy_enabled in configuration")
            return True
        else:
            logger.info("Shell proxy was already disabled in configuration")
            return True

    except Exception as e:
        logger.error(f"Failed to update config file: {e}")
        return False


def setup_all_shell_integrations(config: Dict) -> bool:
    """Set up shell proxy integration for all detected shells."""
    if not config.get("settings", {}).get("shell_proxy_enabled", True):
        logger.info("Shell proxy integration disabled in config")
        return True

    detected_shells, primary_shell = detect_user_shells()
    configured_shells = config.get("settings", {}).get(
        "shell_proxy_shells", detected_shells
    )

    # Only configure shells that are both detected and requested
    shells_to_configure = [s for s in detected_shells if s in configured_shells]

    if not shells_to_configure:
        logger.info("No shells to configure for proxy integration")
        return True

    logger.info(f"Configuring shell proxy for: {shells_to_configure}")

    success = True
    for shell in shells_to_configure:
        try:
            if setup_shell_integration(shell):
                logger.debug(f"✅ Configured {shell} shell proxy integration")
            else:
                logger.warning(f"❌ Failed to configure {shell}")
                success = False
        except Exception as e:
            logger.warning(f"❌ Failed to configure {shell}: {e}")
            success = False

    return success


def remove_all_shell_integrations():
    """Remove NetWatcher proxy integration from all shells."""

    # First, disable in config
    disable_shell_proxy_in_config()

    detected_shells, _ = detect_user_shells()

    for shell in detected_shells:
        try:
            remove_shell_integration(shell)
        except Exception as e:
            logger.warning(f"Failed to remove {shell} integration: {e}")


def cleanup_shell_proxy_files():
    """Remove all shell proxy environment files."""
    cache_dir = Path.home() / ".config/netwatcher"
    proxy_files = [
        cache_dir / "proxy.env.sh",
        cache_dir / "proxy.env.csh",
        cache_dir / "proxy.env.fish",
    ]

    for proxy_file in proxy_files:
        try:
            if proxy_file.exists():
                proxy_file.unlink()
                logger.debug(f"Removed proxy file: {proxy_file}")
        except Exception as e:
            logger.warning(f"Failed to remove {proxy_file}: {e}")


def update_shell_proxy_configuration(
    proxy_url: str, dns_search_domains: Optional[List[str]] = None
):
    """Update shell proxy configuration based on proxy URL and DNS search domains."""
    try:
        proxy_config = parse_proxy_config(proxy_url, dns_search_domains)
        write_all_shell_proxy_files(proxy_config)

        if proxy_config:
            logger.info(
                f"Updated shell proxy configuration: {proxy_config['http_proxy']}"
            )
        else:
            logger.info("Disabled shell proxy configuration")

    except Exception as e:
        logger.error(f"Failed to update shell proxy configuration: {e}")
        # On error, clear proxy files to avoid stale configuration
        cleanup_shell_proxy_files()
