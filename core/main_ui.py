"""DanfossLink2Mqtt Hauptanwendung mit UIAutomator-Integration."""
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

# Logging konfigurieren
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DanfossLink2MQTT:
    """Anwendung zur Fernsteuerung der Danfoss Link App via MQTT."""

    def __init__(self):
        """Initialisiert die Anwendung"""
        self.adb: Optional[ADBController] = None
        self.mqtt: Optional[MQTTBridge] = None
        self.ui_parser: Optional[UIAutomatorParser] = None
        self.ui_config: Optional[UIConfigManager] = None
        self.running = False
        self.polling_thread: Optional[threading.Thread] = None
        self.discovery_registry: Set[str] = set()

        # Signal-Handler für graceful Shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, sig, frame):
        """Handler für SIGINT und SIGTERM"""
        logger.info("Shutdown-Signal empfangen")
        self.stop()
        sys.exit(0)

    def initialize(self) -> bool:
        """
        Initialisiert ADB, MQTT und UIAutomator

        Returns:
            True bei Erfolg, False bei Fehler
        """
        logger.info("Initialisiere DanfossLink2Mqtt...")

        # Lade UIAutomator-Konfiguration zuerst (enthält ggf. adb_device_ip)
        logger.info("Lade UIAutomator-Konfiguration...")
        self.ui_config = UIConfigManager("config.yaml")

        # Validiere Config
        validation = self.ui_config.validate_config()
        if validation["errors"]:
            logger.error(f"Konfigurationsfehler: {validation['errors']}")
        if validation["warnings"]:
            logger.warning(f"Konfigurationswarnungen: {validation['warnings']}")

        # IP und Port aus ui_config lesen (Fallback auf config.py / Umgebungsvariable)
        device_ip = str(self.ui_config.get_setting("adb_device_ip", ADB_DEVICE_IP))
        device_port = int(self.ui_config.get_setting("adb_device_port", ADB_DEVICE_PORT))

        # Initialisiere ADB
        logger.info(f"Verbinde mit ADB-Gerät {device_ip}:{device_port}...")
        self.adb = ADBController(ADB_HOST, ADB_PORT, device_ip, device_port)
        if not self.adb.connect():
            logger.error("ADB-Verbindung fehlgeschlagen")
            return False

        # Lese Geräteeigenschaften
        props = self.adb.get_device_properties()
        logger.info(f"Gerät verbunden: {props.get('ro.build.fingerprint', 'Unbekannt')}")

        # Initialisiere MQTT
        logger.info("Verbinde mit MQTT-Broker...")
        self.mqtt = MQTTBridge(MQTT_BROKER, MQTT_PORT, MQTT_USERNAME, MQTT_PASSWORD, MQTT_TOPIC_BASE)
        if not self.mqtt.connect():
            logger.error("MQTT-Verbindung fehlgeschlagen")
            self.adb.disconnect()
            return False

        if not self.adb or not self.mqtt:
            return False
        adb = self.adb

        # Initialisiere UIAutomator
        logger.info("Initialisiere UIAutomator Parser...")
        self.ui_parser = UIAutomatorParser(adb)


        # Registriere Befehls-Handler
        self._register_command_handlers()

        # Starte Danfoss App automatisch beim Programmstart
        self._launch_danfoss_app()

        logger.info("Initialisierung erfolgreich")
        return True

    def _register_command_handlers(self) -> None:
        """Registriert alle verfügbaren Befehls-Handler"""
        self.mqtt.register_command_handler("set_temperature", self._handle_set_temperature)

    def _launch_danfoss_app(self) -> bool:
        """Startet die Danfoss-App via SplashActivity und bestätigt Fehlerdialoge.

        Einheitliche Startprozedur für alle Auslöser (initialize, app/start, reboot, recovery).
        Läuft die App bereits, wird sie nicht neu gestartet und der Ladevorgang wird übersprungen.

        Returns:
            True wenn App läuft (bereits lief oder erfolgreich gestartet wurde)
        """
        adb = self.adb
        ui_parser = self.ui_parser
        if not adb:
            return False

        # Prüfe ob App bereits läuft
        if adb.is_app_running("com.danfoss.linkapp"):
            logger.info("launch_app: Danfoss Link App läuft bereits – kein Start nötig")
            return True

        logger.info("launch_app: Starte Danfoss Link App (SplashActivity)...")
        adb.start_activity(
            "com.danfoss.linkapp",
            "com.danfoss.cumulus.app.firstuse.SplashActivity"
        )
        # Warte bis App geladen ist
        time.sleep(10.0)
        # Fehlerdialog automatisch bestätigen (android:id/button1)
        if ui_parser:
            ui_parser.dismiss_error_dialog()
        time.sleep(3.0)
        logger.info("launch_app: App gestartet")
        return True


    def _tap_rooms_button(self) -> bool:
        """Wechselt per main_rooms_button in die Raum-Uebersicht.
        Falls der Button nicht gefunden wird, wird die App via SplashActivity neu gestartet.
        """
        adb = self.adb
        ui_parser = self.ui_parser
        if not adb or not ui_parser:
            return False

        rooms_button_res_id = "com.danfoss.linkapp:id/main_rooms_button"
        bounds = ui_parser.get_bounds(rooms_button_res_id)
        if not bounds:
            logger.warning(
                "rooms_button: main_rooms_button nicht gefunden – stoppe und starte App neu: "
                "am start -n com.danfoss.linkapp/com.danfoss.cumulus.app.firstuse.SplashActivity"
            )
            # App zuerst sauber beenden
            adb.stop_app("com.danfoss.linkapp")
            time.sleep(1.0)
            # Gleiche Prozedur wie app/start: SplashActivity + Fehlerdialog bestätigen
            self._launch_danfoss_app()
            # Prüfe ob rooms_button jetzt sichtbar ist
            bounds = ui_parser.get_bounds(rooms_button_res_id)
            if bounds:
                x = (bounds["x1"] + bounds["x2"]) // 2
                y = (bounds["y1"] + bounds["y2"]) // 2
                logger.info(f"rooms_button: Tippe main_rooms_button nach App-Restart bei {x},{y}")
                adb.send_tap(x, y)
                time.sleep(0.6)
            else:
                logger.info("rooms_button: App gestartet, rooms_button noch nicht sichtbar (Splash läuft noch)")
            return True

        x = (bounds["x1"] + bounds["x2"]) // 2
        y = (bounds["y1"] + bounds["y2"]) // 2
        logger.info(f"rooms_button: Tippe main_rooms_button bei {x},{y}")
        adb.send_tap(x, y)
        time.sleep(0.6)
        return True

    def _handle_set_temperature(self, payload: str) -> None:
        """
        Setzt den Sollwert eines Raums via Swipe auf dem Danfoss-Spinner.

        Erwartet JSON-Payload: {"room": "<slug>", "temperature": <float>}
        Beispiel: {"room": "living_room", "temperature": 21.5}
        """
        import json as _json

        adb = self.adb
        ui_parser = self.ui_parser
        ui_config = self.ui_config
        mqtt = self.mqtt

        if not adb or not ui_parser or not ui_config or not mqtt:
            logger.error("set_temperature: Anwendung nicht vollstaendig initialisiert")
            return

        try:
            data = _json.loads(payload)
            room_slug: str = str(data.get("room", "")).strip()
            target_temp: float = float(data["temperature"])
        except Exception as e:
            logger.error(f"set_temperature: Ungueltige Payload '{payload}': {e}")
            return

        max_temp_limit = 26.0
        if target_temp > max_temp_limit:
            logger.warning(
                f"set_temperature: Ziel {target_temp}°C ueber Limit, begrenze auf {max_temp_limit}°C"
            )
            target_temp = max_temp_limit

        if not room_slug:
            logger.error("set_temperature: 'room' fehlt in Payload")
            return

        package_name = DANFOSS_APP_PACKAGE
        edit_res_id = f"{package_name}:id/roomoverview_edit_button"

        # 1) Edit-Button Position ermitteln
        edit_bounds = ui_parser.get_bounds(edit_res_id)
        if not edit_bounds:
            logger.error(f"set_temperature: Edit-Button nicht gefunden ({edit_res_id})")
            return

        ex = (edit_bounds["x1"] + edit_bounds["x2"]) // 2
        ey = (edit_bounds["y1"] + edit_bounds["y2"]) // 2
        logger.info(f"set_temperature: Edit-Button bei {ex},{ey}")

        # 2) Schritte berechnen (0.5°C pro Schritt)
        step_size = 0.5
        tolerance = 0.45  # Werte im Dump sind 0.5er Schritte
        max_iterations = 10
        burst_steps = max(1, int(ui_config.get_setting("set_temperature_burst_steps", 3)))

        inter_step_delay_s = float(ui_config.get_setting("set_temperature_swipe_pause_s", 2.0))
        readback_delay_s = float(ui_config.get_setting("set_temperature_readback_delay_s", 1.5))

        # Edit-Button vor jedem einzelnen 0,5°C-Schritt antippen.
        def tap_edit_button() -> None:
            adb.send_tap(ex, ey)
            time.sleep(0.1)

        # 3) Solange in Bursts stellen, bis Readback den Sollwert erreicht.
        reached = False
        last_setpoint: Optional[float] = None
        recovery_attempted = False
        for step in range(max_iterations):
            spinner_info = ui_parser.get_room_spinner_bounds(package_name, room_slug, use_cache=False)
            if not spinner_info:
                if not recovery_attempted and self._tap_rooms_button():
                    recovery_attempted = True
                    logger.warning(
                        "set_temperature: Kein Spinner gefunden, Rooms-Ansicht geoeffnet und Retry"
                    )
                    continue

                logger.error(f"set_temperature: Spinner fuer '{room_slug}' nicht mehr gefunden")
                break

            current_setpoint: Optional[float] = spinner_info.get("setpoint_c")
            if current_setpoint is None:
                if not recovery_attempted and self._tap_rooms_button():
                    recovery_attempted = True
                    logger.warning(
                        "set_temperature: Sollwert nicht parsebar, Rooms-Ansicht geoeffnet und Retry"
                    )
                    continue

                logger.error(f"set_temperature: Aktueller Sollwert fuer '{room_slug}' unbekannt")
                break

            last_setpoint = current_setpoint
            diff = target_temp - current_setpoint
            if abs(diff) <= tolerance:
                reached = True
                logger.info(f"set_temperature: Ziel erreicht ({current_setpoint}°C)")
                break

            cx: int = int(spinner_info["center_x"])
            cy: int = int(spinner_info["center_y"])
            step_px: int = int(spinner_info["step_px"])
            swipe_direction = -1 if diff > 0 else 1  # hoch = waermer

            remaining_steps = abs(round(diff / step_size))
            planned_steps = max(1, min(remaining_steps, burst_steps))
            logger.info(
                f"set_temperature: Burst {step + 1}: {current_setpoint}°C -> {target_temp}°C, "
                f"{planned_steps} Schritt(e)"
            )

            tap_edit_button()
            # Ein langer Swipe kann mehrere 0.5°C-Schritte in einem Zug abbilden.
            total_dy = swipe_direction * step_px * planned_steps
            swipe_duration_ms = max(220, int(220 * planned_steps))
            adb.send_swipe(cx, cy, cx, cy + total_dy, duration_ms=swipe_duration_ms)

            if planned_steps > 1:
                time.sleep(inter_step_delay_s)

            # Nach dem Burst kurz warten und dann Sollwert per frischem Dump lesen.
            time.sleep(readback_delay_s)

        # 4) Status publizieren
        if reached:
            mqtt.publish(f"thermostats/{room_slug}/setpoint", target_temp)
            mqtt.publish(f"thermostats/{room_slug}/setpoint_set_at", int(time.time()))
            logger.info(f"set_temperature: '{room_slug}' Sollwert auf {target_temp}°C gesetzt")
        else:
            mqtt.publish(
                f"thermostats/{room_slug}/setpoint_error",
                f"target={target_temp}, last={last_setpoint}"
            )
            logger.warning(
                f"set_temperature: Ziel ggf. nicht erreicht (target={target_temp}, last={last_setpoint})"
            )

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        """Konvertiert numerische Werte robust in float (unterstützt auch Dezimalkomma)."""
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
        """Leitet hvac_action aus Ist-/Sollwert ab."""
        if current_temp is None or target_temp is None:
            return None
        return "idle" if target_temp < current_temp else "heating"

    def _publish_danfoss_thermostats(self, force: bool = False) -> None:
        """Analysiert den UI-Dump und publiziert Thermostatnamen und Werte."""
        if not self.ui_parser or not self.ui_config or not self.mqtt:
            return

        package_name = DANFOSS_APP_PACKAGE
        extractor: Optional[Callable[..., List[Dict[str, Any]]]] = getattr(
            self.ui_parser,
            "extract_danfoss_thermostats",
            None
        )
        if not extractor:
            logger.warning("UI parser unterstuetzt keine Danfoss-Thermostat-Extraktion")
            return

        thermostats = extractor(package_name, use_cache=not force)
        if not thermostats:
            if self._tap_rooms_button():
                thermostats = extractor(package_name, use_cache=False)

        if not thermostats:
            logger.debug("Keine Danfoss-Thermostate im aktuellen UI-Dump erkannt")
            return

        thermostats_payload: List[Dict[str, Any]] = []
        for thermostat in thermostats:
            slug = thermostat.get("slug")
            if not slug:
                continue

            base_topic = f"thermostats/{slug}"
            self.mqtt.publish(f"{base_topic}/label", thermostat.get("label", ""))
            self.mqtt.publish(f"{base_topic}/kind", thermostat.get("kind", "room"))
            self.mqtt.publish(f"{base_topic}/value", thermostat.get("temperature_c", ""))
            self.mqtt.publish(f"{base_topic}/setpoint", thermostat.get("setpoint_c", ""))

            # HVAC-Action aus Soll-/Istwert ableiten: setpoint < value -> idle, sonst heating.
            current_temp = self._to_float(thermostat.get("temperature_c"))
            target_temp = self._to_float(thermostat.get("setpoint_c"))
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
        """Publiziert MQTT-Discovery fuer Home Assistant Climate-Entitaeten je Raum."""
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
                "temperature_command_topic": f"{MQTT_TOPIC_BASE}/command/set_temperature",
                "temperature_command_template": (
                    "{\"room\": \"" + room_key + "\", \"temperature\": {{ value }}}"
                ),
                "temperature_state_topic": f"{base_state}/setpoint",
                "current_temperature_topic": f"{base_state}/value",
                "mode_state_topic": f"{base_state}/mode",
                "action_topic": f"{base_state}/hvac_action",
                "modes": ["heat"],
                "min_temp": float(self.ui_config.get_setting("thermostat_min_temp", 5.0)),
                "max_temp": float(self.ui_config.get_setting("thermostat_max_temp", 30.0)),
                "temp_step": float(self.ui_config.get_setting("thermostat_temp_step", 0.5)),
                "precision": 0.5,
                "device": device
            }
            self.mqtt.publish_absolute(climate_config_topic, climate_payload, retain=True)

            self.discovery_registry.add(room_key)

    def poll_data(self) -> None:
        """Pollt Sensor- und UI-Daten vom Android-Gerät"""
        logger.info(f"Starte Daten-Polling alle {POLL_INTERVAL} Sekunden...")
        if not self.adb or not self.mqtt:
            logger.error("Polling ohne initialisierte ADB/MQTT Instanzen abgebrochen")
            return

        while self.running:
            try:
                # Sicherstellen dass ADB verbunden ist
                if not self.adb.ensure_connected():
                    logger.error("Polling: ADB-Neuverbindung fehlgeschlagen – warte 10s")
                    time.sleep(10)
                    continue

                # Lese UIAutomator-Daten
                self._poll_ui_data(force=False)

                # Veröffentliche Danfoss-Thermostatdaten aus UI-Dump-Analyse
                self._publish_danfoss_thermostats(force=False)

                time.sleep(POLL_INTERVAL)

            except Exception as e:
                logger.error(f"Fehler beim Polling: {e}")
                time.sleep(5)


    def _poll_ui_data(self, force: bool = False) -> None:
        """
        Pollt UIAutomator-Daten

        Args:
            force: Erzwinge Update auch wenn gecacht
        """
        try:
            if not self.ui_config or not self.ui_parser:
                return

            ui_config = self.ui_config
            ui_parser = self.ui_parser

            # Hole aktivierte Elemente
            elements = ui_config.get_enabled_elements()

            if not elements:
                return

            logger.debug(f"Polling {len(elements)} UI-Elemente...")

            for element_name, element_config in elements.items():
                try:
                    resource_id = element_config.get("resource_id")
                    value_type = element_config.get("type", "text")
                    mqtt_topic = element_config.get("mqtt_topic")

                    if not resource_id or not mqtt_topic:
                        continue

                    resource_id = str(resource_id)
                    mqtt_topic = str(mqtt_topic)

                    # Extrahiere Wert
                    value = ui_parser.extract_value_by_resource_id(
                        resource_id,
                        value_type
                    )

                    if value is not None:
                        # Überprüfe auf Änderungen wenn konfiguriert
                        publish_only_changes = ui_config.get_setting(
                            "publish_only_changes",
                            True
                        )

                        if publish_only_changes:
                            if ui_parser.is_value_changed(element_name, value):
                                self.mqtt.publish(mqtt_topic, value)
                                logger.debug(f"UI-Wert publiziert: {mqtt_topic} = {value}")
                        else:
                            self.mqtt.publish(mqtt_topic, value)
                            logger.debug(f"UI-Wert publiziert: {mqtt_topic} = {value}")

                except Exception as e:
                    logger.warning(f"Fehler beim Polling von {element_name}: {e}")

        except Exception as e:
            logger.error(f"Fehler beim UI-Polling: {e}")

    def run(self) -> None:
        """Startet die Hauptschleife"""
        if not self.initialize():
            logger.error("Initialisierung fehlgeschlagen")
            return

        self.running = True
        logger.info("Starte Hauptschleife...")

        # Starte Polling in separatem Thread
        self.polling_thread = threading.Thread(target=self.poll_data, daemon=True)
        self.polling_thread.start()

        # Hauptthread bleibt aktiv
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()

    def stop(self) -> None:
        """Stoppt die Anwendung"""
        logger.info("Stoppe DanfossLink2Mqtt...")
        self.running = False

        # Warte auf Polling-Thread
        if self.polling_thread and self.polling_thread.is_alive():
            self.polling_thread.join(timeout=5)

        if self.adb:
            self.adb.disconnect()

        if self.mqtt:
            self.mqtt.disconnect()

        logger.info("Anwendung gestoppt")


def main():
    """Einstiegspunkt"""
    app = DanfossLink2MQTT()
    app.run()



if __name__ == "__main__":
    main()

