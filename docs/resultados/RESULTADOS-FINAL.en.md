# Final results — IoT-SDN-AI

**English** · [Español](RESULTADOS-FINAL.md)

**Current figures (October 2026).** This summary is authoritative; the following sections are the
chronological record of the work and some have been superseded (noted in their title).

| Area | Result | Protocol / artifact |
|---|---|---|
| Dataset | 505,768 flows, 14 classes, 50 features, 6 episodes per attack | `run_20260924-214452` |
| Multiclass classification | **RF F1-macro 0.986 ± 0.014** (accuracy 0.986 ± 0.018); MLP 0.968 ± 0.039; XGB 0.958 ± 0.048 | Grouped CV, 5 folds · `cv_grouped*.json` |
| Attack/benign detection | F1 0.995 · AUC 0.999 (in-domain); threshold 0.10 → FPR 3.96 % | `cross_eval_cic.json`, `threshold_fp.json` |
| 1 % prevalence | XGB recall 0.996 at precision ≥ 0.9 (PR-AUC 0.998); RF precision 0.20 → XGB detects, RF attributes | `base_rate.json` |
| External CIC-IoT-2023 | Detection F1 0.940 · AUC 0.948 · precision 0.999; attribution does not transfer (0.016) | `cross_eval_cic.json` |
| Calibration / bootstrap | RF Brier 0.0022; F1-macro 0.979 [0.978, 0.980] | `calibration_metrics.json`, `bootstrap_ci.json` |
| Robustness | RF 0.979 → 0.210 at σ = 1 | `adversarial_metrics.json` |
| Rule-based baseline | accuracy 0.244 · F1 0.066 | `naive_metrics.json` |
| **Closed loop (final config, 2 s window)** | **39/39 mitigated, 0 false alarms (960 s benign), 243/243 rules, median TTM 2.5 s, 95.2 % reduction** | 3 runs, 60 s cooldown · `closed_loop_cd60_c2_reps.json` |
| Closed loop (5 s window) | 39/39, 0 false alarms, median TTM 4.7 s, 94.6 % reduction | `closed_loop_cd60_c5_reps.json` |

---

## Record: run_20260924-214452 (working document)

**Generated:** 2026-09-24 · **Definitive run** (EPISODES=6). Supersedes
`run_20260924-192239` (see `RESULTADOS-run_20260924-192239.md`, EPISODES=5).

Dataset: `data/processed/run_20260924-214452/dataset.csv` — **505,768 rows, 14
classes, ALL with 6 groups** (BENIGN 62). CRED_BRUTEFORCE 72 → 50,000 flows.
127.7 M packets → 18.1 M flows.

---

## Headline (grouped 5-fold CV, leak-free)

| Model | Accuracy | F1-macro |
|---|---|---|
| **Random Forest** | **0.986 ± 0.018** | **0.986 ± 0.014** |
| XGBoost | 0.982 ± 0.020 | 0.958 ± 0.048 |

RF becomes the **main model**: higher F1-macro and **more stable** (σ 0.014 vs
0.048 for XGB). Improvement over EPISODES=5 (RF was 0.976 ± 0.031) due to more diversity.

### Per class — RF (mean F1, testable folds)

| Class | F1 | recall | folds |
|---|---|---|---|
| HTTP_FLOOD | 1.000 | 1.000 | 3/5 |
| MQTT_MALFORMED | 1.000 | 1.000 | 4/5 |
| MQTT_SUBSCRIBE_FLOOD | 1.000 | 1.000 | 4/5 |
| CREDENTIAL_BRUTEFORCE | 1.000 | 1.000 | 4/5 |
| PORT_SCAN | 1.000 | 1.000 | 4/5 |
| SSDP_AMPLIFICATION | 1.000 | 1.000 | 4/5 |
| COAP_AMPLIFICATION | 0.999 | 1.000 | 3/5 |
| DNS_AMPLIFICATION | 0.999 | 0.999 | 3/5 |
| ICMP_FLOOD | 0.994 | 0.998 | 4/5 |
| SLOWLORIS | 0.991 | 0.983 | 3/5 |
| UDP_FLOOD | 0.991 | 0.984 | 4/5 |
| SYN_FLOOD | 0.986 | 1.000 | 4/5 |
| BENIGN | 0.941 | 0.924 | 5/5 |
| MIRAI_COORDINATED | 0.878 | 0.942 | 3/5 |

