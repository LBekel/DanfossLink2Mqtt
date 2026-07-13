@echo off
REM Startskript fuer DanfossLink2Mqtt (Windows)

echo =====================================
echo DanfossLink2Mqtt - Danfoss Link via MQTT
echo =====================================
echo.

REM Überprüfe Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [!] Python nicht gefunden. Bitte installiere Python 3.8+
    pause
    exit /b 1
)

REM Erstelle virtual environment falls nicht vorhanden
if not exist ".venv\" (
    echo [*] Erstelle Virtual Environment...
    python -m venv .venv
)

REM Aktiviere virtual environment
echo [*] Aktiviere Virtual Environment...
call .venv\Scripts\activate.bat

REM Installiere Abhängigkeiten
echo [*] Überprüfe Abhängigkeiten...
pip install --quiet -r requirements.txt

REM Überprüfe zentrale config.yaml
if not exist "config.yaml" (
    echo [!] config.yaml nicht gefunden.
    echo [!] Bitte lege config.yaml im Projektverzeichnis an.
    pause
    exit /b 1
)

REM Überprüfe ADB
where adb >nul 2>&1
if errorlevel 1 (
    echo [!] ADB nicht in PATH gefunden.
    echo    Stel sicher, dass Android SDK Platform Tools installiert ist.
)

echo.
echo [*] Überprüfe verbundene ADB-Geräte...
adb devices

echo.
echo [*] Starte DanfossLink2Mqtt...
echo.

REM Starte die Anwendung
python main.py

call .venv\Scripts\deactivate.bat
pause

