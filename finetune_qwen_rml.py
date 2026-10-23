"""
Fine-tuning RML (Reinforcement from Mixed-quality Labels) per Qwen
basato sui dataset completi su Supabase.

Usa i dati da ml_training_chatml (train_merged = 40,540 esempi ChatML)
per fine-tuning di Qwen2.5-7B-Instruct con LoRA + SFT.

Requisiti:
- transformers >= 5.14
- peft >= 0.19
- trl >= 0.17
- bitsandbytes >= 0.50
- datasets >= 5.0
- torch >= 2.0
- CUDA GPU con almeno 16GB VRAM (o quantizzazione 4-bit per 8GB)

Uso:
    python finetune_qwen_rml.py --epochs 3 --batch-size 2 --lr 2e-5
    python finetune_qwen_rml.py --export-only  # esporta dataset da Supabase senza training
"""

import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime

import torch
from dotenv import load_dotenv

load_dotenv()

# ─── Configurazione ───────────────────────────────────────────────────────────

MODEL_NAME = "Qwen/Qwen2.5-7B-Instruct"
OUTPUT_DIR = Path("models/qwen_voci_dal_fronte")
DATASET_CACHE = Path("data/training_cache")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

# System prompt per il modello fine-tuned
SYSTEM_PROMPT = (
    "Sei un ricercatore storico specializzato negli eventi bellici del Novecento, "
    "con focus su Prima e Seconda Guerra Mondiale, Internati Militari Italiani (IMI), "
    "caduti, decorati e fonti archivistiche italiane. "
    "Rispondi in italiano con accuratezza storica, citando fonti quando possibile."
)


# ─── Estrazione dati da Supabase ──────────────────────────────────────────────

def fetch_training_data_from_supabase(limit: int = None) -> list[dict]:
    """Estrae tutti i dati di training ChatML da Supabase."""
    import httpx

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }

    all_records = []
    offset = 0
    batch_size = 1000

    print(f"Estrazione dati da Supabase (ml_training_chatml)...")

    while True:
        params = {
            "select": "dataset_name,messages",
            "order": "id",
            "offset": str(offset),
            "limit": str(batch_size),
        }
        if limit and offset >= limit:
            break

        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/ml_training_chatml",
            headers=headers,
            params=params,
            timeout=30,
        )
        if r.status_code != 200:
            print(f"  [ERR] {r.status_code}: {r.text[:200]}")
            break

        batch = r.json()
        if not batch:
            break

        for record in batch:
            messages = record["messages"]
            if isinstance(messages, str):
                messages = json.loads(messages)
            all_records.append({
                "dataset_name": record["dataset_name"],
                "messages": messages,
            })

        offset += len(batch)
        if offset % 5000 == 0:
            print(f"  {offset:,} record estratti...")

        if limit and offset >= limit:
            break

    print(f"  Totale: {len(all_records):,} record estratti da Supabase")
    return all_records


def prepare_dataset(records: list[dict], val_split: float = 0.05):
    """Prepara il dataset per SFT, con system prompt standardizzato."""
    from datasets import Dataset

    processed = []
    for rec in records:
        messages = rec["messages"]
        # Assicura che ci sia un system prompt
        if not messages or messages[0].get("role") != "system":
            messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages
        else:
            # Sostituisci con il nostro system prompt per consistenza
            messages[0]["content"] = SYSTEM_PROMPT

        # Filtra messaggi vuoti
        messages = [m for m in messages if m.get("content", "").strip()]
        if len(messages) < 2:
            continue

        processed.append({"messages": messages})

    print(f"  Dataset processato: {len(processed):,} esempi validi")

    # Split train/val
    ds = Dataset.from_list(processed)
    split = ds.train_test_split(test_size=val_split, seed=42)
    print(f"  Train: {len(split['train']):,}, Val: {len(split['test']):,}")
    return split


# ─── Fine-tuning ──────────────────────────────────────────────────────────────

