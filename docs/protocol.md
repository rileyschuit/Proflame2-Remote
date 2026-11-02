# Proflame 2 protocol

Sources: rtl_433 `proflame2.c`, johnellinwood/smartfire, and the 2026-11-02 capture.

## Radio

- OOK at about 315 MHz. Published values differ: 314.973 MHz (rtl_433) and about 315.07 MHz
  measured (j2deen). We default to 314.973 MHz, and `freq <kHz>` changes it.
- 2400 symbols/s, about 417 us per symbol.
- One press sends 5 copies with 12 silent symbols between them: 958 symbols, about 400 ms.

## Frame

A frame is 7 words, each 13 bit-pairs (26 symbols), with no gap between words:

| Part | Symbols | Value |
| --- | --- | --- |
| Sync | `11` | Marks the start of a word |
| Start guard | `10` | Always 1 |
| Data | 8 pairs | MSB first |
| Pad | 1 pair | 1 on the first word, otherwise 0 |
| Parity | 1 pair | 1 if data + pad has an odd number of ones |
| End guard | `10` | Always 1 |

A data 1 is `10` (on, off), and a 0 is `01`.

Words, in order: `serial[2] serial[1] serial[0] cmd1 cmd2 err1 err2`.

## Commands

| Byte | Bit | Field |
| --- | --- | --- |
| cmd1 | 7 | pilot |
| cmd1 | 6-4 | light, 0-6 |
| cmd1 | 1 | thermostat |
| cmd1 | 0 | power |
| cmd2 | 7 | front ("show") |
| cmd2 | 6-4 | fan, 0-6 |
| cmd2 | 3 | aux |
| cmd2 | 2-0 | flame, 0-6 |

Every frame carries the whole state, so there is no "flame up" command.

## Checksum

With A and B as the high and low nibbles of the command byte:

```
high = (C ^ (A<<1) ^ A ^ (B<<1)) & 0xF
low  = (D ^ A ^ B) & 0xF
err  = high<<4 | low
```

C and D differ per remote. This remote uses err1 C=0x0, D=0xC and err2 C=0xA, D=0x4.

### Working out the constants for another remote

From any captured frame, with `h`/`l` the nibbles of the command byte and `X`/`Y` the
nibbles of its err byte, keeping 4 bits after each shift:

```
C = X ^ ((h<<1)&0xF) ^ h ^ ((l<<1)&0xF)
D = Y ^ h ^ l
```

Do it for cmd1 with err1 and cmd2 with err2, then put the values in `remote_identity.h`.

rtl_433 doesn't verify the err bytes (its `"mic": "CHECKSUM"` is a fixed label), so a
decoded frame doesn't prove the checksum is right. Reports say a fireplace silently
ignores frames with wrong constants.
