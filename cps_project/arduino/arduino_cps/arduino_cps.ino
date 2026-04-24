// ============================================================
//  CPS Inteligente — Arduino UNO
//  Nodo físico: sensado + actuación
//
//  Sensores:
//    DHT11       → D2
//    Potenc. 1   → A0  (vibración simulada)
//    Potenc. 2   → A1  (carga simulada)
//
//  Actuadores:
//    LED RGB R   → D9  (PWM)
//    LED RGB G   → D10 (PWM)
//    LED RGB B   → D11 (PWM)
//    Buzzer      → D8
//
//  Comunicación:
//    SoftwareSerial TX → D6 → ESP32 GPIO16 (RX2)
//    SoftwareSerial RX ← D7 ← ESP32 GPIO17 (TX2)  [via divisor 1k/2k]
//
//  Protocolo salida  → "TEMP,HUM,VIB,CARGA\n"
//  Protocolo entrada ← "NORMAL" | "ALERTA" | "FALLA"
// ============================================================

#include <DHT.h>
#include <SoftwareSerial.h>

// ── Pines ────────────────────────────────────────────────────
#define DHT_PIN       2
#define DHT_TYPE      DHT11
#define POT_VIB       A0
#define POT_CARGA     A1
#define LED_R         9
#define LED_G         10
#define LED_B         11
#define BUZZER_PIN    8
#define SS_TX         6    // Arduino TX → ESP32 RX
#define SS_RX         7    // Arduino RX ← ESP32 TX

// ── Intervalos ───────────────────────────────────────────────
#define SEND_INTERVAL_MS  500    // envía datos cada 500 ms
#define BUZZ_BEEP_MS      120    // duración de cada beep

// ── Objetos ──────────────────────────────────────────────────
DHT dht(DHT_PIN, DHT_TYPE);
SoftwareSerial espSerial(SS_RX, SS_TX);

// ── Estado global ────────────────────────────────────────────
enum EstadoSistema { ESTADO_NORMAL, ESTADO_ALERTA, ESTADO_FALLA };
EstadoSistema estadoActual = ESTADO_NORMAL;

unsigned long ultimoEnvio   = 0;
unsigned long ultimoBuzz    = 0;
bool           buzzActivo    = false;

// ─────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(9600);
  espSerial.begin(9600);
  dht.begin();

  pinMode(LED_R,     OUTPUT);
  pinMode(LED_G,     OUTPUT);
  pinMode(LED_B,     OUTPUT);
  pinMode(BUZZER_PIN,OUTPUT);

  setLED(0, 30, 0);    // verde tenue al inicio
  Serial.println(F("[ CPS ] Arduino listo"));
}

// ─────────────────────────────────────────────────────────────
void loop() {
  unsigned long ahora = millis();

  // 1. Leer y enviar datos al ESP32
  if (ahora - ultimoEnvio >= SEND_INTERVAL_MS) {
    ultimoEnvio = ahora;
    enviarDatos();
  }

  // 2. Leer comando entrante del ESP32
  if (espSerial.available()) {
    String cmd = espSerial.readStringUntil('\n');
    cmd.trim();
    aplicarComando(cmd);
  }

  // 3. Gestionar buzzer no-bloqueante
  if (estadoActual == ESTADO_FALLA) {
    if (!buzzActivo && (ahora - ultimoBuzz >= 800)) {
      tone(BUZZER_PIN, 880);
      buzzActivo  = true;
      ultimoBuzz  = ahora;
    }
    if (buzzActivo && (ahora - ultimoBuzz >= BUZZ_BEEP_MS)) {
      noTone(BUZZER_PIN);
      buzzActivo = false;
    }
  }
}

// ─────────────────────────────────────────────────────────────
// Leer sensores y enviar cadena CSV al ESP32
// ─────────────────────────────────────────────────────────────
void enviarDatos() {
  float temp = dht.readTemperature();
  float hum  = dht.readHumidity();

  if (isnan(temp) || isnan(hum)) {
    Serial.println(F("[ DHT ] Error de lectura"));
    return;
  }

  int vib   = analogRead(POT_VIB);    // 0–1023
  int carga = analogRead(POT_CARGA);  // 0–1023

  // Enviar al ESP32
  espSerial.print(temp,  1); espSerial.print(',');
  espSerial.print(hum,   1); espSerial.print(',');
  espSerial.print(vib);      espSerial.print(',');
  espSerial.println(carga);

  // Echo en monitor serie local
  Serial.print(F("[ TX ] T="));  Serial.print(temp,1);
  Serial.print(F(" H="));        Serial.print(hum,1);
  Serial.print(F(" V="));        Serial.print(vib);
  Serial.print(F(" C="));        Serial.println(carga);
}

// ─────────────────────────────────────────────────────────────
// Aplicar comando recibido desde ESP32
// ─────────────────────────────────────────────────────────────
void aplicarComando(const String& cmd) {
  Serial.print(F("[ RX ] Comando: ")); Serial.println(cmd);

  if (cmd == "NORMAL") {
    estadoActual = ESTADO_NORMAL;
    noTone(BUZZER_PIN);
    setLED(0, 200, 0);          // verde
  }
  else if (cmd == "ALERTA") {
    estadoActual = ESTADO_ALERTA;
    noTone(BUZZER_PIN);
    setLED(200, 120, 0);        // amarillo-naranja
  }
  else if (cmd == "FALLA") {
    estadoActual = ESTADO_FALLA;
    setLED(255, 0, 0);          // rojo
    // el buzzer se gestiona en loop()
  }
}

// ─────────────────────────────────────────────────────────────
// Escribir color en LED RGB (cátodo común)
// ─────────────────────────────────────────────────────────────
void setLED(int r, int g, int b) {
  analogWrite(LED_R, r);
  analogWrite(LED_G, g);
  analogWrite(LED_B, b);
}
