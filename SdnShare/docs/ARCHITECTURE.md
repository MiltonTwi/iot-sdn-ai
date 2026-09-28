# Arquitectura — SDN DDoS Detection

## Visión General

Sistema de detección de ataques DDoS basado en Software-Defined Networking (SDN) con pipeline de Machine Learning.

```
┌─────────────┐    ┌─────────────────┐    ┌──────────────┐
│   infra/    │───▶│    pipeline/     │───▶│     ml/      │
│ topology    │    │ collect/process  │    │ train/predict│
│ controller  │    │ build_dataset    │    │ evaluate     │
│ attacks     │    └────────┬────────┘    └──────┬───────┘
│ monitoring  │             │                     │
└─────────────┘             ▼                     ▼
                    ┌──────────────┐      ┌──────────────┐
                    │    data/     │      │  monitoring/ │
                    │ raw/processed│      │   Grafana    │
                    │   models/    │      │  Prometheus  │
                    └──────────────┘      └──────────────┘
```

## Estructura de Directorios

| Directorio | Responsabilidad |
|---|---|
| `infra/controller/` | Aplicaciones Ryu (spine-leaf switches) |
| `infra/topology/` | Topologías Mininet |
| `infra/attacks/` | Escenarios de ataque (YAML + generador) |
| `infra/configs/` | Configuraciones de red y monitoring |
| `infra/monitoring/` | Apps Ryu para exportar métricas |
| `infra/dashboards/` | Dashboards Grafana + config Graphite |
| `pipeline/` | Captura, procesamiento, construcción de dataset |
| `ml/` | Modelos, entrenamiento, evaluación, inferencia |
| `data/` | Datos crudos, procesados y modelos entrenados |
| `scripts/` | Utilidades standalone |
| `tests/` | Tests unitarios e integración |
| `docs/` | Documentación del proyecto |

## Pipeline de Datos

```
[infra/topology] + [infra/controller]
         │
         ▼
[infra/attacks/generate.py]     ← tráfico normal + malicioso
         │
         ▼
[pipeline/collect.py]            ← captura → data/raw/{run_id}/
         │
         ▼
[pipeline/process.py]            ← features → data/processed/{run_id}/
         │
         ▼
[pipeline/build_dataset.py]      ← dataset final .csv
         │
         ▼
[ml/train.py]                    ← modelo → data/models/
         │
         ▼
[ml/evaluate.py]                 ← métricas, ROC
         │
         ▼
[ml/predict.py]                  ← inferencia en tiempo real
```

## Quick Start

```bash
make setup    # Levanta controller + mininet
make topo     # Inicia topología spine-leaf
make up       # Levanta todo (incluyendo monitoring)
make help     # Ver todos los comandos disponibles
```
