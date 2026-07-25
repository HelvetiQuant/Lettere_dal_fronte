"""CPU LoRA fine-tuning for Qwen2.5-3B-Instruct on WWI/WII historical data.

Splits the 40K dataset into chunks of 500 examples and trains sequentially.
Each chunk saves a checkpoint. Uses 8-bit quantization for memory efficiency.

Usage:
    python finetune_cpu.py
    python finetune_cpu.py --chunk-size 500 --max-chunks 5   # first 5 chunks only
    python finetune_cpu.py --resume                           # resume from last checkpoint
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

TRAIN_FILE = Path(__file__).parent / "data" / "training_chatml" / "train_merged.jsonl"
OUT_DIR = Path(__file__).parent / "models" / "qwen25-05b-wwi-lora-cpu"
PROGRESS_FILE = OUT_DIR / "training_progress.json"

BASE_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"


def load_all_examples() -> list[dict]:
    """Load all training examples from merged JSONL."""
    examples = []
    with open(TRAIN_FILE, "r", encoding="utf-8") as f:
        for line in f:
            examples.append(json.loads(line))
    return examples


def chunk_list(lst: list, size: int) -> list[list]:
    """Split list into chunks of given size."""
    return [lst[i:i + size] for i in range(0, len(lst), size)]


def save_progress(chunk_idx: int, total_chunks: int, total_examples: int):
    """Save training progress for resume."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(PROGRESS_FILE, "w") as f:
        json.dump({
            "last_chunk": chunk_idx,
            "total_chunks": total_chunks,
            "total_examples": total_examples,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }, f, indent=2)


def load_progress() -> int:
    """Load last completed chunk index for resume."""
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE) as f:
            return json.load(f).get("last_chunk", -1)
    return -1


def train_chunk(
    model,
    tokenizer,
    chunk: list[dict],
    chunk_idx: int,
    total_chunks: int,
    optimizer,
    device,
    max_seq_length: int = 1024,
):
    """Train on a single chunk of examples."""
    model.train()
    total_loss = 0.0
    num_batches = 0

    for i, example in enumerate(chunk):
        try:
            messages = example.get("messages", [])
            if len(messages) < 3:
                continue

            # Build text using ChatML format
            text = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=False,
            )

            # Tokenize
            inputs = tokenizer(
                text,
                return_tensors="pt",
                truncation=True,
                max_length=max_seq_length,
                padding=False,
            )
            input_ids = inputs["input_ids"].to(device)

            # Forward + backward
            outputs = model(input_ids=input_ids, labels=input_ids)
            loss = outputs.loss
            loss.backward()
            total_loss += loss.item()
            num_batches += 1

            # Optimizer step every 4 examples (gradient accumulation)
            if (i + 1) % 4 == 0:
                optimizer.step()
                optimizer.zero_grad()

            # Free memory
            del outputs, loss, inputs, input_ids

        except Exception as e:
            print(f"    Skip example {i}: {e}", flush=True)
            continue

        if (i + 1) % 10 == 0:
            avg_loss = total_loss / max(num_batches, 1)
            print(f"    Chunk {chunk_idx + 1}/{total_chunks} — ex {i + 1}/{len(chunk)} — loss: {avg_loss:.4f}", flush=True)

    # Final optimizer step
    optimizer.step()
    optimizer.zero_grad()

    avg_loss = total_loss / max(num_batches, 1)
    return avg_loss


