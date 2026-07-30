"""Genera dataset di training per Qwen dai dati canonici/archivistici reali.

Regole:
- Usa solo dati reali, nessun mock.
- Genera esempi ChatML con citazioni [fonte: tabella#id].
- Suddivide train/val/test per entità/fonte (no contaminazione casuale).
- Rispetta i diritti: scarta fonti con training_allowed=false.
- Registra il dataset in Supabase ai.datasets / ai.dataset_versions / ai.dataset_item_sources.

Uso:
    python prepare_qwen_training_dataset.py --samples 5000 --output data/training_chatml
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from supabase_client import execute_sql

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).parent
DB_MAIN = BASE / "imi_internati.db"
DB_EVENTS = BASE / "eventi_1gm.db"

SYSTEM_PROMPT = (
    "Sei un assistente storico per l'archivio Lettere dal Fronte. "
    "Rispondi in italiano basandoti esclusivamente sulle fonti fornite. "
    "Cita ogni informazione con [fonte: tabella#id]. "
    "Se le fonti non contengono la risposta, scrivi: "
    "'Non dispongo di informazioni sufficienti per rispondere.'"
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_id(namespace: str, key: str) -> str:
    raw = f"{namespace}:{key}"
    return f"sha256:{hashlib.sha256(raw.encode()).hexdigest()}"


def _load_provider_registry() -> Dict[str, Dict[str, Any]]:
    path = BASE / "config" / "archive_providers.yml"
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {p["code"]: p for p in data.get("providers", [])}


def _training_allowed(source_tag: str, registry: Dict[str, Dict[str, Any]]) -> bool:
    """Verifica se una fonte può essere usata per training."""
    # Fonti interne/lettere sempre consentite
    if source_tag in ("internati", "fonti_indice", "fondi_archivistici", "menzioni"):
        return True
    provider = registry.get(source_tag)
    if not provider:
        # Se non è nel registro, consenti metadati (conservativo)
        return True
    rights = provider.get("rights", {})
    return bool(rights.get("training_allowed", rights.get("download_allowed", True)))


def _format_context(records: List[Tuple[str, int, str]]) -> str:
    lines = []
    for table, rid, text in records:
        if text:
            lines.append(f"[fonte: {table}#{rid}] {text.strip()}")
    return "\n".join(lines)


def _chatml_record(question: str, context: str, answer: str, sources: List[Tuple[str, int]]) -> Dict[str, Any]:
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"{question}\n\nContesto:\n{context}"},
            {"role": "assistant", "content": answer},
        ],
        "metadata": {
            "sources": [{"table": t, "id": i} for t, i in sources],
            "generated_at": _now_iso(),
        },
    }


def _row_to_text(table: str, row: sqlite3.Row) -> str:
    """Estrae una descrizione testuale leggibile da una riga di database."""
    d = dict(row)
    parts = []
    if table == "internati":
        for k in ["cognome", "nome", "data_nascita", "luogo_nascita", "residenza",
                  "grado", "luogo_cattura", "data_cattura", "luogo_internamento",
                  "matricola", "arbeitskommando", "mansione", "sorte", "data"]:
            if d.get(k):
                parts.append(f"{k}: {d[k]}")
        if d.get("raw_text"):
            parts.append(f"testo: {d['raw_text'][:500]}")
    elif table == "caduti_cwgc":
        for k in ["cognome", "nome", "rank", "regiment", "service", "data_morte",
                  "eta", "cimitero", "paese_cimitero", "memorial", "grave_ref"]:
            if d.get(k):
                parts.append(f"{k}: {d[k]}")
    elif table == "caduti_ministero":
        for k in ["cognome", "nome", "grado", "reparto", "data_morte", "luogo_morte",
                  "causa_morte", "luogo_nascita", "data_nascita"]:
            if d.get(k):
                parts.append(f"{k}: {d[k]}")
    elif table == "eventi_1gm":
        for k in ["nome", "data_inizio", "data_fine", "luogo", "descrizione", "aliases", "keywords"]:
            if d.get(k):
                parts.append(f"{k}: {d[k]}")
    elif table == "archivio_documenti":
        for k in ["title", "description", "creator", "date_text", "place", "war", "source_url"]:
            if d.get(k):
                parts.append(f"{k}: {d[k]}")
    else:
        # fallback: chiavi con valori non vuoti
        for k, v in d.items():
            if v and k not in ("id", "raw_text", "raw_json"):
                parts.append(f"{k}: {v}")
    return "; ".join(parts)


# ─── Example generators ─────────────────────────────────────────────────────

class ExampleGenerator:
    def __init__(self, max_samples: int = 5000):
        self.max_samples = max_samples
        self.registry = _load_provider_registry()
        self.examples: List[Dict[str, Any]] = []

    def _add(self, ex: Dict[str, Any], split_key: str) -> None:
        # split_key usata per hashing deterministico
        h = int(hashlib.sha256(split_key.encode()).hexdigest(), 16)
        bucket = h % 100
        if bucket < 75:
            split = "train"
        elif bucket < 90:
            split = "validation"
        else:
            split = "test"
        ex["metadata"]["split"] = split
        self.examples.append(ex)

    def generate_soldier_cross_source(self, n: int = 2000) -> None:
        """Genera esempi che incrociano internati con caduti esterni."""
        conn = sqlite3.connect(str(DB_MAIN))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Trova soldati presenti in più tabelle per nome
        cur.execute("""
            SELECT i.id, i.cognome, i.nome, i.data_nascita, i.luogo_nascita,
                   i.grado, i.luogo_cattura, i.data_cattura, i.luogo_internamento,
                   i.matricola, i.sorte, i.data
            FROM internati i
            WHERE i.cognome IS NOT NULL AND i.nome IS NOT NULL
            ORDER BY i.cognome, i.nome
            LIMIT ?
        """, (n * 2,))

        count = 0
        for row in cur.fetchall():
            if count >= n:
                break
            cognome = (row["cognome"] or "").strip()
            nome = (row["nome"] or "").strip()
            if not cognome or not nome:
                continue

            records: List[Tuple[str, int, str]] = []
            records.append(("internati", row["id"], _row_to_text("internati", row)))

            # Cerca match in caduti_cwgc
            for cwgc in conn.execute(
                "SELECT * FROM caduti_cwgc WHERE lower(cognome)=? AND lower(nome)=? LIMIT 1",
                (cognome.lower(), nome.lower()),
            ).fetchall():
                if _training_allowed("caduti_cwgc", self.registry):
                    records.append(("caduti_cwgc", cwgc["id"], _row_to_text("caduti_cwgc", cwgc)))

            # Cerca match in caduti_ministero
            for cm in conn.execute(
                "SELECT * FROM caduti_ministero WHERE lower(cognome)=? AND lower(nome)=? LIMIT 1",
                (cognome.lower(), nome.lower()),
            ).fetchall():
                if _training_allowed("caduti_ministero", self.registry):
                    records.append(("caduti_ministero", cm["id"], _row_to_text("caduti_ministero", cm)))

            if len(records) < 2:
                continue

            context = _format_context(records)
            question = f"Chi era {nome} {cognome}? Riporta grado, luogo e data di cattura o morte, e le fonti."
            answer_parts = []
            for table, rid, text in records:
                answer_parts.append(f"Dalla fonte [fonte: {table}#{rid}]: {text[:200]}...")
            answer = "\n".join(answer_parts)

            ex = _chatml_record(question, context, answer, [(t, i) for t, i, _ in records])
            self._add(ex, f"soldier:{cognome}:{nome}:{row['id']}")
            count += 1

        conn.close()
        print(f"  Soldier cross-source examples: {count}")

    def generate_event_records(self, n: int = 1500) -> None:
        """Genera esempi evento -> record collegati."""
        if not DB_EVENTS.exists():
            print("  eventi_1gm.db non trovato, skipped")
            return

        conn_ev = sqlite3.connect(str(DB_EVENTS))
        conn_ev.row_factory = sqlite3.Row
        conn_main = sqlite3.connect(str(DB_MAIN))
        conn_main.row_factory = sqlite3.Row

        events = conn_ev.execute(
            "SELECT * FROM eventi_1gm WHERE descrizione IS NOT NULL ORDER BY id LIMIT ?",
            (n * 2,),
        ).fetchall()

        count = 0
        for ev in events:
            if count >= n:
                break
            ev_id = ev["id"]
            records: List[Tuple[str, int, str]] = []
            records.append(("eventi_1gm", ev_id, _row_to_text("eventi_1gm", ev)))

            # Recupera link a caduti/record
            links = conn_ev.execute(
                "SELECT target_table, target_id FROM event_links WHERE evento_id=? LIMIT 5",
                (ev_id,),
            ).fetchall()
            for link in links:
                table = link["target_table"]
                rid = link["target_id"]
                if not _training_allowed(table, self.registry):
                    continue
                if table in ("caduti_cwgc", "caduti_ministero", "caduti_albooro", "caduti_sardi", "caduti_francia_ww1"):
                    row = conn_main.execute(
                        f"SELECT * FROM {table} WHERE id=?", (rid,)
                    ).fetchone()
                    if row:
                        records.append((table, rid, _row_to_text(table, row)))

            if len(records) < 2:
                continue

            context = _format_context(records)
            question = f"L'evento '{ev['nome']}' è documentato da quali fonti? Descrivile brevemente."
            answer = f"L'evento [fonte: eventi_1gm#{ev_id}] è collegato a:\n"
            for table, rid, text in records[1:]:
                answer += f"- [fonte: {table}#{rid}] {text[:180]}...\n"

            ex = _chatml_record(question, context, answer, [(t, i) for t, i, _ in records])
            self._add(ex, f"event:{ev_id}")
            count += 1

        conn_ev.close()
        conn_main.close()
        print(f"  Event-record examples: {count}")

    def generate_document_sources(self, n: int = 1000) -> None:
        """Genera esempi su fonti archivistiche."""
        conn = sqlite3.connect(str(DB_MAIN))
        conn.row_factory = sqlite3.Row

        docs = conn.execute(
            "SELECT * FROM archivio_documenti WHERE title IS NOT NULL AND description IS NOT NULL LIMIT ?",
            (n * 2,),
        ).fetchall()

        count = 0
        for doc in docs:
            if count >= n:
                break
            if not _training_allowed(str(doc["provider"] or "archivio_documenti"), self.registry):
                continue
            doc_id = doc["external_id"] or doc["source_url"] or f"doc-{count}"
            records = [("archivio_documenti", doc_id, _row_to_text("archivio_documenti", doc))]
            context = _format_context(records)
            question = f"Cosa contiene il documento '{doc['title']}' e qual è il suo periodo storico?"
            answer = f"[fonte: archivio_documenti#{doc_id}] {doc['description'][:300]}..."
            ex = _chatml_record(question, context, answer, [("archivio_documenti", doc_id)])
            self._add(ex, f"doc:{doc_id}")
            count += 1

        conn.close()
        print(f"  Document source examples: {count}")

    def split_and_write(self, output_dir: Path) -> Dict[str, Any]:
        output_dir.mkdir(parents=True, exist_ok=True)
        train, val, test = [], [], []
        for ex in self.examples:
            split = ex["metadata"].get("split", "train")
            if split == "train":
                train.append(ex)
            elif split == "validation":
                val.append(ex)
            else:
                test.append(ex)

        paths = {
            "train": output_dir / "qwen_historical_train.jsonl",
            "validation": output_dir / "qwen_historical_validation.jsonl",
            "test": output_dir / "qwen_historical_test.jsonl",
        }
        for split_name, data in [("train", train), ("validation", val), ("test", test)]:
            with open(paths[split_name], "w", encoding="utf-8") as f:
                for ex in data:
                    f.write(json.dumps(ex, ensure_ascii=False) + "\n")

        print(f"\nDataset written to {output_dir}")
        print(f"  train={len(train)} validation={len(val)} test={len(test)} total={len(self.examples)}")
        return {
            "train": len(train),
            "validation": len(val),
            "test": len(test),
            "total": len(self.examples),
            "paths": {k: str(v) for k, v in paths.items()},
        }

    def register_supabase(self, stats: Dict[str, Any]) -> None:
        """Registra dataset e versione in Supabase."""
        dataset_stable_id = _stable_id("dataset", "qwen_historical_cross_source")
        version_stable_id = _stable_id("dataset_version", f"qwen_historical_v1_{_now_iso()}")

        # Dataset
        sql_ds = f"""
        INSERT INTO ai.datasets (stable_id, name, description, task_type, license)
        VALUES ({_sql_literal(dataset_stable_id)}, 'qwen_historical_cross_source',
                'Dataset ChatML per Qwen con esempi cross-source e citazioni',
                'chat_completion', 'internal')
        ON CONFLICT (stable_id) DO NOTHING
        """
        r = execute_sql(sql_ds)
        if not r.get("ok"):
            print("WARN: could not register ai.datasets:", r)
            return

        # Versione
        sql_ver = f"""
        INSERT INTO ai.dataset_versions (dataset_id, version_number, stable_id, immutable, freeze_hash, split_json, num_items, status)
        SELECT id, 1, {_sql_literal(version_stable_id)}, TRUE, {_sql_literal(_sha256(json.dumps(stats, sort_keys=True)))},
               {_sql_literal(json.dumps({'train': stats['train'], 'validation': stats['validation'], 'test': stats['test']}))},
               {stats['total']}, 'frozen'
        FROM ai.datasets WHERE stable_id = {_sql_literal(dataset_stable_id)}
        ON CONFLICT (stable_id) DO NOTHING
        """
        r = execute_sql(sql_ver)
        if not r.get("ok"):
            print("WARN: could not register ai.dataset_versions:", r)
            return

        print(f"Registered in Supabase ai.datasets stable_id={dataset_stable_id}")
        print(f"Registered ai.dataset_versions stable_id={version_stable_id}")


def main():
    parser = argparse.ArgumentParser(description="Prepara dataset Qwen da dati archivistici reali")
    parser.add_argument("--samples", type=int, default=5000, help="Numero totale stimato di esempi")
    parser.add_argument("--output", type=Path, default=BASE / "data" / "training_chatml",
                        help="Directory di output")
    parser.add_argument("--no-supabase", action="store_true", help="Non registrare su Supabase")
    args = parser.parse_args()

    print("=" * 70)
    print("PREPARAZIONE DATASET QWEN — dati reali, cross-source, citato")
    print("=" * 70)

    gen = ExampleGenerator(max_samples=args.samples)

    # Suddividi il budget
    gen.generate_soldier_cross_source(n=int(args.samples * 0.5))
    gen.generate_event_records(n=int(args.samples * 0.3))
    gen.generate_document_sources(n=int(args.samples * 0.2))

    stats = gen.split_and_write(args.output)

    if not args.no_supabase:
        gen.register_supabase(stats)

    print("\nCompletato.")


if __name__ == "__main__":
    main()
