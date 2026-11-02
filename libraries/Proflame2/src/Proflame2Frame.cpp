#include "Proflame2Frame.h"

#include <string.h>

namespace proflame2 {

namespace {

const uint8_t kRepeats = 5;
const uint8_t kGapSymbols = 12;

class SymbolWriter {
 public:
  explicit SymbolWriter(uint8_t* out) : out_(out), position_(0) {}

  void symbol(bool on) {
    if (on) out_[position_ / 8] |= static_cast<uint8_t>(0x80 >> (position_ % 8));
    position_++;
  }

  // The remote's Manchester variant: 1 is on-off, 0 is off-on.
  void bit(bool value) {
    symbol(value);
    symbol(!value);
  }

  void skip(size_t symbols) { position_ += symbols; }

 private:
  uint8_t* out_;
  size_t position_;
};

bool oddParity(uint16_t value) {
  bool odd = false;
  while (value) {
    odd = !odd;
    value &= static_cast<uint16_t>(value - 1);
  }
  return odd;
}

// Sync, start guard, 8 data bits, pad, parity, end guard: 26 symbols.
void writeWord(SymbolWriter& writer, uint8_t data, bool pad) {
  writer.symbol(true);
  writer.symbol(true);
  writer.bit(true);
  for (int8_t i = 7; i >= 0; i--) writer.bit((data >> i) & 1);
  writer.bit(pad);
  writer.bit(oddParity(static_cast<uint16_t>((data << 1) | (pad ? 1 : 0))));
  writer.bit(true);
}

}  // namespace

uint8_t cmd1Byte(const FireplaceState& state) {
  return static_cast<uint8_t>((state.pilot ? 0x80 : 0) | ((state.light & 0x07) << 4) |
                              (state.thermostat ? 0x02 : 0) | (state.power ? 0x01 : 0));
}

uint8_t cmd2Byte(const FireplaceState& state) {
  return static_cast<uint8_t>((state.front ? 0x80 : 0) | ((state.fan & 0x07) << 4) |
                              (state.aux ? 0x08 : 0) | (state.flame & 0x07));
}

bool stateFromCommandBytes(uint8_t cmd1, uint8_t cmd2, FireplaceState& state) {
  const uint8_t light = (cmd1 >> 4) & 0x07;
  const uint8_t fan = (cmd2 >> 4) & 0x07;
  const uint8_t flame = cmd2 & 0x07;
  if (light > kMaxLevel || fan > kMaxLevel || flame > kMaxLevel) return false;
  state.pilot = cmd1 & 0x80;
  state.light = light;
  state.thermostat = false;
  state.power = cmd1 & 0x01;
  state.front = cmd2 & 0x80;
  state.fan = fan;
  state.aux = cmd2 & 0x08;
  state.flame = flame;
  return true;
}

uint8_t errByte(uint8_t cmd, uint8_t c, uint8_t d) {
  const uint8_t a = cmd >> 4;
  const uint8_t b = cmd & 0x0F;
  const uint8_t high = (c ^ (a << 1) ^ a ^ (b << 1)) & 0x0F;
  const uint8_t low = (d ^ a ^ b) & 0x0F;
  return static_cast<uint8_t>((high << 4) | low);
}

void buildPayload(const RemoteIdentity& remote, const FireplaceState& state,
                  uint8_t payload[kPayloadBytes]) {
  payload[0] = static_cast<uint8_t>(remote.serial >> 16);
  payload[1] = static_cast<uint8_t>(remote.serial >> 8);
  payload[2] = static_cast<uint8_t>(remote.serial);
  payload[3] = cmd1Byte(state);
  payload[4] = cmd2Byte(state);
  payload[5] = errByte(payload[3], remote.err1C, remote.err1D);
  payload[6] = errByte(payload[4], remote.err2C, remote.err2D);
}

void encodeBurst(const uint8_t payload[kPayloadBytes], uint8_t burst[kBurstBytes]) {
  memset(burst, 0, kBurstBytes);
  SymbolWriter writer(burst);
  for (uint8_t repeat = 0; repeat < kRepeats; repeat++) {
    for (uint8_t word = 0; word < kPayloadBytes; word++) {
      writeWord(writer, payload[word], word == 0);
    }
    if (repeat + 1 < kRepeats) writer.skip(kGapSymbols);
  }
}

}  // namespace proflame2
