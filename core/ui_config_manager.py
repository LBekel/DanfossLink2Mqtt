"""Manager für UIAutomator-Konfigurationsdatei"""
import logging
import yaml
import json
from typing import Dict, List, Optional, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class UIConfigManager:
    """Verwaltet die UIAutomator-Konfiguration"""

    def __init__(self, config_path: str = "config.yaml"):
        """
        Initialisiert den Config Manager

        Args:
            config_path: Pfad zur Konfigurationsdatei
        """
        self.config_path = Path(config_path)
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """
        Lädt die Konfigurationsdatei

        Returns:
            Konfigurationsdict oder leeres Dict bei Fehler
        """
        if not self.config_path.exists():
            logger.warning(f"Konfigurationsdatei nicht gefunden: {self.config_path}")
            return {"ui_elements": {}, "settings": {}}

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                if self.config_path.suffix.lower() == '.yaml':
                    config = yaml.safe_load(f) or {}
                elif self.config_path.suffix.lower() == '.json':
                    config = json.load(f)
                else:
                    logger.error(f"Unbekanntes Dateiformat: {self.config_path.suffix}")
                    return {"ui_elements": {}, "settings": {}}

            logger.info(f"Konfiguration geladen: {self.config_path}")
            return config
        except Exception as e:
            logger.error(f"Fehler beim Laden der Konfiguration: {e}")
            return {"ui_elements": {}, "settings": {}}

    def save_config(self) -> bool:
        """
        Speichert die aktuelle Konfiguration

        Returns:
            True bei Erfolg
        """
        try:
            if self.config_path.suffix.lower() == '.yaml':
                with open(self.config_path, 'w', encoding='utf-8') as f:
                    yaml.dump(self.config, f, default_flow_style=False, allow_unicode=True)
            elif self.config_path.suffix.lower() == '.json':
                with open(self.config_path, 'w', encoding='utf-8') as f:
                    json.dump(self.config, f, indent=2, ensure_ascii=False)

            logger.info(f"Konfiguration gespeichert: {self.config_path}")
            return True
        except Exception as e:
            logger.error(f"Fehler beim Speichern der Konfiguration: {e}")
            return False

    def get_ui_elements(self) -> Dict[str, Dict[str, Any]]:
        """
        Gibt alle definierten UI-Elemente zurück

        Returns:
            Dictionary mit UI-Elementen
        """
        return self.config.get("ui_elements", {})

    def get_enabled_elements(self) -> Dict[str, Dict[str, Any]]:
        """
        Gibt nur aktivierte UI-Elemente zurück

        Returns:
            Dictionary mit aktivierten UI-Elementen
        """
        elements = self.get_ui_elements()
        return {
            name: config for name, config in elements.items()
            if config.get("enabled", True)
        }

    def get_element(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Gibt ein spezifisches UI-Element zurück

        Args:
            name: Name des Elements

        Returns:
            Element-Config oder None
        """
        return self.get_ui_elements().get(name)

    def add_element(self, name: str, resource_id: str, value_type: str = "text",
                   mqtt_topic: str = "", description: str = "", enabled: bool = True) -> bool:
        """
        Fügt ein neues UI-Element hinzu

        Args:
            name: Name des Elements
            resource_id: Die resource-id
            value_type: Typ des auszulesenden Wertes
            mqtt_topic: MQTT-Topic für Veröffentlichung
            description: Beschreibung
            enabled: Ob Element aktiviert ist

        Returns:
            True bei Erfolg
        """
        try:
            if "ui_elements" not in self.config:
                self.config["ui_elements"] = {}

            self.config["ui_elements"][name] = {
                "resource_id": resource_id,
                "type": value_type,
                "mqtt_topic": mqtt_topic or f"ui/{name}",
                "description": description,
                "enabled": enabled
            }

            logger.info(f"Element hinzugefügt: {name}")
            return True
        except Exception as e:
            logger.error(f"Fehler beim Hinzufügen des Elements: {e}")
            return False

    def update_element(self, name: str, **kwargs) -> bool:
        """
        Aktualisiert ein bestehendes Element

        Args:
            name: Name des Elements
            **kwargs: Felder zum Aktualisieren

        Returns:
            True bei Erfolg
        """
        try:
            element = self.get_element(name)
            if not element:
                logger.warning(f"Element nicht gefunden: {name}")
                return False

            element.update(kwargs)
            logger.info(f"Element aktualisiert: {name}")
            return True
        except Exception as e:
            logger.error(f"Fehler beim Aktualisieren des Elements: {e}")
            return False

    def remove_element(self, name: str) -> bool:
        """
        Entfernt ein Element

        Args:
            name: Name des Elements

        Returns:
            True bei Erfolg
        """
        try:
            if name in self.get_ui_elements():
                del self.config["ui_elements"][name]
                logger.info(f"Element entfernt: {name}")
                return True
            else:
                logger.warning(f"Element nicht gefunden: {name}")
                return False
        except Exception as e:
            logger.error(f"Fehler beim Entfernen des Elements: {e}")
            return False

    def toggle_element(self, name: str) -> bool:
        """
        Aktiviert/Deaktiviert ein Element

        Args:
            name: Name des Elements

        Returns:
            True bei Erfolg
        """
        try:
            element = self.get_element(name)
            if not element:
                return False

            element["enabled"] = not element.get("enabled", True)
            state = "aktiviert" if element["enabled"] else "deaktiviert"
            logger.info(f"Element {state}: {name}")
            return True
        except Exception as e:
            logger.error(f"Fehler beim Toggle des Elements: {e}")
            return False

    def get_setting(self, key: str, default: Any = None) -> Any:
        """
        Gibt eine globale Einstellung zurück

        Args:
            key: Schlüssel der Einstellung
            default: Standardwert

        Returns:
            Der Wert oder default
        """
        settings = self.config.get("settings", {})
        return settings.get(key, default)

    def set_setting(self, key: str, value: Any) -> bool:
        """
        Setzt eine globale Einstellung

        Args:
            key: Schlüssel der Einstellung
            value: Der neue Wert

        Returns:
            True bei Erfolg
        """
        try:
            if "settings" not in self.config:
                self.config["settings"] = {}

            self.config["settings"][key] = value
            logger.info(f"Einstellung gespeichert: {key} = {value}")
            return True
        except Exception as e:
            logger.error(f"Fehler beim Setzen der Einstellung: {e}")
            return False

    def list_all_elements(self) -> List[Dict[str, Any]]:
        """
        Listet alle Elemente mit ihren Informationen auf

        Returns:
            Liste aller Elemente
        """
        elements_list = []
        for name, config in self.get_ui_elements().items():
            element_info = {
                "name": name,
                "resource_id": config.get("resource_id", ""),
                "type": config.get("type", ""),
                "mqtt_topic": config.get("mqtt_topic", ""),
                "enabled": config.get("enabled", True),
                "description": config.get("description", "")
            }
            elements_list.append(element_info)

        return elements_list

    def export_to_json(self, filepath: str) -> bool:
        """
        Exportiert Konfiguration zu JSON

        Args:
            filepath: Zielpath

        Returns:
            True bei Erfolg
        """
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            logger.info(f"Konfiguration exportiert: {filepath}")
            return True
        except Exception as e:
            logger.error(f"Fehler beim Export: {e}")
            return False

    def import_from_json(self, filepath: str) -> bool:
        """
        Importiert Konfiguration von JSON

        Args:
            filepath: Quellpath

        Returns:
            True bei Erfolg
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                imported_config = json.load(f)

            # Merge mit bestehender Konfiguration
            if "ui_elements" in imported_config:
                if "ui_elements" not in self.config:
                    self.config["ui_elements"] = {}
                self.config["ui_elements"].update(imported_config["ui_elements"])

            logger.info(f"Konfiguration importiert: {filepath}")
            return True
        except Exception as e:
            logger.error(f"Fehler beim Import: {e}")
            return False

    def validate_config(self) -> Dict[str, List[str]]:
        """
        Validiert die Konfiguration

        Returns:
            Dictionary mit Errors und Warnings
        """
        errors = []
        warnings = []

        try:
            elements = self.get_ui_elements()

            if not elements:
                warnings.append("Keine UI-Elemente definiert")

            for name, config in elements.items():
                # Überprüfe erforderliche Felder
                if not config.get("resource_id"):
                    errors.append(f"Element '{name}': resource_id fehlt")

                if not config.get("mqtt_topic"):
                    warnings.append(f"Element '{name}': mqtt_topic nicht gesetzt")

                # Überprüfe Datentypen
                valid_types = ["text", "content-desc", "checked", "selected", "enabled", "bounds"]
                if config.get("type") not in valid_types:
                    errors.append(f"Element '{name}': Ungültiger type '{config.get('type')}'")

        except Exception as e:
            errors.append(f"Validierungsfehler: {e}")

        return {
            "errors": errors,
            "warnings": warnings
        }

