"""Scarica dataset storici su WWI/WII da HuggingFace per fine-tuning Qwen2.5.

Dataset selezionati (italiano + internazionale):
1. mik3ml/quandho — Q&A storia italiana prima metà XX secolo (IT)
2. DeepMount00/cultura_generale-ITA — Cultura generale storica italiana (IT)
3. giux78/aya_dataset_ita — Q&A italiana con contenuto storico (IT)
4. biglam/muninn-ww1-documents — Documenti WWI (EN, 28.7K)
5. dtufail/nuremberg-trials-corpus — Processi Norimberga (EN, 46K chunk)
6. Euroswarms/CommandNet — Dottrina militare 1900-1999 (EN, 10K)

Output: data/training_datasets/<nome>/  (parquet/jsonl)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

OUT_DIR = Path(__file__).parent / "data" / "training_datasets"
OUT_DIR.mkdir(parents=True, exist_ok=True)

DATASETS = [
    {
        "id": "mik3ml/quandho",
        "name": "quandho",
        "lang": "it",
        "desc": "Q&A storia italiana prima metà XX secolo",
        "subset": None,
        "split": "train",
        "max_rows": 50000,
    },
    {
        "id": "DeepMount00/cultura_generale-ITA",
        "name": "cultura_generale_ita",
        "lang": "it",
        "desc": "Cultura generale storica italiana",
        "subset": None,
        "split": "train",
        "max_rows": 50000,
    },
    {
        "id": "giux78/aya_dataset_ita",
        "name": "aya_ita",
        "lang": "it",
        "desc": "Q&A italiana con contenuto storico",
        "subset": None,
        "split": "train",
        "max_rows": 30000,
    },
    {
        "id": "biglam/muninn-ww1-documents",
        "name": "muninn_ww1",
        "lang": "en",
        "desc": "Documenti WWI dal Muninn Project (28.7K)",
        "subset": "documents",
        "split": "train",
        "max_rows": 28700,
    },
    {
        "id": "dtufail/nuremberg-trials-corpus",
        "name": "nuremberg",
        "lang": "en",
        "desc": "Processi di Norimberga 1945-46 (46K chunk)",
        "subset": None,
        "split": "train",
        "max_rows": 46325,
    },
    {
        "id": "Euroswarms/CommandNet",
        "name": "commandnet",
        "lang": "en",
        "desc": "Dottrina militare 1900-1999 (10K ShareGPT)",
        "subset": None,
        "split": "train",
        "max_rows": 10000,
    },
]


def download_dataset(cfg: dict) -> bool:
    """Download a single dataset and save as JSONL."""
    ds_id = cfg["id"]
    name = cfg["name"]
    out_path = OUT_DIR / f"{name}.jsonl"
    if out_path.exists() and out_path.stat().st_size > 100:
        print(f"  SKIP {name}: already downloaded ({out_path.stat().st_size} bytes)")
        return True

    print(f"  Downloading {ds_id} ...")
    try:
        from datasets import load_dataset

        kwargs = {"path": ds_id}
        if cfg.get("subset"):
            kwargs["name"] = cfg["subset"]
        if cfg.get("split"):
            kwargs["split"] = cfg["split"]

        ds = load_dataset(**kwargs)
        rows_written = 0
        with open(out_path, "w", encoding="utf-8") as f:
            for row in ds:
                if rows_written >= cfg["max_rows"]:
                    break
                record = {}
                for k in row.keys():
                    v = row[k]
                    if isinstance(v, (str, int, float, bool, list, dict)) or v is None:
                        record[k] = v
                    else:
                        record[k] = str(v)
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                rows_written += 1

        print(f"  OK {name}: {rows_written} rows -> {out_path}")
        return True
    except Exception as e:
        print(f"  ERROR {name}: {e}")
        if out_path.exists():
            out_path.unlink()
        return False


def main():
    print("=" * 60)
    print("Download dataset storici WWI/WII per fine-tuning")
    print(f"Output: {OUT_DIR}")
    print("=" * 60)

    # Check if datasets library is available
    try:
        import datasets
        print(f"datasets library v{datasets.__version__} OK")
    except ImportError:
        print("ERROR: datasets library not installed.")
        print("Run: python -m pip install datasets huggingface_hub")
        sys.exit(1)

    results = []
    for cfg in DATASETS:
        print(f"\n[{cfg['lang'].upper()}] {cfg['name']}: {cfg['desc']}")
        ok = download_dataset(cfg)
        results.append((cfg["name"], ok))

    print("\n" + "=" * 60)
    print("Riepilogo:")
    for name, ok in results:
        status = "OK" if ok else "FAILED"
        print(f"  {name:30s} {status}")

    # Show total size
    total_size = sum(f.stat().st_size for f in OUT_DIR.glob("*.jsonl"))
    print(f"\nTotale: {total_size / 1024 / 1024:.1f} MB in {OUT_DIR}")


if __name__ == "__main__":
    main()
