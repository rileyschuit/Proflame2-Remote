import pytest

from proflame2d.cc1101 import Cc1101


class FakeChip:
    """Models the CC1101's SPI surface: registers, FIFO, and draining at 2400 symbols/s."""

    FIFO_SIZE = 64
    BYTES_PER_S = 300

    def __init__(self, clock, part=0x00, version=0x14, stall=False):
        self.clock = clock
        self.part, self.version = part, version
        self.registers = {}
        self.patable = []
        self.fifo = bytearray()
        self.aired = bytearray()
        self.transmitting = False
        self.stall = stall
        self._credit = 0.0
        self._last = clock()
        self.underflowed = False

    def _advance(self):
        now = self.clock()
        if self.transmitting and not self.stall:
            self._credit += (now - self._last) * self.BYTES_PER_S
            while self._credit >= 1 and self.transmitted < self.registers.get(0x06, 0):
                self._credit -= 1
                if not self.fifo:
                    self.underflowed = True
                    return
                self.aired.append(self.fifo.pop(0))
            if self.transmitted >= self.registers.get(0x06, 0):
                self.transmitting = False
        self._last = now

    @property
    def transmitted(self):
        return len(self.aired)

    def xfer2(self, data):
        self._advance()
        first = data[0]
        if len(data) == 1:
            if first == 0x35:
                self.transmitting = True
                self.aired = bytearray()
                self._credit = 0.0
            elif first == 0x36:
                self.transmitting = False
            elif first == 0x3B:
                self.fifo = bytearray()
            return [0]
        if first & 0x80:
            status = first & 0x3F
            value = {
                0x30: self.part,
                0x31: self.version,
                0x35: 0x13 if self.transmitting else 0x01,
                0x3A: len(self.fifo) | (0x80 if self.underflowed else 0),
            }[status]
            return [0, value]
        if first == 0x7F:
            self.fifo.extend(data[1:])
            assert len(self.fifo) <= self.FIFO_SIZE, "FIFO overflow"
            return [0] * len(data)
        if first == 0x7E:
            self.patable = data[1:]
            return [0] * len(data)
        self.registers[first] = data[1]
        return [0, 0]


def make(clock, **kwargs):
    chip = FakeChip(clock, **kwargs)
    return chip, Cc1101(chip, sleep=clock.advance, clock=clock)


def test_begin_configures_ook_at_the_frequency_and_power(clock):
    chip, radio = make(clock)
    assert radio.begin(314973, "low") is True
    assert radio.present and radio.version == 0x14
    assert chip.registers[0x12] == 0x30  # OOK, no preamble, no sync word
    word = chip.registers[0x0D] << 16 | chip.registers[0x0E] << 8 | chip.registers[0x0F]
    assert word * 26_000_000 / 65536 == pytest.approx(314_973_000, abs=400)
    assert chip.patable == [0x00, 0x34]  # symbol 0 must stay silent


@pytest.mark.parametrize("kwargs", [{"version": 0x00}, {"version": 0xFF}, {"part": 0x12}])
def test_begin_reports_a_missing_chip(clock, kwargs):
    _, radio = make(clock, **kwargs)
    assert radio.begin() is False
    assert radio.present is False


def test_begin_refuses_a_bad_frequency(clock):
    _, radio = make(clock)
    with pytest.raises(ValueError):
        radio.begin(433920)


def test_transmit_refilled_fifo_airs_every_byte_in_order(clock):
    chip, radio = make(clock)
    radio.begin()
    data = bytes(range(120))
    assert radio.transmit(data) is True
    assert bytes(chip.aired) == data
    assert chip.underflowed is False
    assert chip.transmitting is False


def test_transmit_without_a_chip_is_refused(clock):
    _, radio = make(clock, version=0)
    radio.begin()
    assert radio.transmit(b"\x01") is False


def test_transmit_times_out_and_stops_the_carrier(clock):
    chip, radio = make(clock, stall=True)
    radio.begin()
    assert radio.transmit(bytes(120)) is False
    assert chip.transmitting is False
    assert len(chip.fifo) == 0
