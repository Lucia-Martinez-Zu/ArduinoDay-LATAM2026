# CPS Inteligente — Guía de configuración y uso

Sistemas ciberfísicos inteligentes: Arduino + ESP32 + MQTT + Machine Learning

---

## Estructura del proyecto

```
cps_project/
├── arduino/
│   └── arduino_cps.ino      → Firmware para Arduino UNO
├── esp32/
│   └── esp32_gateway.ino    → Firmware para ESP32 (gateway IoT)
└── python/
    ├── train_model.py        → Genera dataset y entrena Random Forest
    └── dashboard.py          → Dashboard MQTT + IF vs ML en tiempo real
└── node-red/
    └── dashboard.json        → Dashboard MQTT + IF vs ML en Node Red
```

---

## Hardware necesario

| Componente       | Cantidad | Conexión en Arduino UNO       |
|------------------|----------|-------------------------------|
| Arduino UNO      | 1        | —                             |
| ESP32            | 1        | D6(TX)→GPIO16, D7(RX)←GPIO17 |
| DHT11            | 1        | D2, pull-up 10kΩ a 5V         |
| Potenciómetro    | 2        | wiper → A0 y A1               |
| LED RGB          | 1        | R→D9, G→D10, B→D11 + 220Ω c/u|
| Buzzer pasivo    | 1        | (+)→D8, (−)→GND               |
| Resistencia 220Ω | 3        | En serie con cada canal LED   |
| Resistencia 10kΩ | 1        | Pull-up DATA del DHT11        |
| Resistencia 1kΩ  | 1        | Divisor de tensión (TX 5V→3.3V)|
| Resistencia 2kΩ  | 1        | Divisor de tensión (TX 5V→3.3V)|

> Divisor de tensión en la línea Arduino D6 → ESP32 GPIO16:
>   D6 ──[1kΩ]──┬──[2kΩ]── GND
>               └── GPIO16 del ESP32  (~3.3V)

---

## Paso 1 — Configurar el firmware del ESP32

Editar `esp32/esp32_gateway.ino`:

```cpp
const char* WIFI_SSID     = "TU_SSID";
const char* WIFI_PASSWORD = "TU_PASSWORD";
const char* MQTT_BROKER   = "192.168.1.XXX";  // IP de tu PC
```

Para encontrar la IP de tu PC:
- Windows: `ipconfig` en cmd
- Linux/Mac: `ip a` o `ifconfig`

---

## Paso 2 — Instalar bibliotecas en Arduino IDE

Para **Arduino UNO**:
- `DHT sensor library` by Adafruit
- `Adafruit Unified Sensor` (dependencia del DHT)

Para **ESP32**:
- `PubSubClient` by Nick O'Leary
- `ArduinoJson` by Benoit Blanchon

Gestor de placas ESP32: agregar en Preferencias → URLs adicionales:
```
https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
```

---

## Paso 3 — Instalar y configurar Mosquitto (broker MQTT)

### Windows
1. Descargar desde: https://mosquitto.org/download/
2. Instalar y crear archivo de configuración `mosquitto.conf`:
```
listener 1883 0.0.0.0
allow_anonymous true
```
3. Ejecutar: `mosquitto -c mosquitto.conf -v`

### Linux
```bash
sudo apt install mosquitto
# Editar /etc/mosquitto/mosquitto.conf
# Agregar: listener 1883 0.0.0.0
#           allow_anonymous true
sudo systemctl start mosquitto
```

---

## Paso 4 — Instalar dependencias Python

```bash
pip install paho-mqtt scikit-learn numpy matplotlib joblib pandas
```

---

## Paso 5 — Entrenar el modelo ML

```bash
cd python/
python train_model.py
```

Salida esperada:
```
Dataset generado: 3000 muestras
estado
NORMAL    1350
ALERTA     900
FALLA      750

Entrenando Random Forest...
── Reporte de clasificación ──────────────────────────
              precision    recall  f1-score
NORMAL         0.97          0.98      0.98
ALERTA         0.95          0.94      0.94
FALLA          0.99          0.99      0.99

Modelo guardado en: modelo_cps.pkl
```

---

## Paso 6 — Arrancar el dashboard

```bash
cd python/
python dashboard.py
```

---

## Orden de arranque

1. Abrir Mosquitto en la PC
2. Ejecutar `python dashboard.py`
3. Cargar firmware en Arduino UNO
4. Cargar firmware en ESP32
5. Alimentar el circuito

El sistema estará operativo cuando el LED del Arduino parpadee verde.

---

## Los 4 escenarios de demostración

| Escenario         | Cómo reproducirlo                          | IF dice  | ML dice  |
|-------------------|--------------------------------------------|----------|----------|
| Normal            | Potenciómetros al mínimo, temp. ambiente   | NORMAL   | NORMAL   |
| Falla evidente    | Ambos potenciómetros al máximo + calor     | FALLA    | FALLA    |
| Falla temprana ⚡  | Potenc. al 70%, temp. ~34°C                | NORMAL   | ALERTA   |
| Falso positivo ⚡  | Soplar DHT11 brevemente (pico de temp.)    | FALLA    | NORMAL   |

Los escenarios marcados con ⚡ son los momentos pedagógicos clave:
El ML y el IF divergen, y el ML tiene razón.

---

## Solución de problemas frecuentes

| Problema                          | Posible causa                      | Solución                                  |
|-----------------------------------|------------------------------------|-------------------------------------------|
| ESP32 no conecta al WiFi          | SSID/password incorrectos          | Verificar credenciales en el firmware     |
| MQTT "connection refused"         | Mosquitto no corre o IP incorrecta | Revisar IP y que Mosquitto esté activo    |
| Dashboard no recibe datos         | Topic MQTT incorrecto              | Verificar "sensores/data" en ambos lados  |
| DHT11 siempre da error            | Sin pull-up o pin incorrecto       | Verificar resistencia 10kΩ en DATA        |
| LED no cambia de color            | Conexión de cátodo común invertida | Verificar GND común del LED RGB           |
| Python: FileNotFoundError modelo  | Modelo no entrenado                | Ejecutar train_model.py primero           |
