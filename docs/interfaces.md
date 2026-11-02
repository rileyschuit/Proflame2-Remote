# Interfaces

All of them change the same state. Levels are 0-6, and every command sends the fireplace's
full state in one burst. State is what this device last sent, not a reading from the
fireplace: there's no feedback, and the real remote can change things without us knowing.

## Serial (both sketches, 115200 baud)

| Command | What it does |
| --- | --- |
| `flame <0-6>`, `fan <0-6>`, `light <0-6>` | Set a level |
| `power on\|off`, `front on\|off`, `aux on\|off`, `pilot on\|off` | Set a switch |
| `off` | Power off now |
| `status` | State, timer and the frame bytes |
| `frame` | Show the frame without sending |
| `send` | Send the current state again |
| `timer <1-720>` | Auto-off minutes (restarts a running timer) |
| `id <hex>` / `id real` | Use a test serial the fireplace ignores, or go back |
| `freq <kHz>` | Radio frequency, 300000-348000 |
| `tx low\|mid\|high` | Transmit power: about -10, 0 or +10 dBm |
| `help` | List commands |

## REST (`esp32s3_mqtt_rest`, port 80)

Everything except `/healthz` needs `Authorization: Bearer <kApiToken>`. REST is refused
until you change the token from its placeholder. It's plain HTTP, so a token can be
sniffed on the LAN: keep this device on a trusted network and never forward it to the
internet.

| Method and path | What it does | Success |
| --- | --- | --- |
| `GET /healthz` | Is the radio present? No auth. | 200 |
| `GET /api/state` | Current state | 200 |
| `POST /api/state` | Change any fields; all apply or none do | 202 |
| `POST /api/off` | Power off | 202 |

202 means queued for sending, because there's no way to know that the fireplace heard it.

Errors: 400 for bad JSON, unknown fields or out-of-range values; 401 for a bad token; and
503 if the CC1101 isn't found.

```bash
TOKEN=...; HOST=192.168.0.x
curl -H "Authorization: Bearer $TOKEN" http://$HOST/api/state
curl -X POST -H "Authorization: Bearer $TOKEN" -d '{"power":true,"flame":3}' http://$HOST/api/state
curl -X POST -H "Authorization: Bearer $TOKEN" http://$HOST/api/off
```

Fields: `power`, `front`, `aux`, `pilot` (true/false), and `flame`, `fan`, `light` (0-6).
The thermostat bit is left off on purpose. `GET` also returns `autoOffMinutes`,
`autoOffRemainingS`, `radioOk` and `assumed: true`.

## MQTT (`esp32s3_mqtt_rest` and the Pi service)

With the default `kMqttBaseTopic` of `home/fireplace`:

| Topic | Direction | Payload |
| --- | --- | --- |
| `home/fireplace/set` | To device | Same JSON as `POST /api/state` |
| `home/fireplace/state` | From device, retained | Same JSON as `GET /api/state` |
| `home/fireplace/availability` | From device, retained | `online`, or `offline` via last will |
| `home/fireplace/error` | From device | Why a command was refused |

```bash
mosquitto_pub -h broker -u fireplace -P ... -t home/fireplace/set -m '{"power":true,"flame":3}'
mosquitto_sub -h broker -u fireplace -P ... -t 'home/fireplace/#' -v
```

**Don't publish `set` with the retain flag.** The device refuses retained commands, so a
stale "power on" on the broker can't relight the fireplace after a reboot. The connection
isn't TLS, so run this only on a trusted LAN.

The Pi service uses the same topics and JSON, and has no REST or serial interface. It also
announces itself to Home Assistant; see [home_assistant.md](home_assistant.md).

## Safety behaviour

- **Auto-off:** power turns off after 240 minutes by default, 720 at most. It runs on the
  device, so it works with the network down. Changing levels doesn't extend it. A timed off
  is sent 3 times, since nothing confirms it arrived.
- **Failed sends:** if the radio refuses an off frame, it keeps retrying every 2 s.
- **Reboot, ESP32-S3:** nothing is sent at boot. State is saved in flash, and a fireplace
  that was on gets a fresh timer. Repeated reboots would keep restarting that timer.
- **Reset, Uno:** state and timer are lost, and opening the serial port resets a Uno. The
  fireplace stays as it was, with no timer, so use this build only while you're present.
- **Test serial:** any change from on to off goes out on the real serial, so a test serial
  left set can't block an off.
- **Thermostat bit:** always 0. That mode relies on the remote's own temperature sensor.
