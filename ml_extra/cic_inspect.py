"""Inspect CIC-IoT-2023 dataset structure."""
import pandas as pd
import sys
from pathlib import Path

p = Path(sys.argv[1] if len(sys.argv) > 1 else "/home/ubuntu/iot_run/cic/Merged01.csv")
df = pd.read_csv(p, nrows=20000)
print(f"shape: {df.shape}")
print(f"columns ({len(df.columns)}):")
for c in df.columns:
    print(f"  {c}")
label_col = [c for c in df.columns if "label" in c.lower()]
print(f"\nlabel column: {label_col}")
if label_col:
    print(df[label_col[0]].value_counts().head(30))
