# Changes

Chronological development index for Logche and the thesis.

Newest entries should be added at the top.
Each meaningful commit should update this file or a related development-log entry.

## Unreleased

- Added a self-contained benchmark harness under `benchmark/` with dataset discovery, model and prompt registration, one-model-at-a-time evaluation, deterministic splits or full-dataset evaluation, layered JSON scoring, resumable JSONL results, and documentation.
- Selected Qwen3-0.6B as the current working model, disabled thinking for local serving, removed global prompts and generic second-opinion inference, and added category-specific question-checklist prompts.
- Prepared the movie and book rating datasets: 1,878 shorthand training examples for ratings and favorites.
- Prepared the USDA FoodData Central Foundation Foods dataset: 347 shorthand training examples for food and calorie logging.
- Prepared a curated USDA multi-food dataset: 1,000 shorthand training examples with source-grounded item lists and calorie totals.
- Prepared the Kaggle money dataset: 1,129 shorthand training examples for income, expenses, and transfers.
- Prepared the Strong gym dataset: 1,868 set-level examples with shortnames, relative weight notation, and previous-input context.
- Prepared the PMData movement dataset for initial fine-tuning: 2,246 shorthand training rows.
- Added a GitHub Pages showcase for the Logche research prototype, including the local architecture, Qwen model comparison, fine-tuning workflows, and Rust quantization path.
- Initialized thesis structure with a project-based LaTeX skeleton, writing-style guide, appendix placeholders, and development-log directory.
