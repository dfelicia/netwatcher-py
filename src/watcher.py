import importlib.resources
import logging
import os
import subprocess
from pathlib import Path

# Ensure system paths are in the PATH for launchd, which has a minimal environment
os.environ["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin:" + os.environ.get("PATH", "")

import rumps
from threading import Timer
from CoreFoundation import (
    CFRunLoopAddSource,
    CFRunLoopGetCurrent,
    kCFRunLoopDefaultMode,
)
from SystemConfiguration import (
    SCDynamicStoreCreate,
    SCDynamicStoreCreateRunLoopSource,
    SCDynamicStoreSetNotificationKeys,
)

from . import actions, config


def setup_logging(debug):
    """Sets up logging for the application."""
    # Prevents handlers from being added multiple times
    if logging.getLogger().hasHandlers():
        logging.getLogger().handlers.clear()

    # Use centralized log configuration
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = config.LOG_FILE

    # Create standard formatter without milliseconds
    formatter = logging.Formatter(config.LOG_FORMAT, datefmt=config.LOG_DATE_FORMAT)

    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG if debug else logging.INFO)

    # Always use both file and console handlers
    # For services, stdout/stderr are redirected to /dev/null so no duplication
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)


class NetWatcherApp(rumps.App):
    """Main application class for NetWatcher."""

    def __init__(self, *args, **kwargs):
        """Initializes the NetWatcher application."""
        # Set a default name if not provided, required by rumps
        if "name" not in kwargs and not args:
            kwargs["name"] = "NetWatcher"

        super(NetWatcherApp, self).__init__(*args, **kwargs)

        # We don't need to store the name separately, it's in self.name from rumps
        self.config_path = config.get_config_path()
        self.config = config.load_config()
        self.current_location = None
        self.debounce_timer = None
        self.is_evaluating = False  # Flag to prevent concurrent evaluations
        self.runloop = None
        self.store = None

        # Set up logging right away
        # Check if config has debug enabled
        debug_enabled = self.config.get("settings", {}).get("debug", False)
        setup_logging(debug=debug_enabled)

        # Set the icon
        try:
            with importlib.resources.path("src", "icon_menu.png") as icon_path:
                # Load the icon path
                icon_path_str = str(icon_path)

                # Set the icon
                self.icon = icon_path_str

                # For menu bar icons, we need template mode for proper transparency
                # This tells macOS to treat the image as a template (black pixels become appropriate for menu bar)
                self.template = True

        except Exception as e:
            logging.warning(f"Failed to set application icon: {e}")
            self.icon = None  # Fallback to no icon

        # Build the initial menu
        self.setup_menu()

        # Set up notification callback
        rumps.notifications(self.notification_center)

    def setup_menu(self):
        """Sets up the initial state of the menu bar."""
        self.title = ""  # No text, just show the icon
        self.menu.clear()
        self.menu = [
            "NetWatcher",
            None,
            rumps.MenuItem("Test Configuration", callback=self.run_test),
            None,
            rumps.MenuItem("Quit", callback=self.quit_app),
        ]

    def setup_watcher(self):
        """Sets up the SystemConfiguration watcher."""
        self.store = SCDynamicStoreCreate(None, self.name, self.sc_callback, None)
        if self.store:
            keys_to_watch = [
                "State:/Network/Global/IPv4",
                "State:/Network/Interface/.*/IPv4",
            ]
            SCDynamicStoreSetNotificationKeys(self.store, keys_to_watch, None)
            self.runloop = CFRunLoopGetCurrent()
            source = SCDynamicStoreCreateRunLoopSource(None, self.store, 0)
            CFRunLoopAddSource(self.runloop, source, kCFRunLoopDefaultMode)
            logging.info("SystemConfiguration watcher is set up.")

            # Trigger initial evaluation after a short delay
            self.debounce_timer = Timer(1.0, self.evaluate_network_state)
            self.debounce_timer.start()
        else:
            logging.error("Failed to create SCDynamicStore.")

    def update_menu(self, location_name, connection_info=None, vpn_status=None):
        """Updates the menu bar title and menu items."""
        self.title = ""  # No text, just show the icon

        # Clear existing menu completely to avoid duplicates
        try:
            self.menu.clear()
        except Exception as e:
            logging.error(f"Menu clear error: {e}")

        # Build menu from scratch to avoid menu item conflicts
        menu_items = [
            "NetWatcher",
            None,
            f"Location: {location_name}",
        ]

        if vpn_status:
            # Split VPN status into separate menu items for better display
            vpn_lines = vpn_status.split("\n")
            for line in vpn_lines:
                if line.strip():  # Only add non-empty lines
                    stripped_line = line.strip()
                    # Format VPN menu items with cleaner labels
                    if stripped_line.startswith("VPN Connected to "):
                        # Extract server from "VPN Connected to <server>"
                        server = stripped_line.replace("VPN Connected to ", "")
                        menu_items.append(f"VPN endpoint: {server}")
                    elif stripped_line.startswith("IP: "):
                        # Change "IP: <ip>" to "VPN IP: <ip>"
                        ip = stripped_line.replace("IP: ", "")
                        menu_items.append(f"VPN IP: {ip}")
                    elif stripped_line.startswith("Protocol: "):
                        # Change "Protocol: <protocol>" to "VPN Protocol: <protocol>"
                        protocol = stripped_line.replace("Protocol: ", "")
                        menu_items.append(f"VPN Protocol: {protocol}")
                    else:
                        # Fallback for any other VPN info
                        menu_items.append(stripped_line)

        menu_items.append(None)

        if connection_info:
            for key, value in connection_info.items():
                # Special cases for acronyms to show as uppercase
                if key.lower() == "ip":
                    display_key = "IP"
                elif key.lower() == "isp":
                    display_key = "ISP"
                else:
                    display_key = key.capitalize()
                menu_items.append(f"{display_key}: {value}")
            menu_items.append(None)

        # Create fresh menu items each time to avoid conflicts
        menu_items.extend(
            [
                rumps.MenuItem("Test Configuration", callback=self.run_test),
                None,
                rumps.MenuItem("Quit", callback=self.quit_app),
            ]
        )

        try:
            self.menu = menu_items
        except Exception as e:
            logging.error(f"Menu assignment error: {e}")

    def run_test(self, _):
        """Callback to manually run a configuration test."""
        logging.info("Manual test triggered from menu bar.")

        # Run the evaluation
        location_name, vpn_active, vpn_details = (
            actions.check_and_apply_location_settings(self.config)
        )
        self.current_location = location_name

        # Update the menu to reflect any changes
        connection_info = actions.get_connection_details(silent=True)
        # Use VPN details from the evaluation (no need to fetch again)
        self.update_menu(
            location_name,
            connection_info=connection_info,
            vpn_status=vpn_details,
        )

        # Show a more informative notification with log file callback
        if location_name:
            message = f"Applied settings for location: {location_name}"
        else:
            message = "No matching location found for current network"

        # Use rumps notification - try to force banner style
        rumps.notification(
            title="NetWatcher Test",
            subtitle="Configuration Test Complete",
            message=message,
            sound=True,  # Adding sound may help make it more prominent
            data="open_log",
        )

    def notification_center(self, info):
        """Handle notification clicks."""
        logging.info(f"Notification clicked with info: {info}")

        # Check if this is our test notification
        if isinstance(info, dict) and info.get("data") == "open_log":
            logging.info("Opening log file from dict data")
            self.open_log_file()
        elif hasattr(info, "userInfo") and info.userInfo().get("data") == "open_log":
            logging.info("Opening log file from userInfo")
            self.open_log_file()
        elif hasattr(info, "data") and info.data == "open_log":
            logging.info("Opening log file from info.data")
            self.open_log_file()
        else:
            # For any test notification, open the log
            if "NetWatcher Test" in str(info):
                logging.info("Opening log file from NetWatcher Test match")
                self.open_log_file()
            else:
                logging.info(
                    f"No match found for notification info: {type(info)} - {dir(info)}"
                )

    def open_log_file(self):
        """Open the log file in the default application (usually Console.app)."""
        log_file = config.LOG_FILE
        try:
            # Use 'open' command to open the log file with the default application
            subprocess.run(["open", str(log_file)], check=True)
            logging.info(f"Opened log file: {log_file}")
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to open log file: {e}")
        except Exception as e:
            logging.error(f"Unexpected error opening log file: {e}")

    def sc_callback(self, *args):
        """SystemConfiguration callback for network changes."""
        # If we're already evaluating, ignore additional callbacks
        if self.is_evaluating:
            logging.debug("Network change detected during evaluation, ignoring")
            return

        # Cancel any existing debounce timer
        timer_was_active = self.debounce_timer is not None
        if self.debounce_timer is not None:
            self.debounce_timer.cancel()

        # Only log the debounce message if there wasn't already a timer running
        if not timer_was_active:
            logging.info("Network change detected, evaluating after debounce")

        # Simple approach like bash script: just wait for things to settle, then evaluate
        debounce_seconds = self.config.get("settings", {}).get("debounce_seconds", 5)
        self.debounce_timer = Timer(
            float(debounce_seconds), self.evaluate_network_state
        )
        self.debounce_timer.start()

    def evaluate_network_state(self, *args):
        """The core logic to check network and apply settings."""
        # Set the evaluation flag to prevent concurrent evaluations
        if self.is_evaluating:
            logging.debug("Evaluation already in progress, skipping")
            return

        self.is_evaluating = True

        try:
            logging.info("Evaluating network state after debounce")

            # Reload config in case it changed
            self.config = config.load_config()

            # This now calls the consolidated function in actions
            location_name, vpn_active, vpn_details = (
                actions.check_and_apply_location_settings(self.config)
            )
            self.current_location = location_name

            # Update connection info and VPN status for the menu (fetch silently)
            connection_info = actions.get_connection_details(silent=True)
            # Use VPN details from the evaluation (no need to fetch again)

            # Update the menu bar title and menu items
            self.update_menu(
                location_name,
                connection_info=connection_info,
                vpn_status=vpn_details,
            )

        finally:
            # Always clear the evaluation flag
            self.is_evaluating = False

    def quit_app(self, _):
        """Gracefully stop the launchd service and quit the app."""
        logging.info("Quit button clicked. Unloading launchd service.")
        try:
            plist_path = config.LAUNCH_AGENT_PLIST_PATH
            if plist_path.exists():
                # Use run_command from actions.py for consistency
                actions.run_command(["launchctl", "unload", "-w", str(plist_path)])
            else:
                logging.warning(
                    f"Launch agent plist not found at {plist_path}, cannot unload."
                )
        except Exception as e:
            logging.error(f"Failed to unload launchd service: {e}")

        rumps.quit_application()


def main(debug=False):
    """Main function to run the app."""
    setup_logging(debug)

    # The name is used for the SCDynamicStore and should be unique.
    app = NetWatcherApp(name="com.user.netwatcher", quit_button=None)

    # Hide from dock - this prevents the Python icon from appearing in the dock
    # We need to do this after the app is created but before run() is called
    import AppKit

    try:
        # Get the shared application instance
        shared_app = AppKit.NSApplication.sharedApplication()
        # Set activation policy to accessory (background only, no dock icon)
        shared_app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
        logging.info("Set application activation policy to hide from dock")
    except Exception as e:
        logging.warning(f"Could not hide from dock: {e}")

    app.setup_watcher()
    # Initial state will be evaluated by SystemConfiguration callback
    app.run()


if __name__ == "__main__":
    main()