def run_finetuning(
    dataset_split,
    epochs: int = 3,
    batch_size: int = 2,
    lr: float = 2e-5,
    max_seq_length: int = 2048,
    gradient_accumulation: int = 8,
    use_4bit: bool = True,
):
    """Esegue fine-tuning SFT con LoRA su Qwen2.5-7B-Instruct."""
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
    )
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from trl import SFTTrainer, SFTConfig

    print(f"\n{'='*60}")
    print(f"Fine-tuning RML: {MODEL_NAME}")
    print(f"  Epochs: {epochs}")
    print(f"  Batch size: {batch_size}")
    print(f"  Learning rate: {lr}")
    print(f"  Max seq length: {max_seq_length}")
    print(f"  Gradient accumulation: {gradient_accumulation}")
    print(f"  4-bit quantization: {use_4bit}")
    print(f"  Output: {OUTPUT_DIR}")
    print(f"{'='*60}\n")

    # Tokenizer
    print("Caricamento tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(
        MODEL_NAME,
        trust_remote_code=True,
        padding_side="right",
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Quantization config
    bnb_config = None
    if use_4bit:
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )

    # Model
    print("Caricamento modello...")
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
        torch_dtype=torch.bfloat16 if not use_4bit else None,
        attn_implementation="flash_attention_2" if torch.cuda.is_available() else "eager",
    )

    if use_4bit:
        model = prepare_model_for_kbit_training(model)

    # LoRA config
    lora_config = LoraConfig(
        r=64,
        lora_alpha=128,
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )

    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # Training config
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    training_args = SFTConfig(
        output_dir=str(OUTPUT_DIR),
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
        gradient_accumulation_steps=gradient_accumulation,
        learning_rate=lr,
        weight_decay=0.01,
        warmup_ratio=0.03,
        lr_scheduler_type="cosine",
        logging_steps=10,
        save_strategy="steps",
        save_steps=500,
        eval_strategy="steps",
        eval_steps=500,
        max_seq_length=max_seq_length,
        bf16=torch.cuda.is_bf16_supported() if torch.cuda.is_available() else False,
        fp16=not torch.cuda.is_bf16_supported() if torch.cuda.is_available() else False,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        report_to="none",
        seed=42,
        save_total_limit=3,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
    )

    # Trainer
    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=dataset_split["train"],
        eval_dataset=dataset_split["test"],
        processing_class=tokenizer,
    )

    # Train
    print("\nAvvio training...")
    train_result = trainer.train()

    # Save
    print("\nSalvataggio modello...")
    trainer.save_model(str(OUTPUT_DIR / "final"))
    tokenizer.save_pretrained(str(OUTPUT_DIR / "final"))

    # Metrics
    metrics = train_result.metrics
    metrics["train_samples"] = len(dataset_split["train"])
    metrics["eval_samples"] = len(dataset_split["test"])
    trainer.log_metrics("train", metrics)
    trainer.save_metrics("train", metrics)

    print(f"\n{'='*60}")
    print(f"Training completato!")
    print(f"  Loss finale: {metrics.get('train_loss', 'N/A'):.4f}")
    print(f"  Modello salvato in: {OUTPUT_DIR / 'final'}")
    print(f"{'='*60}")

    return trainer, metrics


# ─── Export per LMStudio/Ollama ───────────────────────────────────────────────

