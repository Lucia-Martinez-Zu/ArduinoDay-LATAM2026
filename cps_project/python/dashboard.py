"""
============================================================
  CPS Inteligente — Dashboard en tiempo real
  MQTT subscriber + Random Forest + comparación IF vs ML

  Uso:
    1. Instalar Mosquitto y arrancarlo:  mosquitto -v
    2. Entrenar el modelo:               python train_model.py
    3. Ejecutar el dashboard:            python dashboard.py

  Dependencias:
    pip install paho-mqtt scikit-learn numpy matplotlib joblib

  Topics MQTT:
    Suscribe ← "sensores/data"   payload JSON {temp,hum,vib,carga}
    Publica  → "control/cmd"     payload "NORMAL" | "ALERTA" | "FALLA"
============================================================
"""

import json
import time
import threading
import numpy as np
import joblib
import paho.mqtt.client as mqtt
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.patches import FancyBboxPatch
from collections import deque

# ─────────────────────────────────────────────────────────────
# Configuración
# ─────────────────────────────────────────────────────────────
MQTT_BROKER   = "localhost"
MQTT_PORT     = 1883
MQTT_CLIENT   = "python_cps_dashboard"
TOPIC_DATA    = "sensores/data"
TOPIC_CMD     = "control/cmd"

MODEL_PATH    = "modelo_cps.pkl"
SCALER_PATH   = "scaler_cps.pkl"

HISTORY_LEN   = 60     # puntos en el gráfico histórico
SEND_CMD_EVERY = 1     # publicar comando cada N mensajes recibidos

# Umbrales del sistema IF (para comparación)
IF_TEMP_MAX   = 35.0
IF_VIB_MAX    = 750
IF_CARGA_MAX  = 640

# Colores por estado
COLORS = {
    "NORMAL": "#02C39A",
    "ALERTA": "#F4A261",
    "FALLA":  "#E63946",
    "---":    "#888787"
}

ESTADO_NOMBRES = {0: "NORMAL", 1: "ALERTA", 2: "FALLA"}

# ─────────────────────────────────────────────────────────────
# Estado compartido entre hilo MQTT y hilo de graficado
# ─────────────────────────────────────────────────────────────
class EstadoGlobal:
    def __init__(self):
        self.lock = threading.Lock()

        # Últimas lecturas
        self.temp  = 0.0
        self.hum   = 0.0
        self.vib   = 0
        self.carga = 0

        # Historial para gráficas
        self.hist_temp  = deque([0.0] * HISTORY_LEN, maxlen=HISTORY_LEN)
        self.hist_vib   = deque([0]   * HISTORY_LEN, maxlen=HISTORY_LEN)
        self.hist_carga = deque([0]   * HISTORY_LEN, maxlen=HISTORY_LEN)

        # Decisiones
        self.decision_if = "---"
        self.decision_ml = "---"
        self.proba_ml    = [0.0, 0.0, 0.0]  # [NORMAL, ALERTA, FALLA]

        # Contador de mensajes
        self.msg_count   = 0
        self.divergencias = 0   # veces que IF y ML difieren

estado = EstadoGlobal()

# ─────────────────────────────────────────────────────────────
# Cargar modelo
# ─────────────────────────────────────────────────────────────
print("Cargando modelo ML...")
try:
    modelo = joblib.load(MODEL_PATH)
    scaler = joblib.load(SCALER_PATH)
    print("Modelo cargado correctamente.")
except FileNotFoundError:
    print("ERROR: No se encontró modelo_cps.pkl o scaler_cps.pkl")
    print("Ejecuta primero:  python train_model.py")
    exit(1)

# ─────────────────────────────────────────────────────────────
# Lógica del sistema IF
# ─────────────────────────────────────────────────────────────
def evaluar_if(temp, vib, carga):
    """Sistema de reglas IF — evalúa cada variable de forma independiente."""
    if temp > IF_TEMP_MAX or vib > IF_VIB_MAX or carga > IF_CARGA_MAX:
        return "FALLA"
    return "NORMAL"

