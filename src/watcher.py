import os

# Ensure system paths are in the PATH for launchd, which has a minimal environment.
os.environ["PATH"] = "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:" + os.environ.get(
    "PATH", ""
)

import rumps
import logging
from threading import Timer
import importlib.resources
from pathlib import Path
from CoreFoundation import (
    CFRunLoopGetCurrent,
    CFRunLoopAddSource,
    kCFRunLoopDefaultMode,
)
import subprocess
from SystemConfiguration import (
    SCDynamicStoreCreate,
    SCDynamicStoreSetNotificationKeys,
    SCDynamicStoreCreateRunLoopSource,
)
from SystemConfiguration import SCDynamicStoreCopyValue

from . import actions, config


class GroupSeparatorFormatter(logging.Formatter):
    """Custom formatter that removes milliseconds and adds blank lines between message groups."""

    def __init__(self, fmt, log_file_path):
        super().__init__(fmt)
        self.log_file_path = log_file_path
        self.group_separation_threshold = 2.0  # seconds between message groups
        self.state_file = Path(log_file_path).parent / ".last_log_time"

    def format(self, record):
        # Use format without milliseconds
        self.datefmt = "%Y-%m-%d %H:%M:%S"
        formatted = super().format(record)

        # Add blank line if enough time has passed since last log message
        import time

        current_time = time.time()

        # Read last log time from state file
        last_log_time = 0
        try:
            if self.state_file.exists():
                last_log_time = float(self.state_file.read_text().strip())
        except (ValueError, FileNotFoundError):
            pass

        # Add blank line if enough time has passed
        if (
            last_log_time > 0
            and (current_time - last_log_time) > self.group_separation_threshold
        ):
            formatted = "\n" + formatted

        # Update state file with current time
        try:
            self.state_file.write_text(str(current_time))
        except Exception:
            pass  # Ignore errors writing state file

        return formatted


def setup_logging(debug):
    """Sets up logging for the application."""
    # Prevents handlers from being added multiple times
    if logging.getLogger().hasHandlers():
        logging.getLogger().handlers.clear()

    log_dir = Path.home() / "Library" / "Logs" / "netwatcher"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "netwatcher.log"

    # Create custom formatter with log file path
    formatter = GroupSeparatorFormatter(
        "%(asctime)s - %(levelname)s - %(message)s", log_file
    )

    # Create file handler with custom formatter
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)

    # Create console handler with same formatter
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
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
        self.runloop = None
        self.store = None

        # Set up logging right away
        # The debug flag is not easily available here, so we assume False.
        # The CLI can set it up again if needed for specific commands.
        setup_logging(debug=False)

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
        else:
            logging.error("Failed to create SCDynamicStore.")

    def update_menu(self, location_name, connection_info=None, vpn_status=None):
        """Updates the menu bar title and menu items."""
        self.title = ""  # No text, just show the icon

        # Clear existing menu completely to avoid duplicates
        self.menu.clear()

        # Build menu from scratch to avoid menu item conflicts
        menu_items = [
            "NetWatcher",
            None,
            f"Location: {location_name}",
        ]

        if vpn_status:
            menu_items.append(f"VPN: {vpn_status}")

        menu_items.append(None)

        if connection_info:
            menu_items.append(rumps.MenuItem("--- Connection ---", callback=None))
            for key, value in connection_info.items():
                # Special case for "ip" to show as "IP"
                display_key = "IP" if key.lower() == "ip" else key.capitalize()
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

        self.menu = menu_items

    def run_test(self, _):
        """Callback to manually run a configuration test."""
        logging.info("Manual test triggered from menu bar.")

        # Run the evaluation
        location_name = actions.check_and_apply_location_settings(self.config)
        self.current_location = location_name

        # Update the menu to reflect any changes
        connection_info = actions.get_connection_details()
        # Only check VPN details if we're actually on a VPN interface
        vpn_status = actions.get_vpn_details() if actions.is_vpn_active() else None
        self.update_menu(
            location_name,
            connection_info=connection_info,
            vpn_status=vpn_status,
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
        logging.info("Network change detected, evaluating state.")
        # Debounce the network state evaluation
        if self.debounce_timer is not None:
            self.debounce_timer.cancel()
        self.debounce_timer = Timer(1.0, self.evaluate_network_state)
        self.debounce_timer.start()

    def evaluate_network_state(self, *args):
        """The core logic to check network and apply settings."""
        logging.info("Evaluating network state after debounce.")

        # Reload config in case it changed
        self.config = config.load_config()

        # This now calls the consolidated function in actions
        location_name = actions.check_and_apply_location_settings(self.config)
        self.current_location = location_name

        # Update connection info and VPN status for the menu
        connection_info = actions.get_connection_details()
        # Only check VPN details if we're actually on a VPN interface
        vpn_status = actions.get_vpn_details() if actions.is_vpn_active() else None

        # Update the menu bar title and menu items
        self.update_menu(
            location_name,
            connection_info=connection_info,
            vpn_status=vpn_status,
        )

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
    app.evaluate_network_state()  # Initial check
    app.run()


if __name__ == "__main__":
    main()
