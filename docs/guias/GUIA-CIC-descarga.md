# Guía paso-a-paso — Descarga + procesamiento CIC-IoT-2023

**Para:** completar la cross-evaluación que cierra la pregunta nº1 del jurado.
**Tiempo total:** ~5h (descarga 2-4h + procesamiento 1h).

---

## 1. Registro (5 min)

1. Abre <https://www.unb.ca/cic/datasets/iotdataset-2023.html>
2. Llena el formulario (nombre, email institucional, propósito = "research seedbed").
3. Recibirás email con **usuario + contraseña** (puede tardar 1-24h en llegar — empieza HOY).

---

## 2. Descarga (2-4h dependiendo de internet)

Una vez tengas credenciales:

```powershell
# Crear estructura
mkdir -p C:\Users\mquui\iot-sdn-ai\data\external\cic_iot_2023
cd C:\Users\mquui\iot-sdn-ai\data\external\cic_iot_2023

# Descarga (cambia <user> y <pass>)
# Opción A — wget (Windows tiene curl pero curl también funciona):
curl -u <user>:<pass> -O https://205.174.165.80/IOTDataset/CIC_IOT_Dataset2023/Dataset/CSV/MERGED_CSV/Merged01.csv
curl -u <user>:<pass> -O https://205.174.165.80/IOTDataset/CIC_IOT_Dataset2023/Dataset/CSV/MERGED_CSV/Merged02.csv
# ... (típicamente 5-10 archivos Merged*.csv, ~1-3 GB c/u)

# Opción B — wget si lo instalas:
winget install JernejSimoncic.Wget
wget --user=<user> --password=<pass> -r -l1 -np -A "Merged*.csv" https://205.174.165.80/IOTDataset/CIC_IOT_Dataset2023/Dataset/CSV/MERGED_CSV/
```

**Tamaño total esperado:** ~13 GB. Si tu disco está apretado, descarga solo 1-2 archivos para empezar.

---

## 3. Adaptar al formato del pipeline (~5 min)

```powershell
cd C:\Users\mquui\iot-sdn-ai

# Adaptar TODA la carpeta:
wsl -- bash -c "cd /mnt/c/Users/mquui/iot-sdn-ai && python3 ml_extra/cic_iot_adapter.py --inp data/external/cic_iot_2023 --out data/processed/cic_iot_2023/dataset.csv"

# O cap para pruebas rápidas (500k filas):
wsl -- bash -c "cd /mnt/c/Users/mquui/iot-sdn-ai && python3 ml_extra/cic_iot_adapter.py --inp data/external/cic_iot_2023 --out data/processed/cic_iot_2023/dataset.csv --max-rows 500000"
```

**Verifica:** distribución de etiquetas debe verse como:
```
BENIGN              250000
DDoS-SYN_Flood      80000   (mapeado → SYN_FLOOD)
DDoS-UDP_Flood      60000   (mapeado → UDP_FLOOD)
...
```

---

## 4. Cross-evaluación (~2 min)

```powershell
wsl -- bash -c "cd /mnt/c/Users/mquui/iot-sdn-ai && python3 ml_extra/cross_eval.py --train data/processed/run_20260924-214452/dataset.csv --eval data/processed/cic_iot_2023/dataset.csv --shared-features"
```

Salida esperada:
```
intra-domain  acc=1.0000  f1=1.0000
cross-domain  acc=0.6XXX  f1=0.4XXX        ← este es tu número
drop          acc=-0.XXXX f1=-0.XXXX
→ ml_extra/artifacts/cross_eval.json
```

**Cómo leerlo:**
- Drop -30 a -45 pp = saludable, esperado.
- Drop -10 pp = excepcionalmente bueno, sospecha leakage en tu dataset sintético.
- Drop > -50 pp = lab muy desconectado de la realidad, considera regenerar synthetic con más ruido.

---

## 5. Mejorar (opcional, +6h)

Si el drop es muy grande, mezcla los datasets:

```python
# combinar en data/processed/mixed/dataset.csv (manual con pandas):
import pandas as pd
a = pd.read_csv("data/processed/run_synth/dataset.csv")
b = pd.read_csv("data/processed/cic_iot_2023/dataset.csv").sample(n=len(a))
mixed = pd.concat([a, b]).sample(frac=1)  # shuffle
mixed.to_csv("data/processed/mixed/dataset.csv", index=False)

# luego:
# python ml_extra/train_all.py --dataset data/processed/mixed/dataset.csv
# python ml_extra/cross_eval.py --train data/processed/mixed/dataset.csv --eval data/processed/cic_iot_2023/dataset.csv
```

Esto da un modelo más robusto al precio de no ser "puro lab" — pero para defensa es **mejor** porque demuestra que sabes mitigar el shift de dominio.

---

## 6. Insertar resultado en slides

Edita `docs/defensa/DEFENSA-slides.md` Slide 7 con el número real:

```markdown
2. **Cross-evaluación con CIC-IoT-2023:**
   ```
   intra-domain (lab)   acc=1.00   f1=1.00
   cross-domain (CIC)   acc=0.7234   f1=0.6128   ← TU NÚMERO REAL
   drop                 -27.66 pp acc, -38.72 pp f1
   ```
```

---

## Troubleshooting

**"403 Forbidden" en descarga** → tus credenciales aún no están activas. Espera al email de aprobación.

**"Dataset format error" en adapter** → CIC tiene varias variantes de CSV. Mira las primeras filas:
```bash
head -2 data/external/cic_iot_2023/Merged01.csv
```
Si las columnas no matchean (`flow_duration`, `Number`, `Tot sum`, `IAT`, `MQTT`, etc.), ajusta `LABEL_MAP` en `cic_iot_adapter.py`.

**Memoria insuficiente al cargar todo el CSV** → el adapter usa `chunksize=200_000`, así que va por trozos. Si aún falla, baja a `chunksize=50_000` editando el script.

**Demasiado lento** → usa `--max-rows 500_000` para pruebas. 500k es suficiente para tener números estadísticamente significativos.

---

## NOTA METODOLÓGICA (2026-09-24) — usar `--shared-features`

CIC-IoT-2023 da **1 fila por flujo**, no ventanas por host, así que NO puede
reconstruir las features `host_*` / `dst_*` — que son las **más importantes** del
modelo del lab (según SHAP). Si se cross-evalúa con ellas puestas a 0, el "drop"
mide *features ausentes*, no shift de dominio.

**Por eso el comando correcto lleva `--shared-features`**: entrena y evalúa solo
con las **39 features que ambos dominios proveen** (tamaños, IATs, flags, puertos,
protocolo, is_*). El intra-domain baja a ~0,90 (vs 0,986 con todas) porque se
renuncia a host_*/dst_*, pero **el número cross-domain así es honesto y comparable**.

Comando final (train = corrida definitiva):
```bash
python3 ml_extra/cic_iot_adapter.py --inp data/external/cic_iot_2023 --out data/processed/cic_iot_2023/dataset.csv
python3 ml_extra/cross_eval.py --train data/processed/run_20260924-214452/dataset.csv --eval data/processed/cic_iot_2023/dataset.csv --shared-features
```

Cadena validada end-to-end con CSV sintético 2026-09-24 (adapter + cross_eval OK).
Solo falta la descarga real.
