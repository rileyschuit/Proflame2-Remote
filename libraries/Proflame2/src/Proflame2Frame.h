// Proflame 2 on-air frame: state -> command bytes -> checksums -> symbols.
// No Arduino dependencies, so tests/ can run it on a PC.
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace proflame2 {

const uint8_t kMaxLevel = 6;
const size_t kPayloadBytes = 7;
const size_t kBurstSymbols = 958;  // 5 x 182 symbols + 4 x 12 silent symbols
const size_t kBurstBytes = 120;    // kBurstSymbols rounded up; the pad bits are silence

// What the fireplace should be doing. Every frame carries all of it.
struct FireplaceState {
  bool pilot;       // true = continuous pilot (CPI), false = intermittent (IPI)
  uint8_t light;    // 0-6
  bool thermostat;  // always false here: the remote's own sensor runs that mode
  bool power;
  bool front;  // front burner, the "show" setting
  uint8_t fan;  // 0-6
  bool aux;
  uint8_t flame;  // 0-6
};

// The remote being imitated. The checksum constants differ between remotes.
struct RemoteIdentity {
  uint32_t serial;  // 24 bits
  uint8_t err1C, err1D;
  uint8_t err2C, err2D;
};

uint8_t cmd1Byte(const FireplaceState& state);
uint8_t cmd2Byte(const FireplaceState& state);
// Rebuilds a state from saved command bytes. Returns false if a level is out of
// range. The thermostat bit is never restored.
bool stateFromCommandBytes(uint8_t cmd1, uint8_t cmd2, FireplaceState& state);
uint8_t errByte(uint8_t cmd, uint8_t c, uint8_t d);

// serial[3], cmd1, cmd2, err1, err2
void buildPayload(const RemoteIdentity& remote, const FireplaceState& state,
                  uint8_t payload[kPayloadBytes]);

// Packs symbols MSB first, the order the CC1101 clocks them out.
void encodeBurst(const uint8_t payload[kPayloadBytes], uint8_t burst[kBurstBytes]);

}  // namespace proflame2
