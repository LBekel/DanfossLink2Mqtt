"""ADB-Controller für die Kommunikation mit Android-Geräten"""
import logging
import threading
from typing import Optional, Dict, Any
from adb_shell.adb_device import AdbDeviceTcp

logger = logging.getLogger(__name__)


class ADBController:
    """Kontrolliert Android-Geräte via ADB"""
    
    def __init__(self, host: str, port: int, device_ip: str, device_port: int):
        """
        Initialisiert den ADB-Controller
        
        Args:
            host: ADB-Host (normalerweise localhost)
            port: ADB-Port (normalerweise 5037)
            device_ip: IP-Adresse des Android-Geräts
            device_port: Port des Android-Geräts (normalerweise 5555)
        """
        self.host = host
        self.port = port
        self.device_ip = device_ip
        self.device_port = device_port
        self.device: Optional[AdbDeviceTcp] = None
        # Garantiert, dass Shell-Befehle strikt sequentiell laufen.
        self._command_lock = threading.RLock()
        
    def connect(self) -> bool:
        """Verbindung zum Android-Gerät herstellen"""
        try:
            logger.info(f"Verbinde mit {self.device_ip}:{self.device_port}")
            self.device = AdbDeviceTcp(self.device_ip, self.device_port)
            self.device.connect()
            logger.info("Erfolgreich verbunden")
            return True
        except Exception as e:
            logger.error(f"Verbindungsfehler: {e}")
            return False
    
    def is_connected(self) -> bool:
        """Prüft ob die ADB-Verbindung aktiv ist.

        Returns:
            True wenn verbunden und erreichbar, False sonst
        """
        if not self.device:
            return False
        try:
            result = self.shell_command("echo ok")
            return result.strip() == "ok"
        except Exception:
            return False

    def ensure_connected(self) -> bool:
        """Stellt sicher dass die ADB-Verbindung aktiv ist. Verbindet bei Bedarf neu.

        Returns:
            True wenn verbunden (oder Neuverbindung erfolgreich), False bei Fehler
        """
        if self.is_connected():
            logger.debug("ADB: Verbindung aktiv")
            return True
        logger.warning("ADB: Verbindung unterbrochen – versuche Neuverbindung...")
        return self.connect()

    def disconnect(self) -> None:
        """Verbindung trennen"""
        if self.device:
            try:
                self.device.close()
                logger.info("Verbindung getrennt")
            except Exception as e:
                logger.error(f"Fehler beim Trennen: {e}")
    
    def shell_command(self, command: str) -> str:
        """
        Führt einen Shell-Befehl auf dem Gerät aus
        
        Args:
            command: Der auszuführende Befehl
            
        Returns:
            Die Ausgabe des Befehls
        """
        if not self.device:
            logger.error("Gerät nicht verbunden")
            return ""
        
        try:
            with self._command_lock:
                result = self.device.shell(command)
            return result
        except Exception as e:
            logger.error(f"Shell-Befehl fehlgeschlagen: {e}")
            return ""
    
    def start_app(self, package_name: str) -> bool:
        """
        Startet eine App

        Args:
            package_name: Paketname der App

        Returns:
            True bei Erfolg, False bei Fehler
        """
        try:
            logger.info(f"Starte App: {package_name}")
            self.shell_command(f"monkey -p {package_name} -c android.intent.category.LAUNCHER 1")
            return True
        except Exception as e:
            logger.error(f"Fehler beim Starten der App: {e}")
            return False

    def stop_app(self, package_name: str) -> bool:
        """
        Stoppt eine App
        
        Args:
            package_name: Paketname der App
            
        Returns:
            True bei Erfolg, False bei Fehler
        """
        try:
            logger.info(f"Stoppe App: {package_name}")
            self.shell_command(f"am force-stop {package_name}")
            return True
        except Exception as e:
            logger.error(f"Fehler beim Stoppen der App: {e}")
            return False
    
    def send_keyevent(self, keycode: int) -> bool:
        """
        Sendet einen Key-Event an das Gerät
        
        Args:
            keycode: Der zu sendende Keycode
            
        Returns:
            True bei Erfolg, False bei Fehler
        """
        try:
            self.shell_command(f"input keyevent {keycode}")
            return True
        except Exception as e:
            logger.error(f"Fehler beim Senden des Key-Events: {e}")
            return False
    
    def send_tap(self, x: int, y: int) -> bool:
        """
        Sendet einen Tap-Event an eine Position
        
        Args:
            x: X-Koordinate
            y: Y-Koordinate
            
        Returns:
            True bei Erfolg, False bei Fehler
        """
        try:
            self.shell_command(f"input tap {x} {y}")
            return True
        except Exception as e:
            logger.error(f"Fehler beim Senden des Tap-Events: {e}")
            return False
    
    def send_swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> bool:
        """
        Sendet einen Swipe-Befehl.

        Args:
            x1, y1: Startposition
            x2, y2: Endposition
            duration_ms: Dauer in Millisekunden

        Returns:
            True bei Erfolg
        """
        try:
            self.shell_command(f"input swipe {x1} {y1} {x2} {y2} {duration_ms}")
            return True
        except Exception as e:
            logger.error(f"Fehler beim Senden des Swipe-Befehls: {e}")
            return False

    def send_text(self, text: str) -> bool:
        """
        Sendet Text an das Gerät (z.B. in ein Textfeld)
        
        Args:
            text: Der zu sendende Text
            
        Returns:
            True bei Erfolg, False bei Fehler
        """
        try:
            # Beende Sonderzeichen und Spaces
            escaped_text = text.replace("'", "\\'").replace(" ", "%s")
            self.shell_command(f"input text '{escaped_text}'")
            return True
        except Exception as e:
            logger.error(f"Fehler beim Senden von Text: {e}")
            return False
    
    def is_app_running(self, package_name: str) -> bool:
        """
        Prüft, ob eine App aktuell läuft.

        Args:
            package_name: Paketname der App

        Returns:
            True wenn die App läuft, False wenn nicht
        """
        try:
            result = self.shell_command(f"pidof {package_name}")
            running = bool(result and result.strip())
            logger.debug(f"is_app_running({package_name}): {'läuft' if running else 'nicht aktiv'} (pidof='{result.strip()}')")
            return running
        except Exception as e:
            logger.error(f"Fehler bei is_app_running: {e}")
            return False

    def start_activity(self, package_name: str, activity_name: str) -> bool:
        """
        Startet eine Activity mit vollem Paketnamen

        Args:
            package_name: Paketname der App
            activity_name: Activity-Name (z.B. com.danfoss.cumulus.app.firstuse.SplashActivity)

        Returns:
            True bei Erfolg, False bei Fehler
        """
        try:
            logger.info(f"Starte Activity: {package_name}/{activity_name}")
            self.shell_command(f"am start -n {package_name}/{activity_name}")
            return True
        except Exception as e:
            logger.error(f"Fehler beim Starten der Activity: {e}")
            return False

    def get_device_properties(self) -> Dict[str, str]:
        """
        Liest Geräteeigenschaften aus
        
        Returns:
            Dictionary mit Geräteeigenschaften
        """
        properties = {}
        try:
            result = self.shell_command("getprop")
            for line in result.split('\n'):
                if line.strip():
                    # Parse Linien wie [ro.build.version.release]: [13]
                    if '[' in line and ']' in line:
                        parts = line.split(']')
                        if len(parts) >= 2:
                            key = parts[0].replace('[', '').strip()
                            value = parts[1].replace('[', '').replace(']', '').strip()
                            properties[key] = value
        except Exception as e:
            logger.error(f"Fehler beim Lesen der Geräteeigenschaften: {e}")
        
        return properties
    

