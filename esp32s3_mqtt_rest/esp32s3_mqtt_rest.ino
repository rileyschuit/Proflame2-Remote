// Fireplace control over REST, MQTT and serial. See docs/interfaces.md.
//
// Safety behaviour, all of it on the device so it works without the network:
// - Nothing transmits at boot.
// - The auto-off timer turns the fireplace off even with Wi-Fi down.
// - State is saved, so a reboot restarts the timer instead of forgetting it.
// - Retained MQTT commands are refused, so a broker can't relight it after a reboot.

#include <ArduinoJson.h>
#include <Preferences.h>
#include <Proflame2.h>
#include <SPI.h>
#include <WebServer.h>
#include <WiFi.h>
#include <espMqttClient.h>

#include "remote_identity.h"
#include "secrets.h"

const uint8_t kCsnPin = 4;   // XIAO D3
const uint8_t kSckPin = 7;   // XIAO D8
const uint8_t kMisoPin = 8;  // XIAO D9
const uint8_t kMosiPin = 9;  // XIAO D10

const uint32_t kMqttRetryMs = 5000;
const size_t kMaxBodyBytes = 256;

proflame2::Cc1101Ook radio(kCsnPin);

bool transmitBurst(const uint8_t* burst, size_t length) {
  return radio.transmit(burst, length);
}

proflame2::Controller controller(kRemote, transmitBurst);
Preferences preferences;
WebServer server(80);
espMqttClient mqtt(espMqttClientTypes::UseInternalTask::NO);

String setTopic, stateTopic, availabilityTopic, errorTopic;
uint32_t lastMqttAttemptMs = 0;
uint8_t savedCmd1, savedCmd2;
uint16_t savedTimer;
bool statePublishPending = true;

char lineBuffer[40];
size_t lineUsed = 0;

// Parses {"flame":3,"power":true} and commits it all or not at all.
const char* applyJson(const char* body, size_t length) {
  if (length == 0 || length > kMaxBodyBytes) return "body must be 1-256 bytes";

  JsonDocument doc;
  if (deserializeJson(doc, body, length)) return "invalid JSON";
  JsonObject object = doc.as<JsonObject>();
  if (object.isNull() || object.size() == 0) return "expected a JSON object";

  proflame2::FireplaceState next = controller.state();
  for (JsonPair pair : object) {
    JsonVariant value = pair.value();
    int number;
    if (value.is<bool>()) number = value.as<bool>() ? 1 : 0;
    else if (value.is<int>()) number = value.as<int>();
    else return "values must be integers or booleans";

    switch (proflame2::setField(next, pair.key().c_str(), number)) {
      case proflame2::SetResult::kOk:
        break;
      case proflame2::SetResult::kUnknownField:
        return "unknown field";
      case proflame2::SetResult::kBadValue:
        return "value out of range";
    }
  }
  controller.commit(next, millis());
  return nullptr;
}

String stateJson() {
  const proflame2::FireplaceState& s = controller.state();
  JsonDocument doc;
  doc["power"] = s.power;
  doc["flame"] = s.flame;
  doc["fan"] = s.fan;
  doc["light"] = s.light;
  doc["front"] = s.front;
  doc["aux"] = s.aux;
  doc["pilot"] = s.pilot;
  doc["autoOffMinutes"] = controller.autoOffMinutes();
  doc["autoOffRemainingS"] = controller.autoOffRemainingMs(millis()) / 1000UL;
  doc["radioOk"] = radio.present() && controller.lastTransmitOk();
  // Only what this device last sent. The real remote can change the fireplace.
  doc["assumed"] = true;
  String out;
  serializeJson(doc, out);
  return out;
}

void sendError(int code, const char* message) {
  JsonDocument doc;
  doc["error"] = message;
  String out;
  serializeJson(doc, out);
  server.send(code, "application/json", out);
}

bool authorized() {
  if (kApiToken[0] == '\0' || !strcmp(kApiToken, "CHANGE_ME")) return false;
  const String header = server.header("Authorization");
  const String expected = String("Bearer ") + kApiToken;
  if (header.length() != expected.length()) return false;
  uint8_t difference = 0;
  for (size_t i = 0; i < expected.length(); i++) difference |= header[i] ^ expected[i];
  return difference == 0;
}

bool requireAuth() {
  if (authorized()) return true;
  server.sendHeader("WWW-Authenticate", "Bearer");
  sendError(401, "unauthorized");
  return false;
}

bool requireRadio() {
  if (radio.present()) return true;
  sendError(503, "CC1101 not found");
  return false;
}

void handleGetState() {
  if (requireAuth()) server.send(200, "application/json", stateJson());
}

void handlePostState() {
  if (!requireAuth() || !requireRadio()) return;
  const String body = server.arg("plain");
  const char* error = applyJson(body.c_str(), body.length());
  if (error) sendError(400, error);
  else server.send(202, "application/json", stateJson());
}

void handlePostOff() {
  if (!requireAuth() || !requireRadio()) return;
  controller.off(millis());
  server.send(202, "application/json", stateJson());
}

