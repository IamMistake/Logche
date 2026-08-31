import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from .inference import call
from .parsing import parse_output
from .contracts import category_for_dataset, contract_for_dataset
from .scoring import score_layers


def prompts(directory):
    return [(p.stem, p.read_text(encoding="utf-8")) for p in sorted(Path(directory).glob("*.txt"))]


def messages(prompt, case):
    return [{"role": "system", "content": prompt}] + case["context"] + [{"role": "user", "content": case["input"]}]


def prompt_applies(prompt_id, dataset_id):
    """Run a prompt only against its matching dataset category."""
    return prompt_id.split("-", 1)[0] == category_for_dataset(dataset_id)


def _evaluate(model_id, model, prompt_id, prompt, prompt_hash, dataset_id, case, evaluation_scope, temperature, max_tokens, timeout):
    first, first_ms, error = call(model, messages(prompt, case), temperature, max_tokens, timeout)
    first_parsed = parse_output(first)
    contract = contract_for_dataset(dataset_id)
    passes = [{"output": first, "parsedOutput": first_parsed, "latencyMs": first_ms, "scores": score_layers(case["expected"], first_parsed, contract)}]
    return {"modelId": model_id, "promptId": prompt_id, "promptSha256": prompt_hash, "datasetId": dataset_id, "caseId": case["id"], "evaluationScope": evaluation_scope, "expected": case["expected"], "passes": passes, "officialPass": len(passes), "status": "error" if error else "ok", "error": error}


def run(model_id, model, datasets, prompt_dir, output_dir, split_name="validation", scope=None, limit=None, temperature=0.0, max_tokens=400, timeout=120, prompt_ids=None, workers=1):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    result_file = output_dir / "results.jsonl"
    done = set()
    if result_file.exists():
        for line in result_file.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
                if record.get("status") == "ok":
                    done.add((record["promptId"], record["datasetId"], record["caseId"]))
            except (json.JSONDecodeError, KeyError):
                pass
    prompt_list = prompts(prompt_dir)
    if prompt_ids is not None:
        prompt_list = [(prompt_id, text) for prompt_id, text in prompt_list if prompt_id in prompt_ids]
    tasks = []
    for prompt_id, prompt in prompt_list:
        for dataset_id, rows in datasets.items():
            prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()
            cases = [case for part in rows.values() for case in part] if scope == "all" else rows[split_name]
            if limit:
                cases = cases[:limit]
            if prompt_applies(prompt_id, dataset_id):
                tasks.extend((prompt_id, prompt, prompt_hash, dataset_id, case) for case in cases if (prompt_id, dataset_id, case["id"]) not in done)
    total = len(tasks) + len(done)
    completed = len(done)
    print(f"Progress: {completed}/{total} cases already complete; workers={workers}", flush=True)
    with result_file.open("a", encoding="utf-8") as output, ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_evaluate, model_id, model, prompt_id, prompt, prompt_hash, dataset_id, case, scope or split_name, temperature, max_tokens, timeout) for prompt_id, prompt, prompt_hash, dataset_id, case in tasks]
        for future in as_completed(futures):
            record = future.result()
            output.write(json.dumps(record, ensure_ascii=True) + "\n")
            output.flush()
            completed += 1
            print(f"Progress: {completed}/{total} | {record['promptId']} | {record['datasetId']} | {record['caseId']} | {record['status']}", flush=True)


def report(output_dir):
    records = [json.loads(line) for line in (Path(output_dir) / "results.jsonl").read_text(encoding="utf-8").splitlines() if line]
    groups = {}
    for record in records:
        official = record["passes"][record["officialPass"] - 1]["scores"]
        groups.setdefault((record["modelId"], record["promptId"]), []).append((record["datasetId"], official))
    summary = []
    for (model, prompt), values in groups.items():
        by_dataset = {}
        for dataset, metrics in values:
            end_to_end = metrics.get("endToEnd", metrics)
            by_dataset.setdefault(dataset, []).append(end_to_end["fieldF1"])
        dataset_scores = [sum(scores) / len(scores) for scores in by_dataset.values()]
        extraction_by_dataset = {}
        for dataset, metrics in values:
            extraction = metrics.get("extraction", metrics)
            extraction_by_dataset.setdefault(dataset, []).append(extraction["fieldF1"])
        extraction_scores = [sum(scores) / len(scores) for scores in extraction_by_dataset.values()]
        summary.append({"modelId": model, "promptId": prompt, "macroFieldF1": sum(dataset_scores) / len(dataset_scores), "macroExtractionF1": sum(extraction_scores) / len(extraction_scores), "cases": len(values), "datasets": {key: sum(value) / len(value) for key, value in by_dataset.items()}, "extractionDatasets": {key: sum(value) / len(value) for key, value in extraction_by_dataset.items()}})
    summary.sort(key=lambda item: item["macroFieldF1"], reverse=True)
    (Path(output_dir) / "summary.json").write_text(json.dumps({"generatedAt": datetime.now(timezone.utc).isoformat(), "winner": summary[0] if summary else None, "results": summary}, indent=2), encoding="utf-8")
    return summary
