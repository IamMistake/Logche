# Logche

Logche is a local-first personal logging concept and research project for turning short shorthand inputs into structured life logs.

Logche is my graduation project. The product is still in design and research, with a local benchmark harness now implemented for model evaluation.

The product source of truth is the Obsidian vault in `Logche/`. Start with `Logche/Logche.md` for the overview and `Logche/Logche Architecture.md` for the current technical direction.

## Repository Contents

- `Logche/` contains the Obsidian product documentation.
- `scripts/` contains helper scripts for prompt, hardware, and thesis workflows.
- `benchmark/` contains the prompt and dataset benchmark harness.
- `thesis/` contains the local LaTeX bachelor thesis material.
- `CHANGES.md` tracks meaningful development progress for thesis evidence.

## Local Models

Local model files are expected outside the repo under `~/models` and should not be committed.

Qwen3.5-0.8B, Qwen3-0.6B, and Qwen2.5-0.5B-Instruct are research candidates, not selected or fine-tuned models.

Current model notes live in `Logche/Model Information/` and `Logche/Fine Tuned Model.md`.

## Planned Research Direction

- Compare prompting, LoRA, QLoRA, and full fine-tuning for shorthand-to-structure conversion.
- Investigate Rust as the core systems layer for parsing, local model execution, storage access, and quantization.
- Evaluate GGUF as a compact local model format after model quality is established.
- Compare SQLite and Turso as storage options for the local-first design.

## Thesis

Thesis material lives in `thesis/`. Read `thesis/WRITING_STYLE.md` before editing thesis files.

Build the thesis with:

```bash
./scripts/build-thesis.sh
```

## Agent Instructions

Agent-specific rules live in `AGENTS.md`.

## Status

This is a design and research repository. The mobile app, fine-tuned model, and Rust inference/quantization engine are not implemented here. The Python benchmark harness is implemented under `benchmark/`; generated benchmark results are not committed.
