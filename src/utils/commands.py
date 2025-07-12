"""
Command execution utilities for NetWatcher.

This module provides robust command execution with error handling and logging.
It serves as the central location for all command execution to avoid duplication.
"""

import logging
import shlex
import subprocess


def run_command(
    command, capture=False, text=True, input=None, shell=False, quiet_on_error=False
):
    """
    Execute a command with robust error handling and logging.

    Args:
        command: Command to execute (list of strings or string if shell=True)
        capture: If True, return command output; if False, return success status
        text: If True, decode output as text; if False, return bytes
        input: Optional input to send to the command's stdin
        shell: If True, execute through the shell; if False, exec directly
        quiet_on_error: If True, suppress error logging for expected failures

    Returns:
        If capture=True: Command output string or None on error
        If capture=False: True on success, False on failure
    """
    # Convert list to string for shell execution
    if shell and isinstance(command, list):
        command = shlex.join(command)

    logging.debug(f"Running command ({'shell' if shell else 'list'}): {command}")

    try:
        result = subprocess.run(
            command,
            shell=shell,
            check=False,
            capture_output=True,
            text=text,
            encoding="utf-8",
            errors="ignore",
            input=input,
        )

        # Log output appropriately
        if result.stderr:
            if result.returncode != 0:
                logging.debug(f"Command failed with stderr: {result.stderr.strip()}")
            else:
                logging.debug(f"Command succeeded with stderr: {result.stderr.strip()}")

        if result.returncode != 0:
            if not quiet_on_error:
                logging.debug(
                    f"Command '{command}' failed with status {result.returncode}"
                )
                if result.stdout:
                    logging.debug(f"Stdout: {result.stdout.strip()}")
            else:
                logging.debug(f"Command '{command}' failed (expected)")

            return (
                ((result.stdout or "") + (result.stderr or "")).strip()
                if capture
                else False
            )

        # Success case
        return result.stdout.strip() if capture else True

    except FileNotFoundError:
        cmd_name = command.split()[0] if shell else command[0]
        logging.error(f"Command not found: {cmd_name}")
        return None if capture else False
    except Exception as e:
        logging.error(f"Unexpected error running command '{command}': {e}")
        return None if capture else False
