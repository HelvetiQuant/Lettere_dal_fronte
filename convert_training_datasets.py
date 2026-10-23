"""Convert downloaded datasets to ChatML format for Qwen2.5 fine-tuning.

Output: data/training_chatml/<name>.jsonl with messages=[{role, content}]
"""
from __future__ import annotations

import json
import re
from pathlib import Path

SRC = Path(__file__).parent / "data" / "training_datasets"
OUT = Path(__file__).parent / "data" / "training_chatml"
OUT.mkdir(parents=True, exist_ok=True)


def to_chatml(system: str, user: str, assistant: str) -> dict:
    return {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ]
    }


SYSTEM_HISTORIAN_IT = (
    "Sei un ricercatore storico specializzato negli eventi bellici del Novecento. "
    "Rispondi in italiano con accuratezza storica, citando le fonti quando possibile. "
    "Se non sei sicuro, dichiara la tua incertezza."
)

SYSTEM_HISTORIAN_EN = (
    "You are a historical researcher specializing in 20th century warfare. "
    "Answer with historical accuracy, citing sources when possible. "
    "If unsure, state your uncertainty."
)


def convert_quandho():
    """Q&A storia italiana XX secolo -> ChatML."""
    out = OUT / "quandho_chatml.jsonl"
    n = 0
    with open(SRC / "quandho.jsonl", "r", encoding="utf-8") as fin, \
         open(out, "w", encoding="utf-8") as fout:
        for line in fin:
            row = json.loads(line)
            q = row.get("question", "").strip()
            a = row.get("answer", "").strip()
            ctx = row.get("context", "")
            if not q or not a:
                continue
            user = f"{q}\n\nContesto: {ctx}" if ctx else q
            record = to_chatml(SYSTEM_HISTORIAN_IT, user, a)
            fout.write(json.dumps(record, ensure_ascii=False) + "\n")
            n += 1
    print(f"quandho: {n} esempi -> {out}")
    return n


def convert_aya_ita():
    """Q&A italiana -> ChatML (filtra solo storiche/geografiche)."""
    out = OUT / "aya_ita_chatml.jsonl"
    n = 0
    history_keywords = ["guerra", "storico", "fascismo", "nazismo", "resistenza",
                        "partigian", "militare", "esercito", "trincea", "fronte",
                        "caporetto", "piave", "carso", "isonzo", "grappa", "dannunzio",
                        "mussolini", "hitler", "alleanza", "pace", "armistizio",
                        "occupazione", "liberazione", "rsg", "regio", "soldato",
                        "medaglia", "decorazione", "caduto", "prigionia", "internato"]
    with open(SRC / "aya_ita.jsonl", "r", encoding="utf-8") as fin, \
         open(out, "w", encoding="utf-8") as fout:
        for line in fin:
            row = json.loads(line)
            q = row.get("inputs", "").strip()
            a = row.get("targets", "").strip()
            if not q or not a:
                continue
            q_lower = q.lower()
            if not any(kw in q_lower for kw in history_keywords):
                continue
            record = to_chatml(SYSTEM_HISTORIAN_IT, q, a)
            fout.write(json.dumps(record, ensure_ascii=False) + "\n")
            n += 1
    print(f"aya_ita: {n} esempi (filtrati storici) -> {out}")
    return n


def convert_muninn_ww1():
    """Documenti WWI -> ChatML (istruzioni su documenti)."""
    out = OUT / "muninn_ww1_chatml.jsonl"
    n = 0
    with open(SRC / "muninn_ww1.jsonl", "r", encoding="utf-8") as fin, \
         open(out, "w", encoding="utf-8") as fout:
        for line in fin:
            row = json.loads(line)
            title = row.get("title", "Unknown document")
            country = row.get("country", "Unknown")
            topic = row.get("primary_topic_name", "")
            first_name = row.get("primary_topic_first_name", "")
            last_name = row.get("primary_topic_last_name", "")
            allegiance = row.get("primary_topic_allegiance", "")
            date = row.get("date_created", "")
            desc = row.get("description", "") or ""
            num_pages = row.get("num_pages", 0)

            person = f"{first_name} {last_name}".strip() or topic
            user = (
                f"Analizza il seguente documento d'archivio della Prima Guerra Mondiale:\n\n"
                f"Titolo: {title}\n"
                f"Paese: {country}\n"
                f"Persona: {person}\n"
                f"Alleanza: {allegiance}\n"
                f"Data: {date}\n"
                f"Pagine: {num_pages}\n"
            )
            if desc:
                user += f"Descrizione: {desc}\n"

            assistant = (
                f"Documento d'archivio WWI identificato:\n"
                f"- Titolo: {title}\n"
                f"- Paese di origine: {country}\n"
                f"- Soggetto principale: {person}"
            )
            if allegiance:
                assistant += f"\n- Alleanza: {allegiance}"
            if date:
                assistant += f"\n- Data creazione: {date}"
            assistant += f"\n- Numero pagine: {num_pages}"
            if desc:
                assistant += f"\n- Descrizione: {desc}"
            assistant += "\n\nQuesto è un documento primario della Prima Guerra Mondiale."

            record = to_chatml(SYSTEM_HISTORIAN_EN, user, assistant)
            fout.write(json.dumps(record, ensure_ascii=False) + "\n")
            n += 1
    print(f"muninn_ww1: {n} esempi -> {out}")
    return n


def convert_commandnet():
    """Dottrina militare 1900-1999 -> ChatML."""
    out = OUT / "commandnet_chatml.jsonl"
    n = 0
    with open(SRC / "commandnet.jsonl", "r", encoding="utf-8") as fin, \
         open(out, "w", encoding="utf-8") as fout:
        for line in fin:
            row = json.loads(line)
            # CommandNet uses ShareGPT format with "conversations" field
            convs = row.get("conversations", [])
            if not convs or len(convs) < 2:
                continue

            messages = [{"role": "system", "content": SYSTEM_HISTORIAN_EN}]
            for c in convs:
                role = c.get("from", "human")
                content = c.get("value", "")
                if role in ("human", "user"):
                    messages.append({"role": "user", "content": content})
                elif role in ("gpt", "assistant", "model"):
                    messages.append({"role": "assistant", "content": content})
                elif role == "system":
                    messages[0]["content"] = content

            if len(messages) >= 3:
                record = {"messages": messages}
                fout.write(json.dumps(record, ensure_ascii=False) + "\n")
                n += 1
    print(f"commandnet: {n} esempi -> {out}")
    return n


def merge_all():
    """Merge all ChatML files into one training file."""
    out = OUT / "train_merged.jsonl"
    total = 0
    with open(out, "w", encoding="utf-8") as fout:
        for f in sorted(OUT.glob("*_chatml.jsonl")):
            with open(f, "r", encoding="utf-8") as fin:
                for line in fin:
                    fout.write(line)
                    total += 1
    size_mb = out.stat().st_size / 1024 / 1024
    print(f"\nMERGED: {total} esempi, {size_mb:.1f} MB -> {out}")
    return total


def main():
    print("=" * 60)
    print("Conversione dataset in formato ChatML per Qwen2.5")
    print("=" * 60)

    total = 0
    total += convert_quandho()
    total += convert_aya_ita()
    total += convert_muninn_ww1()
    total += convert_commandnet()

    print(f"\nSubtotale: {total} esempi")
    merged = merge_all()

    print(f"\nDataset pronto per fine-tuning: {merged} esempi")
    print(f"Prossimo step: LoRA training con unsloth/axolotl")


if __name__ == "__main__":
    main()
