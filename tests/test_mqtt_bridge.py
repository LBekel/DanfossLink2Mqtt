"""Tests for MQTT bridge command dispatch behavior."""
import time
import unittest

from core.mqtt_bridge import MQTTBridge


class _FakeMsg:
    def __init__(self, topic: str, payload: bytes):
        self.topic = topic
        self.payload = payload


class TestMQTTBridgeCommandDispatch(unittest.TestCase):
    def test_on_message_does_not_block_for_long_handler(self):
        bridge = MQTTBridge("localhost", 1883, topic_base="DanfossLink")
        state = {"called": False}

        def slow_handler(_payload: str) -> None:
            time.sleep(0.2)
            state["called"] = True

        bridge.register_command_handler("set_temperature", slow_handler)
        msg = _FakeMsg("DanfossLink/command/set_temperature", b'{"room":"hwr_eg","temperature":21.5}')

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


if __name__ == "__main__":
    unittest.main()