def main():
    parser = argparse.ArgumentParser(description="CPU LoRA fine-tuning Qwen2.5-3B")
    parser.add_argument("--chunk-size", type=int, default=500, help="Examples per chunk")
    parser.add_argument("--max-chunks", type=int, default=0, help="Max chunks (0 = all)")
    parser.add_argument("--resume", action="store_true", help="Resume from last checkpoint")
    parser.add_argument("--lr", type=float, default=1e-4, help="Learning rate")
    parser.add_argument("--max-seq-length", type=int, default=1024, help="Max sequence length")
    parser.add_argument("--dry-run", action="store_true", help="Check data without training")
    args = parser.parse_args()

    print("=" * 70)
    print("CPU LoRA Fine-tuning: Qwen2.5-3B-Instruct on WWI/WII historical data")
    print("=" * 70)
    print(f"Base model: {BASE_MODEL}")
    print(f"Training data: {TRAIN_FILE}")
    print(f"Chunk size: {args.chunk_size}")
    print(f"Max seq length: {args.max_seq_length}")
    print(f"Learning rate: {args.lr}")
    print(f"Output: {OUT_DIR}")
    print()

    # Load data
    print("Loading training data...")
    examples = load_all_examples()
    print(f"Total examples: {len(examples)}")

    chunks = chunk_list(examples, args.chunk_size)
    total_chunks = len(chunks)
    if args.max_chunks > 0:
        total_chunks = min(total_chunks, args.max_chunks)
    print(f"Total chunks: {total_chunks} ({args.chunk_size} examples each)")
    print()

    if args.dry_run:
        print("Dry-run complete. Data ready.")
        print(f"First chunk: {len(chunks[0])} examples")
        print(f"Last chunk: {len(chunks[-1])} examples")
        return

    # Resume
    start_chunk = 0
    if args.resume:
        last = load_progress()
        if last >= 0:
            start_chunk = last + 1
            print(f"Resuming from chunk {start_chunk + 1}/{total_chunks}")

    if start_chunk >= total_chunks:
        print("All chunks already completed!")
        return

    # Import heavy libraries
    print("\nLoading transformers + peft...")
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import LoraConfig, get_peft_model, TaskType

    torch.set_num_threads(max(1, os.cpu_count() - 1))
    device = torch.device("cpu")
    print(f"Device: {device} ({torch.get_num_threads()} threads)")

    # Load tokenizer
    print(f"\nLoading tokenizer: {BASE_MODEL}")
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Load model in float32 on CPU (0.5B fits in ~2GB)
    print(f"Loading model: {BASE_MODEL} (float32, CPU)")
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        torch_dtype=torch.float32,
        device_map="cpu",
        trust_remote_code=True,
        low_cpu_mem_usage=True,
    )

    # Apply LoRA
    print("Applying LoRA adapters...")
    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=8,
        lora_alpha=16,
        lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        bias="none",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # Optimizer
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=args.lr,
        weight_decay=0.01,
    )

    # Training loop
    print(f"\n{'=' * 70}")
    print(f"Training: {total_chunks - start_chunk} chunks, {args.chunk_size} examples each")
    print(f"{'=' * 70}")

    start_time = time.time()

    for chunk_idx in range(start_chunk, total_chunks):
        chunk = chunks[chunk_idx]
        chunk_start = time.time()

        print(f"\n--- Chunk {chunk_idx + 1}/{total_chunks} ({len(chunk)} examples) ---")

        avg_loss = train_chunk(
            model=model,
            tokenizer=tokenizer,
            chunk=chunk,
            chunk_idx=chunk_idx,
            total_chunks=total_chunks,
            optimizer=optimizer,
            device=device,
            max_seq_length=args.max_seq_length,
        )

        chunk_time = time.time() - chunk_start
        elapsed = time.time() - start_time
        remaining = (elapsed / (chunk_idx - start_chunk + 1)) * (total_chunks - chunk_idx - 1)

        print(f"  Chunk {chunk_idx + 1} done — avg loss: {avg_loss:.4f} — time: {chunk_time:.0f}s — ETA: {remaining:.0f}s")

        # Save checkpoint after each chunk
        ckpt_dir = OUT_DIR / f"checkpoint-{chunk_idx + 1}"
        ckpt_dir.mkdir(parents=True, exist_ok=True)
        model.save_pretrained(str(ckpt_dir))
        tokenizer.save_pretrained(str(ckpt_dir))
        save_progress(chunk_idx, total_chunks, (chunk_idx + 1) * args.chunk_size)
        print(f"  Checkpoint saved: {ckpt_dir}")

    # Save final adapter
    print(f"\n{'=' * 70}")
    print("Saving final LoRA adapter...")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(OUT_DIR))
    tokenizer.save_pretrained(str(OUT_DIR))
    print(f"Final adapter saved: {OUT_DIR}")

    total_time = time.time() - start_time
    print(f"\nTraining complete! Total time: {total_time:.0f}s ({total_time / 60:.1f} min)")
    print(f"Chunks trained: {total_chunks - start_chunk}")
    print(f"Examples processed: {(total_chunks - start_chunk) * args.chunk_size}")
    print(f"\nTo use in LM Studio:")
    print(f"  1. Copy {OUT_DIR}/adapter_model.safetensors to your LM Studio models folder")
    print(f"  2. Load Qwen2.5-3B-Instruct as base model")
    print(f"  3. Apply the LoRA adapter")


if __name__ == "__main__":
    main()
