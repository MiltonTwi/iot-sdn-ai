#!/usr/bin/env python3
"""Agrega las repeticiones del lazo cerrado (closed_loop_r*.json, ya re-puntuadas).

  python3 ml_extra/closed_loop_aggregate.py  ->  artifacts/closed_loop_reps.json
"""
from __future__ import annotations

import json
import statistics as st
from pathlib import Path

ART = Path(__file__).resolve().parent / "artifacts"


def _red(r: dict) -> float | None:
    """Reducción medible: el ataque debe al menos duplicar la línea base en el objetivo."""
    v = r.get("victim") or {}
    if v.get("reduction_pct") is None or v.get("peak_pps_pre", 0) < 2 * max(v.get("baseline_pps", 0), 1):
        return None
    return v["reduction_pct"]


def _ms(xs: list[float]) -> dict:
    if not xs:
        return {"n": 0}
    return {"n": len(xs), "mean": round(st.mean(xs), 2), "std": round(st.stdev(xs), 2) if len(xs) > 1 else 0.0,
            "median": round(st.median(xs), 2), "min": round(min(xs), 2), "max": round(max(xs), 2)}


def main() -> None:
    runs = [json.loads(f.read_text()) for f in sorted(ART.glob("closed_loop_r[0-9]*.json"))]
    sids = list(runs[0]["scenarios"])
    per = {}
    for sid in sids:
        rs = [r["scenarios"][sid] for r in runs if sid in r["scenarios"]]
        per[sid] = {
            "runs": len(rs),
            "detected": sum(r["detected"] for r in rs),
            "ttm_s": _ms([r["ttm_s"] for r in rs if r["ttm_s"] is not None]),
            "reduction_pct": _ms([x for x in map(_red, rs) if x is not None]),
            "reduction_not_measurable": sum(_red(r) is None and r.get("victim") is not None for r in rs),
            "attribution_ok": sum(bool(r.get("attribution_ok")) for r in rs),
            "collateral": sum(r["collateral"] for r in rs),
        }
    all_ttm = [r["scenarios"][s]["ttm_s"] for r in runs for s in sids
               if r["scenarios"].get(s, {}).get("ttm_s") is not None]
    all_red = [x for r in runs for s in sids if (x := _red(r["scenarios"].get(s, {}))) is not None]
    run_medians = [r["summary"]["ttm_median_s"] for r in runs if r["summary"].get("ttm_median_s")]
    summary = {
        "runs": len(runs),
        "attacks_total": sum(len(r["scenarios"]) for r in runs),
        "detected_total": sum(p["detected"] for p in per.values()),
        "benign_false_actions_total": sum(r["summary"]["benign_false_actions"] for r in runs),
        "benign_seconds_total": sum(r["benign"]["duration_s"] for r in runs),
        "collateral_total": sum(p["collateral"] for p in per.values()),
        "rules_correct_total": sum(r["summary"].get("rules_correct", 0) for r in runs),
        "rules_total": sum(r["summary"].get("rules_total", 0) for r in runs),
        "attribution_ok_total": sum(p["attribution_ok"] for p in per.values()),
        "ttm_all": _ms(all_ttm),
        "ttm_run_medians": _ms(run_medians),
        "reduction_all": _ms(all_red),
    }
    out = {"summary": summary, "scenarios": per}
    (ART / "closed_loop_reps.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(summary, indent=2))
    for sid, p in per.items():
        t, rd = p["ttm_s"], p["reduction_pct"]
        print(f"{sid:22} det {p['detected']}/{p['runs']}  TTM {t.get('mean')}±{t.get('std')} "
              f"(med {t.get('median')})  red {rd.get('mean')}±{rd.get('std')}  attr {p['attribution_ok']}/{p['runs']}")


if __name__ == "__main__":
    main()
