#!/usr/bin/env python3
"""Decodes our generated bursts with the real rtl_433 and checks every field."""
import json
import os
import subprocess
import sys
import tempfile

GEN_OOK, RTL_433 = sys.argv[1], sys.argv[2]
SERIAL, C1, D1, C2, D2 = 0xA00402, 0x0, 0xC, 0xA, 0x4

# (cmd1, cmd2, err1, err2): the distinct frames captured from the real remote.
CAPTURED = [(128, 166, 132, 136), (129, 166, 165, 136), (129, 38, 165, 0)]


def decode(cmd1, cmd2):
    pulses = subprocess.run(
        [GEN_OOK, hex(SERIAL), str(cmd1), str(cmd2), str(C1), str(D1), str(C2), str(D2)],
        check=True, capture_output=True, text=True).stdout
    with tempfile.NamedTemporaryFile("w", suffix=".ook", delete=False) as handle:
        handle.write(pulses)
    try:
        output = subprocess.run(
            [RTL_433, "-c", "0", "-R", "0", "-R", "207", "-F", "json", "-r", handle.name],
            capture_output=True, text=True, check=False).stdout
    finally:
        os.unlink(handle.name)
    rows = [json.loads(line) for line in output.splitlines() if line.startswith("{")]
    if not rows:
        raise SystemExit(f"rtl_433 decoded nothing for cmd1={cmd1} cmd2={cmd2}")
    return rows[0]


def check(row, cmd1, cmd2):
    expected = {
        "pilot": cmd1 >> 7, "light": (cmd1 >> 4) & 7, "thermostat": (cmd1 >> 1) & 1,
        "power": cmd1 & 1, "front": cmd2 >> 7, "fan": (cmd2 >> 4) & 7,
        "aux": (cmd2 >> 3) & 1, "flame": cmd2 & 7, "id": SERIAL,
        "cmd1": cmd1, "cmd2": cmd2,
    }
    for field, value in expected.items():
        if row[field] != value:
            raise SystemExit(f"{field}: wanted {value}, got {row[field]} in {row}")


count = 0
for cmd1, cmd2, err1, err2 in CAPTURED:
    row = decode(cmd1, cmd2)
    check(row, cmd1, cmd2)
    if row["err1"] != err1 or row["err2"] != err2:
        raise SystemExit(f"checksums differ from the real remote: {row}")
    count += 1

for pilot in (0, 1):
    for level in range(7):
        for power in (0, 1):
            cmd1 = pilot << 7 | level << 4 | power
            for cmd2 in (level, level << 4, 0x80 | level, 0x08 | level):
                check(decode(cmd1, cmd2), cmd1, cmd2)
                count += 1

print(f"rtl_433 decoded all {count} generated bursts correctly")
