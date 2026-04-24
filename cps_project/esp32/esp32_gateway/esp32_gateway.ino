// ============================================================
//  CPS Inteligente — ESP32
//  Gateway IoT: Arduino ↔ WiFi/MQTT
//
//  Hardware:
//    Serial2 RX  → GPIO16 ← Arduino D6 (TX) [via divisor 1k/2k]
//    Serial2 TX  → GPIO17 → Arduino D7 (RX)
//    WiFi 2.4 GHz integrado
//
//  Topics MQTT:
//    Publica  → "sensores/data"   payload: JSON
//    Suscribe ← "control/cmd"    payload: "NORMAL"|"ALERTA"|"FALLA"
//
//  Dependencias (Gestor de bibliotecas Arduino IDE):
//    - PubSubClient  by Nick O'Leary
//    - ArduinoJson   by Benoit Blanchon
// ============================================================

#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// ── Configuración de red ─────────────────────────────────────
const char* WIFI_SSID     = "TU_SSID";
const char* WIFI_PASSWORD = "TU_PASSWORD";

// IP de la PC donde corre Mosquitto (en la misma red)
const char* MQTT_BROKER   = "192.168.1.100";
const int   MQTT_PORT     = 1883;
const char* MQTT_CLIENT   = "esp32_cps_gateway";

// Topics
const char* TOPIC_DATA    = "sensores/data";
const char* TOPIC_CMD     = "control/cmd";

// ── Serial2 hacia Arduino ────────────────────────────────────
#define ARD_RX_PIN   16    // ESP32 recibe del Arduino
#define ARD_TX_PIN   17    // ESP32 transmite al Arduino
#define SERIAL2_BAUD 9600

// ── Objetos ──────────────────────────────────────────────────
WiFiClient   wifiClient;
PubSubClient mqtt(wifiClient);

// ── Buffer de recepción ──────────────────────────────────────
String lineBuffer = "";

// ─────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  Serial2.begin(SERIAL2_BAUD, SERIAL_8N1, ARD_RX_PIN, ARD_TX_PIN);

  conectarWiFi();

  mqtt.setServer(MQTT_BROKER, MQTT_PORT);
  mqtt.setCallback(mqttCallback);
  mqtt.setBufferSize(512);

  conectarMQTT();

  Serial.println(F("[ ESP32 ] Gateway listo"));
}

// ─────────────────────────────────────────────────────────────
void loop() {
  // Mantener conexión MQTT
  if (!mqtt.connected()) {
    conectarMQTT();
  }
  mqtt.loop();

  // Leer datos del Arduino carácter a carácter
  while (Serial2.available()) {
    char c = (char)Serial2.read();
    if (c == '\n') {
      lineBuffer.trim();
      if (lineBuffer.length() > 0) {
        procesarLineaArduino(lineBuffer);
      }
      lineBuffer = "";
    } else {
      lineBuffer += c;
    }
  }
}

// ─────────────────────────────────────────────────────────────
// Parsear CSV del Arduino y publicar JSON por MQTT
// Formato esperado: "TEMP,HUM,VIB,CARGA"
// ─────────────────────────────────────────────────────────────
void procesarLineaArduino(const String& linea) {
  // Parsear los 4 valores separados por coma
  float valores[4];
  int idx = 0;
  int inicio = 0;

  for (int i = 0; i <= linea.length() && idx < 4; i++) {
    if (i == linea.length() || linea[i] == ',') {
      valores[idx++] = linea.substring(inicio, i).toFloat();
      inicio = i + 1;
    }
  }

  if (idx < 4) {
    Serial.println(F("[ WARN ] Línea incompleta, ignorando"));
    return;
  }

  // Construir JSON
  StaticJsonDocument<200> doc;
  doc["temp"]  = valores[0];
  doc["hum"]   = valores[1];
  doc["vib"]   = (int)valores[2];
  doc["carga"] = (int)valores[3];

  char payload[200];
  serializeJson(doc, payload);

  // Publicar al broker
  if (mqtt.publish(TOPIC_DATA, payload)) {
    Serial.print(F("[ MQTT ] Publicado: "));
    Serial.println(payload);
  } else {
    Serial.println(F("[ MQTT ] Error al publicar"));
  }
}

// ─────────────────────────────────────────────────────────────
// Callback MQTT: llega un comando desde Python
// ─────────────────────────────────────────────────────────────
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String topicStr(topic);
  String message;

  for (unsigned int i = 0; i < length; i++) {
    message += (char)payload[i];
  }
  message.trim();

  Serial.print(F("[ MQTT ] Recibido en "));
  Serial.print(topicStr);
  Serial.print(F(": "));
  Serial.println(message);

  // Reenviar al Arduino por Serial2
  if (topicStr == TOPIC_CMD) {
    Serial2.println(message);
    Serial.print(F("[ ARD  ] Reenviado: "));
    Serial.println(message);
  }
}

// ─────────────────────────────────────────────────────────────
// Conectar al WiFi con reintentos
// ─────────────────────────────────────────────────────────────
void conectarWiFi() {
  Serial.print(F("[ WiFi ] Conectando a "));
  Serial.println(WIFI_SSID);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int intentos = 0;
  while (WiFi.status() != WL_CONNECTED && intentos < 30) {
    delay(500);
    Serial.print('.');
    intentos++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println();
    Serial.print(F("[ WiFi ] Conectado. IP: "));
    Serial.println(WiFi.localIP());
  } else {
    Serial.println(F("\n[ WiFi ] ERROR: sin conexión"));
  }
}

// ─────────────────────────────────────────────────────────────
// Conectar al broker MQTT con reintentos
// ─────────────────────────────────────────────────────────────
void conectarMQTT() {
  int intentos = 0;

  while (!mqtt.connected() && intentos < 5) {
    Serial.print(F("[ MQTT ] Conectando al broker..."));

    if (mqtt.connect(MQTT_CLIENT)) {
      Serial.println(F(" OK"));
      mqtt.subscribe(TOPIC_CMD);
      Serial.print(F("[ MQTT ] Suscrito a: "));
      Serial.println(TOPIC_CMD);
    } else {
      Serial.print(F(" FALLO rc="));
      Serial.println(mqtt.state());
      delay(2000);
      intentos++;
    }
  }
}
