"""DanfossLink2Mqtt main application with UIAutomator integration."""
import logging
import time
import sys
import signal
import threading
from typing import Optional, Any, Callable, List, Dict, Set
from .config import (
    ADB_HOST, ADB_PORT, ADB_DEVICE_IP, ADB_DEVICE_PORT,
    MQTT_BROKER, MQTT_PORT, MQTT_USERNAME, MQTT_PASSWORD, MQTT_TOPIC_BASE,
    DANFOSS_APP_PACKAGE, POLL_INTERVAL, LOG_LEVEL
)
from .adb_controller import ADBController
from .mqtt_bridge import MQTTBridge
from .ui_automator import UIAutomatorParser
from .ui_config_manager import UIConfigManager

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DanfossLink2MQTT:
    """Application for remote-controlling the Danfoss Link app via MQTT."""

    def __init__(self):
        """Initializes the application"""
        self.adb: Optional[ADBController] = None
        self.mqtt: Optional[MQTTBridge] = None
        self.ui_parser: Optional[UIAutomatorParser] = None
        self.ui_config: Optional[UIConfigManager] = None
        self.running = False
        self.polling_thread: Optional[threading.Thread] = None
        self.discovery_registry: Set[str] = set()
        # Prevent stale poll readbacks from immediately overwriting a freshly
        # commanded target temperature.
        self.pending_setpoints: Dict[str, Dict[str, float]] = {}

        # Signal handler for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, sig, frame):
        """Handler for SIGINT and SIGTERM"""
        logger.info("Shutdown signal received")
        self.stop()
        sys.exit(0)

    def initialize(self) -> bool:
        """
        Initialize ADB, MQTT and UIAutomator.

        Returns:
            True on success, False on error
        """
        logger.info("Initializing DanfossLink2Mqtt...")

        # Load UIAutomator configuration first (may contain adb_device_ip)
        logger.info("Loading configuration...")
        self.ui_config = UIConfigManager("config.yaml")

        # Read IP and port from ui_config (fallback to config.py / env variable)
        device_ip = str(self.ui_config.get_setting("adb_device_ip", ADB_DEVICE_IP))
        device_port = int(self.ui_config.get_setting("adb_device_port", ADB_DEVICE_PORT))

        # Initialize ADB
        logger.info(f"Connecting to ADB device {device_ip}:{device_port}...")
        self.adb = ADBController(ADB_HOST, ADB_PORT, device_ip, device_port)
        if not self.adb.connect():
            logger.error("ADB connection failed")
            return False

        # Read device properties
        props = self.adb.get_device_properties()
        logger.info(f"Device connected: {props.get('ro.build.fingerprint', 'Unknown')}")

        # Initialize MQTT
        logger.info("Connecting to MQTT broker...")
        self.mqtt = MQTTBridge(MQTT_BROKER, MQTT_PORT, MQTT_USERNAME, MQTT_PASSWORD, MQTT_TOPIC_BASE)
        if not self.mqtt.connect():
            logger.error("MQTT connection failed")
            self.adb.disconnect()
            return False

        if not self.adb or not self.mqtt:
            return False
        adb = self.adb

        # Initialize UIAutomator
        logger.info("Initializing UIAutomator parser...")
        self.ui_parser = UIAutomatorParser(adb)

        # Register command handlers
        self._register_command_handlers()

        # Start Danfoss app automatically on startup
        if not self._launch_danfoss_app():
            logger.error("Initialization aborted: Danfoss app could not be launched")
            self.stop()
            return False

        logger.info("Initialization successful")
        return True

    def _register_command_handlers(self) -> None:
        """Register all available command handlers"""
        self.mqtt.register_command_handler("thermostats/+/setpoint", self._handle_setpoint_topic)

    def _launch_danfoss_app(self, force_start: bool = False) -> bool:
        """Start the Danfoss app via SplashActivity and confirm error dialogs.

        Unified startup procedure for all triggers (initialize, app/start, reboot, recovery).
        If the app is already running it will not be restarted and loading wait is skipped,
        unless force_start is requested.

        Returns:
            True if app is running (was already running or started successfully)
        """
        adb = self.adb
        ui_parser = self.ui_parser
        mqtt = self.mqtt
        if not adb:
            return False

        if not adb.is_app_installed(DANFOSS_APP_PACKAGE):
            message = (
                "Danfoss Link app is not installed on the Android device. "
                "Please install the app and start DanfossLink2Mqtt again."
            )
            install_hint = (
                "Install hint: run `adb install -r \"Danfoss.apk\"` from the project root "
                "or replace `Danfoss.apk` with the full path to your APK file. Start the app and enter pairing code before continuing."
            )
            logger.error(f"launch_app: {message}")
            logger.error(f"launch_app: {install_hint}")
            if mqtt:
                mqtt.publish("status/error", f"{message} {install_hint}", retain=True)
            return False

        # Check if app is already running
        if not force_start and adb.is_app_running(DANFOSS_APP_PACKAGE):
            logger.info("launch_app: Danfoss Link app is already running – no start needed")
            return True

        logger.info("launch_app: Starting Danfoss Link app (SplashActivity)...")
        adb.start_activity(
            DANFOSS_APP_PACKAGE,
            "com.danfoss.cumulus.app.firstuse.SplashActivity"
        )
        # Wait for app to load
        time.sleep(10.0)
        # Automatically dismiss error dialog (android:id/button1)
        if ui_parser:
            ui_parser.dismiss_error_dialog()
        time.sleep(3.0)
        logger.info("launch_app: App started")
        return True

    def _restart_danfoss_app(self, reason: str = "") -> bool:
        """Force-restart the Danfoss app and wait until startup is complete."""
        adb = self.adb
        if not adb:
            return False

        if reason:
            logger.warning(f"restart_app: {reason}")
        else:
            logger.warning("restart_app: restarting Danfoss Link app")

        adb.stop_app(DANFOSS_APP_PACKAGE)
        time.sleep(1.0)
        return self._launch_danfoss_app(force_start=True)

    def _tap_rooms_button(self) -> bool:
        """Switch to room overview via main_rooms_button.
        If the button is not found, the app is restarted via SplashActivity.
        """
        adb = self.adb
        ui_parser = self.ui_parser
        if not adb or not ui_parser:
            return False

        rooms_button_res_id = "com.danfoss.linkapp:id/main_rooms_button"
        bounds = ui_parser.get_bounds(rooms_button_res_id)
        if not bounds:
            logger.warning(
                "rooms_button: main_rooms_button not found – stopping and restarting app: "
                "am start -n com.danfoss.linkapp/com.danfoss.cumulus.app.firstuse.SplashActivity"
            )
            if not self._restart_danfoss_app("rooms_button missing"):
                return False
            # Check if rooms_button is now visible
            bounds = ui_parser.get_bounds(rooms_button_res_id)
            if bounds:
                x = (bounds["x1"] + bounds["x2"]) // 2
                y = (bounds["y1"] + bounds["y2"]) // 2
                logger.info(f"rooms_button: tapping main_rooms_button after app restart at {x},{y}")
                adb.send_tap(x, y)
                time.sleep(0.6)
            else:
                logger.info("rooms_button: app started, rooms_button not yet visible (splash still running)")
            return True

        x = (bounds["x1"] + bounds["x2"]) // 2
        y = (bounds["y1"] + bounds["y2"]) // 2
        logger.info(f"rooms_button: tapping main_rooms_button at {x},{y}")
        adb.send_tap(x, y)
        time.sleep(0.6)
        return True

    def _handle_setpoint_topic(self, topic: str, payload: str) -> None:
        """Set the target setpoint from `thermostats/<slug>/setpoint`."""
        topic_parts = topic.split("/")
        if len(topic_parts) != 3 or topic_parts[0] != "thermostats" or topic_parts[2] != "setpoint":
            logger.error(f"set_temperature: unexpected topic '{topic}'")
            return

        room_slug = str(topic_parts[1]).strip()
        if not room_slug:
            logger.error(f"set_temperature: room slug missing in topic '{topic}'")
            return

        try:
            target_temp = float(str(payload).strip())
        except (TypeError, ValueError) as e:
            logger.error(f"set_temperature: invalid payload '{payload}' for topic '{topic}': {e}")
            return

        self._set_room_temperature(room_slug, target_temp)

    def _set_room_temperature(self, room_slug: str, target_temp: float) -> None:
        """Set the setpoint of a room via swipe on the Danfoss spinner."""
        adb = self.adb
        ui_parser = self.ui_parser
        ui_config = self.ui_config
        mqtt = self.mqtt

        if not adb or not ui_parser or not ui_config or not mqtt:
            logger.error("set_temperature: application not fully initialized")
            return

        max_temp_limit = 26.0
        if target_temp > max_temp_limit:
            logger.warning(
                f"set_temperature: target {target_temp}°C above limit, capping at {max_temp_limit}°C"
            )
            target_temp = max_temp_limit

        if not room_slug:
            logger.error("set_temperature: 'room' missing in payload")
            return

        setpoint_state_topic = f"thermostats/{room_slug}/setpoint_state"

        self.pending_setpoints[room_slug] = {
            "target": float(target_temp),
            "set_at": float(time.time())
        }

        # Optimistic state update: publish command target immediately so
        # downstream consumers do not have to wait for the next poll/readback.
        mqtt.publish(setpoint_state_topic, target_temp)

        package_name = DANFOSS_APP_PACKAGE
        edit_res_id = f"{package_name}:id/roomoverview_edit_button"

        def locate_edit_button() -> Optional[Dict[str, int]]:
            edit_bounds = ui_parser.get_bounds(edit_res_id)
            if not edit_bounds and self._tap_rooms_button():
                edit_bounds = ui_parser.get_bounds(edit_res_id)

            if not edit_bounds:
                logger.error(f"set_temperature: edit button not found ({edit_res_id})")
                return None

            return {
                "x": (edit_bounds["x1"] + edit_bounds["x2"]) // 2,
                "y": (edit_bounds["y1"] + edit_bounds["y2"]) // 2
            }

        # 1) Calculate steps (0.5°C per step)
        step_size = 0.5
        tolerance = 0.45  # Values in dump are in 0.5 steps
        max_iterations = max(1, int(ui_config.get_setting("set_temperature_max_iterations", 10)))
        burst_steps = max(1, int(ui_config.get_setting("set_temperature_burst_steps", 3)))

        inter_step_delay_s = float(ui_config.get_setting("set_temperature_swipe_pause_s", 2.0))
        readback_delay_s = float(ui_config.get_setting("set_temperature_readback_delay_s", 1.5))

        def attempt_set_temperature(attempt_label: str) -> tuple[bool, Optional[float]]:
            edit_button = locate_edit_button()
            if not edit_button:
                return False, None

            ex = int(edit_button["x"])
            ey = int(edit_button["y"])
            logger.info(f"set_temperature: {attempt_label} edit button at {ex},{ey}")

            def tap_edit_button() -> None:
                adb.send_tap(ex, ey)
                time.sleep(0.1)

            reached = False
            last_setpoint: Optional[float] = None
            recovery_attempted = False
            for step in range(max_iterations):
                spinner_info = ui_parser.get_room_spinner_bounds(package_name, room_slug, use_cache=False)
                if not spinner_info:
                    if not recovery_attempted and self._tap_rooms_button():
                        recovery_attempted = True
                        logger.warning(
                            f"set_temperature: {attempt_label} no spinner found, opened rooms view and retrying"
                        )
                        continue

                    logger.error(f"set_temperature: spinner for '{room_slug}' no longer found")
                    break

                current_setpoint: Optional[float] = spinner_info.get("setpoint_c")
                if current_setpoint is None:
                    if not recovery_attempted and self._tap_rooms_button():
                        recovery_attempted = True
                        logger.warning(
                            f"set_temperature: {attempt_label} setpoint not parseable, opened rooms view and retrying"
                        )
                        continue

                    logger.error(f"set_temperature: current setpoint for '{room_slug}' unknown")
                    break

                last_setpoint = current_setpoint
                diff = target_temp - current_setpoint
                if abs(diff) <= tolerance:
                    reached = True
                    logger.info(f"set_temperature: {attempt_label} target reached ({current_setpoint}°C)")
                    break

                cx: int = int(spinner_info["center_x"])
                cy: int = int(spinner_info["center_y"])
                step_px: int = int(spinner_info["step_px"])
                swipe_direction = -1 if diff > 0 else 1  # up = warmer

                remaining_steps = abs(round(diff / step_size))
                planned_steps = max(1, min(remaining_steps, burst_steps))
                logger.info(
                    f"set_temperature: {attempt_label} burst {step + 1}: {current_setpoint}°C -> {target_temp}°C, "
                    f"{planned_steps} step(s)"
                )

                tap_edit_button()
                # A long swipe can cover multiple 0.5°C steps in one go.
                total_dy = swipe_direction * step_px * planned_steps
                swipe_duration_ms = max(220, int(220 * planned_steps))
                adb.send_swipe(cx, cy, cx, cy + total_dy, duration_ms=swipe_duration_ms)

                if planned_steps > 1:
                    time.sleep(inter_step_delay_s)

                # Short wait after burst then read setpoint via fresh dump.
                time.sleep(readback_delay_s)

            return reached, last_setpoint

        # 2) Adjust in bursts until readback reaches target setpoint.
        reached, last_setpoint = attempt_set_temperature("attempt 1")

        if not reached and self._restart_danfoss_app(
            f"set_temperature: target not reached for '{room_slug}' (target={target_temp}, last={last_setpoint})"
        ):
            self._tap_rooms_button()
            reached, last_setpoint = attempt_set_temperature("attempt 2 after app restart")

        # 3) Publish status
        if reached:
            mqtt.publish(setpoint_state_topic, target_temp)
            logger.info(f"set_temperature: '{room_slug}' setpoint set to {target_temp}°C")
        else:
            mqtt.publish(
                f"thermostats/{room_slug}/setpoint_error",
                f"target={target_temp}, last={last_setpoint}"
            )
            logger.warning(
                f"set_temperature: target possibly not reached (target={target_temp}, last={last_setpoint})"
            )

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        """Robustly convert numeric values to float (supports decimal comma)."""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)

        text = str(value).strip().replace(",", ".")
        if not text:
            return None

        try:
            return float(text)
        except ValueError:
            return None

    @staticmethod
    def _derive_hvac_action(current_temp: Optional[float], target_temp: Optional[float]) -> Optional[str]:
        """Derive hvac_action from current/target temperature."""
        if current_temp is None or target_temp is None:
            return None
        return "idle" if target_temp < current_temp else "heating"

    def _publish_danfoss_thermostats(self, force: bool = False) -> None:
        """Analyse the UI dump and publish thermostat names and values."""
        if not self.ui_parser or not self.ui_config or not self.mqtt:
            return

        package_name = DANFOSS_APP_PACKAGE
        extractor: Optional[Callable[..., List[Dict[str, Any]]]] = getattr(
            self.ui_parser,
            "extract_danfoss_thermostats",
            None
        )
        if not extractor:
            logger.warning("UI parser does not support Danfoss thermostat extraction")
            return

        thermostats = extractor(package_name, use_cache=not force)
        if not thermostats:
            if self._tap_rooms_button():
                thermostats = extractor(package_name, use_cache=False)

        if not thermostats:
            logger.debug("No Danfoss thermostats detected in current UI dump")
            return

        thermostats_payload: List[Dict[str, Any]] = []
        for thermostat in thermostats:
            slug_value = thermostat.get("slug")
            if not slug_value:
                continue
            slug = str(slug_value)

            base_topic = f"thermostats/{slug}"
            measured_setpoint = self._to_float(thermostat.get("setpoint_c"))
            pending_entry = self.pending_setpoints.get(slug)
            setpoint_to_publish = thermostat.get("setpoint_c", "")
            if pending_entry:
                pending_target = float(pending_entry.get("target", 0.0))
                pending_age_s = time.time() - float(pending_entry.get("set_at", 0.0))
                pending_ttl_s = 30.0
                pending_tolerance = 0.45

                # Keep optimistic setpoint while the app/UI catches up.
                if (
                    measured_setpoint is not None
                    and abs(measured_setpoint - pending_target) <= pending_tolerance
                ):
                    self.pending_setpoints.pop(slug, None)
                elif pending_age_s <= pending_ttl_s:
                    setpoint_to_publish = pending_target
                else:
                    self.pending_setpoints.pop(slug, None)

            self.mqtt.publish(f"{base_topic}/label", thermostat.get("label", ""))
            self.mqtt.publish(f"{base_topic}/kind", thermostat.get("kind", "room"))
            self.mqtt.publish(f"{base_topic}/value", thermostat.get("temperature_c", ""))
            self.mqtt.publish(f"{base_topic}/setpoint_state", setpoint_to_publish)

            # Derive hvac_action from setpoint/current: setpoint < value -> idle, else heating.
            current_temp = self._to_float(thermostat.get("temperature_c"))
            target_temp = self._to_float(setpoint_to_publish)
            hvac_action = self._derive_hvac_action(current_temp, target_temp)
            if hvac_action:
                self.mqtt.publish(f"{base_topic}/hvac_action", hvac_action)

            if thermostat.get("kind", "room") == "room":
                self.mqtt.publish(f"{base_topic}/mode", "heat")

            thermostats_payload.append({
                "label": thermostat.get("label", ""),
                "slug": slug,
                "kind": thermostat.get("kind", "room"),
                "temperature_c": thermostat.get("temperature_c"),
                "setpoint_c": thermostat.get("setpoint_c"),
                "hvac_action": hvac_action
            })

        self._publish_homeassistant_discovery(thermostats_payload)

    def _publish_homeassistant_discovery(self, thermostats: List[Dict[str, Any]]) -> None:
        """Publish MQTT discovery for Home Assistant climate entities per room."""
        if not self.mqtt or not self.ui_config:
            return

        enabled = bool(self.ui_config.get_setting("homeassistant_discovery", True))
        if not enabled:
            return

        prefix = str(self.ui_config.get_setting("homeassistant_discovery_prefix", "homeassistant"))
        for thermostat in thermostats:
            slug = thermostat.get("slug")
            if not slug:
                continue

            room_key = str(slug)
            if str(thermostat.get("kind", "room")) != "room":
                continue

            if room_key in self.discovery_registry:
                continue

            label = str(thermostat.get("label", room_key))
            base_state = f"{MQTT_TOPIC_BASE}/thermostats/{room_key}"
            device = {
                "identifiers": [f"{MQTT_TOPIC_BASE}"],
                "name": "Thermostat",
                "manufacturer": "Danfoss",
                "model": "Danfoss Link"
            }

            climate_config_topic = f"{prefix}/climate/{MQTT_TOPIC_BASE}_{room_key}/config"
            climate_payload = {
                "name": f"{label}",
                "unique_id": f"{MQTT_TOPIC_BASE}_{room_key}_climate",
                "icon": "mdi:heating-coil",
                "temperature_command_topic": f"{MQTT_TOPIC_BASE}/thermostats/{room_key}/setpoint",
                "temperature_state_topic": f"{base_state}/setpoint_state",
                "current_temperature_topic": f"{base_state}/value",
                "mode_state_topic": f"{base_state}/mode",
                "action_topic": f"{base_state}/hvac_action",
                "availability_topic": f"{MQTT_TOPIC_BASE}/status",
                "payload_available": "online",
                "payload_not_available": "offline",
                "modes": ["heat"],
                "min_temp": float(self.ui_config.get_setting("thermostat_min_temp", 6.0)),
                "max_temp": float(self.ui_config.get_setting("thermostat_max_temp", 30.0)),
                "temp_step": float(self.ui_config.get_setting("thermostat_temp_step", 0.5)),
                "precision": 0.1,
                "device": device
            }
            self.mqtt.publish_absolute(climate_config_topic, climate_payload, retain=True)

            self.discovery_registry.add(room_key)

    def poll_data(self) -> None:
        """Poll sensor and UI data from the Android device"""
        logger.info(f"Starting data polling every {POLL_INTERVAL} seconds...")
        if not self.adb or not self.mqtt:
            logger.error("Polling aborted: ADB/MQTT not initialized")
            return

        while self.running:
            try:
                # Ensure ADB is connected
                if not self.adb.ensure_connected():
                    logger.error("Polling: ADB reconnect failed – waiting 10s")
                    time.sleep(10)
                    continue

                # Read UIAutomator data
                self._poll_ui_data(force=False)

                # Publish Danfoss thermostat data from UI dump analysis
                self._publish_danfoss_thermostats(force=False)

                time.sleep(POLL_INTERVAL)

            except Exception as e:
                logger.error(f"Polling error: {e}")
                time.sleep(5)

    def _poll_ui_data(self, force: bool = False) -> None:
        """
        Poll UIAutomator data.

        Args:
            force: Force update even when cached
        """
        try:
            if not self.ui_config or not self.ui_parser:
                return

            ui_config = self.ui_config
            ui_parser = self.ui_parser

            # Get enabled elements
            elements = ui_config.get_enabled_elements()

            if not elements:
                return

            logger.debug(f"Polling {len(elements)} UI elements...")

            for element_name, element_config in elements.items():
                try:
                    resource_id = element_config.get("resource_id")
                    value_type = element_config.get("type", "text")
                    mqtt_topic = element_config.get("mqtt_topic")

                    if not resource_id or not mqtt_topic:
                        continue

                    resource_id = str(resource_id)
                    mqtt_topic = str(mqtt_topic)

                    # Extract value
                    value = ui_parser.extract_value_by_resource_id(
                        resource_id,
                        value_type
                    )

                    if value is not None:
                        # Check for changes if configured
                        publish_only_changes = ui_config.get_setting(
                            "publish_only_changes",
                            True
                        )

                        if publish_only_changes:
                            if ui_parser.is_value_changed(element_name, value):
                                self.mqtt.publish(mqtt_topic, value)
                                logger.debug(f"UI value published: {mqtt_topic} = {value}")
                        else:
                            self.mqtt.publish(mqtt_topic, value)
                            logger.debug(f"UI value published: {mqtt_topic} = {value}")

                except Exception as e:
                    logger.warning(f"Error polling {element_name}: {e}")

        except Exception as e:
            logger.error(f"UI polling error: {e}")

    def run(self) -> None:
        """Start the main loop"""
        if not self.initialize():
            logger.error("Initialization failed")
            return

        self.running = True
        logger.info("Starting main loop...")

        # Start polling in a separate thread
        self.polling_thread = threading.Thread(target=self.poll_data, daemon=True)
        self.polling_thread.start()

        # Keep main thread alive
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()

    def stop(self) -> None:
        """Stop the application"""
        logger.info("Stopping DanfossLink2Mqtt...")
        self.running = False

        # Wait for polling thread
        if self.polling_thread and self.polling_thread.is_alive():
            self.polling_thread.join(timeout=5)

        if self.adb:
            self.adb.disconnect()

        if self.mqtt:
            self.mqtt.disconnect()

        logger.info("Application stopped")


def main():
    """Entry point"""
    app = DanfossLink2MQTT()
    app.run()


if __name__ == "__main__":
    main()