# ─────────────────────────────────────────────────────────────
# Lógica del modelo ML
# ─────────────────────────────────────────────────────────────
def evaluar_ml(temp, vib, carga):
    """Clasificación multivariada con Random Forest."""
    X = scaler.transform([[temp, vib, carga]])
    pred_idx  = modelo.predict(X)[0]
    proba     = modelo.predict_proba(X)[0]
    return ESTADO_NOMBRES[pred_idx], proba.tolist()

# ─────────────────────────────────────────────────────────────
# Callbacks MQTT
# ─────────────────────────────────────────────────────────────
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"[ MQTT ] Conectado al broker ({MQTT_BROKER}:{MQTT_PORT})")
        client.subscribe(TOPIC_DATA)
        print(f"[ MQTT ] Suscrito a '{TOPIC_DATA}'")
    else:
        print(f"[ MQTT ] Error de conexión, código: {rc}")

def on_message(client, userdata, msg):
    global estado

    try:
        data = json.loads(msg.payload.decode())
    except json.JSONDecodeError:
        print(f"[ WARN ] Payload no válido: {msg.payload}")
        return

    temp  = float(data.get("temp",  0))
    hum   = float(data.get("hum",   0))
    vib   = int(data.get("vib",   0))
    carga = int(data.get("carga", 0))

    # Evaluar ambos sistemas
    dec_if           = evaluar_if(temp, vib, carga)
    dec_ml, proba_ml = evaluar_ml(temp, vib, carga)

    # Actualizar estado compartido
    with estado.lock:
        estado.temp  = temp
        estado.hum   = hum
        estado.vib   = vib
        estado.carga = carga

        estado.hist_temp.append(temp)
        estado.hist_vib.append(vib)
        estado.hist_carga.append(carga)

        estado.decision_if = dec_if
        estado.decision_ml = dec_ml
        estado.proba_ml    = proba_ml

        estado.msg_count += 1
        if dec_if != dec_ml:
            estado.divergencias += 1

    # Publicar comando ML al ESP32 en cada mensaje
    client.publish(TOPIC_CMD, dec_ml)

    print(
        f"[ DATA ] T={temp:.1f}°C H={hum:.1f}% V={vib} C={carga}"
        f"  IF→{dec_if:<7}  ML→{dec_ml:<7}"
        f"  {'⚡ DIVERGEN' if dec_if != dec_ml else ''}"
    )

