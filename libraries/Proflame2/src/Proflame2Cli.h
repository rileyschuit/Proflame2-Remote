// Line-based serial commands, shared by both sketches.
#pragma once

#include <Arduino.h>
#include <ctype.h>
#include <stdlib.h>
#include <string.h>

#include "Cc1101Ook.h"
#include "Proflame2Controller.h"

namespace proflame2 {

inline void printHelp(Print& out) {
  out.println(F("flame|fan|light <0-6>       set a level"));
  out.println(F("power|front|aux|pilot <on|off>"));
  out.println(F("off                         power off now"));
  out.println(F("status                      state and timer"));
  out.println(F("frame                       show the frame, no transmit"));
  out.println(F("send                        transmit the current state again"));
  out.println(F("timer <1-720>               auto-off minutes"));
  out.println(F("id <hex|real>               test serial the fireplace ignores, or back"));
  out.println(F("freq <kHz>                  300000-348000, default 314973"));
  out.println(F("tx <low|mid|high>           transmit power"));
}

inline void printHex2(Print& out, uint8_t value) {
  if (value < 0x10) out.print('0');
  out.print(value, HEX);
}

inline void printFrame(Print& out, const Controller& controller) {
  uint8_t payload[kPayloadBytes];
  buildPayload(controller.remote(), controller.state(), payload);
  out.print(F("frame "));
  for (size_t i = 0; i < kPayloadBytes; i++) {
    printHex2(out, payload[i]);
    out.print(i == 2 ? F(" | ") : F(" "));
  }
  out.println();
}

inline void printStatus(Print& out, const Controller& controller, uint32_t nowMs) {
  const FireplaceState& s = controller.state();
  out.print(F("power="));
  out.print(s.power ? F("on") : F("off"));
  out.print(F(" flame="));
  out.print(s.flame);
  out.print(F(" fan="));
  out.print(s.fan);
  out.print(F(" light="));
  out.print(s.light);
  out.print(F(" front="));
  out.print(s.front ? F("on") : F("off"));
  out.print(F(" aux="));
  out.print(s.aux ? F("on") : F("off"));
  out.print(F(" pilot="));
  out.println(s.pilot ? F("on") : F("off"));
  out.print(F("auto-off "));
  out.print(controller.autoOffMinutes());
  out.print(F(" min, remaining s: "));
  out.println(controller.autoOffRemainingMs(nowMs) / 1000UL);
  out.print(F("last transmit "));
  out.println(controller.lastTransmitOk() ? F("ok") : F("FAILED"));
  printFrame(out, controller);
}

inline int parseOnOff(const char* text) {
  if (!strcmp(text, "on") || !strcmp(text, "1")) return 1;
  if (!strcmp(text, "off") || !strcmp(text, "0")) return 0;
  return -1;
}

// Strict decimal, so "flame 3x" or an empty value is an error rather than 0.
inline long parseNumber(const char* text) {
  char* end;
  const long value = strtol(text, &end, 10);
  return (*text == '\0' || *end != '\0') ? -1 : value;
}

// Modifies line. Returns true if the state changed and should be saved.
inline bool runCommand(char* line, Controller& controller, Cc1101Ook& radio, Print& out,
                       uint32_t nowMs) {
  char* command = strtok(line, " \t\r\n");
  if (!command) return false;
  for (char* c = command; *c; c++) *c = static_cast<char>(tolower(*c));
  char* argument = strtok(nullptr, " \t\r\n");

  if (!strcmp(command, "help")) {
    printHelp(out);
  } else if (!strcmp(command, "status")) {
    printStatus(out, controller, nowMs);
  } else if (!strcmp(command, "frame")) {
    printFrame(out, controller);
  } else if (!strcmp(command, "send")) {
    controller.resend();
    out.println(F("ok"));
  } else if (!strcmp(command, "off")) {
    controller.off(nowMs);
    out.println(F("ok"));
    return true;
  } else if (!argument) {
    out.println(F("missing value, try: help"));
  } else if (!strcmp(command, "timer")) {
    const long minutes = parseNumber(argument);
    const bool valid = minutes > 0 && minutes <= kMaxAutoOffMinutes &&
                       controller.setAutoOffMinutes(static_cast<uint16_t>(minutes), nowMs);
    out.println(valid ? F("ok") : F("use 1-720"));
  } else if (!strcmp(command, "id")) {
    if (!strcmp(argument, "real")) {
      controller.useRealSerial();
    } else {
      char* end;
      const unsigned long serial = strtoul(argument, &end, 16);
      if (*end != '\0' || serial > 0xFFFFFFUL) {
        out.println(F("use 6 hex digits or real"));
        return false;
      }
      controller.setSerial(serial);
    }
    printFrame(out, controller);
  } else if (!strcmp(command, "freq")) {
    const long khz = parseNumber(argument);
    out.println(khz > 0 && radio.setFrequencyKhz(static_cast<uint32_t>(khz)) ? F("ok")
                                                                             : F("use 300000-348000"));
  } else if (!strcmp(command, "tx")) {
    if (!strcmp(argument, "low")) radio.setPaLevel(kPaLow);
    else if (!strcmp(argument, "mid")) radio.setPaLevel(kPaMid);
    else if (!strcmp(argument, "high")) radio.setPaLevel(kPaHigh);
    else {
      out.println(F("use low, mid or high"));
      return false;
    }
    out.println(F("ok"));
  } else {
    FireplaceState next = controller.state();
    const bool isFlag = !strcmp(command, "power") || !strcmp(command, "front") ||
                        !strcmp(command, "aux") || !strcmp(command, "pilot");
    const long value = isFlag ? parseOnOff(argument) : parseNumber(argument);
    const SetResult result =
        value < 0 || value > kMaxLevel ? (setField(next, command, 0) == SetResult::kUnknownField
                                              ? SetResult::kUnknownField
                                              : SetResult::kBadValue)
                                       : setField(next, command, static_cast<int>(value));
    if (result == SetResult::kOk) {
      controller.commit(next, nowMs);
      out.println(F("ok"));
      return true;
    }
    out.println(result == SetResult::kBadValue ? F("bad value") : F("unknown command, try: help"));
  }
  return false;
}

// Collects serial input into a line and runs it. Returns true if the state changed.
inline bool pollSerial(Stream& serial, char* buffer, size_t size, size_t& used,
                       Controller& controller, Cc1101Ook& radio, uint32_t nowMs) {
  bool changed = false;
  while (serial.available()) {
    const char c = static_cast<char>(serial.read());
    if (c == '\n' || c == '\r') {
      if (used >= size) {
        serial.println(F("line too long, ignored"));
      } else {
        buffer[used] = '\0';
        if (buffer[0]) changed = runCommand(buffer, controller, radio, serial, nowMs) || changed;
      }
      used = 0;
    } else if (used + 1 < size) {
      buffer[used++] = c;
    } else {
      used = size;  // never run a truncated command
    }
  }
  return changed;
}

}  // namespace proflame2
