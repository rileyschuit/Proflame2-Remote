# Connecting Home Assistant

The fireplace reaches HA over MQTT, not through Z-Wave. It shows up as its own **Fireplace**
device, next to your Z-Wave devices, and you can use both in the same dashboards and
automations.

**Status: not tried against a real HA yet.** The tests check the discovery messages reach a
real Mosquitto, but no HA has read them.

You can do all of this before the CC1101 arrives. The device appears, **Radio problem** is
on, and turning the fire on is refused.

## 1. Deploy the service

Run the `proflame2_fireplace` role from `OPS_ansible`. It ends by printing the MQTT endpoint.
It also starts a Mosquitto on the Pi with these logins:

| User | Used by | Can do |
| --- | --- | --- |
| `proflame2d` | The service | `home/fireplace/#`, publish discovery |
| `homeassistant` | HA, and you when debugging | Everything |

Anonymous clients are refused. The connection isn't encrypted, so keep it on the LAN and
don't forward port 1883.

## 2. Let HA reach the Pi

HA runs in the cluster, and the `home` namespace's network policy blocks private addresses
by default. It needs a rule allowing the Pi on TCP 1883, in
`clusters/production/home/networkpolicy.yml` in `kubernetes_flux`. Then:

```bash
flux reconcile kustomization flux-system --with-source
```

## 3. Add the MQTT integration

MQTT is set up in the UI and stored in HA's `.storage`, so it isn't in the `HASS` Git repo.

1. Go to **Settings > Devices & services > Add integration > MQTT**.
2. Broker: the Pi's address. Port: `1883`. Username: `homeassistant`. Password: from your
   vault.
3. Leave discovery on, with the prefix `homeassistant`.

If you already have an MQTT integration on another broker, HA only supports one. In that
case, tell the role to use that broker instead (`proflame2_fireplace_broker_enabled: false`).

## 4. Check the device

Under **Settings > Devices & services > MQTT**, look for **Fireplace**:

| Entity | Type | Notes |
| --- | --- | --- |
| Power | Switch | Starts the auto-off timer. |
| Flame | Slider, 0-6 | |
| Front burner | Switch | |
| Fan | Slider, 0-6 | |
| Light | Slider, 0-6 | Other projects report this doing nothing with the burner off. |
| Aux | Switch | |
| Auto-off in | Diagnostic sensor | Seconds left. |
| Radio problem | Diagnostic sensor | On if the CC1101 is missing or a send failed. |

Pilot isn't exposed, because it's a burner setting rather than a dashboard control. It can
still be set over MQTT.

These entities show **what the service last sent**, not what the fireplace is doing. There's
no feedback from the fireplace. If someone uses the real remote, HA won't know, and the next
change from HA will undo theirs. Use one or the other until the listening work is done.

If nothing appears, watch the discovery messages:

```bash
mosquitto_sub -h <pi> -u homeassistant -P '<password>' -t 'homeassistant/+/proflame2_fireplace/#' -v
```

## 5. Automations

These go in `automations.yaml` in the `HASS` repo, because automations edited in the UI are
lost when the pod restarts and resets to Git. Check the entity IDs on your device page first:
these are what I expect HA to name them, not ones I've seen.

```yaml
- alias: Fireplace off when nobody's home
  trigger:
    - platform: state
      entity_id: zone.home
      to: "0"
  action:
    - service: switch.turn_off
      target:
        entity_id: switch.fireplace_power

- alias: Warn when the fireplace service goes offline
  trigger:
    - platform: state
      entity_id: switch.fireplace_power
      to: unavailable
      for: "00:02:00"
  action:
    - service: notify.notify
      data:
        message: The fireplace service is offline. HA can't turn the fireplace off.
```

If the service is offline, HA can't send anything, so that second one can only warn you.
The auto-off timer is still running if only the network dropped.

For a thermostat, have HA switch **Power** using a temperature sensor in the same room,
rather than setting the remote's thermostat bit. Remember the auto-off timer ends a long burn
regardless, at 240 minutes by default.
