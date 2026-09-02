"""Combine Logche datasets into deterministic training, validation, and test CSVs."""

import csv
import json
import random
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DATASETS_DIR = ROOT / "datasets"
OUTPUT_DIR = Path(__file__).resolve().parent
SEED = 42
INCLUDED_DATASETS = {"food-data", "gym-data", "media-data", "money-data", "movement-data", "multi-food-data"}

STANDARD_COLUMNS = {"id", "input", "context", "expected", "group_id"}
OUTPUT_COLUMNS = ("id", "dataset_id", "category", "prompt", "completion", "group_id")
ITEM_FIELDS = ("name", "quantity", "unit")
FIELDS = {
    "food": ("items", "mealType"),
    "gym": ("exercise", "setNumber", "reps", "weightKg"),
    "movement": ("activityName", "averageHeartRate", "kcal", "distance", "elevationGain", "poolLength", "steps", "swimLengths"),
    "money": ("transactionType", "amount", "currency", "category", "description", "fromAccount", "toAccount"),
    "media": ("mediaType", "title", "rating", "favorite"),
}
PROMPTS = {
    "food": "The user selected the food category. Extract only the food items and explicit meal type from the input. Return one compact JSON object with items and mealType. Preserve item order. Each item must contain name, quantity, and unit. Use mealType unknown when no meal is explicitly named. Do not output calories, time, nulls, extra fields, markdown, or explanations.",
    "gym": "The user selected the gym category. Extract one strength-training set from the input. Return one compact JSON object with exercise, setNumber, and reps, plus weightKg when weighted. Use the previous user message only to resolve omitted state such as a leading +N/-N, never to override values present in the current input. Omit weightKg for bodyweight. Do not output nulls, extra fields, markdown, or explanations.",
    "movement": "The user selected the movement category. Extract the activity name and only measurements explicitly present in the input. Return one compact JSON object. Do not infer measurements, output derived units or durations, emit nulls or extra fields, use markdown, or add explanations.",
    "money": "The user selected the money category. Extract the transaction into one compact JSON object with transactionType, amount, currency, category, description, and explicit account route fields when present. Keep amount positive and use the sign to determine transactionType. Do not output relative time, nulls, extra fields, markdown, or explanations.",
    "media": "The user selected the media category. Extract one completed movie or book record into a compact JSON object with mediaType, title, rating, and favorite. Preserve the title. A favorite requires an explicit marker; otherwise use false. Normalize ratings to the dataset's 0-10 scale. Do not output relative time, nulls, extra fields, markdown, or explanations.",
}


def parse_json(value, label, default):
    if value in (None, ""):
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label}: invalid JSON: {exc}") from exc


def number(value):
    if value in (None, ""):
        return None
    parsed = float(value)
    return int(parsed) if parsed.is_integer() else parsed


def category_for(dataset_id):
    name = dataset_id.removesuffix(".csv").removesuffix("-data")
    return "food" if name == "multi-food" else name


def legacy_row(dataset_id, row, index):
    name = dataset_id.removesuffix(".csv")
    context = []
    if name == "gym-data" and row.get("previousInput"):
        context = [{"role": "user", "content": row["previousInput"]}]

    if name == "food-data":
        expected = {
            "items": [{"name": row["itemName"], "quantity": number(row["itemQuantity"]), "unit": row["itemUnit"], "kcal": number(row["itemKcal"])}],
            "totalKcal": number(row["totalKcal"]),
            "mealType": row["mealType"],
            "timeOffset": row["timeOffset"],
        }
    elif name == "multi-food-data":
        expected = {
            "items": parse_json(row["itemsJson"], f"{dataset_id}:{index} itemsJson", []),
            "totalKcal": number(row["totalKcal"]),
            "mealType": row["mealType"],
            "timeOffset": row["timeOffset"],
        }
    elif name == "gym-data":
        expected = {key: number(row[key]) if key != "exercise" else row[key] for key in FIELDS["gym"] if row.get(key, "") != ""}
    elif name == "movement-data":
        expected = {}
        text_fields = {"activityName", "distanceUnit", "poolLengthUnit"}
        for key in ("activityName", "averageHeartRate", "kcal", "distance", "distanceUnit", "duration", "elevationGain", "pace", "poolLength", "poolLengthUnit", "speed", "steps", "swimLengths"):
            if row.get(key, "") != "":
                expected[key] = row[key] if key in text_fields else number(row[key])
    elif name == "money-data":
        expected = {key: row[key] for key in ("transactionType", "currency", "category", "description", "timeOffset", "fromAccount", "toAccount") if row.get(key, "") != ""}
        if row.get("amount", "") != "":
            expected["amount"] = number(row["amount"])
    elif name == "media-data":
        expected = {key: row[key] for key in ("mediaType", "title", "timeOffset") if row.get(key, "") != ""}
        if row.get("rating", "") != "":
            expected["rating"] = number(row["rating"])
        if row.get("favorite", "") != "":
            expected["favorite"] = row["favorite"].lower() == "true"
    else:
        raise ValueError(f"unsupported legacy dataset: {dataset_id}")

    row_id = f"{dataset_id}:{index:06d}"
    return {"id": row_id, "input": row["input"], "context": context, "expected": expected, "group_id": row_id}


