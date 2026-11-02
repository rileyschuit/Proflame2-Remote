// Host tests for the frame encoder and controller. Run with: make test
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>

#include "Proflame2Controller.h"
#include "Proflame2Frame.h"

using namespace proflame2;

static const RemoteIdentity kRiley = {0xA00402, 0x0, 0xC, 0xA, 0x4};

static std::string symbols(const uint8_t* burst, size_t first, size_t count) {
  std::string out;
  for (size_t i = first; i < first + count; i++) {
    out += (burst[i / 8] & (0x80 >> (i % 8))) ? '1' : '0';
  }
  return out;
}

// Frames rtl_433 decoded from the real remote on 2026-11-02.
static void testCapturedChecksums() {
  assert(errByte(128, kRiley.err1C, kRiley.err1D) == 132);
  assert(errByte(129, kRiley.err1C, kRiley.err1D) == 165);
  assert(errByte(166, kRiley.err2C, kRiley.err2D) == 136);
  assert(errByte(38, kRiley.err2C, kRiley.err2D) == 0);
}

static void testCapturedStateBytes() {
  FireplaceState s = {true, 0, false, false, true, 2, false, 6};
  assert(cmd1Byte(s) == 128);
  assert(cmd2Byte(s) == 166);
  s.power = true;
  assert(cmd1Byte(s) == 129);
  s.front = false;
  assert(cmd2Byte(s) == 38);
}

// The worked example in johnellinwood/smartfire's README, on-air bits and all.
static void testPublishedBitString() {
  const uint8_t payload[kPayloadBytes] = {0x25, 0x7A, 0x02, 0x51, 0xE2, 0x04, 0x6B};
  uint8_t burst[kBurstBytes];
  encodeBurst(payload, burst);
  const std::string expected =
      "11100101100101100110100110111001101010100110010110101110010101010101100101101011"
      "10011001100101011001101011101010100101011001010110111001010101011001010110101110"
      "011010011001101001101";
  const std::string actual = symbols(burst, 0, expected.size());
  if (actual != expected) {
    printf("expected %s\nactual   %s\n", expected.c_str(), actual.c_str());
  }
  assert(actual == expected);
}

static void testBurstLayout() {
  uint8_t payload[kPayloadBytes];
  uint8_t burst[kBurstBytes];
  const FireplaceState s = {true, 3, false, true, true, 2, false, 6};
  buildPayload(kRiley, s, payload);
  encodeBurst(payload, burst);
  const std::string first = symbols(burst, 0, 182);
  for (size_t repeat = 1; repeat < 5; repeat++) {
    assert(symbols(burst, repeat * (182 + 12) - 12, 12) == std::string(12, '0'));
    assert(symbols(burst, repeat * (182 + 12), 182) == first);
  }
  assert(symbols(burst, kBurstSymbols, kBurstBytes * 8 - kBurstSymbols) ==
         std::string(kBurstBytes * 8 - kBurstSymbols, '0'));
}

static void testStateRoundTrip() {
  for (int c1 = 0; c1 < 256; c1++) {
    if (c1 & 0x0E) continue;
    for (int c2 = 0; c2 < 256; c2++) {
      FireplaceState s;
      const bool valid = ((c1 >> 4) & 7) <= 6 && ((c2 >> 4) & 7) <= 6 && (c2 & 7) <= 6;
      assert(stateFromCommandBytes(c1, c2, s) == valid);
      if (valid) {
        assert(cmd1Byte(s) == c1);
        assert(cmd2Byte(s) == c2);
      }
    }
  }
  FireplaceState s;
  assert(stateFromCommandBytes(0x02, 0x00, s));
  assert(!s.thermostat);
}

static void testSetField() {
  FireplaceState s = kBootState;
  assert(setField(s, "flame", 6) == SetResult::kOk && s.flame == 6);
  assert(setField(s, "flame", 7) == SetResult::kBadValue && s.flame == 6);
  assert(setField(s, "fan", -1) == SetResult::kBadValue);
  assert(setField(s, "power", 2) == SetResult::kBadValue);
  assert(setField(s, "thermostat", 1) == SetResult::kUnknownField);
  assert(setField(s, "nonsense", 1) == SetResult::kUnknownField);
}

static int sends;
static uint8_t lastBurst[kBurstBytes];
static bool radioWorks;

static bool fakeTransmit(const uint8_t* burst, size_t length) {
  assert(length == kBurstBytes);
  memcpy(lastBurst, burst, length);
  sends++;
  return radioWorks;
}

static void resetRadio() {
  sends = 0;
  radioWorks = true;
}

static bool lastBurstHasPower(bool power) {
  uint8_t payload[kPayloadBytes];
  uint8_t expected[kBurstBytes];
  FireplaceState s = kBootState;
  s.power = power;
  buildPayload(kRiley, s, payload);
  encodeBurst(payload, expected);
  return memcmp(expected, lastBurst, kBurstBytes) == 0;
}

static void testNothingSentAtBoot() {
  resetRadio();
  Controller c(kRiley, fakeTransmit);
  for (uint32_t t = 0; t < 60000; t += 100) c.tick(t);
  assert(sends == 0);
  assert(!c.state().power);
}

static void testRestoreDoesNotTransmitButArmsTimer() {
  resetRadio();
  Controller c(kRiley, fakeTransmit);
  FireplaceState on = kBootState;
  on.power = true;
  c.restore(on, 1000);
  assert(c.autoOffRemainingMs(1000) == kDefaultAutoOffMinutes * 60000UL);
  for (uint32_t t = 1000; t < 60000; t += 100) c.tick(t);
  assert(sends == 0);
}

