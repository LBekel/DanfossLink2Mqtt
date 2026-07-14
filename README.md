# DanfossLink2Mqtt

DanfossLink2Mqtt controls the Danfoss Link Android app via ADB and publishes thermostat data over MQTT.

## Project Focus

- MQTT control and status under `<mqtt_topic_base>/...` (configured in `config.yaml`)
- Home Assistant MQTT Discovery for `climate` entities

## Project Structure

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
  test_mqtt_bridge.py
```

## Quick Start (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

## Docker (Linux VM)

### Prerequisites

- Docker Engine and Docker Compose plugin are installed on the VM.

### Start with Docker Compose

```bash
docker compose build
docker compose up -d
docker compose logs -f danfosslink2mqtt
```

Stop:

```bash
docker compose down
```

### Start without Compose

```bash
docker build -t danfosslink2mqtt:latest .
docker run -d --name danfosslink2mqtt --restart unless-stopped \
  -v $(pwd)/config.yaml:/app/config.yaml:ro \
  danfosslink2mqtt:latest
docker logs -f danfosslink2mqtt
```

Notes:

- `config.yaml` is the only runtime configuration file.
- If MQTT runs on the VM host, set a reachable host/IP in `config.yaml` (for example `host.docker.internal`, depending on platform).

### Auto-start on VM Boot and Restart on Failure

On a Linux VM with `systemd`, enable Docker so it starts automatically after reboot:

```bash
sudo systemctl enable docker
sudo systemctl start docker
sudo systemctl status docker
```

Container restart behavior is already configured:

- In `docker-compose.yml`, the service uses `restart: unless-stopped`.
- In the standalone `docker run` example, `--restart unless-stopped` is already included.

This means the container will be started again automatically after crashes, daemon restarts, and VM reboot (as long as it was not manually stopped).

Optional check after reboot:

```bash
docker ps --filter "name=danfosslink2mqtt"
docker inspect -f '{{ .HostConfig.RestartPolicy.Name }}' danfosslink2mqtt
```

## Configuration

### `config.yaml`

All parameters are loaded from a single file: `config.yaml`.

- `settings.adb_device_ip` and `settings.adb_device_port` for the Android device
- `settings.mqtt_broker`, `settings.mqtt_port`, `settings.mqtt_topic_base` for MQTT
- `settings.poll_interval` for runtime polling behavior
- `settings.homeassistant_discovery` and `settings.homeassistant_discovery_prefix` for HA discovery

## MQTT Topics

Note: Examples below use `DanfossLink`. The prefix is configurable via `settings.mqtt_topic_base`.

### Commands (subscribed)

```text
DanfossLink/command/set_temperature
```

Payload example:

```json
{"room": "living_room", "temperature": 21.5}
```

### Thermostat Status (published)

```text
DanfossLink/thermostats/<slug>/label
DanfossLink/thermostats/<slug>/kind
DanfossLink/thermostats/<slug>/value
DanfossLink/thermostats/<slug>/setpoint
DanfossLink/thermostats/<slug>/mode
DanfossLink/thermostats/<slug>/hvac_action
DanfossLink/thermostats/<slug>/setpoint_error
```

### Service Status (published)

```text
DanfossLink/status
DanfossLink/status/error
```

- `status` uses MQTT LWT: `online` on connect, `offline` on disconnect/shutdown.
- `status/error` is published on startup errors (for example if the Danfoss app is not installed).

### Setpoint Behavior

- On `command/set_temperature`, the target setpoint is published immediately to `thermostats/<slug>/setpoint`.
- If UI readback lags behind, a short internal pending state prevents the polling cycle from immediately overwriting the new value with stale data.
- The `setpoint_set_at` topic is no longer used.

`hvac_action` is derived from current vs target temperature:

- `idle` when `setpoint < value`
- otherwise `heating`

## Home Assistant Integration

### Automatic MQTT Discovery

When discovery is enabled, one MQTT `climate` entity is published per room.

- `temperature_command_topic`: `DanfossLink/command/set_temperature`
- `temperature_state_topic`: `DanfossLink/thermostats/<slug>/setpoint`
- `current_temperature_topic`: `DanfossLink/thermostats/<slug>/value`
- `mode_state_topic`: `DanfossLink/thermostats/<slug>/mode`
- `action_topic`: `DanfossLink/thermostats/<slug>/hvac_action`

Other discovery fields that are set:

- `icon: mdi:heating-coil`
- `availability_topic: <mqtt_topic_base>/status` with `payload_available=online`, `payload_not_available=offline`
- `modes: ["heat"]`
- `min_temp`, `max_temp`, `temp_step` from `config.yaml`
- `precision: 0.1`

## Development and Tests

```powershell
python -m unittest tests.test_hvac_action
python -m unittest tests.test_mqtt_bridge
python -m unittest discover -s tests -p "test_*.py" -v
```
