# Notes and plan

## What we know

Capture from 2026-11-02 on an RTL-SDR: `rtl_433 -f 315M -R 207 -F json`.

| Time | Action | id | cmd1 | cmd2 | err1 | err2 | Decoded |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 12:12:37 | Off | 10486786 | 128 | 166 | 132 | 136 | pilot 1, power 0, front 1, fan 2, flame 6 |
| 12:13:05 | On | 10486786 | 129 | 166 | 165 | 136 | pilot 1, power 1, front 1, fan 2, flame 6 |
| 12:16:07 | Show off | 10486786 | 129 | 38 | 165 | 0 | pilot 1, power 1, front 0, fan 2, flame 6 |
| 12:16:35 | Show on | 10486786 | 129 | 166 | 165 | 136 | pilot 1, power 1, front 1, fan 2, flame 6 |

Findings:

- **No rolling code.** The 12:13:05 and 12:16:35 frames are identical, with other presses
  between them, and the frame has no counter.
- **Every frame carries the full state**, so a frame sent from stale state undoes anything
  changed on the real remote.
- **The id 10486786 (0xA00402) is most likely the remote's serial**, learned by the
  receiver at pairing. It's static across all captures.
- **Fan, light and flame are each 0-6.** Thermostat is 1 when a temperature or "smart" mode
  is set on the remote, and 0 otherwise. Pilot can be 0 or 1.
- **err1 and err2 are checksums, not controls.** The 196/76 flip in err2 follows the front
  bit at fan 6, flame 6. The formula fits all four captured frames; see
  [protocol.md](protocol.md).

## Checked so far

- The checksum formula reproduces every err byte in the capture.
- The encoder reproduces the worked bit string in smartfire's README.
- The real rtl_433 decoder reads back all 115 generated test bursts, field by field.
- All three schematics pass KiCad ERC. That only checks the drawing, not a working circuit.

## Not checked

- Nothing has been built or transmitted.
- The CC1101 driver has only been compiled. Its settings are based on the dangerouslaser
  project and TI's power table.
- We don't know yet that the receiver accepts frames using the remote's serial.
- Other projects report that the light and front burner don't work without the burner on,
  so a light test with the fireplace off may show nothing even when frames are good.

## Final build

The end result is a Raspberry Pi running [proflame2d](pi_service.md) beside zwave-js-ui on
the Z-Wave Pi, in the crawl space next to the fireplace. It connects to Home Assistant over
MQTT; see [home_assistant.md](home_assistant.md). Test the radio on both the ESP32-S3 and the
Pi first. Steps 2-5 below are written for the serial sketch, and
[pi_service.md](pi_service.md#first-test-on-the-pi) has the MQTT equivalent.

Check these at the final location:

- **Range.** The Z-Wave stick and the Pi itself can add noise at 315 MHz, and the crawl space
  may have metal ducting or foil insulation.
- **Heat and damp.** Keep the Pi and module away from the firebox and the gas line.
- **The GPIO header.** If the Z-Wave controller is a card on the header rather than a USB
  stick, it may cover the pins or share them. Check it against
  [wiring.md](wiring.md#raspberry-pi).

## Plan

### 1. Get parts

Check off the [BOM](../README.md#bill-of-materials). Start with the ESP32-S3 unless a Uno
is all you have.

### 2. Bring up the radio, no fireplace involved

Flash `arduino_serial_input` and open the monitor. You want `CC1101 found`, then a version.
`CC1101 NOT FOUND` is a wiring problem.

### 3. Check our frames off the air, using a serial the fireplace ignores

```bash
rtl_433 -f 315M -R 207 -M level -F json     # on the laptop with the RTL-SDR
```
On the board's serial monitor:
```
id 123456
tx low
flame 3
```
rtl_433 should show `id` 1193046 and `flame` 3, with `power` 0. Compare `cmd1`, `cmd2` and
the frequency offset against the real remote. If nothing decodes, debug here, before the
real serial is involved.

### 4. First real frame, beside the fireplace, original remote in hand

```
id real
off
power on
off
```
Start with power on only, at the lowest flame the boot state uses. Listen for the receiver
to beep, and confirm that `off` puts the fire out. If it ignores the frames:

- Capture our frame and the real remote's side by side, and compare them.
- Try `freq 315000`, then `tx mid`, then `tx high`.
- Move closer to rule out range.

### 5. Exercise each control

Flame 1-6, fan, light and front, one at a time, with the burner on. Record anything that
behaves differently from the bit map. Also find out what `flame 0` with power on does.

### 6. Move to the network build

Flash `esp32s3_mqtt_rest`, set `secrets.h`, and test REST and MQTT per
[interfaces.md](interfaces.md). Let the auto-off timer run once with a short `timer 1`,
then again with Wi-Fi turned off.

### 7. Home Assistant

- Add an MQTT entity, or MQTT discovery in the firmware.
- Add an automation that turns it off when `availability` goes `offline`, or when nobody's
  home.
- Decide on a thermostat loop using a sensor in the same room. Prefer HA turning power on
  and off over setting the thermostat bit.

### 8. Stay in sync with the real remote

Today, using the real remote makes our state stale, and our next command undoes its change.
Have the CC1101 listen for this remote's frames and update state from them. GDO0 and GDO2
are already wired on the ESP32-S3 schematic for this. Until then, use one or the other.

### 9. Finish the build

Move from breadboard to a soldered board in a non-metal enclosure, and add a status LED.
Keep it away from the fireplace's heat.

## Safety rules

- Only send commands the remote itself can send. Don't touch the receiver or valve.
- Keep auto-off in the firmware, independent of the network and HA.
- Keep the original remote working as a manual override.
- Be next to the fireplace for any test that can light it. Keep a working CO detector.
- Use the lowest transmit power that works. This is a hobby build, so we also haven't
  checked it against the FCC Part 15 limits the real remote was certified to.
