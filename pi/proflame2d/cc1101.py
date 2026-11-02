"""Minimal CC1101 transmit driver: fixed-length OOK packets at 2400 symbols/s.

Python port of libraries/Proflame2/src/Cc1101Ook.cpp, over spidev. The radio times the
symbols, so a busy Pi can't disturb the frame as long as the FIFO is kept filled.
"""
import time
from typing import Callable, Protocol

PA_LEVELS = {"low": 0x34, "mid": 0x51, "high": 0xC2}  # about -10, 0 and +10 dBm at 315 MHz

DEFAULT_FREQUENCY_KHZ = 314973

_BURST = 0x40
_READ = 0x80

_REG_PKTLEN = 0x06
_REG_FREQ2 = 0x0D
_REG_FREQ1 = 0x0E
_REG_FREQ0 = 0x0F
_REG_PATABLE = 0x3E
_REG_FIFO = 0x3F

_STROBE_RESET = 0x30
_STROBE_TX = 0x35
_STROBE_IDLE = 0x36
_STROBE_FLUSH_TX = 0x3B

_STATUS_PARTNUM = 0x30
_STATUS_VERSION = 0x31
_STATUS_MARCSTATE = 0x35
_STATUS_TXBYTES = 0x3A

_MARC_IDLE = 0x01
_TX_UNDERFLOW = 0x80
_FIFO_SIZE = 64
_CRYSTAL_HZ = 26_000_000
_TRANSMIT_TIMEOUT_S = 1.5
_SPI_HZ = 500_000

_CONFIG = (
    (0x00, 0x2E),  # IOCFG2: GDO2 high impedance
    (0x02, 0x2E),  # IOCFG0: GDO0 high impedance (it defaults to a clock output)
    (0x07, 0x00),  # PKTCTRL1: no address check, no status bytes
    (0x08, 0x00),  # PKTCTRL0: fixed length, no CRC, no whitening
    (0x0B, 0x06),  # FSCTRL1
    (0x10, 0xF6),  # MDMCFG4: DRATE_E = 6
    (0x11, 0x83),  # MDMCFG3: DRATE_M = 131, 2399 symbols/s
    (0x12, 0x30),  # MDMCFG2: OOK, no preamble, no sync word
    (0x13, 0x00),  # MDMCFG1
    (0x14, 0xF8),  # MDMCFG0
    (0x17, 0x00),  # MCSM1: back to idle after TX
    (0x18, 0x18),  # MCSM0: calibrate on the way out of idle
    (0x21, 0x56),  # FREND1
    (0x22, 0x11),  # FREND0: symbol 1 uses PATABLE[1], symbol 0 uses PATABLE[0]
    (0x23, 0xEA),  # FSCAL3
    (0x24, 0x2A),  # FSCAL2
    (0x25, 0x00),  # FSCAL1
    (0x26, 0x1F),  # FSCAL0
)


class Spi(Protocol):
    def xfer2(self, data: list[int]) -> list[int]: ...


def open_spi(bus: int, device: int) -> Spi:
    import spidev  # only on the Pi; tests pass in a fake

    spi = spidev.SpiDev()
    spi.open(bus, device)
    spi.max_speed_hz = _SPI_HZ
    spi.mode = 0
    return spi


class Cc1101:
    def __init__(
        self,
        spi: Spi,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._spi = spi
        self._sleep = sleep
        self._clock = clock
        self.present = False
        self.version = 0

    def begin(self, frequency_khz: int = DEFAULT_FREQUENCY_KHZ, power: str = "low") -> bool:
        """Returns False if no CC1101 answers."""
        self.present = False
        self._strobe(_STROBE_RESET)
        self._sleep(0.005)
        part = self._read_status(_STATUS_PARTNUM)
        self.version = self._read_status(_STATUS_VERSION)
        if part != 0x00 or self.version in (0x00, 0xFF):
            return False
        for address, value in _CONFIG:
            self._write_register(address, value)
        self._set_frequency_khz(frequency_khz)
        self._spi.xfer2([_REG_PATABLE | _BURST, 0x00, PA_LEVELS[power]])  # symbol 0 stays silent
        self._abort_tx()
        self.present = True
        return True

    def transmit(self, data: bytes) -> bool:
        """Blocks for the time on air, about 400 ms. Leaves the radio idle, carrier off."""
        if not self.present or not 0 < len(data) <= 255:
            return False
        self._abort_tx()
        self._write_register(_REG_PKTLEN, len(data))

        sent = min(len(data), _FIFO_SIZE)
        self._write_fifo(data[:sent])
        self._strobe(_STROBE_TX)

        start = self._clock()
        while self._clock() - start < _TRANSMIT_TIMEOUT_S:
            if sent < len(data):
                queued = self._read_tx_bytes()
                if queued & _TX_UNDERFLOW:
                    break
                room = _FIFO_SIZE - queued
                if room >= 8:
                    chunk = data[sent : sent + room]
                    self._write_fifo(chunk)
                    sent += len(chunk)
            elif self._read_status(_STATUS_MARCSTATE) & 0x1F == _MARC_IDLE:
                return True
            self._sleep(0.005)

        self._abort_tx()
        return False

    def _set_frequency_khz(self, khz: int) -> None:
        if not 300_000 <= khz <= 348_000:
            raise ValueError("frequency must be 300000-348000 kHz")
        word = (khz * 1000 * 65536 + _CRYSTAL_HZ // 2) // _CRYSTAL_HZ
        self._write_register(_REG_FREQ2, (word >> 16) & 0xFF)
        self._write_register(_REG_FREQ1, (word >> 8) & 0xFF)
        self._write_register(_REG_FREQ0, word & 0xFF)

    def _strobe(self, command: int) -> None:
        self._spi.xfer2([command])

    def _write_register(self, address: int, value: int) -> None:
        self._spi.xfer2([address, value])

    def _read_status(self, address: int) -> int:
        return self._spi.xfer2([address | _READ | _BURST, 0])[1]

    def _read_tx_bytes(self) -> int:
        # TI errata: this counter can misread if it changes during the SPI read, so read
        # until two values agree.
        previous = self._read_status(_STATUS_TXBYTES)
        for _ in range(8):
            current = self._read_status(_STATUS_TXBYTES)
            if current == previous:
                break
            previous = current
        return previous

    def _write_fifo(self, data: bytes) -> None:
        self._spi.xfer2([_REG_FIFO | _BURST, *data])

    def _abort_tx(self) -> None:
        self._strobe(_STROBE_IDLE)
        self._strobe(_STROBE_FLUSH_TX)