static void testAutoOffFiresAndRepeats() {
  resetRadio();
  Controller c(kRiley, fakeTransmit);
  assert(c.setAutoOffMinutes(1, 0));
  FireplaceState on = kBootState;
  on.power = true;
  c.commit(on, 0);
  c.tick(0);
  assert(sends == 1 && lastBurstHasPower(true));
  c.tick(59999);
  assert(sends == 1 && c.state().power);
  c.tick(60000);
  assert(sends == 2 && !c.state().power && lastBurstHasPower(false));
  c.tick(61000);
  assert(sends == 2);
  c.tick(62000);
  assert(sends == 3 && lastBurstHasPower(false));
  c.tick(64000);
  assert(sends == 4);
  for (uint32_t t = 64000; t < 200000; t += 500) c.tick(t);
  assert(sends == 4);
}

static void testTimerSurvivesMillisRollover() {
  resetRadio();
  Controller c(kRiley, fakeTransmit);
  c.setAutoOffMinutes(1, 0);
  const uint32_t start = 0xFFFFFFFFUL - 1000;
  FireplaceState on = kBootState;
  on.power = true;
  c.commit(on, start);
  c.tick(start);
  c.tick(start + 30000);
  assert(c.state().power);
  c.tick(start + 60000);
  assert(!c.state().power);
}

static void testLevelChangeDoesNotExtendTimer() {
  resetRadio();
  Controller c(kRiley, fakeTransmit);
  c.setAutoOffMinutes(10, 0);
  FireplaceState s = kBootState;
  s.power = true;
  c.commit(s, 0);
  s.flame = 4;
  c.commit(s, 300000);
  assert(c.autoOffRemainingMs(300000) == 300000);
}

static void testOffStopsTimerAndCoalesces() {
  resetRadio();
  Controller c(kRiley, fakeTransmit);
  FireplaceState s = kBootState;
  s.power = true;
  c.commit(s, 0);
  c.tick(0);
  assert(sends == 1);
  s.flame = 2;
  c.commit(s, 100);
  s.flame = 3;
  c.commit(s, 200);
  c.tick(200);
  assert(sends == 1);
  c.tick(500);
  assert(sends == 2);
  c.off(600);
  assert(c.autoOffRemainingMs(600) == 0);
}

static void testTimerRange() {
  Controller c(kRiley, fakeTransmit);
  assert(!c.setAutoOffMinutes(0, 0));
  assert(!c.setAutoOffMinutes(kMaxAutoOffMinutes + 1, 0));
  assert(c.setAutoOffMinutes(kMaxAutoOffMinutes, 0));
}

static void testFailureIsReported() {
  resetRadio();
  radioWorks = false;
  Controller c(kRiley, fakeTransmit);
  c.off(0);
  c.tick(0);
  assert(!c.lastTransmitOk());
}

static void testTestSerialAndBack() {
  Controller c(kRiley, fakeTransmit);
  c.setSerial(0x123456);
  assert(c.remote().serial == 0x123456);
  c.useRealSerial();
  assert(c.remote().serial == kRiley.serial);
}

static void testOffUsesRealSerial() {
  resetRadio();
  Controller c(kRiley, fakeTransmit);
  FireplaceState s = kBootState;
  s.power = true;
  c.commit(s, 0);
  c.setSerial(0x123456);
  c.off(1000);
  assert(c.remote().serial == kRiley.serial);
  c.tick(1000);
  assert(lastBurstHasPower(false));
}

static void testTestSerialSurvivesLevelChangesWhileOff() {
  Controller c(kRiley, fakeTransmit);
  c.setSerial(0x123456);
  FireplaceState s = kBootState;
  s.flame = 3;
  c.commit(s, 0);
  assert(c.remote().serial == 0x123456);
}

static void testFailedOffKeepsRetrying() {
  resetRadio();
  radioWorks = false;
  Controller c(kRiley, fakeTransmit);
  FireplaceState s = kBootState;
  s.power = true;
  c.commit(s, 0);
  c.tick(0);
  c.off(1000);
  c.tick(1000);
  const int afterFirstOff = sends;
  for (uint32_t t = 1000; t < 11000; t += 100) c.tick(t);
  assert(sends >= afterFirstOff + 4);
  radioWorks = true;
  for (uint32_t t = 11000; t < 14000; t += 100) c.tick(t);
  assert(c.lastTransmitOk());
  const int settled = sends;
  for (uint32_t t = 14000; t < 30000; t += 100) c.tick(t);
  assert(sends == settled);
}

int main() {
  testCapturedChecksums();
  testCapturedStateBytes();
  testPublishedBitString();
  testBurstLayout();
  testStateRoundTrip();
  testSetField();
  testNothingSentAtBoot();
  testRestoreDoesNotTransmitButArmsTimer();
  testAutoOffFiresAndRepeats();
  testTimerSurvivesMillisRollover();
  testLevelChangeDoesNotExtendTimer();
  testOffStopsTimerAndCoalesces();
  testTimerRange();
  testFailureIsReported();
  testTestSerialAndBack();
  testOffUsesRealSerial();
  testTestSerialSurvivesLevelChangesWhileOff();
  testFailedOffKeepsRetrying();
  puts("all host tests passed");
  return 0;
}
