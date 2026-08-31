# Logche Benchmark

The benchmark compares system prompts on Logche datasets using one model at a time.
For one run, the matrix is:

```text
selected model x every prompt x every discovered dataset x selected cases
```

The benchmark does not start model servers. A model must already be available through
an OpenAI-compatible `/chat/completions` endpoint. The configured `local` model is
Qwen3-0.6B.

## Quick Start

For a guided run, simply start the benchmark without arguments:

```bash
python -m benchmark
```

The wizard asks for the model, dataset folder, CSV filename, datasets or all,
prompts or all, validation/test/all-row evaluation, an optional case limit,
parallel workers from 1 to 3, and the output directory.

See what is available before running anything:

```bash
python -m benchmark list models
python -m benchmark list prompts
python -m benchmark list datasets
```

Check which datasets will be used:

```bash
python -m benchmark validate
```

Run a small category-specific smoke test:

```bash
python -m benchmark run --model qwen3-0.6b \
  --dataset gym-data.csv \
  --prompt gym-strict --prompt gym-fewshot \
  --limit 2
```

Run the full validation split:

```bash
python -m benchmark run --model qwen3-0.6b
```

The default dataset folder is `benchmark/generated-datasets/`. The default
split is `validation`. When `--output` is omitted, `run` creates a timestamped result
directory. If
`--model` is omitted in an interactive terminal, the CLI presents a model menu.

## Datasets

Generate standardized copies of the source datasets with:

```bash
python -m benchmark prepare
```

This reads source files from `datasets/` and writes copies to
`benchmark/generated-datasets/`. Re-run it after changing a source CSV. Use
`--source`, `--csv-name`, or `--output` when the layout changes.

The runner recursively searches for `training.csv` files. The dataset name is the
parent directory followed by `.csv`:

```text
datasets/food-data/training.csv -> food-data.csv
datasets/gym-data/training.csv  -> gym-data.csv
```

If the filename changes, use `--csv-name`:

```bash
python -m benchmark run --model qwen3-0.6b --csv-name examples.csv
```

For exact selection, use one or more explicit paths:

```bash
python -m benchmark validate \
  --csv datasets/food-data/training.csv \
  --csv datasets/gym-data/training.csv
```

Run only selected discovered datasets with `--dataset`:

```bash
python -m benchmark run --model qwen3-0.6b \
  --dataset food-data.csv --dataset gym-data.csv
```

Duplicate parent directory names are rejected instead of being silently merged.

### Standard CSV Format

New datasets should use this header:

```text
id,input,context,expected,group_id
```

Example:

```csv
id,input,context,expected,group_id
gym-data:000001,60x4,"[{""role"":""user"",""content"":""snatch set6 60kgx4""}]","{""exercise"":""snatch"",""setNumber"":7,""reps"":4,""weightKg"":60}",session-001
```

Column meanings:

- `id`: unique stable case identifier.
- `input`: shorthand sent as the current user message.
- `context`: JSON array of prior chat messages. Use `[]` when there is no context.
- `expected`: canonical expected JSON object.
- `group_id`: related cases that must stay in the same split.

Run validation before benchmarking:

```bash
python -m benchmark validate
```

The loader also supports the current legacy CSV formats in the repository, including
gym `previousInput`, until those files are migrated to the standard schema.

## Models

Models are registered in `benchmark/models.json`. Only the model selected with
`--model` runs during a command.

```json
{
  "my-model": {
    "base_url": "http://localhost:8080/v1",
    "model": "model-name-used-by-server",
    "api_key_env": "OPENAI_API_KEY"
  }
}
```

Run it with:

```bash
python -m benchmark run --model my-model
```

The included Qwen entries are candidates from the project README. Their endpoint is
the same because only one local model is expected to be served at a time.

## Prompts

Every `.txt` file in `benchmark/prompts/` is included by default. The filename
without `.txt` becomes the prompt ID.

```text
benchmark/prompts/baseline.txt      -> baseline
benchmark/prompts/strict-json.txt   -> strict-json
benchmark/prompts/my-prompt.txt     -> my-prompt
```

Add or remove prompt files without changing the Python code.

