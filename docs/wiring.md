# Wiring

The schematics in `hardware/` are the reference. Boards are drawn with a net label on each
pin, so matching labels are connected.

**Before wiring:** cheap CC1101 modules don't all use the same pin order, so follow the
silkscreen on yours rather than the pin numbers on our symbol.

## ESP32-S3

Connect directly, since both sides are 3.3 V.

```
 XIAO ESP32-S3                 CC1101 (315 MHz)
 +-------------+               +-------------+
 | 3V3         |---+-----------| VCC     ANT |--- antenna
 | GND         |---|--+--------| GND         |
 | D3  GPIO4   |---|--|--------| CSN         |
 | D8  GPIO7   |---|--|--------| SCK         |
 | D10 GPIO9   |---|--|--------| MOSI        |
 | D9  GPIO8   |---|--|--------| MISO        |
 | D1  GPIO2   |---|--|--------| GDO0        |  not used yet
 | D0  GPIO1   |---|--|--------| GDO2        |  not used yet
 +-------------+   |  |        +-------------+
                  ===C1 100 nF
                  ===C2 10 uF    (both at the CC1101)
                   |  |
                   +--+
```

| Signal | CC1101 | XIAO | DevKitC-1 |
| --- | --- | --- | --- |
| Power | VCC | 3V3 | 3V3 |
| Ground | GND | GND | GND |
| Chip select | CSN | D3 | GPIO4 |
| Clock | SCK | D8 | GPIO7 |
| Data out | MOSI | D10 | GPIO9 |
| Data in | MISO | D9 | GPIO8 |
| Spare, for listening later | GDO0 | D1 | GPIO2 |
| Spare, for listening later | GDO2 | D0 | GPIO1 |

## Uno R3

**Never connect a Uno signal pin straight to the CC1101.** The Uno drives 5 V, and the
CC1101 is rated for about 3.6 V. Power the CC1101 from the Uno's 3.3 V pin, not 5 V.

```
 Uno R3          BSS138 shifter            CC1101 (315 MHz)
 +------+        +------------+            +-------------+
 | 5V   |--------| HV      LV |-----+------| VCC     ANT |--- antenna
 | 3V3  |--------|------------|-----+      |             |
 | GND  |--------| GND    GND |-----|--+---| GND         |
 | D13  |--------| HV1    LV1 |-----|--|---| SCK         |
 | D11  |--------| HV2    LV2 |-----|--|---| MOSI        |
 | D10  |--------| HV3    LV3 |-----|--|---| CSN         |
 | D12  |--------| HV4    LV4 |-----|--|---| MISO        |
 +------+        +------------+     |  |   | GDO0, GDO2  |  leave open
                                  ===C1,C2 +-------------+
                                    |  |
                                    +--+
```

| Signal | Uno | Shifter HV | Shifter LV | CC1101 |
| --- | --- | --- | --- | --- |
| Power, high side | 5V | HV | | |
| Power, low side | 3V3 | | LV | VCC |
| Ground | GND | GND | GND | GND |
| Clock | D13 | HV1 | LV1 | SCK |
| Data out | D11 | HV2 | LV2 | MOSI |
| Chip select | D10 | HV3 | LV3 | CSN |
| Data in | D12 | HV4 | LV4 | MISO |

**No shifter on hand?** On D13, D11 and D10, use a divider: Uno pin to a 1 k resistor to the
CC1101 pin, then 1.8 k from the CC1101 pin to GND. Connect MISO directly, since it only
drives from the CC1101 to the Uno. The Uno's 3.3 V high is close to its input threshold of
3 V, so if `CC1101 NOT FOUND` shows up, suspect that link first.

## Antenna

Keep the antenna vertical and away from the board. Use `tx low` at first, then go up only
if the fireplace needs it. The RF power table is in `Cc1101Ook.h`.
