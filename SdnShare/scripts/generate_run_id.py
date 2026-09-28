#!/usr/bin/env python3
"""
Genera un run_id único para cada sesión de captura de datos.

Formato: YYYYMMDDHHMMSS-{hash_corto}
Ejemplo: 20260303190000-a1b2c3

Uso:
    python scripts/generate_run_id.py
    python scripts/generate_run_id.py --create-dir
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Directorio raíz del proyecto (relativo al script)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
TEMPLATE_FILE = DATA_DIR / "metadata-template.json"


def generate_run_id() -> str:
    """Genera un run_id único basado en timestamp + hash."""
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d%H%M%S")
    hash_input = f"{timestamp}-{os.getpid()}-{id(now)}"
    short_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:6]
    return f"{timestamp}-{short_hash}"


def create_run_directory(run_id: str) -> Path:
    """Crea la estructura de directorios para un run_id."""
    raw_dir = DATA_DIR / "raw" / run_id
    processed_dir = DATA_DIR / "processed" / run_id

    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    # Copiar template de metadata
    metadata_file = raw_dir / "metadata.json"
    if TEMPLATE_FILE.exists() and not metadata_file.exists():
        with open(TEMPLATE_FILE) as f:
            metadata = json.load(f)

        metadata["run_id"] = run_id
        metadata["created_at"] = datetime.now().isoformat()

        with open(metadata_file, "w") as f:
            json.dump(metadata, f, indent=2)

    return raw_dir


def main():
    parser = argparse.ArgumentParser(description="Genera un run_id para captura de datos")
    parser.add_argument(
        "--create-dir",
        action="store_true",
        help="Crear directorio data/raw/{run_id}/ con metadata.json",
    )
    args = parser.parse_args()

    run_id = generate_run_id()

    if args.create_dir:
        run_dir = create_run_directory(run_id)
        print(f"{run_id}")
        print(f"  → {run_dir}", file=sys.stderr)
    else:
        print(run_id)


if __name__ == "__main__":
    main()
