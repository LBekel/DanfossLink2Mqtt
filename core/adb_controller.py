"""ADB controller for communication with Android devices"""
import logging
import threading
from typing import Optional, Dict, Any
from adb_shell.adb_device import AdbDeviceTcp

logger = logging.getLogger(__name__)


class ADBController:
    """Controls Android devices via ADB"""

    def __init__(self, host: str, port: int, device_ip: str, device_port: int):
        """
        Initializes the ADB controller.

        Args:
            host: ADB host (usually localhost)
            port: ADB port (usually 5037)
            device_ip: IP address of the Android device
            device_port: Port of the Android device (usually 5555)
        """
        self.host = host
        self.port = port
        self.device_ip = device_ip
        self.device_port = device_port
        self.device: Optional[AdbDeviceTcp] = None
        # Ensures that shell commands run strictly sequential.
        self._command_lock = threading.RLock()

    def connect(self) -> bool:
        """Establish connection to the Android device"""
        try:
            logger.info(f"Connecting to {self.device_ip}:{self.device_port}")
            self.device = AdbDeviceTcp(self.device_ip, self.device_port)
            self.device.connect()
            logger.info("Connected successfully")
            # Set screen size and density so the UI dump contains all elements
            self.device.shell("wm size 500x5000")
            logger.info("Screen size set: 500x5000")
            self.device.shell("wm density 200")
            logger.info("Screen density set: 200")
            return True
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False

    def is_connected(self) -> bool:
        """Check whether the ADB connection is active.

        Returns:
            True if connected and reachable, False otherwise
        """
        if not self.device:
            return False
        try:
            result = self.shell_command("echo ok")
            return result.strip() == "ok"
        except Exception:
            return False

    def ensure_connected(self) -> bool:
        """Ensure the ADB connection is active. Reconnects if necessary.

        Returns:
            True if connected (or reconnection successful), False on error
        """
        if self.is_connected():
            logger.debug("ADB: connection active")
            return True
        logger.warning("ADB: connection lost – attempting reconnect...")
        return self.connect()

    def disconnect(self) -> None:
        """Disconnect from the device"""
        if self.device:
            try:
                self.device.close()
                logger.info("Disconnected")
            except Exception as e:
                logger.error(f"Error while disconnecting: {e}")

    def shell_command(self, command: str) -> str:
        """
        Execute a shell command on the device.

        Args:
            command: The command to execute

        Returns:
            Output of the command
        """
        if not self.device:
            logger.error("Device not connected")
            return ""

        try:
            with self._command_lock:
                result = self.device.shell(command)
            return result
        except Exception as e:
            logger.error(f"Shell command failed: {e}")
            return ""

    def start_app(self, package_name: str) -> bool:
        """
        Start an app.

        Args:
            package_name: Package name of the app

        Returns:
            True on success, False on error
        """
        try:
            logger.info(f"Starting app: {package_name}")
            self.shell_command(f"monkey -p {package_name} -c android.intent.category.LAUNCHER 1")
            return True
        except Exception as e:
            logger.error(f"Error starting app: {e}")
            return False

    def stop_app(self, package_name: str) -> bool:
        """
        Stop an app.

        Args:
            package_name: Package name of the app

        Returns:
            True on success, False on error
        """
        try:
            logger.info(f"Stopping app: {package_name}")
            self.shell_command(f"am force-stop {package_name}")
            return True
        except Exception as e:
            logger.error(f"Error stopping app: {e}")
            return False

    def send_keyevent(self, keycode: int) -> bool:
        """
        Send a key event to the device.

        Args:
            keycode: The keycode to send

        Returns:
            True on success, False on error
        """
        try:
            self.shell_command(f"input keyevent {keycode}")
            return True
        except Exception as e:
            logger.error(f"Error sending key event: {e}")
            return False

    def send_tap(self, x: int, y: int) -> bool:
        """
        Send a tap event to a position.

        Args:
            x: X coordinate
            y: Y coordinate

        Returns:
            True on success, False on error
        """
        try:
            self.shell_command(f"input tap {x} {y}")
            return True
        except Exception as e:
            logger.error(f"Error sending tap event: {e}")
            return False

    def send_swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> bool:
        """
        Send a swipe command.

        Args:
            x1, y1: Start position
            x2, y2: End position
            duration_ms: Duration in milliseconds

        Returns:
            True on success
        """
        try:
            self.shell_command(f"input swipe {x1} {y1} {x2} {y2} {duration_ms}")
            return True
        except Exception as e:
            logger.error(f"Error sending swipe command: {e}")
            return False

    def send_text(self, text: str) -> bool:
        """
        Send text to the device (e.g. into a text field).

        Args:
            text: The text to send

        Returns:
            True on success, False on error
        """
        try:
            # Escape special characters and spaces
            escaped_text = text.replace("'", "\\'").replace(" ", "%s")
            self.shell_command(f"input text '{escaped_text}'")
            return True
        except Exception as e:
            logger.error(f"Error sending text: {e}")
            return False

    def is_app_running(self, package_name: str) -> bool:
        """
        Check whether an app is currently running.

        Args:
            package_name: Package name of the app

        Returns:
            True if the app is running, False otherwise
        """
        try:
            result = self.shell_command(f"pidof {package_name}")
            running = bool(result and result.strip())
            logger.debug(f"is_app_running({package_name}): {'running' if running else 'not active'} (pidof='{result.strip()}')")
            return running
        except Exception as e:
            logger.error(f"Error in is_app_running: {e}")
            return False

    def is_app_installed(self, package_name: str) -> bool:
        """Check whether an app package is installed on the device."""
        try:
            result = self.shell_command(f"pm path {package_name}")
            installed = bool(result and result.strip().startswith("package:"))
            logger.debug(
                f"is_app_installed({package_name}): {'installed' if installed else 'not installed'} "
                f"(pm path='{result.strip()}')"
            )
            return installed
        except Exception as e:
            logger.error(f"Error in is_app_installed: {e}")
            return False

    def start_activity(self, package_name: str, activity_name: str) -> bool:
        """
        Start an activity with full package name.

        Args:
            package_name: Package name of the app
            activity_name: Activity name (e.g. com.danfoss.cumulus.app.firstuse.SplashActivity)

        Returns:
            True on success, False on error
        """
        try:
            logger.info(f"Starting activity: {package_name}/{activity_name}")
            self.shell_command(f"am start -n {package_name}/{activity_name}")
            return True
        except Exception as e:
            logger.error(f"Error starting activity: {e}")
            return False

    def get_device_properties(self) -> Dict[str, str]:
        """
        Read device properties.

        Returns:
            Dictionary with device properties
        """
        properties = {}
        try:
            result = self.shell_command("getprop")
            for line in result.split('\n'):
                if line.strip():
                    # Parse lines like [ro.build.version.release]: [13]
                    if '[' in line and ']' in line:
                        parts = line.split(']')
                        if len(parts) >= 2:
                            key = parts[0].replace('[', '').strip()
                            value = parts[1].replace('[', '').replace(']', '').strip()
                            properties[key] = value
        except Exception as e:
            logger.error(f"Error reading device properties: {e}")

        return properties
