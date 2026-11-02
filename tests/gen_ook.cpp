// Prints a burst as an rtl_433 pulse file: gen_ook <serial> <cmd1> <cmd2> <c1> <d1> <c2> <d2>
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

  const int symbolUs = 417;
  puts(";pulse data\n;version 1\n;timescale 1us\n;ook 1 pulses");
  int on = 0;
  int off = 0;
  for (size_t i = 0; i < kBurstSymbols; i++) {
    const bool high = burst[i / 8] & (0x80 >> (i % 8));
    if (high && off) {
      printf("%d %d\n", on * symbolUs, off * symbolUs);
      on = off = 0;
    }
    if (high) on++;
    else off++;
  }
  printf("%d %d\n;end\n", on * symbolUs, (off + 40) * symbolUs);
  return 0;
}
