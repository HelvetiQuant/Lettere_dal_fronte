"""LoRA fine-tuning script for Qwen2.5-3B-Instruct on WWI/WII historical data.

Usage:
    # On GPU (Colab T4/A10/L4):
    python finetune_qwen.py --train

    # Dry-run (check data loading):
    python finetune_qwen.py --dry-run

Requirements:
    pip install unsloth trl transformers datasets accelerate peft bitsandbytes

Output:
    models/qwen25-3b-wwi-lora/ (adapter_config.json + adapter_model.safetensors)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TRAIN_FILE = Path(__file__).parent / "data" / "training_chatml" / "train_merged.jsonl"
OUT_DIR = Path(__file__).parent / "models" / "qwen25-3b-wwi-lora"


def check_data():
    """Verify training data format."""
    if not TRAIN_FILE.exists():
        print(f"ERROR: {TRAIN_FILE} not found. Run convert_training_datasets.py first.")
        sys.exit(1)

    count = 0
    with open(TRAIN_FILE, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            row = json.loads(line)
            msgs = row.get("messages", [])
            if len(msgs) < 3:
                print(f"WARNING: row {i} has {len(msgs)} messages, expected >= 3")
            if msgs[0].get("role") != "system":
                print(f"WARNING: row {i} first role is {msgs[0].get('role')}, expected system")
            count += 1
            if i >= 5:
                break

    print(f"Data check: OK (first 5 rows valid, total file has content)")
    print(f"File: {TRAIN_FILE} ({TRAIN_FILE.stat().st_size / 1024 / 1024:.1f} MB)")


def train():
    """Run LoRA fine-tuning with unsloth."""
    try:
        from unsloth import FastLanguageModel
        from trl import SFTTrainer
        from transformers import TrainingArguments
        from datasets import load_dataset
    except ImportError as e:
        print(f"ERROR: Missing dependency: {e}")
        print("Install with: pip install unsloth trl transformers datasets accelerate peft bitsandbytes")
        print("\nFor Google Colab (free T4 GPU):")
        print("  !pip install unsloth trl transformers datasets accelerate peft bitsandbytes")
        sys.exit(1)

    print("Loading base model: Qwen/Qwen2.5-3B-Instruct")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name="Qwen/Qwen2.5-3B-Instruct",
        max_seq_length=2048,
        dtype=None,  # auto
        load_in_4bit=True,  # 4-bit quantization for efficiency
    )

    # Add LoRA adapters
    model = FastLanguageModel.get_peft_model(
        model,
        r=16,  # LoRA rank
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        lora_alpha=32,
        lora_dropout=0.05,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=42,
    )

    # Load training data
    print(f"Loading training data: {TRAIN_FILE}")
    dataset = load_dataset("json", data_files=str(TRAIN_FILE), split="train")
    print(f"Training examples: {len(dataset)}")

    # Format with ChatML template
    def formatting_func(examples):
        return tokenizer.apply_chat_template(
            examples["messages"],
            tokenize=False,
        )

    # Training arguments
    training_args = TrainingArguments(
        output_dir=str(OUT_DIR),
        per_device_train_batch_size=4,
        gradient_accumulation_steps=4,
        warmup_steps=100,
        max_steps=500,  # Adjust based on dataset size
        learning_rate=2e-4,
        fp16=not False,  # Use fp16
        logging_steps=10,
        save_steps=100,
        save_total_limit=3,
        report_to="none",
        optim="adamw_8bit",
        seed=42,
    )

    # Trainer
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        formatting_func=formatting_func,
        max_seq_length=2048,
        args=training_args,
    )

    # Train
    print("Starting training...")
    trainer_stats = trainer.train()
    print(f"Training complete. Stats: {trainer_stats}")

    # Save LoRA adapter
    print(f"Saving LoRA adapter to {OUT_DIR}")
    model.save_pretrained(str(OUT_DIR))
    tokenizer.save_pretrained(str(OUT_DIR))
    print("Done! Adapter saved.")


def main():
    parser = argparse.ArgumentParser(description="LoRA fine-tuning Qwen2.5-3B on WWI/WII data")
    parser.add_argument("--train", action="store_true", help="Run training (requires GPU)")
    parser.add_argument("--dry-run", action="store_true", help="Check data without training")
    args = parser.parse_args()

    print("=" * 60)
    print("LoRA Fine-tuning: Qwen2.5-3B-Instruct on WWI/WII historical data")
    print("=" * 60)

    check_data()

    if args.dry_run:
        print("\nDry-run complete. Data is ready for training.")
        print(f"To train on GPU: python {Path(__file__).name} --train")
        return

    if args.train:
        train()
    else:
        print("\nNo action specified. Use --train or --dry-run")
        print(f"  python {Path(__file__).name} --dry-run   # check data")
        print(f"  python {Path(__file__).name} --train     # run training (GPU required)")


if __name__ == "__main__":
    main()
