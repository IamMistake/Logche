import csv
import hashlib
import json
import random
from pathlib import Path

STANDARD = {"id", "input", "context", "expected", "group_id"}


def discover(root, csv_name="training.csv", explicit=None):
    if explicit:
        paths = [Path(p) for p in explicit]
    else:
        paths = sorted(Path(root).rglob(csv_name))
    paths = [p for p in paths if p.is_file()]
    names = [p.parent.name + ".csv" for p in paths]
    if len(names) != len(set(names)):
        raise ValueError("duplicate dataset parent names: " + ", ".join(names))
    return [(p.parent.name + ".csv", p) for p in paths]


def _json(value, label, default):
    if value in (None, ""):
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label}: invalid JSON: {exc}") from exc


def _number(value):
    if value in (None, ""):
        return None
    try:
        number = float(value)
        return int(number) if number.is_integer() else number
    except ValueError:
        return value


def _legacy(dataset, row, index):
    name = dataset.removesuffix(".csv")
    inp = row.get("input", "")
    context = []
    if name == "gym-data" and row.get("previousInput"):
        context = [{"role": "user", "content": row["previousInput"]}]
    expected = {}
    if name == "multi-food-data":
        expected = {"items": _json(row.get("itemsJson"), "itemsJson", []), "totalKcal": _number(row.get("totalKcal")), "mealType": row.get("mealType"), "timeOffset": row.get("timeOffset")}
    elif name == "food-data":
        expected = {"items": [{"name": row.get("itemName"), "quantity": _number(row.get("itemQuantity")), "unit": row.get("itemUnit"), "kcal": _number(row.get("itemKcal"))}], "totalKcal": _number(row.get("totalKcal")), "mealType": row.get("mealType"), "timeOffset": row.get("timeOffset")}
    elif name == "gym-data":
        expected = {k: _number(row[k]) if k != "exercise" else row[k] for k in ("exercise", "setNumber", "reps", "weightKg") if row.get(k, "") != ""}
    elif name == "movement-data":
        for key in ("activityName", "averageHeartRate", "kcal", "distance", "distanceUnit", "duration", "elevationGain", "pace", "poolLength", "poolLengthUnit", "speed", "steps", "swimLengths"):
            if row.get(key, "") != "":
                expected[key] = _number(row[key]) if key not in ("activityName", "distanceUnit", "poolLengthUnit") else row[key]
    elif name == "money-data":
        for key in ("transactionType", "currency", "category", "description", "timeOffset", "fromAccount", "toAccount"):
            if row.get(key, "") != "":
                expected[key] = row[key]
        for key in ("amount",):
            if row.get(key, "") != "":
                expected[key] = _number(row[key])
    elif name == "media-data":
        for key in ("mediaType", "title", "rating", "favorite", "timeOffset"):
            if row.get(key, "") != "":
                value = row[key]
                expected[key] = _number(value) if key == "rating" else value
                if key == "favorite":
                    expected[key] = value.lower() == "true"
    else:
        raise ValueError(f"{dataset}: unsupported CSV schema; use id,input,context,expected,group_id")
    return {"id": f"{dataset}:{index:06d}", "input": inp, "context": context, "expected": expected, "group_id": f"{dataset}:{index:06d}"}


def load(dataset, path):
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or [])
        if not fields:
            raise ValueError(f"{path}: missing CSV header")
        rows = []
        for index, row in enumerate(reader, 1):
            item = ({k: row[k] for k in ("id", "input", "context", "expected", "group_id")} if STANDARD <= fields else _legacy(dataset, row, index))
            if not item["id"] or not item["input"]:
                raise ValueError(f"{path}:{index}: id and input are required")
            item["context"] = _json(item["context"], f"{path}:{index} context", [])
            item["expected"] = _json(item["expected"], f"{path}:{index} expected", {})
            if not isinstance(item["context"], list) or not isinstance(item["expected"], dict):
                raise ValueError(f"{path}:{index}: context must be an array and expected an object")
            item["group_id"] = item["group_id"] or item["id"]
            rows.append(item)
    if len({r["id"] for r in rows}) != len(rows):
        raise ValueError(f"{path}: duplicate ids")
    _repair_row_unique_groups(rows, dataset)
    return rows


def _repair_row_unique_groups(rows, dataset):
    """Keep related generated records together when legacy IDs are row-level."""
    if len({row["group_id"] for row in rows}) != len(rows):
        return
    name = dataset.removesuffix(".csv")
    if name == "gym-data":
        _repair_gym_groups(rows)
        return
    for row in rows:
        expected = row["expected"]
        if name in {"food-data", "multi-food-data"}:
            key = tuple(item.get("name") for item in expected.get("items", []))
        elif name == "media-data":
            key = (expected.get("mediaType"), expected.get("title"))
        elif name == "money-data":
            key = tuple(expected.get(field) for field in ("transactionType", "category", "description", "fromAccount", "toAccount"))
        else:
            continue
        serialized_key = json.dumps(key, ensure_ascii=True, separators=(",", ":"))
        row["group_id"] = f"{name}:{serialized_key}"


def _repair_gym_groups(rows):
    parents = list(range(len(rows)))
    inputs = {}
    for index, row in enumerate(rows):
        inputs.setdefault(row["input"], []).append(index)

    def root(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def join(left, right):
        left, right = root(left), root(right)
        if left != right:
            parents[right] = left

    for index, row in enumerate(rows):
        context = row.get("context", [])
        if not context:
            continue
        previous = context[-1].get("content") if isinstance(context[-1], dict) else None
        for previous_index in inputs.get(previous, []):
            join(index, previous_index)
            break
    for index, row in enumerate(rows):
        row["group_id"] = f"gym-session:{root(index):06d}"


def split(rows, dataset, seed=42):
    groups = {}
    for row in rows:
        groups.setdefault(row["group_id"], []).append(row)
    keys = list(groups)
    random.Random(f"{seed}:{dataset}").shuffle(keys)
    total = len(rows)
    targets = {"train": total * .7, "validation": total * .85}
    output, count = {"train": [], "validation": [], "test": []}, 0
    for key in keys:
        part = "train" if count < targets["train"] else "validation" if count < targets["validation"] else "test"
        output[part].extend(groups[key])
        count += len(groups[key])
    return output


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
