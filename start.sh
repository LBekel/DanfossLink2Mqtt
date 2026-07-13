#!/bin/bash
# Startskript fuer DanfossLink2Mqtt

set -e

echo "====================================="
echo "DanfossLink2Mqtt - Danfoss Link via MQTT"
echo "====================================="
echo ""

# Überprüfe Python-Version
python_version=$(python --version 2>&1 | awk '{print $2}')
echo "[*] Python Version: $python_version"

# Überprüfe virtual environment
if [ ! -d ".venv" ]; then
    echo "[!] Virtual Environment nicht gefunden, erstelle es..."
    python -m venv .venv
fi

# Aktiviere virtual environment
echo "[*] Aktiviere Virtual Environment..."
source .venv/bin/activate

# Installiere/Update Abhängigkeiten
echo "[*] Überprüfe Abhängigkeiten..."
pip install --quiet -r requirements.txt

# Überprüfe zentrale config.yaml
if [ ! -f "config.yaml" ]; then
    echo "[!] config.yaml nicht gefunden."
    echo "[!] Bitte lege config.yaml im Projektverzeichnis an."
    exit 1
fi

# Überprüfe ADB
echo "[*] Überprüfe ADB..."
if ! command -v adb &> /dev/null; then
    echo "[!] ADB nicht gefunden. Bitte installiere Android SDK Platform Tools."
    exit 1
fi

# Zeige connected Geräte
echo "[*] Verbundene ADB-Geräte:"
adb devices 2>/dev/null | tail -n +2 || echo "   Keine Geräte gefunden"

echo ""
echo "[*] Starte DanfossLink2Mqtt..."
echo ""

# Starte die Anwendung
python main.py

deactivate

