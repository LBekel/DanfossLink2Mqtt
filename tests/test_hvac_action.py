"""Unit-Tests fuer HVAC-Action-Ableitung."""
import unittest
from unittest.mock import Mock
import json
import time

from core.adb_controller import ADBController
from core.main_ui import DanfossLink2MQTT


class TestHvacAction(unittest.TestCase):
    def test_idle_when_target_lower_than_current(self):
        self.assertEqual(
            DanfossLink2MQTT._derive_hvac_action(current_temp=21.0, target_temp=20.0),
            "idle"
        )

    def test_heating_when_target_equal_or_higher(self):
        self.assertEqual(
            DanfossLink2MQTT._derive_hvac_action(current_temp=21.0, target_temp=21.0),
            "heating"
        )
        self.assertEqual(
            DanfossLink2MQTT._derive_hvac_action(current_temp=21.0, target_temp=22.0),
            "heating"
        )

    def test_none_when_values_missing(self):
        self.assertIsNone(DanfossLink2MQTT._derive_hvac_action(current_temp=None, target_temp=22.0))
        self.assertIsNone(DanfossLink2MQTT._derive_hvac_action(current_temp=21.0, target_temp=None))


class TestDanfossAppAvailability(unittest.TestCase):
    def test_is_app_installed_returns_true_for_valid_pm_path(self):
        adb = ADBController("localhost", 5037, "127.0.0.1", 5555)
        adb.shell_command = Mock(return_value="package:/data/app/~~abc/base.apk")

        self.assertTrue(adb.is_app_installed("com.danfoss.linkapp"))

    def test_is_app_installed_returns_false_when_package_missing(self):
        adb = ADBController("localhost", 5037, "127.0.0.1", 5555)
        adb.shell_command = Mock(return_value="")

        self.assertFalse(adb.is_app_installed("com.danfoss.linkapp"))

    def test_launch_danfoss_app_publishes_message_when_app_not_installed(self):
        app = DanfossLink2MQTT()
        app.adb = Mock()
        app.adb.is_app_installed.return_value = False
        app.mqtt = Mock()
        publish_mock = Mock()
        app.mqtt.publish = publish_mock

        result = app._launch_danfoss_app()

        self.assertFalse(result)
        publish_mock.assert_called_once()
        topic, message = publish_mock.call_args.args[:2]
        self.assertEqual(topic, "status/error")
        self.assertIn("not installed", message)
        self.assertIn("adb install -r", message)


class TestTemperatureParsing(unittest.TestCase):
    def test_parse_single_decimal_place(self):
        from core.ui_automator import UIAutomatorParser
        parser = UIAutomatorParser(Mock())

        self.assertEqual(parser._parse_temperature("21.5 C"), 21.5)
        self.assertEqual(parser._parse_temperature("21,5°C"), 21.5)
        self.assertEqual(parser._parse_temperature("21.5"), 21.5)

    def test_parse_two_decimal_places(self):
        from core.ui_automator import UIAutomatorParser
        parser = UIAutomatorParser(Mock())

        # Now with extended regex, should parse 2 decimal places
        self.assertEqual(parser._parse_temperature("21.25 C"), 21.25)
        self.assertEqual(parser._parse_temperature("21,50°C"), 21.50)
        self.assertEqual(parser._parse_temperature("21.75"), 21.75)

    def test_parse_no_decimal(self):
        from core.ui_automator import UIAutomatorParser
        parser = UIAutomatorParser(Mock())

        self.assertEqual(parser._parse_temperature("21 C"), 21.0)
        self.assertEqual(parser._parse_temperature("21°C"), 21.0)

    def test_parse_invalid(self):
        from core.ui_automator import UIAutomatorParser
        parser = UIAutomatorParser(Mock())

        self.assertIsNone(parser._parse_temperature(""))
        self.assertIsNone(parser._parse_temperature("invalid"))
        self.assertIsNone(parser._parse_temperature("-- C"))


class TestSetTemperaturePublish(unittest.TestCase):
    def test_setpoint_is_published_immediately_after_command(self):
        app = DanfossLink2MQTT()
        app.adb = Mock()
        app.ui_parser = Mock()
        app.ui_config = Mock()
        app.ui_config.get_setting = Mock(side_effect=lambda key, default=None: default)
        app.mqtt = Mock()

        # Force an early return after immediate publish to prove
        # publishing does not wait for spinner/polling success.
        app.ui_parser.get_bounds.return_value = None

        payload = json.dumps({"room": "hwr_eg", "temperature": 23.5})
        app._handle_set_temperature(payload)

        app.mqtt.publish.assert_any_call("thermostats/hwr_eg/setpoint", 23.5)


class TestPendingSetpointOverride(unittest.TestCase):
    def test_polling_uses_pending_setpoint_until_ui_catches_up(self):
        app = DanfossLink2MQTT()
        app.mqtt = Mock()
        app.ui_parser = Mock()
        app.ui_parser.extract_danfoss_thermostats.return_value = [
            {
                "slug": "hwr_eg",
                "label": "HWR EG",
                "kind": "room",
                "temperature_c": 20.0,
                "setpoint_c": 19.0,
            }
        ]

        app.ui_config = Mock()
        app.ui_config.get_setting = Mock(side_effect=lambda key, default=None: False if key == "homeassistant_discovery" else default)
        app.pending_setpoints["hwr_eg"] = {"target": 22.5, "set_at": time.time()}

        app._publish_danfoss_thermostats(force=True)

        app.mqtt.publish.assert_any_call("thermostats/hwr_eg/setpoint", 22.5)
        app.mqtt.publish.assert_any_call("thermostats/hwr_eg/hvac_action", "heating")


if __name__ == "__main__":
    unittest.main()
