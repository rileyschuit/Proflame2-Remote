// Copy to secrets.h (git-ignored) and fill in.
#pragma once

const char* const kWifiSsid = "your-ssid";
const char* const kWifiPassword = "your-wifi-password";

const char* const kMqttHost = "192.168.0.x";
const uint16_t kMqttPort = 1883;
const char* const kMqttUser = "fireplace";
const char* const kMqttPassword = "your-mqtt-password";
const char* const kMqttBaseTopic = "home/fireplace";

// Generate with: openssl rand -hex 24
const char* const kApiToken = "CHANGE_ME";
