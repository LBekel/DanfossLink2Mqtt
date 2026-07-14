"""MQTT bridge for publishing ADB data via MQTT"""
import logging
import json
import time
import queue
import threading
from typing import Callable, Dict, Any
import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)


class MQTTBridge:
    """MQTT bridge for communication with ADB data"""

    def __init__(self, broker: str, port: int, username: str = "", password: str = "",
                 topic_base: str = "DanfossLink2Mqtt"):
        """
        Initializes the MQTT bridge.

        Args:
            broker: MQTT broker address
            port: MQTT broker port
            username: MQTT username (optional)
            password: MQTT password (optional)
            topic_base: Base topic for all published data
        """
        self.broker = broker
        self.port = port
        self.username = username
        self.password = password
        self.topic_base = topic_base
        self.client = mqtt.Client(client_id="DanfossLink2Mqtt")
        self.connected = False
        self.callbacks: Dict[str, Callable] = {}
        self._command_queue: "queue.Queue[tuple[str, str]]" = queue.Queue()
        self._command_worker = threading.Thread(target=self._command_worker_loop, daemon=True)
        self._command_worker.start()

        # Set callbacks
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.on_publish = self._on_publish

    def connect(self) -> bool:
        """Establish connection to the MQTT broker"""
        try:
            if self.username and self.password:
                self.client.username_pw_set(self.username, self.password)

            # Set Last Will Testament (LWT) message
            lwt_topic = f"{self.topic_base}/status"
            self.client.will_set(lwt_topic, "offline", qos=1, retain=True)
            logger.debug(f"LWT configured: {lwt_topic} = 'offline'")

            logger.info(f"Connecting to MQTT broker: {self.broker}:{self.port}")
            self.client.connect(self.broker, self.port, keepalive=60)
            self.client.loop_start()

            # Wait for connection
            timeout = time.time() + 10
            while not self.connected and time.time() < timeout:
                time.sleep(0.1)

            if self.connected:
                logger.info("Successfully connected to MQTT broker")
                return True
            else:
                logger.error("MQTT connection timeout")
                return False
        except Exception as e:
            logger.error(f"MQTT connection error: {e}")
            return False

    def disconnect(self) -> None:
        """Disconnect from the MQTT broker"""
        try:
            # Publish an explicit offline status on controlled shutdown so HA
            # immediately marks entities unavailable even without LWT.
            if self.connected:
                status_topic = f"{self.topic_base}/status"
                self.client.publish(status_topic, "offline", qos=1, retain=True)

            # Send DISCONNECT while loop is active, then stop loop thread.
            self.client.disconnect()
            self.client.loop_stop()
            self.connected = False
            logger.info("MQTT connection closed")
        except Exception as e:
            logger.error(f"Error closing MQTT connection: {e}")

    def _on_connect(self, client, userdata, flags, rc):
        """Callback on connection"""
        if rc == 0:
            self.connected = True
            logger.info("MQTT broker connected")
            # Publish online status
            online_topic = f"{self.topic_base}/status"
            self.client.publish(online_topic, "online", qos=1, retain=True)
            logger.debug(f"Published online status: {online_topic} = 'online'")
            # Subscribe to command topics
            command_topic = f"{self.topic_base}/command/#"
            self.client.subscribe(command_topic)
            logger.info(f"Subscribed: {command_topic}")
        else:
            logger.error(f"MQTT connection failed with code {rc}")

    def _on_disconnect(self, client, userdata, rc):
        """Callback on disconnect"""
        self.connected = False
        if rc != 0:
            logger.warning(f"Unexpected disconnect with code {rc} – Last Will Testament will be published")

    def _on_message(self, client, userdata, msg):
        """Callback for incoming messages"""
        topic = msg.topic
        payload = msg.payload.decode('utf-8', errors='ignore')

        logger.debug(f"MQTT message received: {topic} = {payload}")

        # Extract command type from topic
        parts = topic.split('/')
        if len(parts) >= 3 and parts[0] == self.topic_base.split('/')[0]:
            command_type = '/'.join(parts[2:])

            if command_type in self.callbacks:
                # Handlers can take several seconds (ADB/UI automation). Run
                # them outside MQTT callback thread so outgoing publishes are
                # not delayed until handler completion.
                self._command_queue.put((command_type, payload))

    def _command_worker_loop(self) -> None:
        """Process command handlers sequentially outside MQTT callback thread."""
        while True:
            command_type, payload = self._command_queue.get()
            try:
                handler = self.callbacks.get(command_type)
                if not handler:
                    continue
                handler(payload)
            except Exception as e:
                logger.error(f"Error processing command '{command_type}': {e}")
            finally:
                self._command_queue.task_done()

    def _on_publish(self, client, userdata, mid):
        """Callback after publish"""
        logger.debug(f"Message published (MID: {mid})")

    def publish(self, topic_suffix: str, payload: Any, retain: bool = False, qos: int = 1) -> bool:
        """
        Publish a message.

        Args:
            topic_suffix: Suffix for the full topic
            payload: The message to publish
            retain: Whether the message should be retained
            qos: Quality of Service (0, 1, 2)

        Returns:
            True on success, False on error
        """
        if not self.connected:
            logger.warning("Not connected to MQTT")
            return False

        try:
            full_topic = f"{self.topic_base}/{topic_suffix}"

            # Convert payload to JSON if necessary
            if isinstance(payload, (dict, list)):
                payload_str = json.dumps(payload)
            else:
                payload_str = str(payload)

            self.client.publish(full_topic, payload_str, retain=retain, qos=qos)
            logger.debug(f"Published: {full_topic} = {payload_str}")
            return True
        except Exception as e:
            logger.error(f"Error publishing: {e}")
            return False

    def publish_absolute(self, topic: str, payload: Any, retain: bool = False, qos: int = 1) -> bool:
        """Publish to an absolute topic without topic_base prefix."""
        if not self.connected:
            logger.warning("Not connected to MQTT")
            return False

        try:
            if isinstance(payload, (dict, list)):
                payload_str = json.dumps(payload)
            else:
                payload_str = str(payload)

            self.client.publish(topic, payload_str, retain=retain, qos=qos)
            logger.debug(f"Published (absolute): {topic} = {payload_str}")
            return True
        except Exception as e:
            logger.error(f"Error publishing to absolute topic: {e}")
            return False

    def register_command_handler(self, command_name: str, handler: Callable) -> None:
        """
        Register a handler for a command.

        Args:
            command_name: The command name
            handler: The callback function
        """
        self.callbacks[command_name] = handler
        logger.info(f"Command handler registered: {command_name}")

    def is_connected(self) -> bool:
        """Return whether the client is connected"""
        return self.connected
