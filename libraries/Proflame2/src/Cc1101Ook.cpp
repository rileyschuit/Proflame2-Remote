#include "Cc1101Ook.h"

#include <SPI.h>

namespace proflame2 {

namespace {

// 500 kHz keeps the Uno's BSS138 level shifter well inside its limits, and the
// FIFO only needs 300 bytes/s.
const SPISettings kSpi(500000, MSBFIRST, SPI_MODE0);

const uint8_t kBurstFlag = 0x40;
const uint8_t kReadFlag = 0x80;

const uint8_t kRegPktLen = 0x06;
const uint8_t kRegFreq2 = 0x0D;
const uint8_t kRegFreq1 = 0x0E;
const uint8_t kRegFreq0 = 0x0F;
const uint8_t kRegPaTable = 0x3E;
const uint8_t kRegFifo = 0x3F;

const uint8_t kStrobeReset = 0x30;
const uint8_t kStrobeTx = 0x35;
const uint8_t kStrobeIdle = 0x36;
const uint8_t kStrobeFlushTx = 0x3B;

const uint8_t kStatusPartNum = 0x30;
const uint8_t kStatusVersion = 0x31;
const uint8_t kStatusMarcState = 0x35;
const uint8_t kStatusTxBytes = 0x3A;

const uint8_t kMarcIdle = 0x01;
const uint8_t kTxUnderflowFlag = 0x80;
const uint8_t kFifoSize = 64;
const uint32_t kCrystalHz = 26000000UL;
const uint32_t kTransmitTimeoutMs = 1500;

const uint8_t kConfig[][2] = {
    {0x00, 0x2E},  // IOCFG2: GDO2 high impedance
    {0x02, 0x2E},  // IOCFG0: GDO0 high impedance (it defaults to a clock output)
    {0x07, 0x00},  // PKTCTRL1: no address check, no status bytes
    {0x08, 0x00},  // PKTCTRL0: fixed length, no CRC, no whitening
    {0x0B, 0x06},  // FSCTRL1
    {0x10, 0xF6},  // MDMCFG4: DRATE_E = 6
    {0x11, 0x83},  // MDMCFG3: DRATE_M = 131, 2399 symbols/s
    {0x12, 0x30},  // MDMCFG2: OOK, no preamble, no sync word
    {0x13, 0x00},  // MDMCFG1
    {0x14, 0xF8},  // MDMCFG0
    {0x17, 0x00},  // MCSM1: back to idle after TX
    {0x18, 0x18},  // MCSM0: calibrate on the way out of idle
    {0x21, 0x56},  // FREND1
    {0x22, 0x11},  // FREND0: symbol 1 uses PATABLE[1], symbol 0 uses PATABLE[0]
    {0x23, 0xEA},  // FSCAL3
    {0x24, 0x2A},  // FSCAL2
    {0x25, 0x00},  // FSCAL1
    {0x26, 0x1F},  // FSCAL0
};

}  // namespace

void Cc1101Ook::select() {
  SPI.beginTransaction(kSpi);
  digitalWrite(csn_, LOW);
  delayMicroseconds(20);  // the radio's crystal is stable well within this when idle
}

void Cc1101Ook::deselect() {
  digitalWrite(csn_, HIGH);
  SPI.endTransaction();
}

uint8_t Cc1101Ook::strobe(uint8_t command) {
  select();
  const uint8_t status = SPI.transfer(command);
  deselect();
  return status;
}

void Cc1101Ook::writeRegister(uint8_t address, uint8_t value) {
  select();
  SPI.transfer(address);
  SPI.transfer(value);
  deselect();
}

uint8_t Cc1101Ook::readStatus(uint8_t address) {
  select();
  SPI.transfer(address | kReadFlag | kBurstFlag);
  const uint8_t value = SPI.transfer(0);
  deselect();
  return value;
}

// TI errata: this counter can misread if it changes during the SPI read, so
// read until two values agree.
uint8_t Cc1101Ook::readTxBytes() {
  uint8_t previous = readStatus(kStatusTxBytes);
  for (uint8_t attempt = 0; attempt < 8; attempt++) {
    const uint8_t current = readStatus(kStatusTxBytes);
    if (current == previous) break;
    previous = current;
  }
  return previous;
}

void Cc1101Ook::writeFifo(const uint8_t* data, size_t length) {
  select();
  SPI.transfer(kRegFifo | kBurstFlag);
  for (size_t i = 0; i < length; i++) SPI.transfer(data[i]);
  deselect();
}

void Cc1101Ook::abortTx() {
  strobe(kStrobeIdle);
  strobe(kStrobeFlushTx);
}

bool Cc1101Ook::begin() {
  pinMode(csn_, OUTPUT);
  digitalWrite(csn_, HIGH);
  delay(1);

  strobe(kStrobeReset);
  delay(5);

  const uint8_t part = readStatus(kStatusPartNum);
  version_ = readStatus(kStatusVersion);
  present_ = part == 0x00 && version_ != 0x00 && version_ != 0xFF;
  if (!present_) return false;

  for (size_t i = 0; i < sizeof(kConfig) / sizeof(kConfig[0]); i++) {
    writeRegister(kConfig[i][0], kConfig[i][1]);
  }
  setFrequencyKhz(kDefaultFrequencyKhz);
  setPaLevel(kPaMid);
  abortTx();
  return true;
}

bool Cc1101Ook::setFrequencyKhz(uint32_t khz) {
  if (khz < 300000UL || khz > 348000UL) return false;
  const uint64_t word =
      (static_cast<uint64_t>(khz) * 1000ULL * 65536ULL + kCrystalHz / 2) / kCrystalHz;
  writeRegister(kRegFreq2, static_cast<uint8_t>(word >> 16));
  writeRegister(kRegFreq1, static_cast<uint8_t>(word >> 8));
  writeRegister(kRegFreq0, static_cast<uint8_t>(word));
  return true;
}

void Cc1101Ook::setPaLevel(uint8_t level) {
  select();
  SPI.transfer(kRegPaTable | kBurstFlag);
  SPI.transfer(0x00);  // symbol 0 must stay silent
  SPI.transfer(level);
  deselect();
}

bool Cc1101Ook::transmit(const uint8_t* data, size_t length) {
  if (!present_ || length == 0 || length > 255) return false;

  abortTx();
  writeRegister(kRegPktLen, static_cast<uint8_t>(length));

  size_t sent = length < kFifoSize ? length : kFifoSize;
  writeFifo(data, sent);
  strobe(kStrobeTx);

  const uint32_t start = millis();
  while (millis() - start < kTransmitTimeoutMs) {
    if (sent < length) {
      const uint8_t queued = readTxBytes();
      if (queued & kTxUnderflowFlag) break;
      const uint8_t room = kFifoSize - queued;
      if (room >= 8) {
        const size_t chunk = length - sent < room ? length - sent : room;
        writeFifo(data + sent, chunk);
        sent += chunk;
      }
    } else if ((readStatus(kStatusMarcState) & 0x1F) == kMarcIdle) {
      return true;
    }
    delay(5);
  }

  abortTx();
  return false;
}

}  // namespace proflame2