Amplification solved (F1 ~1.0). BENIGN improved (F1 0.893 → 0.941; recall
0.837 → 0.924). Weakest now: MIRAI_COORDINATED (0.878) — confused with
SYN_FLOOD (both TCP floods).

Single-split fold-0 (reference): RF 0.986/0.979 · XGB 0.998/0.994 · MLP 0.999/0.998.

---

## Binary detection (ATTACK vs BENIGN) and benign FP — SOLVED

Two-stage, default threshold (argmax): recall 0.999 · precision 0.978 · **F1
0.988 ± 0.014** · benign FPR 0.140.

**Threshold tuning (`threshold_fp.py`, RF):** lowering the decision threshold on
P(attack) to **thr = 0.102**:

| Metric | Value |
|---|---|
| Recall (attack) | 1.000 |
| Precision | 0.999 |
| **Benign FPR** | **0.040 (3.96 %)** |
| F1 | 0.999 |

Benign FP drops from ~14 % to **< 4 %** while keeping recall ~100 %. **The false-positive
problem is solved via the operating point**, without retraining.

---

## Other analyses (regenerated on this run)

- **Bootstrap CI (fold-0):** RF F1-macro 0.979 [0.978, 0.980]; XGB 0.994 [0.993, 0.995].
- **Calibration (Brier):** RF 0.0022 · XGB 0.0018 (reliable probabilities).
- **Adversarial robustness** (Gaussian noise on continuous features only, RF): 0.979 → 0.879
  (σ 0.01) → 0.533 (σ 0.1) → 0.210 (σ 1.0). Motivates future adversarial training.
- **Latency:** ML inference 0.67 ms (p95 1.44), REST mitigation 3.54 ms.
- **Naive rule-based:** acc 0.244 / F1 0.066 on the corrected dataset → fixed rules
  are not enough; ML adds value.
- **Mitigation (quantitative evidence):** victim 895,587 pkts baseline → **0 after
  DROP (100 % reduction)**, 10 rules (one per switch).
- **SHAP:** behavioral features dominate (host_flows_5s, syn_count, proto) →
  no leakage through attacker identity.
- Artifacts in `ml_extra/artifacts/`: metrics.json, cv_grouped.json, two_stage.json,
  threshold_fp.json, bootstrap_ci.json, calibration_metrics.json, adversarial_metrics.json,
  naive_metrics.json, mitigation_evidence.json, report_run_20260924-214452.pdf, PNGs.

---

## Open items status

- [x] Train/test leakage → CV grouped by episode/device.
- [x] Amplification (capture + labeling) → F1 ~1.0.
- [x] Flow diversity → 6 groups/class (all), stable CV (σ 0.014).
- [x] CREDENTIAL_BRUTEFORCE → 50,000 flows (live-hosts fix).
- [x] **Benign FP** → 3.96 % via threshold (was ~16 %).
- [x] Naive / bootstrap / latency → regenerated.
- [x] Mitigation → 100 % reduction evidence.
- [x] ARP_SPOOF → documented as a limitation (L2, outside the flow classifier;
      the control plane does not catch a non-existent gateway).
