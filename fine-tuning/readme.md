# Logche Fine-Tuning

This folder contains the complete Qwen3-0.6B LoRA training workflow.

## Layout

- `dataset-split/split_it.py` combines every `datasets/*/training.csv`, keeps related examples in the same split, adds category prompts, and writes deterministic CSV files.
- `dataset-split/train.csv` updates the adapter.
- `dataset-split/validation.csv` is evaluated after each epoch.
- `dataset-split/test.csv` is reserved for final testing and is not loaded by the trainer.
- `train.py` contains the model and training constants, trains the adapter, and writes reproducibility metadata.
- `archive/` contains one directory per trained adapter.

## Prepare Data

From the repository root:

```bash
python fine-tuning/dataset-split/split_it.py
```

The split uses seed `42` and keeps related records together to prevent leakage.
Prompts and expected compact JSON completions are stored directly in each output row.
Only the six intended source datasets are included. `datasets/external-money-data/`
is retained for separate evaluation and is intentionally excluded from training.

## Train

Install the environment, review the constants at the top of `train.py`, and run:

```bash
python -m pip install -r fine-tuning/requirements.txt
python fine-tuning/train.py
```

The default run trains a rank-16 LoRA adapter for three epochs with an effective
batch size of 32. Qwen thinking is disabled and loss is calculated only on the
assistant JSON completion.

The output is saved to:

```text
fine-tuning/archive/qwen3-0.6b-lora/
```

Each completed adapter directory includes its weights, tokenizer, configuration,
and `reproducibility.json`.
