#include "Proflame2Controller.h"

#include <string.h>

namespace proflame2 {

namespace {

const uint32_t kMinSendGapMs = 500;      // a burst is on air for about 400 ms
const uint32_t kOffResendGapMs = 2000;
const uint8_t kOffResends = 2;  // there is no ACK path yet, so repeat the timed off

bool setLevel(uint8_t& field, int value) {
  if (value < 0 || value > kMaxLevel) return false;
  field = static_cast<uint8_t>(value);
  return true;
}

bool setFlag(bool& field, int value) {
  if (value != 0 && value != 1) return false;
  field = value == 1;
  return true;
}

}  // namespace

SetResult setField(FireplaceState& state, const char* name, int value) {
  bool ok;
  if (!strcmp(name, "power")) ok = setFlag(state.power, value);
  else if (!strcmp(name, "flame")) ok = setLevel(state.flame, value);
  else if (!strcmp(name, "fan")) ok = setLevel(state.fan, value);
  else if (!strcmp(name, "light")) ok = setLevel(state.light, value);
  else if (!strcmp(name, "front")) ok = setFlag(state.front, value);
  else if (!strcmp(name, "aux")) ok = setFlag(state.aux, value);
  else if (!strcmp(name, "pilot")) ok = setFlag(state.pilot, value);
  else return SetResult::kUnknownField;
  return ok ? SetResult::kOk : SetResult::kBadValue;
}

Controller::Controller(const RemoteIdentity& remote, TransmitFn transmit)
    : remote_(remote),
      realSerial_(remote.serial),
      transmit_(transmit),
      state_(kBootState),
      autoOffMinutes_(kDefaultAutoOffMinutes),
      timerRunning_(false),
      timerStartMs_(0),
      dirty_(false),
      sentOnce_(false),
      lastSendMs_(0),
      offResends_(0),
      lastTransmitOk_(true) {}

void Controller::armTimer(uint32_t nowMs) {
  timerRunning_ = true;
  timerStartMs_ = nowMs;
}

void Controller::restore(const FireplaceState& state, uint32_t nowMs) {
  state_ = state;
  if (state_.power) armTimer(nowMs);
}

void Controller::commit(const FireplaceState& next, uint32_t nowMs) {
  if (next.power && !state_.power) armTimer(nowMs);
  if (!next.power) timerRunning_ = false;
  // A real fireplace must hear this off, even if a test serial was left set.
  if (state_.power && !next.power) useRealSerial();
  else offResends_ = 0;
  state_ = next;
  dirty_ = true;
}

void Controller::off(uint32_t nowMs) {
  FireplaceState next = state_;
  next.power = false;
  commit(next, nowMs);
}

bool Controller::setAutoOffMinutes(uint16_t minutes, uint32_t nowMs) {
  if (minutes == 0 || minutes > kMaxAutoOffMinutes) return false;
  autoOffMinutes_ = minutes;
  if (timerRunning_) armTimer(nowMs);
  return true;
}

uint32_t Controller::autoOffRemainingMs(uint32_t nowMs) const {
  if (!timerRunning_) return 0;
  const uint32_t total = static_cast<uint32_t>(autoOffMinutes_) * 60000UL;
  const uint32_t elapsed = nowMs - timerStartMs_;
  return elapsed >= total ? 0 : total - elapsed;
}

bool Controller::send(uint32_t nowMs) {
  uint8_t payload[kPayloadBytes];
  uint8_t burst[kBurstBytes];
  buildPayload(remote_, state_, payload);
  encodeBurst(payload, burst);
  lastTransmitOk_ = transmit_(burst, kBurstBytes);
  lastSendMs_ = nowMs;
  sentOnce_ = true;
  // The radio refused an off frame: keep trying, tick() paces the retries.
  if (!lastTransmitOk_ && !state_.power && offResends_ == 0) offResends_ = 1;
  return lastTransmitOk_;
}

bool Controller::tick(uint32_t nowMs) {
  if (timerRunning_ && autoOffRemainingMs(nowMs) == 0) {
    off(nowMs);
    offResends_ = kOffResends;
  }

  const uint32_t sinceSend = nowMs - lastSendMs_;
  if (dirty_ && (!sentOnce_ || sinceSend >= kMinSendGapMs)) {
    dirty_ = false;
    send(nowMs);
    return true;
  }
  if (offResends_ > 0 && !state_.power && sinceSend >= kOffResendGapMs) {
    offResends_--;
    send(nowMs);
    return true;
  }
  return false;
}

}  // namespace proflame2
