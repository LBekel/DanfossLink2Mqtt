"""Unit-Tests fuer HVAC-Action-Ableitung."""
import unittest

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


if __name__ == "__main__":
    unittest.main()

