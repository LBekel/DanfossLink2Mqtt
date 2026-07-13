# DanfossLink2Mqtt

DanfossLink2Mqtt steuert die Danfoss Link Android-App per ADB und publiziert Thermostatdaten per MQTT.

## Projektfokus

- MQTT-Steuerung und Status unter `DanfossLink2Mqtt/...`
- Home Assistant MQTT Discovery fuer `climate`-Entitaeten

## Projektstruktur

```text
main.py
  Dockerfile
  docker-compose.yml
  .dockerignore
  docker/
    entrypoint.sh
  core/
    adb_controller.py
    config.py
    main_ui.py
    mqtt_bridge.py
    ui_automator.py
    ui_config_manager.py
  config.yaml
tests/
  test_hvac_action.py
```

## Schnellstart (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

## Docker (Linux VM)

### Voraussetzung

- Docker Engine und Docker Compose Plugin sind auf der VM installiert.

### Start mit Docker Compose

```bash
docker compose build
docker compose up -d
docker compose logs -f danfosslink2mqtt
```

Stoppen:

```bash
docker compose down
```

### Start ohne Compose

```bash
docker build -t danfosslink2mqtt:latest .
docker run -d --name danfosslink2mqtt --restart unless-stopped \
  -v $(pwd)/config.yaml:/app/config.yaml:ro \
  danfosslink2mqtt:latest
docker logs -f danfosslink2mqtt
```

Hinweise:

- `config.yaml` bleibt die einzige Konfigurationsdatei.
- Wenn MQTT auf dem Host der VM laeuft, setze in `config.yaml` einen erreichbaren Hostnamen/IP (z.B. `host.docker.internal` je nach Plattform).

## Konfiguration

### `config.yaml`

Alle Parameter werden aus einer einzigen Datei gelesen: `config.yaml`.

- `settings.adb_device_ip` und `settings.adb_device_port` fuer das Android-Geraet
- `settings.mqtt_broker`, `settings.mqtt_port`, `settings.mqtt_topic_base` fuer MQTT
- `settings.poll_interval` fuer Laufzeitverhalten
- `settings.homeassistant_discovery` und `settings.homeassistant_discovery_prefix` fuer HA Discovery
- Optionale `ui_elements` koennen zusaetzliche App-Werte publizieren

## MQTT Topics

### Befehle (abonniert)

```text
DanfossLink2Mqtt/command/set_temperature
```

Payload-Beispiel:

```json
{"room": "living_room", "temperature": 21.5}
```

### Thermostat-Status (publiziert)

```text
DanfossLink2Mqtt/thermostats/<slug>/label
DanfossLink2Mqtt/thermostats/<slug>/kind
DanfossLink2Mqtt/thermostats/<slug>/value
DanfossLink2Mqtt/thermostats/<slug>/setpoint
DanfossLink2Mqtt/thermostats/<slug>/mode
DanfossLink2Mqtt/thermostats/<slug>/hvac_action
DanfossLink2Mqtt/thermostats/<slug>/setpoint_set_at
DanfossLink2Mqtt/thermostats/<slug>/setpoint_error
```

`hvac_action` wird aus Ist/Soll abgeleitet:

- `idle`, wenn `setpoint < value`
- sonst `heating`

## Home Assistant Integration

### Automatische MQTT Discovery

Bei aktivem Discovery wird pro Raum eine MQTT-`climate`-Entity angelegt.

- `temperature_command_topic`: `DanfossLink2Mqtt/command/set_temperature`
- `temperature_state_topic`: `DanfossLink2Mqtt/thermostats/<slug>/setpoint`
- `current_temperature_topic`: `DanfossLink2Mqtt/thermostats/<slug>/value`
- `mode_state_topic`: `DanfossLink2Mqtt/thermostats/<slug>/mode`
- `action_topic`: `DanfossLink2Mqtt/thermostats/<slug>/hvac_action`

## Entwicklung und Tests

```powershell
python -m unittest tests.test_hvac_action
python -m unittest tests.test_connections
```
