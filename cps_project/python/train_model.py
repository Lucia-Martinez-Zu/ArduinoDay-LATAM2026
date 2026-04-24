"""
============================================================
  CPS Inteligente — Entrenamiento del modelo ML
  Genera dataset sintético y entrena Random Forest

  Uso:
    python train_model.py

  Salida:
    modelo_cps.pkl   → modelo entrenado listo para inferencia
    scaler_cps.pkl   → StandardScaler ajustado

  Clases:
    0 → NORMAL
    1 → ALERTA   (firma multivariada: todos ligeramente elevados)
    2 → FALLA    (valores claramente fuera de rango)
============================================================
"""

import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix

RANDOM_SEED = 42
N_SAMPLES   = 3000
np.random.seed(RANDOM_SEED)

# ─────────────────────────────────────────────────────────────
# 1. Generar dataset sintético
#    Variables: temperatura (°C), vibración (0-1023), carga (0-1023)
#
#    NORMAL  → temp 20-31, vib 50-600,  carga 50-500
#    ALERTA  → valores próximos a umbral individual pero NINGUNO
#              supera el umbral solo → la firma es su combinación
#              temp 31-35, vib 600-749, carga 490-639
#    FALLA   → al menos dos sensores claramente fuera de rango
#              temp >35,   vib >750,    carga >640
# ─────────────────────────────────────────────────────────────
def generar_clase(n, clase):
    if clase == 0:  # NORMAL
        temp  = np.random.uniform(20,  31,  n)
        vib   = np.random.uniform(50,  600, n)
        carga = np.random.uniform(50,  500, n)
    elif clase == 1:  # ALERTA — firma multivariada
        temp  = np.random.uniform(31,  35,  n)
        vib   = np.random.uniform(600, 749, n)
        carga = np.random.uniform(490, 639, n)
    else:  # FALLA
        temp  = np.random.uniform(35,  60,  n)
        vib   = np.random.uniform(750, 1023,n)
        carga = np.random.uniform(640, 1023,n)

    # Añadir ruido gaussiano realista
    temp  += np.random.normal(0, 0.5,  n)
    vib   += np.random.normal(0, 10,   n).astype(int)
    carga += np.random.normal(0, 10,   n).astype(int)

    # Clampear a rangos físicos
    temp  = np.clip(temp,  10, 70)
    vib   = np.clip(vib,   0,  1023)
    carga = np.clip(carga, 0,  1023)

    labels = np.full(n, clase)
    return temp, vib, carga, labels

n_normal = int(N_SAMPLES * 0.45)
n_alerta = int(N_SAMPLES * 0.30)
n_falla  = N_SAMPLES - n_normal - n_alerta

t0,v0,c0,l0 = generar_clase(n_normal, 0)
t1,v1,c1,l1 = generar_clase(n_alerta, 1)
t2,v2,c2,l2 = generar_clase(n_falla,  2)

temp  = np.concatenate([t0, t1, t2])
vib   = np.concatenate([v0, v1, v2])
carga = np.concatenate([c0, c1, c2])
label = np.concatenate([l0, l1, l2])

df = pd.DataFrame({
    "temperatura": temp,
    "vibracion":   vib,
    "carga":       carga,
    "estado":      label
})
df = df.sample(frac=1, random_state=RANDOM_SEED).reset_index(drop=True)

print(f"Dataset generado: {len(df)} muestras")
print(df["estado"].value_counts().rename({0:"NORMAL",1:"ALERTA",2:"FALLA"}))
print()

# ─────────────────────────────────────────────────────────────
# 2. Preparar features y escalado
# ─────────────────────────────────────────────────────────────
X = df[["temperatura","vibracion","carga"]].values
y = df["estado"].values

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.20, random_state=RANDOM_SEED, stratify=y
)

scaler = StandardScaler()
X_train_s = scaler.fit_transform(X_train)
X_test_s  = scaler.transform(X_test)

# ─────────────────────────────────────────────────────────────
# 3. Entrenar Random Forest
# ─────────────────────────────────────────────────────────────
modelo = RandomForestClassifier(
    n_estimators = 100,
    max_depth    = 10,
    min_samples_leaf = 5,
    class_weight = "balanced",
    random_state = RANDOM_SEED,
    n_jobs       = -1
)

print("Entrenando Random Forest...")
modelo.fit(X_train_s, y_train)

# ─────────────────────────────────────────────────────────────
# 4. Evaluar
# ─────────────────────────────────────────────────────────────
y_pred = modelo.predict(X_test_s)

nombres = ["NORMAL", "ALERTA", "FALLA"]
print("\n── Reporte de clasificación ──────────────────────────")
print(classification_report(y_test, y_pred, target_names=nombres))

print("── Matriz de confusión ───────────────────────────────")
cm = confusion_matrix(y_test, y_pred)
print(pd.DataFrame(cm, index=nombres, columns=nombres))

importancias = modelo.feature_importances_
print("\n── Importancia de variables ──────────────────────────")
for nombre, imp in zip(["Temperatura","Vibración","Carga"], importancias):
    bar = "█" * int(imp * 40)
    print(f"  {nombre:<12} {bar}  {imp:.3f}")

# ─────────────────────────────────────────────────────────────
# 5. Guardar modelo y scaler
# ─────────────────────────────────────────────────────────────
joblib.dump(modelo,  "modelo_cps.pkl")
joblib.dump(scaler,  "scaler_cps.pkl")

print("\nModelo guardado en:  modelo_cps.pkl")
print("Scaler guardado en:  scaler_cps.pkl")
print("\nListo para usar con dashboard.py")
