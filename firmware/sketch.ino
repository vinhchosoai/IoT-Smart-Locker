/**
 * IoT Smart Locker Firmware (1 ESP32 = 1 Ngan tu) - Ban danh cho Wokwi Web
 * Simulator Doi LOCKER_ID neu nap cho cac ngan tu tiep theo (2, 3, ...).
 */
#define LOCKER_ID 1

#include <Arduino.h>
#include <ArduinoJson.h>
#include <LiquidCrystal_I2C.h>
#include <PubSubClient.h>
#include <WiFi.h>
#include <Wire.h>

// Cau hinh WiFi & MQTT Broker
const char *WIFI_SSID = "Wokwi-GUEST";
const char *WIFI_PASSWORD = "";
const char *MQTT_HOST = "broker.hivemq.com";
const int MQTT_PORT = 1883;
const char *MQTT_TOPIC_PREFIX = "iot_smartlocker_2026";

// Phan cung GPIO
const int PIN_RELAY = 26;       // HIGH = mo khoa, LOW = dong khoa
const int PIN_DOOR_SENSOR = 32; // INPUT_PULLUP: LOW = dong cua, HIGH = mo cua
const int PIN_BUZZER = 15;      // Coi bao hieu

// Hang so thoi gian (ms) - Non-blocking millis()
const unsigned long UNLOCK_DURATION_MS =
    5000UL; // TC-06: Tu dong ngat relay sau 5 giay
const unsigned long DOOR_TIMEOUT_MS =
    30000UL; // TC-07: Canh bao cua mo qua 30 giay
const unsigned long HEARTBEAT_INTERVAL_MS =
    10000UL; // Gui heartbeat moi 10 giay
const unsigned long RECONNECT_INTERVAL_MS = 5000UL;

WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);
LiquidCrystal_I2C lcd(0x27, 16, 2);

String commandTopic;
String legacyCommandTopic;
String statusTopic;
String clientId;

// Trang thai he thong
bool isUnlocked = false;
unsigned long unlockedAt = 0;

bool isDoorOpen = false;
unsigned long doorOpenedAt = 0;
bool doorTimeoutAlert = false;

bool shortBeepActive = false;
unsigned long shortBeepUntil = 0;
unsigned long lastAlarmToggle = 0;
bool alarmToneState = false;

unsigned long lastHeartbeatAt = 0;
unsigned long lastReconnectAttempt = 0;
String lastLcdLine1 = "";
String lastLcdLine2 = "";

void updateLcd(const String &line1, const String &line2) {
  if (line1 == lastLcdLine1 && line2 == lastLcdLine2) {
    return;
  }
  lastLcdLine1 = line1;
  lastLcdLine2 = line2;

  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(line1.substring(0, 16));
  lcd.setCursor(0, 1);
  lcd.print(line2.substring(0, 16));
}

void refreshDisplay() {
  String line1 = "LOCKER #" + String(LOCKER_ID);
  String line2;
  if (doorTimeoutAlert) {
    line1 = "ALERT: LOCKER #" + String(LOCKER_ID);
    line2 = "CLOSE THE DOOR!";
  } else if (isUnlocked) {
    line2 = "UNLOCKED (5s)";
  } else if (isDoorOpen) {
    line2 = "LOCKED | DOOR:OPN";
  } else {
    line2 = "LOCKED | DOOR:CLS";
  }
  updateLcd(line1, line2);
}

void publishStatus() {
  if (!mqttClient.connected()) {
    return;
  }
  JsonDocument doc;
  doc["locker_id"] = LOCKER_ID;
  doc["online"] = true;
  const char *doorStr = isDoorOpen ? "OPEN" : "CLOSED";
  doc["door"] = doorStr;
  doc["door_state"] = doorStr;
  doc["lock_state"] = isUnlocked ? "UNLOCKED" : "LOCKED";
  doc["alert"] = doorTimeoutAlert ? "DOOR_OPEN_TIMEOUT" : "NONE";
  doc["uptime_ms"] = millis();

  char buffer[256];
  size_t len = serializeJson(doc, buffer, sizeof(buffer));
  mqttClient.publish(statusTopic.c_str(), (const uint8_t *)buffer, len, false);
}

void triggerUnlock(const char *reason) {
  digitalWrite(PIN_RELAY, HIGH);
  isUnlocked = true;
  unlockedAt = millis();

  digitalWrite(PIN_BUZZER, HIGH);
  shortBeepActive = true;
  shortBeepUntil = millis() + 250UL;

  Serial.printf("[LOCKER %d] UNLOCKED (reason=%s)\n", LOCKER_ID, reason);
  refreshDisplay();
  publishStatus();
}

void onMqttMessage(char *topic, byte *payload, unsigned int length) {
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, payload, length);
  if (err) {
    Serial.printf("[MQTT] Loi JSON: %s\n", err.c_str());
    return;
  }

  int targetId = doc["locker_id"] | LOCKER_ID;
  if (targetId != LOCKER_ID) {
    return;
  }

  const char *cmd = doc["action"] | doc["command"] | "";
  const char *reason = doc["reason"] | doc["user_type"] | "REMOTE";
  if (strcmp(cmd, "OPEN") == 0) {
    triggerUnlock(reason);
  }
}

