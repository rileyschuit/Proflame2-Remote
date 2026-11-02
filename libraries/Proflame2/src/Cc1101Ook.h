// Minimal CC1101 transmit driver: fixed-length OOK packets at 2400 symbols/s.
// The radio times the symbols, so Wi-Fi and interrupts can't disturb the frame.
#pragma once

#include <Arduino.h>

namespace proflame2 {

// Nominal 315 MHz PATABLE values from TI's CC1101 power table.
const uint8_t kPaLow = 0x34;   // about -10 dBm
const uint8_t kPaMid = 0x51;   // about 0 dBm
const uint8_t kPaHigh = 0xC2;  // about +10 dBm

const uint32_t kDefaultFrequencyKhz = 314973;

class Cc1101Ook {
 public:
  explicit Cc1101Ook(uint8_t csnPin) : csn_(csnPin), present_(false), version_(0) {}

  // Call SPI.begin() first. Returns false if no CC1101 answers.
  bool begin();
  bool setFrequencyKhz(uint32_t khz);  // 300000-348000
  void setPaLevel(uint8_t level);

  // Blocks for the time on air, about 400 ms. Leaves the radio idle, carrier off.
  bool transmit(const uint8_t* data, size_t length);

  bool present() const { return present_; }
  uint8_t version() const { return version_; }

 private:
  void select();
  void deselect();
  uint8_t strobe(uint8_t command);
  void writeRegister(uint8_t address, uint8_t value);
  uint8_t readStatus(uint8_t address);
  uint8_t readTxBytes();
  void writeFifo(const uint8_t* data, size_t length);
  void abortTx();

  uint8_t csn_;
  bool present_;
  uint8_t version_;
};

}  // namespace proflame2
