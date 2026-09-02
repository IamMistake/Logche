import argparse
import json
from pathlib import Path
from datetime import datetime

from .datasets import discover, file_hash, load, split
from .runner import prompt_applies
from .runner import report, run

ROOT = Path(__file__).parent
DATASETS = ROOT.parent / "datasets"


def _datasets(args):
    found = discover(args.datasets, args.csv_name, args.csv)
    if args.dataset:
        wanted = set(args.dataset)
        found = [(name, path) for name, path in found if name in wanted or name.removesuffix(".csv") in wanted]
        missing = wanted - {name for name, _ in found} - {name.removesuffix(".csv") for name, _ in found}
        if missing:
            raise SystemExit("unknown dataset(s): " + ", ".join(sorted(missing)))
    return {name: load(name, path) for name, path in found}, found


def _models():
    return json.loads((ROOT / "models.json").read_text(encoding="utf-8"))


def _choose_model(models):
    if not models:
        raise SystemExit("no models configured in benchmark/models.json")
    print("Available models:")
    names = list(models)
    for index, name in enumerate(names, 1):
        print(f"  {index}. {name}")
    while True:
        choice = input("Select model number: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(names):
            return names[int(choice) - 1]
        print("Enter one of the listed numbers.")


def _choose_many(title, values):
    print(f"\n{title}")
    print("  0. All")
    for index, value in enumerate(values, 1):
        print(f"  {index}. {value}")
    while True:
        choice = input("Choose numbers separated by commas [0]: ").strip() or "0"
        if choice == "0":
            return values
        try:
            indexes = [int(part.strip()) for part in choice.split(",")]
            if indexes and all(1 <= index <= len(values) for index in indexes):
                return [values[index - 1] for index in indexes]
        except ValueError:
            pass
        print("Use 0, or valid numbers separated by commas.")


def _interactive():
    if not __import__("sys").stdin.isatty():
        raise SystemExit("interactive mode requires a terminal; use --help for command-line usage")
    models = _models()
    model_id = _choose_model(models)
    dataset_root = input(f"\nDataset folder [{DATASETS}]: ").strip() or str(DATASETS)
    csv_name = input("CSV filename [training.csv]: ").strip() or "training.csv"
    found = discover(dataset_root, csv_name)
    if not found:
        raise SystemExit(f"no {csv_name} files found under {dataset_root}")
    dataset_names = _choose_many("Datasets", [name for name, _ in found])
    dataset_paths = dict(found)
    datasets = {name: load(name, dataset_paths[name]) for name in dataset_names}
    prompt_names = [path.stem for path in sorted((ROOT / "prompts").glob("*.txt"))]
    selected_prompts = _choose_many("System prompts", prompt_names)
    print("\nEvaluation data")
    print("  1. Validation split (recommended)")
    print("  2. Test split")
    print("  3. All rows (raw model)")
    while True:
        scope_choice = input("Choose evaluation data [1]: ").strip() or "1"
        if scope_choice in {"1", "2", "3"}:
            break
        print("Choose 1, 2, or 3.")
    split_name = {"1": "validation", "2": "test", "3": "validation"}[scope_choice]
    scope = "all" if scope_choice == "3" else None
    while True:
        limit_text = input("Limit cases per dataset, or press Enter for all: ").strip()
        if not limit_text:
            limit = None
            break
        if limit_text.isdigit() and int(limit_text) > 0:
            limit = int(limit_text)
            break
        print("Enter a positive whole number or leave it empty.")
    output = input("Output directory, or press Enter for timestamped default: ").strip() or "benchmark-results/" + datetime.now().strftime("%Y%m%d-%H%M%S")
    while True:
        workers_text = input("Parallel workers, 1-3 [1]: ").strip() or "1"
        if workers_text in {"1", "2", "3"}:
            workers = int(workers_text)
            break
        print("Choose 1, 2, or 3.")
    prepared = {name: split(rows, name) for name, rows in datasets.items()}
    print(f"\nStarting {model_id} with {len(selected_prompts)} prompt(s) on {len(datasets)} dataset(s), workers={workers}.")
    run(model_id, models[model_id], prepared, ROOT / "prompts", output, split_name, scope, limit, 0.0, 400, 120, set(selected_prompts), workers)
    result = report(output)
    print(json.dumps({"winner": result[0] if result else None, "output": output}, indent=2))


def main():
    parser = argparse.ArgumentParser(
        prog="python -m benchmark",
        description="Benchmark one model with every system prompt against discovered Logche datasets.",
        epilog="Examples:\n"
        "  %(prog)s validate --datasets datasets/\n"
        "  %(prog)s run --datasets datasets/ --model local --limit 2\n"
        "  %(prog)s run --datasets datasets/ --model local --scope all\n"
        "  %(prog)s report benchmark-results/run",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--datasets", default=str(DATASETS), help="root folder searched recursively (default: datasets/)")
    common.add_argument("--csv-name", default="training.csv", help="CSV filename to discover (default: training.csv)")
    common.add_argument("--csv", action="append", help="use an explicit CSV path instead; repeatable")
    common.add_argument("--dataset", action="append", help="only use this dataset ID; repeatable")
    sub.add_parser("validate", parents=[common], help="find and validate dataset CSV files")
    split_cmd = sub.add_parser("split", parents=[common], help="create deterministic train/validation/test splits")
    split_cmd.add_argument("--output", default="benchmark-results/splits.json", help="split manifest output path")
    run_cmd = sub.add_parser("run", parents=[common], help="run one model across prompts and datasets")
    run_cmd.add_argument("--model", help="model ID from benchmark/models.json; omit for interactive selection")
    run_cmd.add_argument("--prompt", action="append", help="only use this prompt ID; repeatable")
    run_cmd.add_argument("--scope", choices=["all", "split"], default="split", help="use every row or one deterministic split")
    run_cmd.add_argument("--split", dest="split_name", choices=["train", "validation", "test"], default="validation", help="split to run when scope is split")
    run_cmd.add_argument("--limit", type=int, metavar="N", help="smoke-test only: run at most N cases per dataset")
    run_cmd.add_argument("--temperature", type=float, default=0.0, help="sampling temperature (default: 0)")
    run_cmd.add_argument("--max-tokens", type=int, default=400, help="maximum generated tokens (default: 400)")
    run_cmd.add_argument("--timeout", type=int, default=120, help="request timeout in seconds (default: 120)")
    run_cmd.add_argument("--workers", type=int, choices=[1, 2, 3], default=1, help="parallel requests, maximum 3 (default: 1)")
    run_cmd.add_argument("--output", help="result directory (default: unique timestamped directory)")
    run_cmd.add_argument("--dry-run", action="store_true", help="show the matrix without calling the model")
    report_cmd = sub.add_parser("report", help="rank completed model/prompt combinations")
    report_cmd.add_argument("output_dir", help="result directory containing results.jsonl")
    list_cmd = sub.add_parser("list", help="list configured models, prompts, or discovered datasets")
    list_cmd.add_argument("target", choices=["models", "prompts", "datasets"], help="what to list")
    list_cmd.add_argument("--datasets", default=str(DATASETS), help="root folder searched for datasets")
    list_cmd.add_argument("--csv-name", default="training.csv", help="CSV filename to discover")
    list_cmd.add_argument("--csv", action="append", help="explicit CSV path; repeatable")
    args = parser.parse_args()
    if not args.command:
        _interactive()
        return
    if args.command == "report":
        summary = report(args.output_dir)
        print(json.dumps({"winner": summary[0] if summary else None, "combinations": len(summary)}, indent=2))
        return
    if args.command == "list":
        if args.target == "models":
            for name, model in _models().items():
                print(f"{name}: {model['base_url']} ({model['model']})")
        elif args.target == "prompts":
            for path in sorted((ROOT / "prompts").glob("*.txt")):
                print(path.stem)
        else:
            for name, path in discover(args.datasets, args.csv_name, args.csv):
                print(f"{name}: {path}")
        return
    datasets, found = _datasets(args)
    if args.command == "validate":
        print(json.dumps({"datasets": [{"id": name, "path": str(path), "rows": len(datasets[name]), "sha256": file_hash(path)} for name, path in found]}, indent=2))
    elif args.command == "split":
        result = {name: split(rows, name) for name, rows in datasets.items()}
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"wrote {args.output}")
    else:
        models = _models()
        if not args.model:
            if not __import__("sys").stdin.isatty():
                raise SystemExit("--model is required when not running interactively")
            args.model = _choose_model(models)
        if args.model not in models:
            raise SystemExit(f"unknown model {args.model}; add it to benchmark/models.json")
        prompt_ids = set(args.prompt) if args.prompt else None
        if prompt_ids:
            known_prompts = {path.stem for path in (ROOT / "prompts").glob("*.txt")}
            unknown_prompts = prompt_ids - known_prompts
            if unknown_prompts:
                raise SystemExit("unknown prompt(s): " + ", ".join(sorted(unknown_prompts)))
        if not args.output:
            args.output = "benchmark-results/" + datetime.now().strftime("%Y%m%d-%H%M%S")
        prepared = {name: split(rows, name) for name, rows in datasets.items()}
        if args.dry_run:
            counts = {}
            selected_prompts = [path.stem for path in (ROOT / "prompts").glob("*.txt") if not prompt_ids or path.stem in prompt_ids]
            for name, rows in prepared.items():
                cases = [case for part in rows.values() for case in part] if args.scope == "all" else rows[args.split_name]
                count = min(len(cases), args.limit) if args.limit else len(cases)
                counts[name] = {prompt: count if prompt_applies(prompt, name) else 0 for prompt in selected_prompts}
            print(json.dumps({"model": args.model, "prompts": selected_prompts, "datasets": counts, "note": "no inference performed"}, indent=2))
            return
        run(args.model, models[args.model], prepared, ROOT / "prompts", args.output, args.split_name, "all" if args.scope == "all" else None, args.limit, args.temperature, args.max_tokens, args.timeout, prompt_ids, args.workers)
        result = report(args.output)
        print(json.dumps({"winner": result[0] if result else None, "output": args.output}, indent=2))