void ensureConnections() {
  if (WiFi.status() != WL_CONNECTED) {
    return;
  }
  if (mqttClient.connected()) {
    return;
  }

  unsigned long now = millis();
  if (now - lastReconnectAttempt < RECONNECT_INTERVAL_MS &&
      lastReconnectAttempt != 0) {
    return;
  }
  lastReconnectAttempt = now;

  JsonDocument lwtDoc;
  lwtDoc["locker_id"] = LOCKER_ID;
  lwtDoc["online"] = false;
  char lwtBuffer[96];
  serializeJson(lwtDoc, lwtBuffer, sizeof(lwtBuffer));

  Serial.printf("[MQTT] Dang ket noi broker %s...\n", MQTT_HOST);
  if (mqttClient.connect(clientId.c_str(), statusTopic.c_str(), 1, false,
                         lwtBuffer)) {
    Serial.println("[MQTT] Ket noi thanh cong.");
    mqttClient.subscribe(commandTopic.c_str(), 1);
    mqttClient.subscribe(legacyCommandTopic.c_str(), 1);
    Serial.printf("[MQTT] Da subscribe: %s, %s\n", commandTopic.c_str(),
                  legacyCommandTopic.c_str());
    publishStatus();
    lastHeartbeatAt = millis();
  } else {
    Serial.printf("[MQTT] Ket noi that bai, state=%d\n", mqttClient.state());
  }
}

void setup() {
  Serial.begin(115200);

  pinMode(PIN_RELAY, OUTPUT);
  digitalWrite(PIN_RELAY, LOW);

  pinMode(PIN_BUZZER, OUTPUT);
  digitalWrite(PIN_BUZZER, LOW);

  pinMode(PIN_DOOR_SENSOR, INPUT_PULLUP);

  Wire.begin(21, 22);
  lcd.init();
  lcd.backlight();
  updateLcd("SMART LOCKER #" + String(LOCKER_ID), "Booting WiFi...");

  commandTopic =
      String(MQTT_TOPIC_PREFIX) + "/locker/" + String(LOCKER_ID) + "/command";
  legacyCommandTopic = String(MQTT_TOPIC_PREFIX) + "/command";
  statusTopic =
      String(MQTT_TOPIC_PREFIX) + "/locker/" + String(LOCKER_ID) + "/status";
  clientId = "esp32-locker-" + String(LOCKER_ID) + "-" +
             String((uint32_t)ESP.getEfuseMac(), HEX);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  unsigned long wifiStart = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - wifiStart < 10000UL) {
    delay(200);
  }

  mqttClient.setServer(MQTT_HOST, MQTT_PORT);
  mqttClient.setCallback(onMqttMessage);

  isDoorOpen = (digitalRead(PIN_DOOR_SENSOR) == HIGH);
  if (isDoorOpen) {
    doorOpenedAt = millis();
  }
  refreshDisplay();
}

void loop() {
  unsigned long now = millis();

  ensureConnections();
  if (mqttClient.connected()) {
    mqttClient.loop();
  }

  if (isUnlocked && (now - unlockedAt >= UNLOCK_DURATION_MS)) {
    digitalWrite(PIN_RELAY, LOW);
    isUnlocked = false;
    Serial.printf("[LOCKER %d] AUTO LOCKED (5s elapsed)\n", LOCKER_ID);
    refreshDisplay();
    publishStatus();
  }

  if (shortBeepActive && (long)(now - shortBeepUntil) >= 0) {
    shortBeepActive = false;
    if (!doorTimeoutAlert) {
      digitalWrite(PIN_BUZZER, LOW);
    }
  }

  bool currentDoorOpen = (digitalRead(PIN_DOOR_SENSOR) == HIGH);
  if (currentDoorOpen != isDoorOpen) {
    isDoorOpen = currentDoorOpen;
    if (isDoorOpen) {
      doorOpenedAt = now;
      Serial.printf("[LOCKER %d] Door OPENED\n", LOCKER_ID);
    } else {
      doorTimeoutAlert = false;
      if (!shortBeepActive) {
        digitalWrite(PIN_BUZZER, LOW);
      }
      Serial.printf("[LOCKER %d] Door CLOSED\n", LOCKER_ID);
    }
    refreshDisplay();
    publishStatus();
  }

  if (isDoorOpen && !doorTimeoutAlert &&
      (now - doorOpenedAt >= DOOR_TIMEOUT_MS)) {
    doorTimeoutAlert = true;
    Serial.printf("[LOCKER %d] ALERT: DOOR_OPEN_TIMEOUT (>30s)\n", LOCKER_ID);
    refreshDisplay();
    publishStatus();
  }

  if (doorTimeoutAlert) {
    if (now - lastAlarmToggle >= 500UL) {
      lastAlarmToggle = now;
      alarmToneState = !alarmToneState;
      digitalWrite(PIN_BUZZER, alarmToneState ? HIGH : LOW);
    }
  }

  if (now - lastHeartbeatAt >= HEARTBEAT_INTERVAL_MS) {
    lastHeartbeatAt = now;
    publishStatus();
  }
}