- [x] **Cross-eval CIC-IoT-2023** → DONE (Merged01+02, 1.46 M flows, 200k eval cap).
      **Binary detection transfers: attack F1 0.940 · AUC 0.948 · recall 0.887 ·
      precision 0.999** (39 shared features, no host_*/dst_*). Multiclass attribution
      does NOT transfer (acc 0.016) due to extractor incompatibility
      (our tshark vs CIC's CICFlowMeter) → different feature ranges;
      documented limitation, not a model failure. `cross_eval_cic.json`.
- [ ] MIRAI_COORDINATED 0.878 (confused with SYN_FLOOD) — minor limitation, document.

---

## Narrative changes for the thesis (applied)

- Headline: **RF, grouped CV, F1-macro 0.986 ± 0.014** (not single split, not XGB).
- Amplification: from "the hard part (recall 0.00–0.21)" → **solved** (~1.0).
- Benign: report FP and its **mitigation via threshold** (14 % → 4 %).
- Binary detection: F1 0.988; with threshold, FPR < 4 % at recall ~100 %.
- Add a section on **data leakage detection and correction** (near-duplicates +
  broken capture/labeling) — adds rigor.
- Latency 0.67 ms (not 34 ms). Mitigation with quantitative evidence (100 %).
- ARP: scope limitation.

## External validation — CIC-IoT-2023 (DONE)

Cross-dataset on CIC-IoT-2023 (Merged01+02, 1.46 M real flows; 39 shared
features, `--shared-features`):

| Task | Cross-domain |
|---|---|
| **Detection (ATTACK vs BENIGN)** | **F1 0.940 · AUC 0.948 · recall 0.887 · precision 0.999** |
| Attribution (multiclass) | acc 0.016 — does NOT transfer |

**Reading:** **detection capability generalizes to a real external dataset**
(F1 0.94, AUC 0.95), strong evidence that it is not overfitting to the lab. Fine-grained
attribution does not transfer because CIC uses a different flow extractor
(CICFlowMeter) with features of different semantics/ranges — a known cross-dataset
NIDS problem, not a model failure. Report both separately.
`ml_extra/artifacts/cross_eval_cic.json`.

---

## Phase 3 — Realistic base rate + PR-AUC (DONE 2026-09-26)

`ml_extra/base_rate.py` → `ml_extra/artifacts/base_rate.json`. **Run in the VM**
(sklearn 1.7.2): with the host's sklearn 1.9, `StratifiedGroupKFold` yields a different
fold-0 and the pickles don't match → wrong numbers.

Test fold-0 has **96.7 % attack prevalence** (4,616 benign / 133,664 attacks)
→ the reported precision is optimistic. Benign samples are re-weighted to simulate deployment.

**Per-class PR-AUC (one-vs-rest):** macro 0.999 for RF and XGB; worst BENIGN (0.993 / 0.995).

**ATTACK vs BENIGN detection by attack prevalence** (operating threshold = 0.102):

| Prevalence | RF PR-AUC | RF precision | RF recall@P≥0.9 | XGB PR-AUC | XGB precision | XGB recall@P≥0.9 |
|---|---|---|---|---|---|---|
| 96.7 % (test) | 1.000 | 0.999 | 1.000 | 1.000 | 1.000 | 1.000 |
| 50 % | 0.992 | 0.962 | 1.000 | 1.000 | 0.992 | 0.999 |
| 10 % | 0.934 | 0.737 | 1.000 | 0.999 | 0.933 | 0.999 |
| 1 % | 0.563 | 0.203 | **0.000** | 0.998 | 0.557 | 0.996 |
| 0.1 % | 0.113 | 0.025 | **0.000** | 0.996 | 0.111 | 0.996 |

**Reading:**
- RF (multiclass headline) **is not usable as a detector when attacks are rare**: at 1 %
  prevalence it yields ~4 false alarms per real alert and no threshold reaches P ≥ 0.9.
  Its residual FPR (~4 %) comes from benign flows with high P(attack) — thresholding can't fix it.
- XGB separates benign traffic more confidently: PR-AUC ≥ 0.996 even at 0.1 %; re-tuning
  the threshold keeps recall 0.996 at precision ≥ 0.9.
- **Architecture recommendation:** stage 1 detection = XGB (threshold tuned to the
  expected prevalence); stage 2 attribution = RF. Consistent with `two_stage.py`.
- **Caveat:** only 4,616 benign test flows (few devices) → at 0.1 % each
  benign flow weighs ~29,000×; figures at ≤ 1 % have high variance. More diverse benign
  traffic in future runs would tighten them.

## Live closed loop: detection → automatic mitigation (2026-09-26) — figures SUPERSEDED (see summary)

Previously mitigation was triggered **manually** (REST). Now the whole cycle runs
on its own, against real attacks in Mininet:

```
tcpdump (mirror s_iot_0) → flow_extractor --live (persistent state, snapshot every 5 s)
  → feature_engineering → live_detector.py [XGB detects → RF attributes → incident]
  → POST /iot/mitigate → OpenFlow rules on the 10 switches
```

Code: `iot/pipeline/live_capture.sh`, `iot/pipeline/flow_extractor.py --live-dir`,
`ml_extra/live_detector.py`, `ml_extra/closed_loop_eval.py` (+ `closed_loop_rescore.py`).
`make -f Makefile.iot iot-live-start|iot-live-stop|iot-closed-loop`.
Result: `ml_extra/artifacts/closed_loop.json`.

**Experiment:** 120 s benign only + 13 attacks × 30 s, no intervention.

| Metric | Value |
|---|---|
| Attacks detected and mitigated | **13/13** |
| Time to mitigate (TTM) | median **4.0 s**, max 27.9 s (port scan) |
| False alarms (120 s benign, ~5,000 flows) | **0** |
| Correct rules / collateral on benign | **29/29** / **0** |
| Attack traffic reduction at target | median **95.1 %**, min 79.8 % |
| Correct type attribution (1st rule) | 10/13 |
| Latency end of window → rule installed | ~1–1.7 s |

Per scenario (reduction at victim; for amplification, at the reflector):
SYN 99.7 · UDP 100 · ICMP 80.9 · HTTP 97.2 · Slowloris 82.2 · DNS amp 90.2 ·
CoAP amp 79.8 · SSDP amp 94.6 · MQTT sub 97.2 · MQTT malformed 99.7 · Mirai 95.1.
Port scan and brute force: no single victim (only TTM and correctness measured).

**Mitigation policy (minimal match that contains the attack):**
- Destination with ≥ 20 attacking sources (spoofed/distributed source): LIMIT 64 kbps
  on dst+proto; amplification: LIMIT the queries to the reflector (dst+udp+port).
- Single source: DROP (floods, botnet, brute force, MQTT abuse, slowloris; TCP with
  handshake → authentic source). Recon: LIMIT 512 kbps.
- Infrastructure servers are never blocked globally (only pairs).

**Bugs/defects found and fixed along the way:**
1. **LIMIT = DROP** (severe): the L2 switch used only table 0; the LIMIT rule did
   `meter + goto_table:1` to an empty table → 100 % loss. Fix: table 0 = security
   (miss → goto 1), L2 in table 1. Test: `scripts/test_limit.sh`.
2. Mitigation by `src_ip` only: in amplification the source is a legitimate server
   (reflector) → blocking it took down DNS for the whole network. Fix: generic match
   (src/dst/proto/ports) in `iot_mitigation.py`.
3. 5 s windows truncated long connections (slowloris, MQTT) → invisible to the
   model. Fix: persistent extractor across windows (cumulative snapshots).
4. Under flood (~190 k pps) batch processing fell behind indefinitely. Fix: always
   the most recent window + sampling to 20 k rows.
5. A single strict threshold (P ≥ 0.99989) hid slowloris (median P 0.97). Fix: two
   thresholds (strict per flow for distributed destinations; 0.9 per aggregated source
   ≥ 5 flows and ≥ 50 % in 3 windows). Live benign: P(attack) < 0.5.
6. LIMIT 512 kbps didn't stop small packets (98 B ICMP, DNS queries) → 64 kbps.

**Honest limitations:**
- Live attribution is worse than offline (10/13): slowloris → MQTT_SUB, scan → Mirai,
  MQTT_SUB → MQTT_MALF. The chosen action is still correct (it depends on the family
  and the source/destination pattern, not on the fine-grained label).
- Per-destination LIMIT (ICMP/amplification) also throttles legitimate traffic of that
  type to that destination while the rule lasts (60 s).
- Amplification in the lab: the "victim" doesn't receive responses, it receives ~150 ARP/s
  from the reflector resolving non-existent spoofed IPs → measured at the reflector.
- 1 run per scenario (30 s); TTM varies between runs (SYN 5–10 s).

## MLP under grouped CV (DONE 2026-09-26)

`eval_grouped_cv.py --models mlp` → `artifacts/cv_grouped_mlp.json`. Same protocol as RF/XGB:

| Model | Accuracy | F1-macro |
|---|---|---|
| **RF** | 0.986 ± 0.018 | **0.986 ± 0.014** |
| MLP | 0.987 ± 0.021 | 0.968 ± 0.039 |
| XGB | 0.982 ± 0.020 | 0.958 ± 0.048 |

The MLP's 0.998 came from a single favorable split (fold 0). Under CV it drops
on slowloris (F1 0.67) and ICMP (0.89). **RF remains the best and most stable multiclass
model** → the claim "ensembles > MLP" holds when all three are reported with CV.

## Closed loop — 5 runs (2026-09-28) — WITHDRAWN: 20 s cooldown with carry-over between scenarios

`scripts/closed_loop_reps.sh 5` → `artifacts/closed_loop_r1..r5.json` (r1 = 09-26 run);
aggregation `ml_extra/closed_loop_aggregate.py` → `artifacts/closed_loop_reps.json`.

| Metric | Value |
|---|---|
| Attacks detected and mitigated | **65/65** |
| False alarms (5 × 120 s benign) | **0** |
| Correct / collateral rules | **142/142** / 0 |
| Overall median / max TTM | **5.3 s** / 34.2 s |
| Per-run median TTM | 5.1 ± 0.9 s (4.0–6.2) |
| Attack traffic reduction | median **94.6 %**, min 76.6 % (50 valid measurements) |
| Correct attribution | 48/65 (74 %) |

Per scenario (mean TTM ± sd; attribution): SYN 9.3±0.7 (5/5) · UDP 3.8±1.3 (5/5) ·
ICMP 3.2±1.5 (5/5) · HTTP 2.9±1.8 (5/5) · Slowloris 21.8±7.1 (0/5) · Scan 20.9±7.7 (1/5) ·
DNS 3.4±2.0 · CoAP 4.3±1.7 · SSDP 4.0±1.6 (5/5) · MQTT sub 4.9±2.2 (0/5) ·
MQTT malf 17.4±11.3 (2/5) · Bruteforce 11.8±3.0 (5/5) · Mirai 3.2±1.9 (5/5).

**Measurable-reduction criterion:** the prior peak must be ≥ 2× the baseline. In 3 runs
MQTT_MALFORMED barely exceeded the broker baseline (peak ≈ 33 pps vs ≈ 25) → reduction not
measurable (detected and mitigated anyway). Attribution errors are systematic (slowloris, scan,
MQTT sub); the action applied was correct in all cases.

## Optimized closed loop and clean comparison (DONE 2026-10-01) — SUPERSEDES the 5 runs

**Measurement defect found:** with 20 s pauses between scenarios, retransmissions
from the previous attack (same attacker) triggered mitigation before the new attack → artificial
TTMs (as low as 0.07 s) and the previous class's label. This also affected the 5 earlier
runs (e.g., "unmeasurable" MQTT_MALFORMED was carry-over from MQTT_SUB), which were withdrawn.
All current figures use `COOLDOWN=60` (> rule lifetime).

**Optimizations (commit fe9a439):** 2 s live window with a 5 s flow snapshot
(features identical to training), sampling to 20 k after features and before sshfs,
RF attributes ≤ 2 k flows, per-source evidence = distinct flows in 15 s of capture.

| Metric (3 runs each, 60 s cooldown) | 5 s window | 2 s window |
|---|---|---|
| Detected and mitigated | 39/39 | 39/39 |
| False alarms | 0 (360 s) | 0 (960 s, incl. 600 s continuous benign) |
| Correct / collateral rules | 155/155 / 0 | 243/243 / 0 |
| Median / max TTM | 4.7 s / 8.5 s | **2.5 s** / 7.5 s |
| Per-run median | 4.8 ± 0.4 s | 2.6 ± 0.4 s |
| Median / min reduction | 94.6 % / 78.2 % | 95.2 % / 78.1 % |
| Attribution | 33/39 | 33/39 |

Per scenario, TTM 5 s → 2 s: SYN 7.3→5.5 · UDP 3.4→3.0 · ICMP 1.8→2.3 · HTTP 3.9→2.0 ·
Slowloris 7.9→6.3 · Scan 4.9→2.7 · DNS 5.3→1.8 · CoAP 4.2→1.7 · SSDP 2.9→2.3 ·
MQTT sub 4.8→3.2 · MQTT malf 3.9→2.1 · Bruteforce 7.0→4.4 · Mirai 3.4→2.1.
Remaining limit: the SYN flood (~200 k pps) saturates the Python extractor.
Artifacts: `closed_loop_cd60_c{5,2}_r{1..3}.json`, `closed_loop_cd60_c{5,2}_reps.json`,
`closed_loop_c2_benign600.json`.