def export_gguf(adapter_path: Path):
    """Esporta il modello LoRA merged in formato GGUF per LMStudio."""
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    print("\nMerge LoRA adapter + export...")

    base_model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        torch_dtype=torch.float16,
        device_map="cpu",
        trust_remote_code=True,
    )
    model = PeftModel.from_pretrained(base_model, str(adapter_path))
    merged = model.merge_and_unload()

    merged_path = OUTPUT_DIR / "merged"
    merged_path.mkdir(parents=True, exist_ok=True)
    merged.save_pretrained(str(merged_path))

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
    tokenizer.save_pretrained(str(merged_path))

    print(f"Modello merged salvato in: {merged_path}")
    print(f"\nPer convertire in GGUF:")
    print(f"  python llama.cpp/convert_hf_to_gguf.py {merged_path} --outtype q4_k_m")
    print(f"  oppure usa: ollama create voci-dal-fronte -f Modelfile")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Fine-tuning RML Qwen per Voci dal Fronte")
    parser.add_argument("--epochs", type=int, default=3, help="Numero di epoche")
    parser.add_argument("--batch-size", type=int, default=2, help="Batch size per device")
    parser.add_argument("--lr", type=float, default=2e-5, help="Learning rate")
    parser.add_argument("--max-seq-length", type=int, default=2048, help="Max sequence length")
    parser.add_argument("--gradient-accumulation", type=int, default=8, help="Gradient accumulation steps")
    parser.add_argument("--no-4bit", action="store_true", help="Disabilita quantizzazione 4-bit")
    parser.add_argument("--limit", type=int, default=None, help="Limita record estratti (per test)")
    parser.add_argument("--export-only", action="store_true", help="Solo export dataset, no training")
    parser.add_argument("--export-gguf", action="store_true", help="Export modello in GGUF")
    parser.add_argument("--local-data", action="store_true", help="Usa dati locali (data/training_chatml/train_merged.jsonl)")
    args = parser.parse_args()

    print(f"{'='*60}")
    print(f"  Fine-tuning RML — Qwen2.5-7B-Instruct")
    print(f"  Progetto: Voci dal Fronte")
    print(f"  Data: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}\n")

    # Check GPU
    if torch.cuda.is_available():
        gpu_name = torch.cuda.get_device_name(0)
        gpu_mem = torch.cuda.get_device_properties(0).total_mem / 1e9
        print(f"GPU: {gpu_name} ({gpu_mem:.1f} GB)")
    else:
        print("ATTENZIONE: Nessuna GPU CUDA disponibile. Il training sarà molto lento.")
        if not args.export_only:
            print("Usa --export-only per preparare i dati senza training.")

    # Step 1: Carica dati
    DATASET_CACHE.mkdir(parents=True, exist_ok=True)
    cache_file = DATASET_CACHE / "train_merged_supabase.jsonl"

    if args.local_data:
        # Usa file locale
        local_file = Path("data/training_chatml/train_merged.jsonl")
        print(f"\nCaricamento dati locali: {local_file}")
        records = []
        with open(local_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    obj = json.loads(line)
                    records.append({"dataset_name": "train_merged", "messages": obj.get("messages", [])})
        print(f"  {len(records):,} record caricati")
    elif cache_file.exists():
        print(f"Cache trovata: {cache_file}")
        records = []
        with open(cache_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line))
        print(f"  {len(records):,} record dalla cache")
    else:
        records = fetch_training_data_from_supabase(limit=args.limit)
        # Save cache
        with open(cache_file, "w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"  Cache salvata: {cache_file}")

    if not records:
        print("ERRORE: Nessun dato di training trovato!")
        sys.exit(1)

    # Step 2: Prepara dataset
    dataset_split = prepare_dataset(records)

    if args.export_only:
        # Salva dataset processato
        out_file = DATASET_CACHE / "processed_dataset.jsonl"
        with open(out_file, "w", encoding="utf-8") as f:
            for item in dataset_split["train"]:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        print(f"\nDataset processato salvato in: {out_file}")
        print("Per avviare il training, esegui senza --export-only")
        return

    # Step 3: Fine-tuning
    if args.export_gguf:
        adapter_path = OUTPUT_DIR / "final"
        if not adapter_path.exists():
            print(f"ERRORE: Adapter non trovato in {adapter_path}")
            sys.exit(1)
        export_gguf(adapter_path)
        return

    trainer, metrics = run_finetuning(
        dataset_split,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        max_seq_length=args.max_seq_length,
        gradient_accumulation=args.gradient_accumulation,
        use_4bit=not args.no_4bit,
    )

    # Step 4: Registra su Supabase
    if SUPABASE_URL and SUPABASE_KEY:
        import httpx
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }
        run_record = {
            "provider_id": 6,  # LMStudio/Local
            "model_id": None,
            "policy_id": None,
            "task_type": "finetune_rml",
            "input_text": f"Qwen2.5-7B finetune: {len(records)} samples, {args.epochs} epochs",
            "output_text": json.dumps(metrics, default=str),
            "tokens_in": 0,
            "tokens_out": 0,
            "latency_ms": int(metrics.get("train_runtime", 0) * 1000),
            "success": True,
        }
        r = httpx.post(f"{SUPABASE_URL}/rest/v1/ai_task_runs", headers=headers, json=run_record, timeout=15)
        if r.status_code in (200, 201, 204):
            print("  Training run registrato su Supabase ✓")


if __name__ == "__main__":
    main()
