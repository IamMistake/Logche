"""Fine-tune Qwen3-0.6B with LoRA for Logche JSON extraction."""

import csv
import hashlib
import importlib.metadata
import json
from datetime import datetime, timezone
from pathlib import Path

import torch
from datasets import load_dataset
from peft import LoraConfig
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import SFTConfig, SFTTrainer


ROOT = Path(__file__).resolve().parent
MODEL = "Qwen/Qwen3-0.6B"
DATA_DIR = ROOT / "dataset-split"
OUTPUT_DIR = ROOT / "archive" / "qwen3-0.6b-lora"

EPOCHS = 3
BATCH_SIZE = 2
GRADIENT_ACCUMULATION = 16
MAX_LENGTH = 512
LEARNING_RATE = 2e-4
WARMUP_RATIO = 0.05
SEED = 42

LORA_RANK = 16
LORA_ALPHA = 32
LORA_DROPOUT = 0.05


def render(example, tokenizer):
    prompt = tokenizer.apply_chat_template(
        json.loads(example["prompt"]),
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )
    return {"prompt": prompt, "completion": example["completion"] + tokenizer.eos_token}


def file_info(path):
    with path.open(newline="", encoding="utf-8") as handle:
        rows = sum(1 for _ in csv.reader(handle)) - 1
    return {"rows": rows, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def save_reproducibility():
    packages = ["torch", "transformers", "trl", "peft", "datasets", "accelerate", "safetensors"]
    record = {
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "model": MODEL,
        "method": "LoRA",
        "command": "python fine-tuning/train.py",
        "configuration": {
            "precision": "bfloat16" if torch.cuda.is_bf16_supported() else "float16",
            "epochs": EPOCHS,
            "batchSize": BATCH_SIZE,
            "gradientAccumulation": GRADIENT_ACCUMULATION,
            "effectiveBatchSize": BATCH_SIZE * GRADIENT_ACCUMULATION,
            "maxLength": MAX_LENGTH,
            "learningRate": LEARNING_RATE,
            "warmupRatio": WARMUP_RATIO,
            "loraRank": LORA_RANK,
            "loraAlpha": LORA_ALPHA,
            "loraDropout": LORA_DROPOUT,
            "targetModules": "all-linear",
            "thinking": False,
            "seed": SEED,
        },
        "datasets": {path.name: file_info(path) for path in sorted(DATA_DIR.glob("*.csv"))},
        "software": {package: importlib.metadata.version(package) for package in packages},
        "gpu": torch.cuda.get_device_name() if torch.cuda.is_available() else None,
    }
    (OUTPUT_DIR / "reproducibility.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def main():
    tokenizer = AutoTokenizer.from_pretrained(MODEL)
    tokenizer.pad_token = tokenizer.pad_token or tokenizer.eos_token
    dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=dtype)

    datasets = load_dataset("csv", data_files={"train": str(DATA_DIR / "train.csv"), "validation": str(DATA_DIR / "validation.csv")})
    datasets = datasets.map(lambda example: render(example, tokenizer), remove_columns=datasets["train"].column_names)

    trainer = SFTTrainer(
        model=model,
        train_dataset=datasets["train"],
        eval_dataset=datasets["validation"],
        processing_class=tokenizer,
        peft_config=LoraConfig(
            r=LORA_RANK,
            lora_alpha=LORA_ALPHA,
            lora_dropout=LORA_DROPOUT,
            target_modules="all-linear",
            task_type="CAUSAL_LM",
        ),
        args=SFTConfig(
            output_dir=str(OUTPUT_DIR),
            num_train_epochs=EPOCHS,
            per_device_train_batch_size=BATCH_SIZE,
            gradient_accumulation_steps=GRADIENT_ACCUMULATION,
            gradient_checkpointing=True,
            learning_rate=LEARNING_RATE,
            warmup_ratio=WARMUP_RATIO,
            lr_scheduler_type="cosine",
            max_length=MAX_LENGTH,
            completion_only_loss=True,
            bf16=dtype == torch.bfloat16,
            fp16=dtype == torch.float16,
            eval_strategy="epoch",
            save_strategy="epoch",
            save_total_limit=2,
            logging_steps=1,
            report_to="none",
            seed=SEED,
        ),
    )
    trainer.train()
    trainer.save_model(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
    save_reproducibility()


if __name__ == "__main__":
    main()
