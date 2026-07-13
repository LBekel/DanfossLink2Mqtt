"""Konfiguration fuer DanfossLink2Mqtt aus der zentralen config.yaml."""
from pathlib import Path
from typing import Any, Dict

import yaml


def _load_settings() -> Dict[str, Any]:
	"""Laedt settings aus der zentralen config.yaml."""
	config_path = Path(__file__).resolve().parent.parent / "config.yaml"
	if not config_path.exists():
		return {}

	try:
		with open(config_path, "r", encoding="utf-8") as f:
			data = yaml.safe_load(f) or {}
		settings = data.get("settings", {})
		return settings if isinstance(settings, dict) else {}
	except Exception:
		return {}


def _get_str(settings: Dict[str, Any], key: str, default: str) -> str:
	value = settings.get(key, default)
	return str(value)


def _get_int(settings: Dict[str, Any], key: str, default: int) -> int:
	value = settings.get(key, default)
	try:
		return int(value)
	except (TypeError, ValueError):
		return default


_SETTINGS = _load_settings()

# ADB Konfiguration
ADB_HOST = _get_str(_SETTINGS, "adb_host", "localhost")
ADB_PORT = _get_int(_SETTINGS, "adb_port", 5037)
ADB_DEVICE_IP = _get_str(_SETTINGS, "adb_device_ip", "192.168.1.100")
ADB_DEVICE_PORT = _get_int(_SETTINGS, "adb_device_port", 5555)

# MQTT Konfiguration
MQTT_BROKER = _get_str(_SETTINGS, "mqtt_broker", "localhost")
MQTT_PORT = _get_int(_SETTINGS, "mqtt_port", 1883)
MQTT_USERNAME = _get_str(_SETTINGS, "mqtt_username", "")
MQTT_PASSWORD = _get_str(_SETTINGS, "mqtt_password", "")
MQTT_TOPIC_BASE = _get_str(_SETTINGS, "mqtt_topic_base", "DanfossLink2Mqtt")

# App-Konfiguration
# Paketname ist fest und wird nicht mehr aus der YAML gelesen.
DANFOSS_APP_PACKAGE = "com.danfoss.linkapp"
POLL_INTERVAL = _get_int(_SETTINGS, "poll_interval", 5)

# Logging
LOG_LEVEL = _get_str(_SETTINGS, "log_level", "INFO")

