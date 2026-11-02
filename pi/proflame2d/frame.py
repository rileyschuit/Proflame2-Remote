"""Proflame 2 on-air frame: state -> command bytes -> checksums -> symbols.

Python port of libraries/Proflame2/src/Proflame2Frame.cpp. tests/test_frame.py checks
that both produce the same bytes. See docs/protocol.md.
"""
from dataclasses import dataclass

MAX_LEVEL = 6
BURST_SYMBOLS = 958  # 5 x 182 symbols + 4 x 12 silent symbols
BURST_BYTES = 120  # BURST_SYMBOLS rounded up; the pad bits are silence
_REPEATS = 5
_GAP_SYMBOLS = 12


@dataclass(frozen=True)
class State:
    """What the fireplace should be doing. Every frame carries all of it.

    There is no thermostat field: that bit is always 0, because that mode relies on the
    remote's own temperature sensor.
    """

    pilot: bool = True
    light: int = 0
    power: bool = False
    front: bool = True
    fan: int = 0
    aux: bool = False
    flame: int = 1


@dataclass(frozen=True)
class Identity:
    """The remote being imitated. The checksum constants differ between remotes."""

    serial: int
    err1_c: int
    err1_d: int
    err2_c: int
    err2_d: int


def cmd1_byte(state: State) -> int:
    return (0x80 if state.pilot else 0) | (state.light & 0x07) << 4 | (1 if state.power else 0)


def cmd2_byte(state: State) -> int:
    return (
        (0x80 if state.front else 0)
        | (state.fan & 0x07) << 4
        | (0x08 if state.aux else 0)
        | (state.flame & 0x07)
    )


def state_from_command_bytes(cmd1: int, cmd2: int) -> State:
    """Rebuilds a state from saved command bytes. The thermostat bit is never restored."""
    light, fan, flame = (cmd1 >> 4) & 0x07, (cmd2 >> 4) & 0x07, cmd2 & 0x07
    if max(light, fan, flame) > MAX_LEVEL:
        raise ValueError("level out of range")
    return State(
        pilot=bool(cmd1 & 0x80),
        light=light,
        power=bool(cmd1 & 0x01),
        front=bool(cmd2 & 0x80),
        fan=fan,
        aux=bool(cmd2 & 0x08),
        flame=flame,
    )


def err_byte(cmd: int, c: int, d: int) -> int:
    a, b = cmd >> 4, cmd & 0x0F
    high = (c ^ (a << 1) ^ a ^ (b << 1)) & 0x0F
    low = (d ^ a ^ b) & 0x0F
    return high << 4 | low


def build_payload(identity: Identity, state: State) -> bytes:
    """serial[3], cmd1, cmd2, err1, err2"""
    cmd1, cmd2 = cmd1_byte(state), cmd2_byte(state)
    return bytes(
        (
            (identity.serial >> 16) & 0xFF,
            (identity.serial >> 8) & 0xFF,
            identity.serial & 0xFF,
            cmd1,
            cmd2,
            err_byte(cmd1, identity.err1_c, identity.err1_d),
            err_byte(cmd2, identity.err2_c, identity.err2_d),
        )
    )


def _bit_symbols(value: int) -> list[int]:
    # The remote's Manchester variant: 1 is on-off, 0 is off-on.
    return [1, 0] if value else [0, 1]


def _word_symbols(data: int, pad: bool) -> list[int]:
    # Sync, start guard, 8 data bits, pad, parity, end guard: 26 symbols.
    symbols = [1, 1] + _bit_symbols(1)
    for shift in range(7, -1, -1):
        symbols += _bit_symbols((data >> shift) & 1)
    symbols += _bit_symbols(int(pad))
    symbols += _bit_symbols(bin(data << 1 | int(pad)).count("1") & 1)
    return symbols + _bit_symbols(1)


def encode_burst(payload: bytes) -> bytes:
    """Packs symbols MSB first, the order the CC1101 clocks them out."""
    symbols: list[int] = []
    for repeat in range(_REPEATS):
        for index, word in enumerate(payload):
            symbols += _word_symbols(word, index == 0)
        if repeat + 1 < _REPEATS:
            symbols += [0] * _GAP_SYMBOLS
    burst = bytearray(BURST_BYTES)
    for position, symbol in enumerate(symbols):
        if symbol:
            burst[position // 8] |= 0x80 >> (position % 8)
    return bytes(burst)
