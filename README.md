# Logche

Logche is a local-first personal logging app that turns short shorthand inputs into structured life logs.

Logche is my graduation project, and it will be implemented very very soon.

The product source of truth is the Obsidian vault in `Logche/`. Start with `Logche/Logche.md` for the overview and `Logche/Logche Architecture.md` for the current technical direction.

## Repository Contents

- `Logche/` contains the Obsidian product documentation.
- `quant-test/` contains a Rust GGUF metadata reader used to inspect local model files.
- `scripts/` contains helper scripts for prompt, hardware, and thesis workflows.
- `thesis/` contains the local LaTeX bachelor thesis material.
- `CHANGES.md` tracks meaningful development progress for thesis evidence.
- `docs/development-log/` contains longer development notes when useful.

## Local Models

Local model files are expected outside the repo under `~/models` and should not be committed.

Current model notes live in `Logche/Model Information/` and `Logche/Fine Tuned Model.md`.

## Thesis

Thesis material lives in `thesis/`. Read `thesis/WRITING_STYLE.md` before editing thesis files.

Build the thesis with:

```bash
./scripts/build-thesis.sh
```

## Agent Instructions

Agent-specific rules live in `AGENTS.md`.

## Status

This is an early prototype/design repository. The main implemented code currently lives in `quant-test/`.
