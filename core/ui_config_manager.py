"""Manager for the UIAutomator configuration file"""
import logging
import yaml
import json
from typing import Dict, List, Optional, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class UIConfigManager:
    """Manages the UIAutomator configuration"""

    def __init__(self, config_path: str = "config.yaml"):
        """
        Initializes the config manager.

        Args:
            config_path: Path to the configuration file
        """
        self.config_path = Path(config_path)
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """
        Load the configuration file.

        Returns:
            Configuration dict or empty dict on error
        """
        if not self.config_path.exists():
            logger.warning(f"Configuration file not found: {self.config_path}")
            return {"ui_elements": {}, "settings": {}}

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                if self.config_path.suffix.lower() == '.yaml':
                    config = yaml.safe_load(f) or {}
                elif self.config_path.suffix.lower() == '.json':
                    config = json.load(f)
                else:
                    logger.error(f"Unknown file format: {self.config_path.suffix}")
                    return {"ui_elements": {}, "settings": {}}

            logger.info(f"Configuration loaded: {self.config_path}")
            return config
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            return {"ui_elements": {}, "settings": {}}

    def save_config(self) -> bool:
        """
        Save the current configuration.

        Returns:
            True on success
        """
        try:
            if self.config_path.suffix.lower() == '.yaml':
                with open(self.config_path, 'w', encoding='utf-8') as f:
                    yaml.dump(self.config, f, default_flow_style=False, allow_unicode=True)
            elif self.config_path.suffix.lower() == '.json':
                with open(self.config_path, 'w', encoding='utf-8') as f:
                    json.dump(self.config, f, indent=2, ensure_ascii=False)

            logger.info(f"Configuration saved: {self.config_path}")
            return True
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
            return False

    def get_ui_elements(self) -> Dict[str, Dict[str, Any]]:
        """
        Return all defined UI elements.

        Returns:
            Dictionary with UI elements
        """
        return self.config.get("ui_elements", {})

    def get_enabled_elements(self) -> Dict[str, Dict[str, Any]]:
        """
        Return only enabled UI elements.

        Returns:
            Dictionary with enabled UI elements
        """
        elements = self.get_ui_elements()
        return {
            name: config for name, config in elements.items()
            if config.get("enabled", True)
        }

    def get_element(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Return a specific UI element.

        Args:
            name: Name of the element

        Returns:
            Element config or None
        """
        return self.get_ui_elements().get(name)

    def add_element(self, name: str, resource_id: str, value_type: str = "text",
                   mqtt_topic: str = "", description: str = "", enabled: bool = True) -> bool:
        """
        Add a new UI element.

        Args:
            name: Name of the element
            resource_id: The resource-id
            value_type: Type of value to read
            mqtt_topic: MQTT topic for publishing
            description: Description
            enabled: Whether the element is enabled

        Returns:
            True on success
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

            logger.info(f"Element added: {name}")
            return True
        except Exception as e:
            logger.error(f"Error adding element: {e}")
            return False

    def update_element(self, name: str, **kwargs) -> bool:
        """
        Update an existing element.

        Args:
            name: Name of the element
            **kwargs: Fields to update

        Returns:
            True on success
        """
        try:
            element = self.get_element(name)
            if not element:
                logger.warning(f"Element not found: {name}")
                return False

            element.update(kwargs)
            logger.info(f"Element updated: {name}")
            return True
        except Exception as e:
            logger.error(f"Error updating element: {e}")
            return False

    def remove_element(self, name: str) -> bool:
        """
        Remove an element.

        Args:
            name: Name of the element

        Returns:
            True on success
        """
        try:
            if name in self.get_ui_elements():
                del self.config["ui_elements"][name]
                logger.info(f"Element removed: {name}")
                return True
            else:
                logger.warning(f"Element not found: {name}")
                return False
        except Exception as e:
            logger.error(f"Error removing element: {e}")
            return False

    def toggle_element(self, name: str) -> bool:
        """
        Enable/disable an element.

        Args:
            name: Name of the element

        Returns:
            True on success
        """
        try:
            element = self.get_element(name)
            if not element:
                return False

            element["enabled"] = not element.get("enabled", True)
            state = "enabled" if element["enabled"] else "disabled"
            logger.info(f"Element {state}: {name}")
            return True
        except Exception as e:
            logger.error(f"Error toggling element: {e}")
            return False

    def get_setting(self, key: str, default: Any = None) -> Any:
        """
        Return a global setting.

        Args:
            key: Key of the setting
            default: Default value

        Returns:
            The value or default
        """
        settings = self.config.get("settings", {})
        return settings.get(key, default)

    def set_setting(self, key: str, value: Any) -> bool:
        """
        Set a global setting.

        Args:
            key: Key of the setting
            value: The new value

        Returns:
            True on success
        """
        try:
            if "settings" not in self.config:
                self.config["settings"] = {}

            self.config["settings"][key] = value
            logger.info(f"Setting saved: {key} = {value}")
            return True
        except Exception as e:
            logger.error(f"Error setting value: {e}")
            return False

    def list_all_elements(self) -> List[Dict[str, Any]]:
        """
        List all elements with their information.

        Returns:
            List of all elements
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
        Export configuration to JSON.

        Args:
            filepath: Target path

        Returns:
            True on success
        """
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            logger.info(f"Configuration exported: {filepath}")
            return True
        except Exception as e:
            logger.error(f"Error exporting: {e}")
            return False

    def import_from_json(self, filepath: str) -> bool:
        """
        Import configuration from JSON.

        Args:
            filepath: Source path

        Returns:
            True on success
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                imported_config = json.load(f)

            # Merge with existing configuration
            if "ui_elements" in imported_config:
                if "ui_elements" not in self.config:
                    self.config["ui_elements"] = {}
                self.config["ui_elements"].update(imported_config["ui_elements"])

            logger.info(f"Configuration imported: {filepath}")
            return True
        except Exception as e:
            logger.error(f"Error importing: {e}")
            return False

    def validate_config(self) -> Dict[str, List[str]]:
        """
        Validate the configuration.

        Returns:
            Dictionary with errors and warnings
        """
        errors = []
        warnings = []

        try:
            elements = self.get_ui_elements()

            if not elements:
                warnings.append("No UI elements defined")

            for name, config in elements.items():
                # Check required fields
                if not config.get("resource_id"):
                    errors.append(f"Element '{name}': resource_id missing")

                if not config.get("mqtt_topic"):
                    warnings.append(f"Element '{name}': mqtt_topic not set")

                # Check data types
                valid_types = ["text", "content-desc", "checked", "selected", "enabled", "bounds"]
                if config.get("type") not in valid_types:
                    errors.append(f"Element '{name}': invalid type '{config.get('type')}'")

        except Exception as e:
            errors.append(f"Validation error: {e}")

        return {
            "errors": errors,
            "warnings": warnings
        }
