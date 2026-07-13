"""MQTT-Bridge für die Bereitstellung von ADB-Daten"""
import logging
import json
import time
from typing import Callable, Dict, Any
import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)


class MQTTBridge:
    """MQTT-Bridge zur Kommunikation mit ADB-Daten"""
    
    def __init__(self, broker: str, port: int, username: str = "", password: str = "",
                 topic_base: str = "DanfossLink2Mqtt"):
        """
        Initialisiert die MQTT-Bridge
        
        Args:
            broker: MQTT Broker Adresse
            port: MQTT Broker Port
            username: MQTT Benutzername (optional)
            password: MQTT Passwort (optional)
            topic_base: Basis-Topic für alle veröffentlichten Daten
        """
        self.broker = broker
        self.port = port
        self.username = username
        self.password = password
        self.topic_base = topic_base
        self.client = mqtt.Client(client_id="DanfossLink2Mqtt")
        self.connected = False
        self.callbacks: Dict[str, Callable] = {}
        
        # Setze Callbacks
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.on_publish = self._on_publish
    
    def connect(self) -> bool:
        """Verbindung zum MQTT Broker herstellen"""
        try:
            if self.username and self.password:
                self.client.username_pw_set(self.username, self.password)
            
            logger.info(f"Verbinde mit MQTT Broker: {self.broker}:{self.port}")
            self.client.connect(self.broker, self.port, keepalive=60)
            self.client.loop_start()
            
            # Warte auf Verbindung
            timeout = time.time() + 10
            while not self.connected and time.time() < timeout:
                time.sleep(0.1)
            
            if self.connected:
                logger.info("Erfolgreich mit MQTT Broker verbunden")
                return True
            else:
                logger.error("MQTT Verbindung Timeout")
                return False
        except Exception as e:
            logger.error(f"MQTT Verbindungsfehler: {e}")
            return False
    
    def disconnect(self) -> None:
        """Verbindung zum MQTT Broker trennen"""
        try:
            self.client.loop_stop()
            self.client.disconnect()
            logger.info("MQTT Verbindung getrennt")
        except Exception as e:
            logger.error(f"Fehler beim Trennen der MQTT-Verbindung: {e}")
    
    def _on_connect(self, client, userdata, flags, rc):
        """Callback bei Verbindung"""
        if rc == 0:
            self.connected = True
            logger.info("MQTT Broker verbunden")
            # Abonniere Steuerbefehle
            command_topic = f"{self.topic_base}/command/#"
            self.client.subscribe(command_topic)
            logger.info(f"Abonniert: {command_topic}")
        else:
            logger.error(f"MQTT Verbindung fehlgeschlagen mit Code {rc}")
    
    def _on_disconnect(self, client, userdata, rc):
        """Callback bei Trennung"""
        self.connected = False
        if rc != 0:
            logger.warning(f"Unerwartete Trennung mit Code {rc}")
    
    def _on_message(self, client, userdata, msg):
        """Callback für eingehende Nachrichten"""
        topic = msg.topic
        payload = msg.payload.decode('utf-8', errors='ignore')
        
        logger.debug(f"MQTT Nachricht empfangen: {topic} = {payload}")
        
        # Extrahiere Befehlstyp aus Topic
        parts = topic.split('/')
        if len(parts) >= 3 and parts[0] == self.topic_base.split('/')[0]:
            command_type = '/'.join(parts[2:])
            
            if command_type in self.callbacks:
                try:
                    self.callbacks[command_type](payload)
                except Exception as e:
                    logger.error(f"Fehler beim Verarbeiten des Befehls '{command_type}': {e}")
    
    def _on_publish(self, client, userdata, mid):
        """Callback nach Veröffentlichung"""
        logger.debug(f"Nachricht veröffentlicht (MID: {mid})")
    
    def publish(self, topic_suffix: str, payload: Any, retain: bool = False, qos: int = 1) -> bool:
        """
        Veröffentlicht eine Nachricht
        
        Args:
            topic_suffix: Suffix für den vollständigen Topic
            payload: Die zu veröffentlichende Nachricht
            retain: Ob die Nachricht behalten werden soll
            qos: Quality of Service (0, 1, 2)
            
        Returns:
            True bei Erfolg, False bei Fehler
        """
        if not self.connected:
            logger.warning("Nicht mit MQTT verbunden")
            return False
        
        try:
            full_topic = f"{self.topic_base}/{topic_suffix}"
            
            # Konvertiere Payload zu JSON wenn nötig
            if isinstance(payload, (dict, list)):
                payload_str = json.dumps(payload)
            else:
                payload_str = str(payload)
            
            self.client.publish(full_topic, payload_str, retain=retain, qos=qos)
            logger.debug(f"Veröffentlicht: {full_topic} = {payload_str}")
            return True
        except Exception as e:
            logger.error(f"Fehler beim Veröffentlichen: {e}")
            return False

    def publish_absolute(self, topic: str, payload: Any, retain: bool = False, qos: int = 1) -> bool:
        """Veröffentlicht auf einem absoluten Topic ohne topic_base-Präfix."""
        if not self.connected:
            logger.warning("Nicht mit MQTT verbunden")
            return False

        try:
            if isinstance(payload, (dict, list)):
                payload_str = json.dumps(payload)
            else:
                payload_str = str(payload)

            self.client.publish(topic, payload_str, retain=retain, qos=qos)
            logger.debug(f"Veröffentlicht (absolut): {topic} = {payload_str}")
            return True
        except Exception as e:
            logger.error(f"Fehler beim absoluten Veröffentlichen: {e}")
            return False

    def register_command_handler(self, command_name: str, handler: Callable) -> None:
        """
        Registriert einen Handler für einen Befehl
        
        Args:
            command_name: Der Befehlsname
            handler: Die Callback-Funktion
        """
        self.callbacks[command_name] = handler
        logger.info(f"Befehl-Handler registriert: {command_name}")
    
    def is_connected(self) -> bool:
        """Gibt zurück, ob verbunden ist"""
        return self.connected

