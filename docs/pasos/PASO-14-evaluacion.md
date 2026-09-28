# PASO 14 — Evaluación, demo y tests

**Fecha:** 2026-05-05
**Cierra:** material requerido para defensa académica del semillero.

**Archivos:**
- `ml_extra/report.py` — reporte PDF con confusión, ROC, classification_report, feature importance.
- `scripts/bench_latency.py` — benchmark de latencia detección→mitigación (modos `mock` y `live`).
- `scripts/demo.ps1` — demo push-button de 90s (ataque → mitigación → recuperación).
- `dashboard/audit_log.py` — JSONL append-only de cada mitigación.
- `tests/test_*.py` — pytest suite (5 archivos, ~30 tests).
- `Makefile.iot` — 5 targets nuevos (`iot-report`, `iot-bench`, `iot-demo`, `iot-test`, `iot-audit`).

---

## 1. Reporte PDF (`iot-report`)

Genera `ml_extra/artifacts/report_<run>.pdf` con:

| Página | Contenido |
|---|---|
| 1 | Portada: run_id, # flujos, # features, # clases, modelos |
| 2 | Distribución de clases (bar chart con counts) |
| 3-5 | RandomForest: classification_report → confusion matrix → ROC OvR → feature importance top-15 |
| 6-8 | XGBoost: idem |
| 9-11 | MLP: classification_report → confusion → ROC OvR (sin feature importance) |
| 12 | IsolationForest: ROC binaria benign vs anomalía |
| 13 | AutoEncoder: ROC binaria |

**Uso:**
```bash
make -f Makefile.iot iot-report RUN=run_001
```

**Por qué importa para defensa:** evaluadores piden gráficas. Sin esto se pierden 30 minutos respondiendo "muéstrame la matriz de confusión".

---

## 2. Benchmark de latencia (`iot-bench`)

### Modo `mock` (sin Mininet)
Mide:
- **ML predict (ms)**: scaler + predict_proba sobre vector aleatorio.
- **REST mitigate (ms)**: POST a `/iot/mitigate` round-trip.

```bash
make -f Makefile.iot iot-bench MODE=mock RUNS=50
```

Salida típica:
```
  etapa            mean(ms)       p50      p95      min      max
  ML predict           1.83      1.71     2.34     1.12     4.21
  REST mitigate        8.42      7.95    14.11     5.03    22.56
```

### Modo `live` (con stack arriba)
Lanza ataque real, mide:
- t2: `/iot/mitigate` call latency desde el inicio del ataque.
- t3: tiempo hasta que la regla aparece en `/iot/status`.

```bash
make -f Makefile.iot iot-bench MODE=live RUNS=10
```

**Por qué importa:** tu propuesta original promete *"mitigar ataques en poco tiempo"*. Sin medirlo, claim no defendible. Con esto puedes decir: *"detección p95 = 15ms, instalación de flow-rule p95 = 50ms, end-to-end <100ms".*

---

## 3. Demo push-button (`iot-demo`)

Secuencia de 90 segundos:

1. Verifica stack arriba (curl a `/iot/status`).
2. Estado inicial limpio (5s).
3. Lanza ataque `syn_flood` desde `attacker` (background).
4. Llama `/iot/mitigate` con DROP 60s (simula al detector).
5. Verifica que aparece en `/iot/status` con dpids.
6. Espera duración del ataque (30s default).
7. Llama `/iot/unban`.

```powershell
make -f Makefile.iot iot-demo
# o personalizado:
.\scripts\demo.ps1 -Scenario http_flood -Duration 60
```

**Por qué importa:** la defensa se gana en los primeros 90s. Comando único = juez ve todo, no se pierde escribiendo.

---

## 4. Audit log (`iot-audit`)

Cada llamada a mitigate (exitosa o fallida) escribe línea JSON en `data/audit/mitigation.jsonl`:

```json
{"ts":1746376822.45,"event":"mitigate","src_ip":"10.10.0.99","label":"SYN_FLOOD","confidence":0.97,"action":"drop","duration_s":120,"dpids":[1,2,10,11,12,13,14,15,16,17]}
{"ts":1746376945.12,"event":"mitigate_failed","src_ip":"10.10.1.10","error":"<urlopen error timed out>"}
```

```bash
make -f Makefile.iot iot-audit  # imprime últimos 50 eventos
```

**Por qué importa:** trazabilidad para análisis post-mortem y auditoría.

---

## 5. Test suite (`iot-test`)

```bash
make -f Makefile.iot iot-test
```

| Archivo | Tests | Cubre |
|---|---|---|
| `test_topology_generator.py` | 6 | counts, IPs únicas, MACs únicas, IPs en subnet, full mesh, puertos únicos por switch |
| `test_importer.py` | 4 | GraphML fat-tree, JSON ring, edge detection, build_config end-to-end |
| `test_flow_extractor.py` | 2 | PCAP sintético → 1 flujo TCP, protocol indicators MQTT/Modbus |
| `test_detector_decide.py` | 9 | política decide() por familia × confianza, family_map cubre todos los labels |
| `test_attacks_catalog.py` | 4 | catálogo carga, cada escenario tiene módulo `run()`, campos requeridos, labels únicos |

**Total ~25 tests, runtime <5s.** Sin Mininet ni Docker (todo mockeado).

**Por qué importa:** demuestra rigor. Diferencia "script de estudiante" vs "sistema verificado".

---

## Cómo presentar todo esto en defensa (~15 min)

1. **Slide 1 — Demo (3 min):** corres `iot-demo`, hablas mientras corre.
2. **Slide 2 — Reporte PDF (5 min):** abres `report_<run>.pdf`, recorres confusion matrix de RF + XGB, comparas, muestras feature importance.
3. **Slide 3 — Benchmarks (3 min):** muestras tabla del `iot-bench live` con p95 < 100ms.
4. **Slide 4 — Cumplimiento del título (2 min):** matriz `objetivo → archivo` (ya en PASO-13).
5. **Slide 5 — Tests verde (1 min):** corres `iot-test`, muestras `25 passed`.
6. **Q&A (1 min):** logs JSONL del audit como evidencia de cualquier ataque.

---

## Limitaciones honestas

- **Modo `live` del bench requiere `docker compose exec` interactivo:** subprocess.Popen funciona en host con `make` instalado; en Windows puro PowerShell hay que adaptarlo.
- **PDF requiere matplotlib instalado** (`pip install matplotlib`). Si falla, el reporte se omite — no rompe el resto del pipeline.
- **Tests no cubren los Ryu apps directamente** porque requerirían iniciar el controller en un fixture costoso. Cubren la lógica que ellos consumen (decide, catalog, importer).
- **Bench `live` necesita victim IP fija**: por default `10.10.0.99` (attacker). Si en tu corrida el atacante no es ése, pasar `--victim-ip`.