void onMqttConnect(bool) {
  mqtt.subscribe(setTopic.c_str(), 0);
  mqtt.publish(availabilityTopic.c_str(), 1, true, "online");
  statePublishPending = true;
  Serial.println(F("MQTT connected"));
}

void onMqttMessage(const espMqttClientTypes::MessageProperties& properties, const char*,
                   const uint8_t* payload, size_t length, size_t index, size_t total) {
  const char* error = nullptr;
  if (properties.retain) error = "retained commands are refused";
  else if (index != 0 || length != total) error = "payload too large";
  else if (!radio.present()) error = "CC1101 not found";
  else error = applyJson(reinterpret_cast<const char*>(payload), length);

  if (error) {
    Serial.print(F("MQTT command refused: "));
    Serial.println(error);
    mqtt.publish(errorTopic.c_str(), 0, false, error);
  }
}

void maintainMqtt() {
  mqtt.loop();
  if (WiFi.status() != WL_CONNECTED || mqtt.connected()) return;
  if (millis() - lastMqttAttemptMs < kMqttRetryMs) return;
  lastMqttAttemptMs = millis();
  mqtt.connect();
}

void restoreState() {
  preferences.begin("fireplace", false);
  savedTimer = preferences.getUShort("timer", proflame2::kDefaultAutoOffMinutes);
  controller.setAutoOffMinutes(savedTimer, millis());

  proflame2::FireplaceState state = proflame2::kBootState;
  savedCmd1 = preferences.getUChar("cmd1", proflame2::cmd1Byte(state));
  savedCmd2 = preferences.getUChar("cmd2", proflame2::cmd2Byte(state));
  if (proflame2::stateFromCommandBytes(savedCmd1, savedCmd2, state)) {
    controller.restore(state, millis());
  }
}

void saveIfChanged() {
  const uint8_t cmd1 = proflame2::cmd1Byte(controller.state());
  const uint8_t cmd2 = proflame2::cmd2Byte(controller.state());
  if (cmd1 != savedCmd1 || cmd2 != savedCmd2) {
    preferences.putUChar("cmd1", cmd1);
    preferences.putUChar("cmd2", cmd2);
    savedCmd1 = cmd1;
    savedCmd2 = cmd2;
    statePublishPending = true;
  }
  if (controller.autoOffMinutes() != savedTimer) {
    savedTimer = controller.autoOffMinutes();
    preferences.putUShort("timer", savedTimer);
  }
}

void setup() {
  Serial.begin(115200);
  delay(1500);  // give USB serial time to enumerate

  if (!strcmp(kApiToken, "CHANGE_ME")) {
    Serial.println(F("Set kApiToken in secrets.h. REST calls will be refused until then."));
  }

  SPI.begin(kSckPin, kMisoPin, kMosiPin, kCsnPin);
  if (radio.begin()) {
    Serial.print(F("CC1101 found, version 0x"));
    Serial.println(radio.version(), HEX);
  } else {
    Serial.println(F("CC1101 NOT FOUND: check wiring. Commands will be refused."));
  }

  restoreState();
  proflame2::printStatus(Serial, controller, millis());

  const String base(kMqttBaseTopic);
  setTopic = base + "/set";
  stateTopic = base + "/state";
  availabilityTopic = base + "/availability";
  errorTopic = base + "/error";

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(kWifiSsid, kWifiPassword);

  mqtt.setServer(kMqttHost, kMqttPort);
  mqtt.setCredentials(kMqttUser, kMqttPassword);
  mqtt.setClientId("fireplace-remote");
  mqtt.setCleanSession(true);  // no queued commands waiting for us after an outage
  mqtt.setWill(availabilityTopic.c_str(), 1, true, "offline");
  mqtt.onConnect(onMqttConnect);
  mqtt.onMessage(onMqttMessage);

  const char* headers[] = {"Authorization"};
  server.collectHeaders(headers, 1);
  server.on("/healthz", HTTP_GET, []() {
    server.send(200, "application/json", radio.present() ? "{\"radio\":true}" : "{\"radio\":false}");
  });
  server.on("/api/state", HTTP_GET, handleGetState);
  server.on("/api/state", HTTP_POST, handlePostState);
  server.on("/api/off", HTTP_POST, handlePostOff);
  server.begin();
}

void loop() {
  static bool wifiWasUp = false;
  const bool wifiUp = WiFi.status() == WL_CONNECTED;
  if (wifiUp && !wifiWasUp) {
    Serial.print(F("Wi-Fi up, http://"));
    Serial.println(WiFi.localIP());
  }
  wifiWasUp = wifiUp;

  server.handleClient();
  maintainMqtt();
  proflame2::pollSerial(Serial, lineBuffer, sizeof(lineBuffer), lineUsed, controller, radio,
                        millis());

  if (controller.tick(millis())) statePublishPending = true;
  saveIfChanged();

  if (statePublishPending && mqtt.connected()) {
    statePublishPending = false;
    mqtt.publish(stateTopic.c_str(), 0, true, stateJson().c_str());
  }
}
