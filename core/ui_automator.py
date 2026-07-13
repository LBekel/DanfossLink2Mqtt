"""UIAutomator XML Parser für ADB-basierte UI-Automation"""
import logging
import time
import xml.etree.ElementTree as ET
import re
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from .adb_controller import ADBController

logger = logging.getLogger(__name__)


class UIAutomatorParser:
    """Parst XMLDump von UIAutomator und extrahiert Werte basierend auf resource-ids"""
    
    def __init__(self, adb: ADBController):
        """
        Initialisiert den UIAutomator Parser
        
        Args:
            adb: ADBController Instanz
        """
        self.adb = adb
        self.last_xml = None
        self.last_xml_time = None
        self.cache_duration = 5  # Sekunden
        self.cached_values = {}
        self.last_values = {}  # Für Change-Detection

    def _extract_xml_payload(self, raw_output: str) -> Optional[str]:
        """Extrahiert das reine XML-Dokument aus UIAutomator-Shell-Output."""
        if not raw_output:
            return None

        cleaned = raw_output.replace("\x00", "").strip()

        # UIAutomator hängt je nach Android-Version oft Status-Text vor/nach XML an.
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
        """Lädt den XML-Dump und liefert den geparsten Root-Knoten zurück."""
        xml_str = self.get_ui_dump(use_cache=use_cache)
        if not xml_str:
            return None

        try:
            return ET.fromstring(xml_str)
        except ET.ParseError as e:
            logger.error(f"XML Parse-Fehler: {e}")
            return None
    
    def get_ui_dump(self, use_cache: bool = True) -> Optional[str]:
        """
        Holt den aktuellen UI-Dump vom Android-Gerät
        
        Args:
            use_cache: Benutze gecachte Daten wenn verfügbar
            
        Returns:
            XML-String oder None bei Fehler
        """
        # Überprüfe Cache
        if use_cache and self.last_xml and self.last_xml_time:
            age = datetime.now() - self.last_xml_time
            if age.total_seconds() < self.cache_duration:
                logger.debug(f"UIAutomator Cache verwendet (Alter: {age.total_seconds():.1f}s)")
                return self.last_xml
        
        try:
            logger.debug("Hole UI-Dump von UIAutomator...")
            # UIAutomator Befehl
            result = self.adb.shell_command("uiautomator dump /dev/stdout")
            
            if result:
                xml_payload = self._extract_xml_payload(result)
                if not xml_payload:
                    logger.error("Konnte kein gueltiges UIAutomator-XML im Shell-Output finden")
                    return None

                self.last_xml = xml_payload
                self.last_xml_time = datetime.now()
                logger.debug(f"UI-Dump erhalten ({len(xml_payload)} Bytes)")
                return xml_payload
            else:
                logger.error("UIAutomator Dump ist leer")
                return None
        except Exception as e:
            logger.error(f"Fehler beim Abrufen des UI-Dumps: {e}")
            return None
    
    def save_ui_dump(self, filepath: str = "ui_dump.xml") -> bool:
        """
        Speichert den UI-Dump lokal als XML-Datei zum Debugging
        
        Args:
            filepath: Zielpath (lokal auf dem Computer, z.B. "ui_dump.xml" oder "C:\\Users\\user\\Downloads\\dump.xml")
            
        Returns:
            True bei Erfolg
        """
        try:
            xml_data = self.get_ui_dump(use_cache=False)
            if xml_data:
                # Speichere lokal auf dem Computer
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(xml_data)
                logger.info(f"UI-Dump gespeichert: {filepath}")
                return True
            else:
                logger.error("Konnte XML-Daten nicht abrufen")
        except Exception as e:
            logger.error(f"Fehler beim Speichern des UI-Dumps: {e}")
        
        return False
    
    def extract_value_by_resource_id(self, resource_id: str, value_type: str = "text") -> Optional[str]:
        """
        Extrahiert einen Wert basierend auf resource-id
        
        Args:
            resource_id: Die resource-id (z.B. "com.android.systemui:id/clock")
            value_type: Art des auszulesenden Wertes:
                - text: Text-Inhalt des Elements
                - content-desc: content-description Attribut
                - checked: Wert des checked Attributs
                - selected: Wert des selected Attributs
                - enabled: Wert des enabled Attributs
                - bounds: Position des Elements
                
        Returns:
            Der extrahierte Wert oder None
        """
        try:
            root = self._get_xml_root()
            if root is None:
                return None
            
            # Suche Element mit matching resource-id
            for elem in root.iter():
                res_id = elem.get("resource-id", "")
                if res_id == resource_id:
                    logger.debug(f"Element gefunden: {resource_id}")
                    
                    # Extrahiere gewünschten Wert-Typ
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
                    
                    logger.debug(f"Wert extrahiert ({value_type}): {value}")
                    return value if value else None
            
            logger.warning(f"Element mit resource-id nicht gefunden: {resource_id}")
            return None
        
        except Exception as e:
            logger.error(f"Fehler beim Extrahieren des Wertes: {e}")
            return None
    
    def extract_multiple_by_class(self, class_name: str) -> List[Dict[str, str]]:
        """
        Extrahiert mehrere Elemente basierend auf Klasse
        
        Args:
            class_name: Die Klasse (z.B. "android.widget.TextView")
            
        Returns:
            Liste von Dictionaries mit Element-Attributen
        """
        results = []
        try:
            root = self._get_xml_root()
            if root is None:
                return results
            
            # Suche alle Elemente mit matching Klasse
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
            
            logger.debug(f"{len(results)} Elemente der Klasse '{class_name}' gefunden")
            return results
        
        except Exception as e:
            logger.error(f"Fehler beim Auslesen mehrerer Elemente: {e}")
            return results
    
    def extract_all_by_package(self, package_name: str) -> List[Dict[str, str]]:
        """
        Extrahiert alle UI-Elemente eines Packages
        
        Args:
            package_name: Paketname (z.B. "com.netflix.mediaclient")
            
        Returns:
            Liste von Dictionaries mit Element-Attributen
        """
        results = []
        try:
            root = self._get_xml_root()
            if root is None:
                return results
            
            # Suche alle Elemente mit matching package in resource-id
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
            
            logger.debug(f"{len(results)} Elemente des Packages '{package_name}' gefunden")
            return results
        
        except Exception as e:
            logger.error(f"Fehler beim Auslesen von Package-Elementen: {e}")
            return results
    
    def find_element_by_text(self, text: str, partial: bool = False) -> Optional[Dict[str, str]]:
        """
        Findet ein Element basierend auf Text
        
        Args:
            text: Der zu suchende Text
            partial: Ob Partial-Match erlaubt ist
            
        Returns:
            Dictionary mit Element-Attributen oder None
        """
        try:
            root = self._get_xml_root()
            if root is None:
                return None
            
            # Suche Element mit matching Text
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
            
            logger.warning(f"Element mit Text nicht gefunden: {text}")
            return None
        
        except Exception as e:
            logger.error(f"Fehler beim Suchen nach Text: {e}")
            return None
    
    def get_bounds(self, resource_id: str) -> Optional[Dict[str, int]]:
        """
        Extrahiert die Bounds/Position eines Elements
        
        Args:
            resource_id: Die resource-id
            
        Returns:
            Dictionary mit x1, y1, x2, y2 Koordinaten oder None
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
            logger.error(f"Fehler beim Parsen der Bounds: {e}")
        
        return None

    def _parse_bounds_string(self, bounds_str: str) -> Optional[Dict[str, int]]:
        """Parst das Android-Bounds-Format [x1,y1][x2,y2]."""
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
        """Berechnet den Mittelpunkt fuer Distanzvergleiche."""
        return (
            (bounds["x1"] + bounds["x2"]) // 2,
            (bounds["y1"] + bounds["y2"]) // 2
        )

    def _parse_temperature(self, value: str) -> Optional[float]:
        """Extrahiert Temperaturwerte wie '21.5 C' oder '21,5°C'."""
        if not value:
            return None

        match = re.search(r"(-?\d{1,2}(?:[.,]\d)?)\s*°?(?:\s*[Cc])?", value)
        if not match:
            return None

        try:
            return float(match.group(1).replace(",", "."))
        except ValueError:
            return None

    def _slugify(self, text: str) -> str:
        """Erzeugt MQTT-kompatible Slugs aus UI-Labels."""
        slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
        return slug or "unknown_zone"

    def get_room_spinner_bounds(self, package_name: str, room_slug: str, use_cache: bool = False) -> Optional[Dict[str, Any]]:
        """
        Gibt Bounds und aktuellen Sollwert des Temperatur-Spinners fuer einen Raum per Slug zurueck.

        Returns:
            Dict mit keys: bounds, center_x, center_y, setpoint_c, step_px
        """
        root = self._get_xml_root(use_cache=use_cache)
        if root is None:
            return None

        room_res_id = f"{package_name}:id/roomoverview_room"
        title_res_id = f"{package_name}:id/title"
        spinner_res_id = f"{package_name}:id/adjustable_temp"
        picker_value_res_id = "android:id/text1"

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

            spinner_bounds = None
            picker_items: List[float] = []

            for elem in room.iter():
                res_id = elem.get("resource-id", "")
                if res_id == spinner_res_id:
                    spinner_bounds = self._parse_bounds_string(elem.get("bounds", ""))
                elif res_id == picker_value_res_id:
                    temp_c = self._parse_temperature(elem.get("text", ""))
                    if temp_c is not None:
                        picker_items.append(temp_c)

            if not spinner_bounds or not picker_items:
                return None

            center_x = (spinner_bounds["x1"] + spinner_bounds["x2"]) // 2
            center_y = (spinner_bounds["y1"] + spinner_bounds["y2"]) // 2
            step_px = (spinner_bounds["y2"] - spinner_bounds["y1"]) // max(len(picker_items), 1)
            selected_idx = len(picker_items) // 2
            setpoint_c = picker_items[selected_idx] if picker_items else None

            return {
                "bounds": spinner_bounds,
                "center_x": center_x,
                "center_y": center_y,
                "setpoint_c": setpoint_c,
                "step_px": step_px,
                "picker_items": picker_items,
                "room_label": room_label
            }

        return None

    def extract_danfoss_thermostats(self, package_name: str, use_cache: bool = True) -> List[Dict[str, Any]]:
        """
        Analysiert den UI-Dump der Danfoss-App und erkennt Thermostatwerte mit Bezeichnung.

        Returns:
            Liste erkannter Thermostate mit Label, Temperaturwert und resource-id.
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
        picker_value_res_id = "android:id/text1"

        # 1) Optional: Outdoor-Wert separat exportieren.
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

        # 2) Räume gezielt über roomoverview_room auslesen.
        for room in root.iter():
            if room.get("resource-id", "") != room_res_id:
                continue

            room_name = "Unknown"
            current_raw = ""
            current_c: Optional[float] = None
            picker_values: List[Dict[str, Any]] = []

            for elem in room.iter():
                res_id = elem.get("resource-id", "")
                text_value = elem.get("text", "").strip()
                if not text_value:
                    continue

                if res_id == title_res_id and room_name == "Unknown":
                    room_name = text_value
                elif res_id == cur_temp_res_id:
                    current_raw = text_value
                    current_c = self._parse_temperature(text_value)
                elif res_id == picker_value_res_id:
                    temp_c = self._parse_temperature(text_value)
                    if temp_c is not None:
                        picker_values.append({"raw": text_value, "c": temp_c})

            if room_name == "Unknown" and not current_raw:
                continue

            setpoint_raw = None
            setpoint_c: Optional[float] = None
            if picker_values:
                # Im Danfoss-Spinner ist der mittlere Eintrag der aktive Sollwert.
                selected_idx = len(picker_values) // 2
                selected = picker_values[selected_idx]
                setpoint_raw = selected["raw"]
                setpoint_c = selected["c"]

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

        # Bei identischen Labels den naechsten Treffer als _2, _3 usw. kennzeichnen.
        slug_counts: Dict[str, int] = {}
        for entry in thermostats:
            base_slug = entry["slug"]
            slug_counts[base_slug] = slug_counts.get(base_slug, 0) + 1
            if slug_counts[base_slug] > 1:
                entry["slug"] = f"{base_slug}_{slug_counts[base_slug]}"

        return thermostats

    def is_value_changed(self, key: str, current_value: str) -> bool:
        """
        Überprüft ob sich ein Wert seit dem letzten Check geändert hat
        
        Args:
            key: Der Schlüssel für den Wert
            current_value: Der aktuelle Wert
            
        Returns:
            True wenn Wert geändert, False wenn gleich
        """
        old_value = self.last_values.get(key)
        self.last_values[key] = current_value
        
        if old_value is None:
            return True  # Erstes Mal, daher "geändert"
        
        changed = old_value != current_value
        if changed:
            logger.debug(f"Wertänderung erkannt: {key} = {old_value} -> {current_value}")
        
        return changed
    
    def list_all_elements(self, verbose: bool = False) -> List[Dict[str, str]]:
        """
        Listet alle UI-Elemente auf
        
        Args:
            verbose: Ausgabe aller Attribute
            
        Returns:
            Liste aller Elemente
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
                
                if element_info["resource_id"]:  # Nur mit resource-id
                    elements.append(element_info)
        
        except Exception as e:
            logger.error(f"Fehler beim Auflisten von Elementen: {e}")
        
        return elements
    
    def get_screen_info(self) -> Dict[str, Any]:
        """
        Gibt allgemeine Bildschirm-Informationen
        
        Returns:
            Dictionary mit Bildschirm-Infos
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
            
            # Zähle Elemente und sammle Packages
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
            logger.error(f"Fehler beim Abrufen von Bildschirm-Infos: {e}")

        return info

    def dismiss_error_dialog(self) -> bool:
        """
        Versucht, einen Fehlerdialog zu schließen indem der Standard-OK-Button
        (android:id/button1) gesucht und angetippt wird.

        Returns:
            True wenn ein Dialog-Button gefunden und angetippt wurde, sonst False
        """
        try:
            root = self._get_xml_root(use_cache=False)
            if root is None:
                logger.debug("dismiss_error_dialog: Konnte XML nicht laden")
                return False

            # Suche nach dem Android-Standard OK-Button (android:id/button1)
            for elem in root.iter():
                res_id = elem.get("resource-id", "")
                if res_id == "android:id/button1":
                    bounds_str = elem.get("bounds", "")
                    bounds = self._parse_bounds_string(bounds_str)
                    if bounds:
                        x = (bounds["x1"] + bounds["x2"]) // 2
                        y = (bounds["y1"] + bounds["y2"]) // 2
                        logger.info(
                            f"dismiss_error_dialog: OK-Button (android:id/button1) "
                            f"gefunden und betätigt bei {x},{y}"
                        )
                        self.adb.send_tap(x, y)
                        time.sleep(0.5)
                        return True

            logger.debug("dismiss_error_dialog: Kein OK-Button (android:id/button1) gefunden")
            return False

        except Exception as e:
            logger.error(f"dismiss_error_dialog: Fehler: {e}")
            return False


