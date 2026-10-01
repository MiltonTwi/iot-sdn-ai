# IoT-SDN-AI: automatic detection and mitigation of IoT attacks with machine learning over SDN

**English** · [Español](README.md)

Reproducible lab that **emulates a 67-host IoT network over SDN, generates benign traffic and 14 attack scenarios, trains detection models and wires them into the controller to mitigate attacks in a closed loop, with no human intervention**.

Undergraduate thesis project — Systems Engineering, Universidad Cooperativa de Colombia (2026).
Author: Milton Alberto Quintero Estrada · Advisor: Ph.D. Néstor Alzate Mejía.

<p align="center">
  <img src="docs/tesis/figuras/lazo_cerrado.png" alt="Closed detection and mitigation loop" width="820">
</p>

## Main results

| Metric | Value | Protocol |
|---|---|---|
| Multiclass F1-macro (Random Forest, 14 classes) | **0.986 ± 0.014** | Episode-grouped CV, 5 folds (no data leakage) |
| Attack/benign detection F1 | **0.995** (AUC 0.999) | Lab |
| Generalization to CIC-IoT-2023 | **F1 0.940** · AUC 0.948 | 39 shared features |
| Detector at realistic prevalence (1 % attacks, XGBoost) | recall **0.996** at precision ≥ 0.9 | Benign re-weighting |
| Closed loop: attacks detected and mitigated | **39/39** · 0 false alarms · 0 collateral rules | 3 runs × (120 s benign + 13 real attacks) + 600 s benign |
| Time to mitigation | median **2.5 s** (4.7 s with 5 s window) | Attack start → OpenFlow rule installed |
| Attack traffic reduction | median **95.2 %** | Measured at victim / reflector |
| Inference latency | ~0.7 ms per batch | — |

Details, limitations and all figures: [`docs/resultados/RESULTADOS-FINAL.en.md`](docs/resultados/RESULTADOS-FINAL.en.md).

## Architecture

<p align="center">
  <img src="docs/tesis/figuras/topologia.png" alt="Spine-leaf topology" width="820">
</p>

- **Network:** Mininet + Open vSwitch, spine-leaf topology of 10 OpenFlow 1.3 switches with RSTP; 60 simulated IoT devices in 7 zones (MQTT, CoAP, HTTP, DNS, NTP, SSDP, Modbus) and 6 servers.
- **Control:** Ryu with three apps — L2 switching, mitigation (DROP / LIMIT with OpenFlow meters, REST API) and IP-MAC anti-spoofing.
- **Attacks:** 14 scenarios in 8 families (floods, slowloris, scanning, DNS/CoAP/SSDP amplification, MQTT abuse, brute force, Mirai botnet, ARP spoofing), run in episodes with rotated sources.
- **Data:** mirror-port capture → streaming flow extractor → manifest-based labeling → 50 features per flow.
- **Models:** Random Forest, XGBoost, MLP, Isolation Forest and AutoEncoder; live two-stage architecture (XGBoost detects, Random Forest attributes the type).

<p align="center">
  <img src="docs/tesis/figuras/pipeline.png" alt="Data pipeline" width="820">
</p>

## Repository layout

```
.
├── iot/                    # IoT lab
│   ├── zones.yaml          #   zone and device catalog
│   ├── topology/           #   topology generator and importer, Mininet launcher
│   ├── devices/            #   device and server simulators
│   ├── attacks/            #   attack catalog and scenarios
│   ├── controller/         #   Ryu apps: L2, mitigation, anti-spoofing
│   └── pipeline/           #   mirror, flow extraction, labeling, features
├── ml_extra/               # Training, evaluation and closed loop
│   ├── models/             #   definitions of the 5 models
│   ├── artifacts/          #   metrics (JSON), figures and generated reports
│   ├── eval_grouped_cv.py  #   grouped cross-validation (leak-free)
│   ├── live_detector.py    #   two-stage live detector
│   └── closed_loop_eval.py #   closed-loop experiment
├── dashboard/              # Web panel (FastAPI) + Grafana/Prometheus
├── scripts/                # Orchestration, benchmarks and mitigation tests
│   └── debug/              #   lab diagnostic utilities
├── tests/                  # Unit tests (pytest)
├── docs/                   # Documentation (see docs/README.en.md)
├── SdnShare/               # Base SDN lab (third party)
├── Makefile, Makefile.iot  # All commands: `make help`
└── docker-compose.override.yaml
```

## Quick start

Requirements: Linux VM (Ubuntu 22.04 tested, ≥ 4 GB RAM, ~30 GB disk) with Docker and Docker Compose.

```bash
make help                               # list commands
make iot-up                             # controller + Mininet container
make iot-topo                           # IoT topology with automatic benign traffic
make iot-attack SCN=syn_flood           # launch one scenario
bash scripts/rerun_pipeline.sh          # full run: attacks + capture + dataset
make iot-train RUN=<run_id>             # train the 5 models
make iot-closed-loop                    # closed-loop experiment (13 attacks)
CHUNK=2 COOLDOWN=60 bash scripts/closed_loop_reps.sh 3 1   # 3 runs; aggregate with ml_extra/closed_loop_aggregate.py
make iot-test                           # unit tests
```

Full lab guide: [`docs/guias/laboratorio.en.md`](docs/guias/laboratorio.en.md).

## Reproducibility

- ML analysis must run with the exact versions in [`requirements-ml.txt`](requirements-ml.txt) (scikit-learn 1.7.2, XGBoost 3.2.0): other versions change the grouped split and the serialized models become incompatible.
- Fixed seeds (42) for splits, sampling and models.
- Data (PCAP, flows and dataset, ~9 GB) and `.joblib` models are not versioned: they are regenerated with `scripts/rerun_pipeline.sh` and `make iot-train`. The resulting metrics and figures are in `ml_extra/artifacts/`.
- External validation: [`docs/guias/GUIA-CIC-descarga.md`](docs/guias/GUIA-CIC-descarga.md) (Spanish).

## Documentation

English versions are available for this README, the [docs index](docs/README.en.md), the [lab guide](docs/guias/laboratorio.en.md) and the [final results](docs/resultados/RESULTADOS-FINAL.en.md). The remaining documents are in Spanish.

| Document | Content |
|---|---|
| [`docs/pasos/`](docs/pasos) | Step-by-step lab construction (15 guides) |
| [`docs/resultados/`](docs/resultados) | Final results, improvement plan and mitigation evidence |
| [`docs/tesis/`](docs/tesis) | System diagrams (`figuras/diagramas.py`) and re-run runbook |

The thesis document will be published after its defense.

## Citation

See [`CITATION.cff`](CITATION.cff).

## License and credits

Original code under the [MIT](LICENSE) license. The `SdnShare/` directory is the base lab from [SdnShare](https://github.com/JosephRodriri/SdnShare); that repository declares no license and is included with credit to its author.
