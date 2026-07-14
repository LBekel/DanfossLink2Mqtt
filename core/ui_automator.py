"""UIAutomator XML parser for ADB-based UI automation"""
import logging
import time
import xml.etree.ElementTree as ET
import re
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from .adb_controller import ADBController

logger = logging.getLogger(__name__)


class UIAutomatorParser:
    """Parses XML dump from UIAutomator and extracts values based on resource-ids"""

    def __init__(self, adb: ADBController):
        """
        Initializes the UIAutomator parser.

        Args:
            adb: ADBController instance
        """
        self.adb = adb
        self.last_xml = None
        self.last_xml_time = None
        self.cache_duration = 5  # seconds
        self.cached_values = {}
        self.last_values = {}  # For change detection

    def _extract_xml_payload(self, raw_output: str) -> Optional[str]:
        """Extracts the pure XML document from UIAutomator shell output."""
        if not raw_output:
            return None

        cleaned = raw_output.replace("\x00", "").strip()

        # UIAutomator sometimes prepends/appends status text around the XML.
        match = re.search(r"<hierarchy[^>]*>.*?</hierarchy>", cleaned, re.DOTALL)
        if match:
            return match.group(0).strip()

        xml_start = cleaned.find("<?xml")
        if xml_start != -1:
            cleaned = cleaned[xml_start:]

        hierarchy_start = cleaned.find("<hierarchy")
        hierarchy_end = cleaned.rfind("</hierarchy>")
        if hierarchy_start != -1 and hierarchy_end != -1:
            hierarchy_end += len("</hierarchy>")
            return cleaned[hierarchy_start:hierarchy_end].strip()

        return None

    def _get_xml_root(self, use_cache: bool = True) -> Optional[ET.Element]:
        """Load the XML dump and return the parsed root element."""
        xml_str = self.get_ui_dump(use_cache=use_cache)
        if not xml_str:
            return None

        try:
            return ET.fromstring(xml_str)
        except ET.ParseError as e:
            logger.error(f"XML parse error: {e}")
            return None

    def get_ui_dump(self, use_cache: bool = True) -> Optional[str]:
        """
        Fetch the current UI dump from the Android device.

        Args:
            use_cache: Use cached data if available

        Returns:
            XML string or None on error
        """
        # Check cache
        if use_cache and self.last_xml and self.last_xml_time:
            age = datetime.now() - self.last_xml_time
            if age.total_seconds() < self.cache_duration:
                logger.debug(f"UIAutomator cache used (age: {age.total_seconds():.1f}s)")
                return self.last_xml

        try:
            logger.debug("Fetching UI dump from UIAutomator...")
            result = self.adb.shell_command("uiautomator dump /dev/stdout")

            if result:
                xml_payload = self._extract_xml_payload(result)
                if not xml_payload:
                    logger.error("Could not find valid UIAutomator XML in shell output")
                    return None

                self.last_xml = xml_payload
                self.last_xml_time = datetime.now()
                logger.debug(f"UI dump received ({len(xml_payload)} bytes)")
                return xml_payload
            else:
                logger.error("UIAutomator dump is empty")
                return None
        except Exception as e:
            logger.error(f"Error fetching UI dump: {e}")
            return None

    def save_ui_dump(self, filepath: str = "ui_dump.xml") -> bool:
        """
        Save the UI dump locally as an XML file for debugging.

        Args:
            filepath: Local file path (e.g. "ui_dump.xml")

        Returns:
            True on success
        """
        try:
            xml_data = self.get_ui_dump(use_cache=False)
            if xml_data:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(xml_data)
                logger.info(f"UI dump saved: {filepath}")
                return True
            else:
                logger.error("Could not retrieve XML data")
        except Exception as e:
            logger.error(f"Error saving UI dump: {e}")

        return False

    def extract_value_by_resource_id(self, resource_id: str, value_type: str = "text") -> Optional[str]:
        """
        Extract a value based on resource-id.

        Args:
            resource_id: The resource-id (e.g. "com.android.systemui:id/clock")
            value_type: Type of value to read:
                - text: text content of the element
                - content-desc: content-description attribute
                - checked: value of the checked attribute
                - selected: value of the selected attribute
                - enabled: value of the enabled attribute
                - bounds: position of the element

        Returns:
            The extracted value or None
        """
        try:
            root = self._get_xml_root()
            if root is None:
                return None

            # Find element with matching resource-id
            for elem in root.iter():
                res_id = elem.get("resource-id", "")
                if res_id == resource_id:
                    logger.debug(f"Element found: {resource_id}")

                    # Extract requested value type
                    if value_type == "text":
                        value = elem.get("text", "")
                    elif value_type == "content-desc":
                        value = elem.get("content-desc", "")
                    elif value_type == "checked":
                        value = elem.get("checked", "false")
                    elif value_type == "selected":
                        value = elem.get("selected", "false")
                    elif value_type == "enabled":
                        value = elem.get("enabled", "true")
                    elif value_type == "bounds":
                        value = elem.get("bounds", "")
                    else:
                        value = elem.get(value_type, "")

                    logger.debug(f"Value extracted ({value_type}): {value}")
                    return value if value else None

            logger.warning(f"Element with resource-id not found: {resource_id}")
            return None

        except Exception as e:
            logger.error(f"Error extracting value: {e}")
            return None

    def extract_multiple_by_class(self, class_name: str) -> List[Dict[str, str]]:
        """
        Extract multiple elements based on class.

        Args:
            class_name: The class (e.g. "android.widget.TextView")

        Returns:
            List of dictionaries with element attributes
        """
        results = []
        try:
            root = self._get_xml_root()
            if root is None:
                return results

            # Find all elements with matching class
            for elem in root.iter():
                if elem.get("class") == class_name:
                    result = {
                        "resource_id": elem.get("resource-id", ""),
                        "text": elem.get("text", ""),
                        "content_desc": elem.get("content-desc", ""),
                        "bounds": elem.get("bounds", ""),
                        "class": class_name
                    }
                    results.append(result)

            logger.debug(f"{len(results)} elements of class '{class_name}' found")
            return results

        except Exception as e:
            logger.error(f"Error extracting multiple elements: {e}")
            return results

    def extract_all_by_package(self, package_name: str) -> List[Dict[str, str]]:
        """
        Extract all UI elements of a package.

        Args:
            package_name: Package name (e.g. "com.netflix.mediaclient")

        Returns:
            List of dictionaries with element attributes
        """
        results = []
        try:
            root = self._get_xml_root()
            if root is None:
                return results

            # Find all elements with matching package in resource-id
            for elem in root.iter():
                res_id = elem.get("resource-id", "")
                if res_id.startswith(package_name):
                    result = {
                        "resource_id": res_id,
                        "text": elem.get("text", ""),
                        "content_desc": elem.get("content-desc", ""),
                        "class": elem.get("class", ""),
                        "bounds": elem.get("bounds", "")
                    }
                    results.append(result)

            logger.debug(f"{len(results)} elements of package '{package_name}' found")
            return results

        except Exception as e:
            logger.error(f"Error extracting package elements: {e}")
            return results

    def find_element_by_text(self, text: str, partial: bool = False) -> Optional[Dict[str, str]]:
        """
        Find an element based on text.

        Args:
            text: The text to search for
            partial: Whether partial match is allowed

        Returns:
            Dictionary with element attributes or None
        """
        try:
            root = self._get_xml_root()
            if root is None:
                return None

            # Find element with matching text
            for elem in root.iter():
                elem_text = elem.get("text", "")

                if partial:
                    if text.lower() in elem_text.lower():
                        return {
                            "resource_id": elem.get("resource-id", ""),
                            "text": elem_text,
                            "class": elem.get("class", ""),
                            "bounds": elem.get("bounds", "")
                        }
                else:
                    if elem_text == text:
                        return {
                            "resource_id": elem.get("resource-id", ""),
                            "text": elem_text,
                            "class": elem.get("class", ""),
                            "bounds": elem.get("bounds", "")
                        }

            logger.warning(f"Element with text not found: {text}")
            return None

        except Exception as e:
            logger.error(f"Error searching by text: {e}")
            return None

    def get_bounds(self, resource_id: str) -> Optional[Dict[str, int]]:
        """
        Extract the bounds/position of an element.

        Args:
            resource_id: The resource-id

        Returns:
            Dictionary with x1, y1, x2, y2 coordinates or None
        """
        try:
            bounds_str = self.extract_value_by_resource_id(resource_id, "bounds")
            if not bounds_str:
                return None

            # Parse format: [x1,y1][x2,y2]
            match = re.search(r'\[(\d+),(\d+)]\[(\d+),(\d+)]', bounds_str)
            if match:
                return {
                    "x1": int(match.group(1)),
                    "y1": int(match.group(2)),
                    "x2": int(match.group(3)),
                    "y2": int(match.group(4))
                }
        except Exception as e:
            logger.error(f"Error parsing bounds: {e}")

        return None

    def _parse_bounds_string(self, bounds_str: str) -> Optional[Dict[str, int]]:
        """Parse the Android bounds format [x1,y1][x2,y2]."""
        if not bounds_str:
            return None

        match = re.search(r'\[(\d+),(\d+)]\[(\d+),(\d+)]', bounds_str)
        if not match:
            return None

        return {
            "x1": int(match.group(1)),
            "y1": int(match.group(2)),
            "x2": int(match.group(3)),
            "y2": int(match.group(4))
        }

    def _center_from_bounds(self, bounds: Dict[str, int]) -> Tuple[int, int]:
        """Calculate the center point for distance comparisons."""
        return (
            (bounds["x1"] + bounds["x2"]) // 2,
            (bounds["y1"] + bounds["y2"]) // 2
        )

    def _parse_temperature(self, value: str) -> Optional[float]:
        """Extract temperature values like '21.5 C', '21,5°C', or '21.25°C'."""
        if not value:
            return None

        # Extended regex: allow up to 2 decimal places for more precision
        match = re.search(r"(-?\d{1,2}(?:[.,]\d{1,2})?)\s*°?(?:\s*[Cc])?", value)
        if not match:
            return None

        try:
            parsed = float(match.group(1).replace(",", "."))
            return parsed
        except ValueError:
            return None

    def _slugify(self, text: str) -> str:
        """Generate MQTT-compatible slugs from UI labels."""
        slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
        return slug or "unknown_zone"

    def _extract_spinner_values_with_indices(self, spinner_elem: Any, package_name: str) -> Tuple[List[Dict[str, Any]], Optional[float]]:
        """
        Extract all temperature values and their indices from a spinner element.
        Returns tuple of (picker_values list, setpoint_c value from index=1).

        The setpoint is always the element with index=1 in the temperature_spinner_wrapper.
        """
        wrapper_res_id = f"{package_name}:id/temperature_spinner_wrapper"
        picker_value_res_id = "android:id/text1"
        picker_values: List[Dict[str, Any]] = []
        setpoint_c: Optional[float] = None

        # Iterate through wrapper nodes within the spinner
        for wrapper in spinner_elem:
            if wrapper.get("resource-id", "") == wrapper_res_id:
                wrapper_index_str = wrapper.get("index", "-1")
                try:
                    wrapper_index = int(wrapper_index_str)
                except ValueError:
                    wrapper_index = -1

                # Find text element within the wrapper
                for text_elem in wrapper:
                    if text_elem.get("resource-id", "") == picker_value_res_id:
                        text_value = text_elem.get("text", "").strip()
                        if text_value:
                            temp_c = self._parse_temperature(text_value)
                            if temp_c is not None:
                                picker_values.append({
                                    "raw": text_value,
                                    "c": temp_c,
                                    "index": wrapper_index
                                })
                                # Setpoint is always at index=1
                                if wrapper_index == 1:
                                    setpoint_c = temp_c

        return picker_values, setpoint_c

    def get_room_spinner_bounds(self, package_name: str, room_slug: str, use_cache: bool = False) -> Optional[Dict[str, Any]]:
        """
        Return bounds and current setpoint of the temperature spinner for a room by slug.
        The setpoint is always extracted from index=1 wrapper element.

        Returns:
            Dict with keys: bounds, center_x, center_y, setpoint_c, step_px
        """
        root = self._get_xml_root(use_cache=use_cache)
        if root is None:
            return None

        room_res_id = f"{package_name}:id/roomoverview_room"
        title_res_id = f"{package_name}:id/title"
        spinner_res_id = f"{package_name}:id/adjustable_temp"

        for room in root.iter():
            if room.get("resource-id", "") != room_res_id:
                continue

            room_label = "Unknown"
            for elem in room.iter():
                if elem.get("resource-id", "") == title_res_id and elem.get("text", "").strip():
                    room_label = elem.get("text", "").strip()
                    break

            if self._slugify(room_label) != room_slug:
                continue

            # Find the spinner element
            spinner_elem = None
            for elem in room.iter():
                if elem.get("resource-id", "") == spinner_res_id:
                    spinner_elem = elem
                    break

            if spinner_elem is None:
                return None

            # Extract spinner values with indices
            spinner_bounds = self._parse_bounds_string(spinner_elem.get("bounds", ""))
            picker_values, setpoint_c = self._extract_spinner_values_with_indices(spinner_elem, package_name)

            if not spinner_bounds or not picker_values:
                return None

            center_x = (spinner_bounds["x1"] + spinner_bounds["x2"]) // 2
            center_y = (spinner_bounds["y1"] + spinner_bounds["y2"]) // 2
            step_px = (spinner_bounds["y2"] - spinner_bounds["y1"]) // max(len(picker_values), 1)

            logger.debug(
                f"get_room_spinner: room='{room_label}' setpoint={setpoint_c}°C "
                f"picker_items={len(picker_values)} step_px={step_px}"
            )

            return {
                "bounds": spinner_bounds,
                "center_x": center_x,
                "center_y": center_y,
                "setpoint_c": setpoint_c,
                "step_px": step_px,
                "picker_items": [pv["c"] for pv in picker_values],
                "room_label": room_label
            }

        return None

    def extract_danfoss_thermostats(self, package_name: str, use_cache: bool = True) -> List[Dict[str, Any]]:
        """
        Analyse the Danfoss app UI dump and detect thermostat values with labels.
        The setpoint is always extracted from index=1 wrapper element in the spinner.

        Returns:
            List of detected thermostats with label, temperature value and resource-id.
        """
        thermostats: List[Dict[str, Any]] = []
        root = self._get_xml_root(use_cache=use_cache)
        if root is None:
            return thermostats

        room_res_id = f"{package_name}:id/roomoverview_room"
        title_res_id = f"{package_name}:id/title"
        cur_temp_res_id = f"{package_name}:id/cur_temp"
        outdoor_temp_res_id = f"{package_name}:id/outdoor_temp"
        outdoor_title_res_id = f"{package_name}:id/outdoor_title"
        spinner_res_id = f"{package_name}:id/adjustable_temp"

        # 1) Optional: export outdoor value separately.
        outdoor_label = None
        outdoor_value = None
        for elem in root.iter():
            res_id = elem.get("resource-id", "")
            if res_id == outdoor_title_res_id:
                outdoor_label = elem.get("text", "").strip() or "Outdoor"
            elif res_id == outdoor_temp_res_id:
                outdoor_value = elem.get("text", "").strip()

        if outdoor_value:
            outdoor_c = self._parse_temperature(outdoor_value)
            thermostats.append({
                "label": outdoor_label or "Outdoor",
                "slug": self._slugify(outdoor_label or "Outdoor"),
                "temperature_c": outdoor_c,
                "raw_temperature": outdoor_value,
                "setpoint_c": None,
                "setpoint_raw": None,
                "kind": "outdoor"
            })

        # 2) Read rooms via roomoverview_room.
        for room in root.iter():
            if room.get("resource-id", "") != room_res_id:
                continue

            room_name = "Unknown"
            current_raw = ""
            current_c: Optional[float] = None
            spinner_elem = None

            for elem in room.iter():
                res_id = elem.get("resource-id", "")
                text_value = elem.get("text", "").strip()

                if res_id == title_res_id and room_name == "Unknown":
                    room_name = text_value
                elif res_id == cur_temp_res_id:
                    current_raw = text_value
                    current_c = self._parse_temperature(text_value)
                elif res_id == spinner_res_id:
                    spinner_elem = elem

            if room_name == "Unknown" and not current_raw:
                continue

            setpoint_raw = None
            setpoint_c: Optional[float] = None
            picker_values: List[Dict[str, Any]] = []

            # Extract setpoint from spinner using index=1
            if spinner_elem is not None:
                picker_values, setpoint_c = self._extract_spinner_values_with_indices(spinner_elem, package_name)

                # Find raw value for the setpoint
                if setpoint_c is not None:
                    for pv in picker_values:
                        if pv.get("c") == setpoint_c:
                            setpoint_raw = pv.get("raw")
                            break

                logger.debug(
                    f"extract_danfoss: room='{room_name}' current={current_c}°C "
                    f"setpoint={setpoint_c}°C (raw='{setpoint_raw}') "
                    f"picker_count={len(picker_values)} "
                    f"min={min((v['c'] for v in picker_values), default=None)}°C "
                    f"max={max((v['c'] for v in picker_values), default=None)}°C"
                )

            thermostats.append({
                "label": room_name,
                "slug": self._slugify(room_name),
                "temperature_c": current_c,
                "raw_temperature": current_raw,
                "setpoint_c": setpoint_c,
                "setpoint_raw": setpoint_raw,
                "setpoint_min_c": min((v["c"] for v in picker_values), default=None),
                "setpoint_max_c": max((v["c"] for v in picker_values), default=None),
                "kind": "room"
            })

        # Disambiguate duplicate slugs by appending _2, _3 etc.
        slug_counts: Dict[str, int] = {}
        for entry in thermostats:
            base_slug = entry["slug"]
            slug_counts[base_slug] = slug_counts.get(base_slug, 0) + 1
            if slug_counts[base_slug] > 1:
                entry["slug"] = f"{base_slug}_{slug_counts[base_slug]}"

        return thermostats

    def is_value_changed(self, key: str, current_value: str) -> bool:
        """
        Check whether a value has changed since the last call.

        Args:
            key: The key for the value
            current_value: The current value

        Returns:
            True if value changed, False if unchanged
        """
        old_value = self.last_values.get(key)
        self.last_values[key] = current_value

        if old_value is None:
            return True  # First time, therefore "changed"

        changed = old_value != current_value
        if changed:
            logger.debug(f"Value change detected: {key} = {old_value} -> {current_value}")

        return changed

    def list_all_elements(self, verbose: bool = False) -> List[Dict[str, str]]:
        """
        List all UI elements.

        Args:
            verbose: Output all attributes

        Returns:
            List of all elements
        """
        elements = []
        try:
            root = self._get_xml_root()
            if root is None:
                return elements

            for elem in root.iter():
                element_info = {
                    "resource_id": elem.get("resource-id", ""),
                    "text": elem.get("text", ""),
                    "class": elem.get("class", ""),
                }

                if verbose:
                    element_info.update({
                        "content_desc": elem.get("content-desc", ""),
                        "bounds": elem.get("bounds", ""),
                        "checked": elem.get("checked", ""),
                        "selected": elem.get("selected", ""),
                        "enabled": elem.get("enabled", "")
                    })

                if element_info["resource_id"]:  # Only elements with resource-id
                    elements.append(element_info)

        except Exception as e:
            logger.error(f"Error listing elements: {e}")

        return elements

    def get_screen_info(self) -> Dict[str, Any]:
        """
        Return general screen information.

        Returns:
            Dictionary with screen info
        """
        info: Dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "xml_size": 0,
            "element_count": 0,
            "packages": set()
        }

        try:
            xml_str = self.get_ui_dump()
            if not xml_str:
                return info

            info["xml_size"] = len(xml_str)
            root = self._get_xml_root()
            if root is None:
                return info

            # Count elements and collect packages
            element_count = 0
            for elem in root.iter():
                element_count += 1
                res_id = elem.get("resource-id", "")
                if ":" in res_id:
                    package = res_id.split(":")[0]
                    info["packages"].add(package)

            info["element_count"] = element_count
            info["packages"] = list(info["packages"])

        except Exception as e:
            logger.error(f"Error fetching screen info: {e}")

        return info

    def dismiss_error_dialog(self) -> bool:
        """
        Try to close an error dialog by finding and tapping the standard OK button
        (android:id/button1).

        Returns:
            True if a dialog button was found and tapped, False otherwise
        """
        try:
            root = self._get_xml_root(use_cache=False)
            if root is None:
                logger.debug("dismiss_error_dialog: could not load XML")
                return False

            # Search for the Android standard OK button (android:id/button1)
            for elem in root.iter():
                res_id = elem.get("resource-id", "")
                if res_id == "android:id/button1":
                    bounds_str = elem.get("bounds", "")
                    bounds = self._parse_bounds_string(bounds_str)
                    if bounds:
                        x = (bounds["x1"] + bounds["x2"]) // 2
                        y = (bounds["y1"] + bounds["y2"]) // 2
                        logger.info(
                            f"dismiss_error_dialog: OK button (android:id/button1) "
                            f"found and tapped at {x},{y}"
                        )
                        self.adb.send_tap(x, y)
                        time.sleep(0.5)
                        return True

            logger.debug("dismiss_error_dialog: no OK button (android:id/button1) found")
            return False

        except Exception as e:
            logger.error(f"dismiss_error_dialog: error: {e}")
            return False