# ─────────────────────────────────────────────────────────────
# Dashboard Matplotlib
# ─────────────────────────────────────────────────────────────
def construir_dashboard():
    plt.style.use("dark_background")

    fig = plt.figure(figsize=(14, 8))
    fig.patch.set_facecolor("#0D1B2A")
    fig.suptitle(
        "CPS Inteligente — IF vs ML en tiempo real",
        fontsize=15, fontweight="bold",
        color="#E8F4FD", y=0.97
    )

    gs = gridspec.GridSpec(
        3, 3, figure=fig,
        left=0.06, right=0.97,
        top=0.91,  bottom=0.07,
        wspace=0.35, hspace=0.55
    )

    ax_temp  = fig.add_subplot(gs[0, :2])
    ax_vib   = fig.add_subplot(gs[1, :2])
    ax_carga = fig.add_subplot(gs[2, :2])
    ax_dec   = fig.add_subplot(gs[0, 2])
    ax_bar   = fig.add_subplot(gs[1, 2])
    ax_info  = fig.add_subplot(gs[2, 2])

    SURF  = "#112B3C"
    CARD  = "#1A3A52"
    TEXT  = "#E8F4FD"
    MUTED = "#90B4CE"

    # ── Historial de temperatura ──────────────────────────────
    ax_temp.set_facecolor(SURF)
    ax_temp.set_title("Temperatura (°C)", color=TEXT, fontsize=10, pad=4)
    ax_temp.tick_params(colors=MUTED, labelsize=8)
    ax_temp.spines[:].set_color("#1E4266")
    ax_temp.axhline(IF_TEMP_MAX, color="#E63946", linewidth=0.8,
                    linestyle="--", label=f"Umbral IF {IF_TEMP_MAX}°C")
    ax_temp.legend(fontsize=7, loc="upper left",
                   facecolor=CARD, edgecolor="none", labelcolor=MUTED)
    line_temp, = ax_temp.plot([], [], color="#00B4D8", linewidth=1.5)
    ax_temp.set_xlim(0, HISTORY_LEN)
    ax_temp.set_ylim(0, 65)

    # ── Historial de vibración ────────────────────────────────
    ax_vib.set_facecolor(SURF)
    ax_vib.set_title("Vibración (ADC 0–1023)", color=TEXT, fontsize=10, pad=4)
    ax_vib.tick_params(colors=MUTED, labelsize=8)
    ax_vib.spines[:].set_color("#1E4266")
    ax_vib.axhline(IF_VIB_MAX, color="#E63946", linewidth=0.8,
                   linestyle="--", label=f"Umbral IF {IF_VIB_MAX}")
    ax_vib.legend(fontsize=7, loc="upper left",
                  facecolor=CARD, edgecolor="none", labelcolor=MUTED)
    line_vib, = ax_vib.plot([], [], color="#F4A261", linewidth=1.5)
    ax_vib.set_xlim(0, HISTORY_LEN)
    ax_vib.set_ylim(0, 1023)

    # ── Historial de carga ────────────────────────────────────
    ax_carga.set_facecolor(SURF)
    ax_carga.set_title("Carga (ADC 0–1023)", color=TEXT, fontsize=10, pad=4)
    ax_carga.tick_params(colors=MUTED, labelsize=8)
    ax_carga.spines[:].set_color("#1E4266")
    ax_carga.axhline(IF_CARGA_MAX, color="#E63946", linewidth=0.8,
                     linestyle="--", label=f"Umbral IF {IF_CARGA_MAX}")
    ax_carga.legend(fontsize=7, loc="upper left",
                    facecolor=CARD, edgecolor="none", labelcolor=MUTED)
    line_carga, = ax_carga.plot([], [], color="#9B5DE5", linewidth=1.5)
    ax_carga.set_xlim(0, HISTORY_LEN)
    ax_carga.set_ylim(0, 1023)

    # ── Panel de decisiones IF vs ML ─────────────────────────
    ax_dec.set_facecolor(CARD)
    ax_dec.set_xticks([])
    ax_dec.set_yticks([])
    ax_dec.set_title("Decisión en tiempo real", color=TEXT, fontsize=10, pad=6)
    for sp in ax_dec.spines.values():
        sp.set_color("#1E4266")

    txt_if = ax_dec.text(
        0.5, 0.68, "---", ha="center", va="center",
        fontsize=16, fontweight="bold",
        color=COLORS["---"], transform=ax_dec.transAxes
    )
    ax_dec.text(
        0.5, 0.82, "IF", ha="center", va="center",
        fontsize=9, color=MUTED, transform=ax_dec.transAxes
    )
    txt_ml = ax_dec.text(
        0.5, 0.32, "---", ha="center", va="center",
        fontsize=16, fontweight="bold",
        color=COLORS["---"], transform=ax_dec.transAxes
    )
    ax_dec.text(
        0.5, 0.18, "ML", ha="center", va="center",
        fontsize=9, color=MUTED, transform=ax_dec.transAxes
    )
    ax_dec.axhline(0.5, color="#1E4266", linewidth=0.8)

    txt_div = ax_dec.text(
        0.5, 0.02, "", ha="center", va="bottom",
        fontsize=8, color="#F4A261", transform=ax_dec.transAxes
    )

    # ── Barras de probabilidad ML ─────────────────────────────
    ax_bar.set_facecolor(CARD)
    ax_bar.set_title("Prob. ML por clase", color=TEXT, fontsize=10, pad=6)
    ax_bar.tick_params(colors=MUTED, labelsize=9)
    ax_bar.spines[:].set_color("#1E4266")
    ax_bar.set_xlim(0, 1)
    ax_bar.set_yticks([0, 1, 2])
    ax_bar.set_yticklabels(["NORMAL", "ALERTA", "FALLA"], color=MUTED)
    bar_cols  = [COLORS["NORMAL"], COLORS["ALERTA"], COLORS["FALLA"]]
    bars = ax_bar.barh(
        [0, 1, 2], [0.33, 0.33, 0.34],
        color=bar_cols, alpha=0.75, height=0.55
    )

    # ── Panel de estadísticas ─────────────────────────────────
    ax_info.set_facecolor(CARD)
    ax_info.set_xticks([])
    ax_info.set_yticks([])
    ax_info.set_title("Métricas sesión", color=TEXT, fontsize=10, pad=6)
    for sp in ax_info.spines.values():
        sp.set_color("#1E4266")

    txt_msgs = ax_info.text(
        0.5, 0.80, "Mensajes: 0",
        ha="center", va="center", fontsize=11,
        color=MUTED, transform=ax_info.transAxes
    )
    txt_divcount = ax_info.text(
        0.5, 0.58, "Divergencias: 0",
        ha="center", va="center", fontsize=11,
        color=MUTED, transform=ax_info.transAxes
    )
    txt_divpct = ax_info.text(
        0.5, 0.38, "Tasa div.: 0.0%",
        ha="center", va="center", fontsize=10,
        color="#F4A261", transform=ax_info.transAxes
    )
    txt_vals = ax_info.text(
        0.5, 0.12, "T=--  V=--  C=--",
        ha="center", va="center", fontsize=9,
        color="#90B4CE", transform=ax_info.transAxes,
        fontfamily="monospace"
    )

    # ─────────────────────────────────────────────────────────
    # Función de actualización (llama matplotlib en hilo principal)
    # ─────────────────────────────────────────────────────────
    def actualizar(frame):
        with estado.lock:
            temp_hist  = list(estado.hist_temp)
            vib_hist   = list(estado.hist_vib)
            carga_hist = list(estado.hist_carga)
            dec_if     = estado.decision_if
            dec_ml     = estado.decision_ml
            proba      = estado.proba_ml
            msgs       = estado.msg_count
            divs       = estado.divergencias
            t          = estado.temp
            v          = estado.vib
            c          = estado.carga

        x = list(range(HISTORY_LEN))

        line_temp.set_data(x, temp_hist)
        line_vib.set_data(x, vib_hist)
        line_carga.set_data(x, carga_hist)

        txt_if.set_text(dec_if)
        txt_if.set_color(COLORS.get(dec_if, MUTED))

        txt_ml.set_text(dec_ml)
        txt_ml.set_color(COLORS.get(dec_ml, MUTED))

        if dec_if != dec_ml and dec_if != "---":
            txt_div.set_text("⚡ DIVERGEN")
        else:
            txt_div.set_text("")

        for bar, p in zip(bars, proba):
            bar.set_width(p)

        txt_msgs.set_text(f"Mensajes: {msgs}")
        txt_divcount.set_text(f"Divergencias: {divs}")
        pct = (divs / msgs * 100) if msgs > 0 else 0
        txt_divpct.set_text(f"Tasa div.: {pct:.1f}%")
        txt_vals.set_text(f"T={t:.1f}  V={v}  C={c}")

        return (line_temp, line_vib, line_carga,
                txt_if, txt_ml, txt_div,
                *bars,
                txt_msgs, txt_divcount, txt_divpct, txt_vals)

    return fig, actualizar

# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────
def main():
    from matplotlib.animation import FuncAnimation

    # Conectar MQTT en hilo separado
    client = mqtt.Client(client_id=MQTT_CLIENT)
    client.on_connect = on_connect
    client.on_message = on_message

    print(f"Conectando al broker MQTT {MQTT_BROKER}:{MQTT_PORT}...")
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    except ConnectionRefusedError:
        print("ERROR: No se pudo conectar al broker MQTT.")
        print("Verifica que Mosquitto esté corriendo:  mosquitto -v")
        return

    mqtt_thread = threading.Thread(target=client.loop_forever, daemon=True)
    mqtt_thread.start()

    # Construir y animar dashboard
    fig, actualizar = construir_dashboard()
    ani = FuncAnimation(
        fig, actualizar,
        interval=500,       # actualizar cada 500 ms
        blit=False,
        cache_frame_data=False
    )

    plt.show()
    client.disconnect()

if __name__ == "__main__":
    main()
