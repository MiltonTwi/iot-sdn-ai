# Diagrama final — flujo end-to-end

```
┌──────────────────────────────────────────────────────────────────────┐
│                      DECLARATIVO  (versionable)                      │
│   iot/zones.yaml   iot/attacks/catalog.yaml                          │
└──────────────────────────┬───────────────────────────────────────────┘
                           │ generate_topology.py
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│  network_config.iot.yaml   (auto-generado, 10 sw + 70 hosts)         │
└──────────────────────────┬───────────────────────────────────────────┘
                           │ mn_iot_topo.py --auto-traffic
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│            DOCKER STACK (SdnShare + override)                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────┐ │
│  │ controller   │  │ mininet      │  │ prom+grafana │  │ dashboard│ │
│  │ Ryu+FlowMgr  │◀─│ 70 hosts     │─▶│ + alerts IoT │  │ FastAPI  │ │
│  │ :8080        │  │ 14 attackers │  │ :3000 :9090  │  │ :8000 WS │ │
│  └──────────────┘  └──────┬───────┘  └──────────────┘  └────┬─────┘ │
└────────────────────────────┼─────────────────────────────────┼──────┘
                             │ tshark PCAP                     │
                             ▼                                 │
                  data/raw/{run}/capture.pcap                  │
                             │                                 │
                             │ flow_extractor.py               │
                             ▼                                 │
                  data/processed/{run}/flows.csv               │
                             │                                 │
                             │ label_dataset.py                │
                             │ (cruza /tmp/attack_*.json)      │
                             ▼                                 │
                  flows_labeled.csv                            │
                             │                                 │
                             │ feature_engineering.py          │
                             ▼                                 │
                  dataset.csv  ───────────────┐                │
                                              │                │
                       ml_extra/train_all.py  │                │
                                              ▼                │
                       ┌────────────────────────────────┐      │
                       │  ml_extra/artifacts/           │      │
                       │   rf.joblib    xgb.joblib      │      │
                       │   mlp.joblib   isoforest.joblib│──────┤
                       │   autoencoder.joblib           │      │
                       │   metrics.json                 │      │
                       └────────────────────────────────┘      │
                                              │                │
                                              └────────────────┘
                                                       │
                                                       ▼
                                            ┌────────────────────┐
                                            │  PC navegador      │
                                            │  http://localhost  │
                                            └─────────┬──────────┘
                                                      │ LAN o tunnel
                                                      ▼
                                            ┌────────────────────┐
                                            │  📱 celular        │
                                            └────────────────────┘
```

## Camino crítico (start_all.ps1)

```
env_check → generate_topology → docker up → mininet topo → 14 ataques
   ↓             ↓                 ↓             ↓             ↓
  10s          <1s              ~30s         ~15s         ~25min
                                                            ↓
                            tshark capture (en paralelo con ataques)
                                                            ↓
                                                       pipeline (~2min)
                                                            ↓
                                                       train (~3min)
                                                            ↓
                                                  dashboard listo
```
