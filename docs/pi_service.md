# Pi service (proflame2d)

Runs the fireplace from a Raspberry Pi with a CC1101 on SPI. It takes MQTT commands, sends
radio frames, and enforces the auto-off timer. Its topics and safety rules match
`esp32s3_mqtt_rest`, so you can test either build the same way. See
[interfaces.md](interfaces.md).

**Status: tested with a fake radio and a real Mosquitto. Never run on a Pi or with a real
CC1101, and nothing has been transmitted.**

It can't run inside zwave-js-ui, which only drives Z-Wave controllers. It runs beside it, as
its own container.

## How it fits together

```
Home Assistant --MQTT--> Mosquitto --MQTT--> proflame2d --SPI--> CC1101 ~~315 MHz~~> fireplace
 (in the cluster)        |<------- on the Pi, Docker Compose ----->|
```

Setup is the `proflame2_fireplace` role in `SturgeonTechnologies/OPS_ansible`
(`docs/provision_fireplace.md` there). To connect it to HA, see
[home_assistant.md](home_assistant.md).

## Code

| Path | What it does |
| --- | --- |
| `pi/proflame2d/frame.py` | Frame encoder. A test checks it gives the same bytes as the C++ one. |
| `pi/proflame2d/controller.py` | State, command checks, auto-off timer. |
| `pi/proflame2d/cc1101.py` | CC1101 driver over `spidev`. |
| `pi/proflame2d/service.py` | Main loop and MQTT. |
| `pi/proflame2d/discovery.py` | Home Assistant discovery messages. |
| `pi/proflame2d/store.py` | Saves state and the timer across restarts. |
| `pi/proflame2d/config.py` | Settings, from environment variables. |

## Settings

| Variable | Default | What it is |
| --- | --- | --- |
| `PROFLAME2_SERIAL` | required | Remote serial, hex. In `remote_identity.h`. |
| `PROFLAME2_ERR1_C`, `_ERR1_D`, `_ERR2_C`, `_ERR2_D` | required | Checksum constants, one hex digit each. Also in `remote_identity.h`. |
| `PROFLAME2_MQTT_HOST` | required | Broker address. |
| `PROFLAME2_MQTT_PORT` | `1883` | |
| `PROFLAME2_MQTT_USER`, `_MQTT_PASSWORD` | empty | Broker login. |
| `PROFLAME2_BASE_TOPIC` | `home/fireplace` | Topic prefix. |
| `PROFLAME2_DISCOVERY_PREFIX` | `homeassistant` | HA's discovery prefix. |
| `PROFLAME2_AUTO_OFF_MINUTES` | `240` | 1-720. |
| `PROFLAME2_FREQUENCY_KHZ` | `314973` | 300000-348000. |
| `PROFLAME2_TX_POWER` | `low` | `low`, `mid` or `high`: about -10, 0 or +10 dBm. |
| `PROFLAME2_SPI_BUS`, `_SPI_DEVICE` | `0`, `0` | `/dev/spidev0.0`, which is CE0. |
| `PROFLAME2_STATE_FILE` | `/data/state.json` | Keep this on a volume. |
| `PROFLAME2_HEARTBEAT_FILE` | `/run/proflame2/heartbeat` | Read by the container health check. |

The image holds no identity or credentials.

## What it does when things go wrong

- **MQTT or Home Assistant down:** the timer still runs, because it's in this service.
- **Service stopped or container restarted:** if the fire is on, it sends off 3 times first.
  **Redeploying the container therefore turns the fireplace off.**
- **Service crashed:** nothing is sent on startup. State comes back from `/data`, and the
  timer keeps its original end time, so crash loops can't extend it. If the time passed
  while it was down, it sends off.
- **No CC1101, or bad wiring:** the service keeps running and retries every 30 s. Turning
  the fire on is refused, and HA shows **Radio problem**. So you can deploy before the
  module arrives.
- **Retained `set` message:** refused, so a broker can't relight the fire after a restart.
- **Pi loses power, or the kernel hangs:** nothing can send off. The fire stays as it was
  until someone uses the real remote. Keep the real remote where you can get to it, since
  this Pi is going in the crawl space.

## Not built yet

- **Listening for the real remote.** Using it makes our state stale, and our next command
  undoes its change. This is step 8 of [notes.md](notes.md). GDO0 and GDO2 are wired for it.
- **REST.** The Pi service is MQTT only.
- **The thermostat bit.** Always 0, because that mode uses the remote's own sensor.

## Build and test

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e 'pi[test]'
make pi-test                     # needs mosquitto on the PATH
docker build -t proflame2d pi    # the image is arm64 in CI; this builds for your machine
```

Merging to `main` pushes `ghcr.io/rileyschuit/proflame2-remote:sha-<7>`. The package is
private, so the Pi needs a classic PAT with only `read:packages`. To list tags:

```bash
gh api /user/packages/container/proflame2-remote/versions \
  --jq '.[:5][] | [.created_at, (.metadata.container.tags|join(","))] | @tsv'
```

## First test on the Pi

Follow steps 3-5 of [notes.md](notes.md), using MQTT instead of the serial monitor. Stay
beside the fireplace with the real remote in your hand.

```bash
mosquitto_sub -h <pi> -u homeassistant -P '<password>' -t 'home/fireplace/#' -v
mosquitto_pub -h <pi> -u homeassistant -P '<password>' -t home/fireplace/set -m '{"power":true,"flame":1}'
mosquitto_pub -h <pi> -u homeassistant -P '<password>' -t home/fireplace/set -m '{"power":false}'
```

Unlike the serial sketch, the service has no test-serial command. To check frames off the
air without the fireplace reacting, run it with a different `PROFLAME2_SERIAL` for that test,
and read them with `rtl_433 -f 315M -R 207 -F json`.