The category-specific prompts have `strict`, `fewshot`, and `questions` variants for
food, gym, movement, money, and media. They use extraction-only contracts;
deterministic app code handles calorie lookup, totals, unit/time normalization, and
derived values.
The food prompts support both `food-data.csv` and
`multi-food-data.csv` because they share one output schema. Select matching prompts
with repeatable `--prompt` options when the input category is known:

```bash
python -m benchmark run --model qwen3-0.6b \
  --dataset money-data.csv \
  --prompt money-strict --prompt money-fewshot
```

An unknown prompt ID is rejected. Omitting `--prompt` runs all matching category
prompts for each discovered dataset. Explicitly selecting a prompt does not bypass
category routing. Global prompts are intentionally not active.

## Evaluation Modes

By default, the benchmark creates deterministic grouped splits and evaluates the
`validation` split:

```bash
python -m benchmark run --model qwen3-0.6b --split validation
```

Available splits are `train`, `validation`, and `test`. Use the test split only for
final comparisons:

```bash
python -m benchmark run --model qwen3-0.6b --split test
```

Raw models that were not trained on these datasets can be evaluated on every row:

```bash
python -m benchmark run --model qwen3-0.6b --scope all
```

Create and inspect a split manifest separately when needed:

```bash
python -m benchmark split --output benchmark-results/splits.json
```

`group_id` keeps related examples together. This prevents cases such as gym sets
from one session from being spread across multiple splits.

When a legacy dataset has only row-unique group IDs, the loader derives stable
groups from food item signatures, media titles, money transaction signatures, and
gym context chains before splitting. This reduces leakage for the current datasets;
source-level provenance IDs remain preferable for future dataset regeneration.

## Inference

The benchmark uses one model response per case. Generic second-opinion inference was
removed because it doubled latency and did not improve the recorded results.

## Limit and Dry Run

`--limit N` is only for smoke tests. It runs at most `N` cases per dataset, for each
prompt:

```bash
python -m benchmark run --model qwen3-0.6b --limit 2
```

It does not permanently change the dataset or split.

Requests are sequential by default. Enable bounded parallel execution with up to
three workers:

```bash
python -m benchmark run --model qwen3-0.6b --workers 3
```

Progress is printed after every completed case and each result is flushed immediately
to `results.jsonl`. Use `--workers 1` for the most consistent latency measurements.

Use `--dry-run` to inspect the matrix without contacting the model:

```bash
python -m benchmark run --model qwen3-0.6b --limit 2 --dry-run
```

## Results and Winner

Results are written incrementally to:

```text
benchmark-results/run/
├── results.jsonl
└── summary.json
```

Each JSONL record contains the model, prompt, dataset, case, expected output, raw
output, parsed output, latency, status, and scores. Interrupted cases can be resumed
by running the same command again.

The report contains two metrics. `macroExtractionF1` evaluates fields owned by the
model extraction contract. `macroFieldF1` is the end-to-end score against the final
object and remains a diagnostic until deterministic enrichment is connected:

1. Calculate each layer's field F1 for every case.
2. Average cases within each dataset.
3. Average dataset scores equally.
4. Rank each model and prompt combination.

There is one overall winner: the highest-scoring model and prompt combination.
Dataset scores are shown as diagnostics, not as separate model winners.

View a completed result:

```bash
python -m benchmark report benchmark-results/run
```

The main CLI also exposes discovery and selection help:

```bash
python -m benchmark --help
python -m benchmark run --help
python -m benchmark list --help
```

Additional recorded metrics include valid JSON rate, exact match rate, field
precision, field recall, hallucinated fields, and latency.

## Commands

```bash
python -m benchmark --help
python -m benchmark validate
python -m benchmark prepare
python -m benchmark split
python -m benchmark run --model MODEL
python -m benchmark run --model MODEL --dataset DATASET --prompt PROMPT
python -m benchmark run --model MODEL --scope all
python -m benchmark run --model MODEL --workers 3
python -m benchmark report benchmark-results/run
```

For Qwen3, start the server with thinking disabled and Jinja templates enabled:

```bash
llama-server -m /path/to/Qwen3-0.6B.gguf --jinja --reasoning off
```

The client also sends `chat_template_kwargs` with `enable_thinking: false` and
requests JSON mode. JSON mode constrains syntax; application validation must still
check field values and calculations.
