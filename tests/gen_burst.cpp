// Prints a burst as hex, to compare the C++ and Python encoders:
// gen_burst <serial> <cmd1> <cmd2> <c1> <d1> <c2> <d2>
#include <cstdio>
#include <cstdlib>

#include "Proflame2Frame.h"

using namespace proflame2;

int main(int argc, char** argv) {
  if (argc != 8) return 2;
  const RemoteIdentity remote = {
      static_cast<uint32_t>(strtoul(argv[1], nullptr, 0)),
      static_cast<uint8_t>(strtoul(argv[4], nullptr, 0)),
      static_cast<uint8_t>(strtoul(argv[5], nullptr, 0)),
      static_cast<uint8_t>(strtoul(argv[6], nullptr, 0)),
      static_cast<uint8_t>(strtoul(argv[7], nullptr, 0))};
  FireplaceState state;
  if (!stateFromCommandBytes(strtoul(argv[2], nullptr, 0), strtoul(argv[3], nullptr, 0), state)) {
    return 3;
  }
  uint8_t payload[kPayloadBytes];
  uint8_t burst[kBurstBytes];
  buildPayload(remote, state, payload);
  encodeBurst(payload, burst);
  for (size_t i = 0; i < kBurstBytes; i++) printf("%02x", burst[i]);
  puts("");
  return 0;
}
