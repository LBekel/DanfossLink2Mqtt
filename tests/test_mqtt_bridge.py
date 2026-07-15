"""Tests for MQTT bridge command dispatch behavior."""
import time
import unittest
from typing import Any

from core.mqtt_bridge import MQTTBridge


class _FakeMsg:
    def __init__(self, topic: str, payload: bytes):
        self.topic = topic
        self.payload = payload


class TestMQTTBridgeCommandDispatch(unittest.TestCase):
    def test_on_message_does_not_block_for_long_handler(self):
        bridge = MQTTBridge("localhost", 1883, topic_base="DanfossLink")
        state: dict[str, Any] = {"called": False, "topic": None, "payload": None}

        def slow_handler(topic: str, payload: str) -> None:
            time.sleep(0.2)
            state["topic"] = topic
            state["payload"] = payload
            state["called"] = True

        bridge.register_command_handler("thermostats/+/setpoint", slow_handler)
        msg = _FakeMsg("DanfossLink/thermostats/hwr_eg/setpoint", b'21.5')

        started = time.time()
        bridge._on_message(None, None, msg)
        elapsed = time.time() - started

        # Callback should return quickly because handler is queued to worker.
        self.assertLess(elapsed, 0.05)
        # Handler is still running immediately after return.
        self.assertFalse(state["called"])

        deadline = time.time() + 1.0
        while not state["called"] and time.time() < deadline:
            time.sleep(0.02)

        self.assertTrue(state["called"])
        self.assertEqual(state["topic"], "thermostats/hwr_eg/setpoint")
        self.assertEqual(state["payload"], "21.5")

    def test_on_message_ignores_recent_self_publish_echo(self):
        bridge = MQTTBridge("localhost", 1883, topic_base="DanfossLink")
        handler = unittest.mock.Mock()

        bridge.register_command_handler("thermostats/+/setpoint", handler)
        bridge._remember_publish("DanfossLink/thermostats/hwr_eg/setpoint", "21.5")

        msg = _FakeMsg("DanfossLink/thermostats/hwr_eg/setpoint", b'21.5')
        bridge._on_message(None, None, msg)

        handler.assert_not_called()


if __name__ == "__main__":
    unittest.main()