def load_dataset(path):
    dataset_id = f"{path.parent.name}.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or [])
        rows = []
        for index, row in enumerate(reader, 1):
            if STANDARD_COLUMNS <= fields:
                item = {key: row[key] for key in STANDARD_COLUMNS}
                item["context"] = parse_json(item["context"], f"{path}:{index} context", [])
                item["expected"] = parse_json(item["expected"], f"{path}:{index} expected", {})
                item["group_id"] = item["group_id"] or item["id"]
            else:
                item = legacy_row(dataset_id, row, index)
            if not item["id"] or not item["input"]:
                raise ValueError(f"{path}:{index}: id and input are required")
            rows.append(item)
    if len({row["id"] for row in rows}) != len(rows):
        raise ValueError(f"{path}: duplicate IDs")
    repair_groups(rows, dataset_id)
    return dataset_id, rows


def repair_groups(rows, dataset_id):
    if len({row["group_id"] for row in rows}) != len(rows):
        return
    category = category_for(dataset_id)
    if category == "gym":
        repair_gym_groups(rows)
        return
    for row in rows:
        expected = row["expected"]
        if category == "food":
            key = tuple(item.get("name") for item in expected.get("items", []))
        elif category == "media":
            key = (expected.get("mediaType"), expected.get("title"))
        elif category == "money" and dataset_id == "money-data.csv":
            key = tuple(expected.get(field) for field in ("transactionType", "category", "description", "fromAccount", "toAccount"))
        else:
            continue
        row["group_id"] = f"{dataset_id}:{json.dumps(key, ensure_ascii=True, separators=(',', ':'))}"


def repair_gym_groups(rows):
    parents = list(range(len(rows)))
    inputs = {row["input"]: index for index, row in enumerate(rows)}

    def root(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    for index, row in enumerate(rows):
        if row["context"]:
            previous = row["context"][-1].get("content")
            if previous in inputs:
                parents[root(index)] = root(inputs[previous])
    for index, row in enumerate(rows):
        row["group_id"] = f"gym-session:{root(index):06d}"


def model_target(expected, category):
    target = {}
    for key in FIELDS[category]:
        if key not in expected:
            continue
        value = expected[key]
        if key == "items":
            value = [{field: item[field] for field in ITEM_FIELDS if field in item} for item in value]
        target[key] = value
    return target


def training_row(dataset_id, row):
    category = category_for(dataset_id)
    messages = [{"role": "system", "content": PROMPTS[category]}, *row["context"], {"role": "user", "content": row["input"]}]
    return {
        "id": row["id"],
        "dataset_id": dataset_id,
        "category": category,
        "prompt": json.dumps(messages, ensure_ascii=False, separators=(",", ":")),
        "completion": json.dumps(model_target(row["expected"], category), ensure_ascii=False, separators=(",", ":")),
        "group_id": row["group_id"],
    }


def split(rows, dataset_id):
    groups = {}
    for row in rows:
        groups.setdefault(row["group_id"], []).append(row)
    keys = list(groups)
    random.Random(f"{SEED}:{dataset_id}").shuffle(keys)
    limits = (len(rows) * 0.70, len(rows) * 0.85)
    parts = {"train": [], "validation": [], "test": []}
    count = 0
    for key in keys:
        part = "train" if count < limits[0] else "validation" if count < limits[1] else "test"
        parts[part].extend(groups[key])
        count += len(groups[key])
    return parts


def write_csv(name, rows):
    with (OUTPUT_DIR / f"{name}.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda row: row["id"]))


def main():
    output = {"train": [], "validation": [], "test": []}
    for path in sorted(DATASETS_DIR.glob("*/training.csv")):
        if path.parent.name not in INCLUDED_DATASETS:
            continue
        dataset_id, rows = load_dataset(path)
        for part, selected in split(rows, dataset_id).items():
            output[part].extend(training_row(dataset_id, row) for row in selected)
    for part, rows in output.items():
        write_csv(part, rows)
    print({part: len(rows) for part, rows in output.items()})


if __name__ == "__main__":
    main()
