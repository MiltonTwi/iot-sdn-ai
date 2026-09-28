"""Audit log JSONL para acciones de mitigación.

Append-only, 1 línea = 1 evento. Sin dependencias.
Path por defecto: data/audit/mitigation.jsonl (configurable AUDIT_LOG env).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from threading import Lock

DEFAULT = Path(os.getenv("AUDIT_LOG", "data/audit/mitigation.jsonl"))
_lock = Lock()


def log_event(event: str, **fields) -> None:
    record = {"ts": time.time(), "event": event, **fields}
    DEFAULT.parent.mkdir(parents=True, exist_ok=True)
    with _lock, DEFAULT.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_recent(n: int = 100) -> list[dict]:
    if not DEFAULT.exists():
        return []
    with DEFAULT.open("r", encoding="utf-8") as f:
        lines = f.readlines()[-n:]
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return out
