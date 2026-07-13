"""Haupteinstiegspunkt für DanfossLink2Mqtt.

Delegiert an DanfossLink2MQTT aus main_ui.py, welches UIAutomator,
automatischen App-Start und Dialog-Behandlung enthält.
"""
from core.main_ui import DanfossLink2MQTT


def main():
    """Einstiegspunkt"""
    app = DanfossLink2MQTT()
    app.run()


if __name__ == "__main__":
    main()
