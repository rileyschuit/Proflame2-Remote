// Fireplace state, command handling and the auto-off timer. Radio and clock
// come in from the caller, so tests/ can run this on a PC too.
#pragma once

#include "Proflame2Frame.h"

namespace proflame2 {

const uint16_t kDefaultAutoOffMinutes = 240;
const uint16_t kMaxAutoOffMinutes = 720;

// Off, lowest flame, light and fan off. Pilot and front match the 11-02 capture.
const FireplaceState kBootState = {true, 0, false, false, true, 0, false, 1};

typedef bool (*TransmitFn)(const uint8_t* burst, size_t length);

enum class SetResult : uint8_t { kOk, kUnknownField, kBadValue };

// Changes one user-settable field. thermostat is left out on purpose.
SetResult setField(FireplaceState& state, const char* name, int value);

class Controller {
 public:
  Controller(const RemoteIdentity& remote, TransmitFn transmit);

  // Restores saved state after a reboot without transmitting. A fireplace that
  // was on gets a fresh auto-off timer.
  void restore(const FireplaceState& state, uint32_t nowMs);

  // Takes a validated state. tick() sends it.
  void commit(const FireplaceState& next, uint32_t nowMs);
  void off(uint32_t nowMs);
  void resend() { dirty_ = true; }

  // Call often. Sends pending frames and enforces the auto-off timer.
  // Returns true if it attempted a transmission.
  bool tick(uint32_t nowMs);

  const FireplaceState& state() const { return state_; }
  const RemoteIdentity& remote() const { return remote_; }
  void setSerial(uint32_t serial) { remote_.serial = serial & 0xFFFFFF; }
  void useRealSerial() { remote_.serial = realSerial_; }

  bool setAutoOffMinutes(uint16_t minutes, uint32_t nowMs);
  uint16_t autoOffMinutes() const { return autoOffMinutes_; }
  uint32_t autoOffRemainingMs(uint32_t nowMs) const;
  bool lastTransmitOk() const { return lastTransmitOk_; }

 private:
  void armTimer(uint32_t nowMs);
  bool send(uint32_t nowMs);

  RemoteIdentity remote_;
  uint32_t realSerial_;
  TransmitFn transmit_;
  FireplaceState state_;
  uint16_t autoOffMinutes_;
  bool timerRunning_;
  uint32_t timerStartMs_;
  bool dirty_;
  bool sentOnce_;
  uint32_t lastSendMs_;
  uint8_t offResends_;
  bool lastTransmitOk_;
};

}  // namespace proflame2
