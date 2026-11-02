// Bench sketch: set fireplace levels from the serial monitor at 115200 baud.
// Builds for an Arduino Uno R3 and an ESP32-S3. Type "help" for the commands.
//
// Nothing is transmitted until you send a command. State lives in RAM and a Uno
// resets when the serial port opens, so after a reset this sketch no longer knows
// the fireplace is on and its auto-off timer is gone. Keep the real remote handy.

#include <Proflame2.h>
#include <SPI.h>

#include "remote_identity.h"

#if defined(ARDUINO_ARCH_AVR)
const uint8_t kCsnPin = 10;  // SCK 13, MISO 12, MOSI 11, through the level shifter
#else
const uint8_t kCsnPin = 4;  // XIAO D3
const uint8_t kSckPin = 7;  // XIAO D8
const uint8_t kMisoPin = 8;  // XIAO D9
const uint8_t kMosiPin = 9;  // XIAO D10
#endif

proflame2::Cc1101Ook radio(kCsnPin);

bool transmitBurst(const uint8_t* burst, size_t length) {
  return radio.transmit(burst, length);
}

proflame2::Controller controller(kRemote, transmitBurst);

char lineBuffer[40];
size_t lineUsed = 0;

void setup() {
  Serial.begin(115200);
#if defined(ARDUINO_ARCH_AVR)
  SPI.begin();
#else
  SPI.begin(kSckPin, kMisoPin, kMosiPin, kCsnPin);
  delay(1500);  // give USB serial time to enumerate
#endif

  Serial.println(F("Proflame 2 serial remote"));
  if (radio.begin()) {
    Serial.print(F("CC1101 found, version 0x"));
    Serial.println(radio.version(), HEX);
  } else {
    Serial.println(F("CC1101 NOT FOUND: check wiring. Commands will not transmit."));
  }
  Serial.println(F("State below is assumed, not read from the fireplace."));
  Serial.println(F("If the fireplace is on, this sketch has no timer for it: send 'power on' or 'off'."));
  proflame2::printStatus(Serial, controller, millis());
}

void loop() {
  proflame2::pollSerial(Serial, lineBuffer, sizeof(lineBuffer), lineUsed, controller, radio,
                        millis());

  if (controller.tick(millis())) {
    Serial.println(controller.lastTransmitOk() ? F("sent") : F("TRANSMIT FAILED"));
  }
}
