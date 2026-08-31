#!/usr/bin/env python3
"""Generate deterministic, source-grounded multi-food shorthand examples."""

from __future__ import annotations

import csv
import hashlib
import itertools
import json
import random
import re
from collections import Counter, defaultdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
SOURCE_PATH = HERE.parent / "food-data" / "food_records_clean.csv"
CONFIG_PATH = HERE / "pairing_templates.json"
TRAINING_PATH = HERE / "training.csv"
SHORTHAND_PATH = HERE / "multi_food_shorthand.txt"
EXAMPLES_PATH = HERE / "multi_food_examples.jsonl"
MANIFEST_PATH = HERE / "multi_food_manifest.json"
SEED = 20260831
TRAINING_COLUMNS = ("input", "itemsJson", "totalKcal", "mealType", "timeOffset")
ITEM_UNITS = {"g", "kg", "mg", "ml", "l", "slice", "piece", "cup", "serving", "tablespoon", "teaspoon"}
MEAL_TYPES = {"breakfast", "lunch", "dinner", "snack", "late_night", "unknown"}


def decimal_value(value: str, field: str) -> Decimal:
    parsed = Decimal(value.strip())
    if not parsed.is_finite():
        raise ValueError(f"{field} is not finite")
    return parsed


def number(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def json_number(value: Decimal) -> int | float:
    value = value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    return int(value) if value == value.to_integral_value() else float(value)


def load_source() -> tuple[dict[str, dict[str, str]], str]:
    source_bytes = SOURCE_PATH.read_bytes()
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    with SOURCE_PATH.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        expected = (
            "sourceIndex", "fdcId", "name", "sourceCategory", "kcalPer100g",
            "energyNutrient", "quantity", "unit", "gramWeight", "portionSourceId",
        )
        if tuple(reader.fieldnames or ()) != expected:
            raise ValueError(f"unexpected clean food columns: {reader.fieldnames}")
        records = {row["fdcId"]: row for row in reader}
    return records, source_hash


def quantity_token(quantity: Decimal, unit: str, rng: random.Random) -> str:
    value = number(quantity)
    singular = quantity == 1
    forms = {
        "g": (f"{value}g", f"{value} g", f"g{value}", f"{value} {'gram' if singular else 'grams'}", f"{value} gr"),
        "kg": (f"{value}kg", f"{value} kg", f"kg{value}"),
        "mg": (f"{value}mg", f"{value} mg", f"mg{value}"),
        "ml": (f"{value}ml", f"{value} ml", f"ml{value}"),
        "l": (f"{value}l", f"{value} l", f"l{value}"),
        "slice": (f"{value}slice", f"{value} {'slice' if singular else 'slices'}", f"slice{value}"),
        "piece": (f"{value}piece", f"{value} {'piece' if singular else 'pieces'}", f"piece{value}"),
        "cup": (f"{value}cup", f"{value} {'cup' if singular else 'cups'}", f"cup{value}"),
        "serving": (f"{value}serving", f"{value} serving", f"serving{value}"),
        "tablespoon": (f"{value}tbsp", f"{value} {'tablespoon' if singular else 'tablespoons'}", f"tbsp{value}"),
        "teaspoon": (f"{value}tsp", f"{value} {'teaspoon' if singular else 'teaspoons'}", f"tsp{value}"),
    }
    return rng.choice(forms[unit])


def meal_phrase(rng: random.Random, allowed: list[str]) -> tuple[str, str]:
    if rng.random() < 0.35:
        return "", "unknown"
    meal_type = rng.choice([value for value in allowed if value != "unknown"])
    phrases = {
        "breakfast": ("breakfast", "bf"),
        "lunch": ("lunch",),
        "dinner": ("dinner",),
        "snack": ("snack",),
        "late_night": ("late night", "ln"),
    }
    return rng.choice(phrases[meal_type]), meal_type


def time_expression(rng: random.Random) -> tuple[str, str]:
    roll = rng.random()
    if roll < 0.55:
        return "", "PT0M"
    if roll < 0.75:
        hours = rng.randint(1, 23)
        return rng.choice((f"-{hours}h", f"{hours}h ago")), f"-PT{hours}H"
    if roll < 0.95:
        days = rng.randint(1, 30)
        if days == 1:
            return rng.choice(("yesterday", "ye", "-1d", "1d ago")), "-P1D"
        return rng.choice((f"-{days}d", f"{days}d ago")), f"-P{days}D"
    return rng.choice(("tmr", "tomorrow", "+1d")), "P1D"


def item_from_source(
    source: dict[str, str], input_name: str, quantity: Decimal,
) -> tuple[dict[str, Any], dict[str, Any]]:
    source_quantity = decimal_value(source["quantity"], "source quantity")
    gram_weight = decimal_value(source["gramWeight"], "source gram weight") * quantity / source_quantity
    kcal = (decimal_value(source["kcalPer100g"], "kcal per 100 g") * gram_weight / Decimal("100")).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    if quantity <= 0 or gram_weight <= 0 or kcal <= 0:
        raise ValueError(f"invalid generated item for {source['fdcId']}")
    item = {
        "name": source["name"],
        "quantity": json_number(quantity),
        "unit": source["unit"],
        "kcal": int(kcal),
    }
    provenance = {
        "fdcId": source["fdcId"],
        "sourceIndex": int(source["sourceIndex"]),
        "inputName": input_name,
        "name": source["name"],
        "quantity": item["quantity"],
        "unit": item["unit"],
        "gramWeight": number(gram_weight),
        "kcalPer100g": source["kcalPer100g"],
        "kcal": item["kcal"],
    }
    return item, provenance


def build_pools(config: dict[str, Any], records: dict[str, dict[str, str]]) -> dict[str, list[dict[str, Any]]]:
    pools: dict[str, list[dict[str, Any]]] = {}
    for template in config["templates"]:
        role_options = []
        for role in template["roles"]:
            choices = []
            for food in config["foodGroups"][role["group"]]:
                if food["fdcId"] not in records:
                    raise ValueError(f"unknown clean food ID: {food['fdcId']}")
                source = records[food["fdcId"]]
                if source["unit"] not in ITEM_UNITS:
                    raise ValueError(f"unsupported unit in source: {source['unit']}")
                for quantity in role["quantities"]:
                    choices.append((food, decimal_value(quantity, "template quantity")))
            role_options.append(choices)
        combinations = []
        for choices in itertools.product(*role_options):
            foods = [choice[0] for choice in choices]
            ids = [food["fdcId"] for food in foods]
            names = [records[fdc_id]["name"] for fdc_id in ids]
            if len(set(ids)) != len(ids) or len(set(names)) != len(names):
                continue
            items = []
            provenance = []
            for food, quantity in choices:
                item, item_provenance = item_from_source(records[food["fdcId"]], food["inputName"], quantity)
                items.append(item)
                provenance.append(item_provenance)
            combinations.append({
                "template": template["name"],
                "items": items,
                "provenance": provenance,
                "mealTypes": template["mealTypes"],
            })
        pools[template["name"]] = combinations
    return pools


def render_example(combo: dict[str, Any], rng: random.Random) -> tuple[str, dict[str, Any], str, str]:
    ordered = list(zip(combo["items"], combo["provenance"]))
    if rng.random() < 0.25:
        rng.shuffle(ordered)
    segments = []
    for item, provenance in ordered:
        token = quantity_token(Decimal(str(item["quantity"])), item["unit"], rng)
        segments.append(rng.choice((f"{provenance['inputName']} {token}", f"{token} {provenance['inputName']}")))
    total_kcal = sum(item["kcal"] for item in combo["items"])
    meal_text, meal_type = meal_phrase(rng, combo["mealTypes"])
    time_text, time_offset = time_expression(rng)
    input_text = " + ".join(segments)
    if rng.random() < 0.30 and time_offset != "P1D":
        input_text = f"ate {input_text}"
    if rng.random() < 0.15:
        input_text = f"{input_text} {rng.choice((f'{total_kcal}kcal', f'kcal{total_kcal}', f'{total_kcal} cal'))}"
    if meal_text:
        input_text = f"{input_text} {meal_text}"
    if time_text:
        input_text = f"{input_text} {time_text}"
    target = {
        "items": [item for item, _ in ordered],
        "totalKcal": total_kcal,
        "mealType": meal_type,
        "timeOffset": time_offset,
    }
    return input_text, target, meal_type, time_offset


def validate_example(
    input_text: str, target: dict[str, Any], provenance: list[dict[str, Any]],
    meal_type: str, time_offset: str,
) -> list[str]:
    errors = []
    if not input_text.strip():
        errors.append("empty input")
    if set(target) != {"items", "totalKcal", "mealType", "timeOffset"}:
        errors.append("unsupported target fields")
        return errors
    if not 2 <= len(target["items"]) <= 4:
        errors.append("item count outside 2-4")
    if target["mealType"] != meal_type or meal_type not in MEAL_TYPES:
        errors.append("invalid meal type")
    if target["timeOffset"] != time_offset:
        errors.append("invalid time offset")
    if target["totalKcal"] != sum(item["kcal"] for item in target["items"]):
        errors.append("totalKcal does not equal item sum")
    if input_text.count(" + ") != len(target["items"]) - 1:
        errors.append("item delimiter count does not match item count")
    for item, item_provenance in zip(target["items"], provenance):
        if item["name"] != item_provenance["name"] or item["unit"] not in ITEM_UNITS:
            errors.append("item is not source-grounded")
        if item_provenance["inputName"] not in input_text:
            errors.append("input food alias missing")
        quantity = Decimal(str(item["quantity"]))
        token_pattern = rf"(?<![a-z0-9])(?:{re.escape(number(quantity))}\s*(?:{re.escape(item['unit'])}|{'|'.join({'g': ('gram', 'grams', 'gr'), 'slice': ('slices',), 'piece': ('pieces',), 'cup': ('cups',), 'tablespoon': ('tbsp',), 'teaspoon': ('tsp',)}.get(item['unit'], ()))})|(?:{re.escape(item['unit'])}|{'|'.join({'g': ('gram', 'grams', 'gr'), 'slice': ('slices',), 'piece': ('pieces',), 'cup': ('cups',), 'tablespoon': ('tbsp',), 'teaspoon': ('tsp',)}.get(item['unit'], ()) )})\s*{re.escape(number(quantity))})(?![a-z0-9])"
        if not re.search(token_pattern, input_text.casefold()):
            errors.append("item quantity/unit missing or mismatched")
        source_quantity = Decimal(str(item_provenance["quantity"]))
        # Provenance quantity is the generated quantity, so use its recorded gram weight directly.
        expected = (Decimal(item_provenance["kcalPer100g"]) * Decimal(item_provenance["gramWeight"]) / Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        if item["kcal"] != int(expected):
            errors.append("item calorie cannot be reproduced")
        if source_quantity <= 0:
            errors.append("non-positive provenance quantity")
    calorie_numbers = re.findall(r"(?:kcal|cal)\s*(\d+)|(?<![a-z])([0-9]+)\s*(?:kcal|cal)", input_text, re.I)
    if any(int(first or second) != target["totalKcal"] for first, second in calorie_numbers):
        errors.append("total calorie token disagrees")
    if meal_type == "unknown" and any(token in input_text.casefold().split() for token in ("breakfast", "bf", "lunch", "dinner", "snack", "ln")):
        errors.append("unexpected meal phrase")
    if time_offset == "PT0M" and re.search(r"(?<![a-z0-9])(?:-\d+h|\d+h ago|yesterday|ye|-\d+d|\d+d ago|tmr|tomorrow|\+1d)(?![a-z0-9])", input_text.casefold()):
        errors.append("unexpected time phrase")
    if time_offset == "P1D" and input_text.casefold().startswith("ate "):
        errors.append("past-tense prefix conflicts with future time")
    return errors


def write_outputs(examples: list[dict[str, Any]], manifest: dict[str, Any]) -> None:
    with TRAINING_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=TRAINING_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for example in examples:
            target = example["target"]
            writer.writerow({
                "input": example["input"],
                "itemsJson": json.dumps(target["items"], separators=(",", ":"), ensure_ascii=True),
                "totalKcal": target["totalKcal"],
                "mealType": target["mealType"],
                "timeOffset": target["timeOffset"],
            })
    lines = []
    for example in examples:
        lines.append(f"Input: {example['input']}")
        lines.append(json.dumps(example["target"], separators=(",", ":"), ensure_ascii=True))
        lines.append("")
    SHORTHAND_PATH.write_text("\n".join(lines), encoding="utf-8")
    with EXAMPLES_PATH.open("w", encoding="utf-8") as handle:
        for example in examples:
            handle.write(json.dumps({
                "input": example["input"],
                "target": example["target"],
                "provenance": {
                    "syntheticCombination": True,
                    "sourceDataset": "USDA FoodData Central Foundation Foods 2025-12-18",
                    "template": example["template"],
                    "items": example["provenance"],
                },
            }, separators=(",", ":"), ensure_ascii=True) + "\n")
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def main() -> None:
    records, source_hash = load_source()
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    pools = build_pools(config, records)
    by_count: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for template in config["templates"]:
        by_count[len(template["roles"])].extend(pools[template["name"]])
    for count, pool in by_count.items():
        random.Random(SEED + count).shuffle(pool)
    requested_counts = {2: 500, 3: 350, 4: 150}
    examples: list[dict[str, Any]] = []
    used_inputs: set[str] = set()
    collision_retries = 0
    validation_retries = 0
    template_counts: Counter[str] = Counter()
    combination_counts: Counter[str] = Counter()
    food_counts: Counter[str] = Counter()
    for count, requested in requested_counts.items():
        for ordinal in range(requested):
            pool = by_count[count]
            combo = pool[ordinal % len(pool)]
            template_name = combo["template"]
            for attempt in range(100):
                rng = random.Random(SEED + len(examples) * 1009 + attempt * 7919)
                input_text, target, meal_type, time_offset = render_example(combo, rng)
                ordered_provenance = []
                for item in target["items"]:
                    ordered_provenance.append(next(p for p in combo["provenance"] if p["inputName"] in input_text and p["name"] == item["name"]))
                errors = validate_example(input_text, target, ordered_provenance, meal_type, time_offset)
                if errors:
                    validation_retries += 1
                    continue
                if input_text in used_inputs:
                    collision_retries += 1
                    continue
                used_inputs.add(input_text)
                signature = "|".join(sorted(f"{p['fdcId']}:{p['quantity']}" for p in ordered_provenance))
                examples.append({
                    "input": input_text,
                    "target": target,
                    "template": template_name,
                    "provenance": ordered_provenance,
                    "combinationSignature": signature,
                })
                template_counts[template_name] += 1
                combination_counts[signature] += 1
                for item in target["items"]:
                    food_counts[item["name"]] += 1
                break
            else:
                raise RuntimeError(f"could not generate unique valid example {len(examples)}")

    calories = [example["target"]["totalKcal"] for example in examples]
    lengths = [len(example["input"]) for example in examples]
    manifest = {
        "seed": SEED,
        "source": "USDA FoodData Central Foundation Foods 2025-12-18 clean records",
        "sourcePath": "../food-data/food_records_clean.csv",
        "sourceSha256": source_hash,
        "sourceCleanRows": len(records),
        "templates": list(pools),
        "trainingRows": len(examples),
        "itemCountCounts": dict(Counter(len(example["target"]["items"]) for example in examples)),
        "templateCounts": dict(sorted(template_counts.items())),
        "foodCounts": dict(sorted(food_counts.items())),
        "uniqueCombinationSignatures": len(combination_counts),
        "maximumCombinationReuse": max(combination_counts.values()),
        "mealTypeCounts": dict(sorted(Counter(example["target"]["mealType"] for example in examples).items())),
        "timeOffsetModeCounts": dict(sorted(Counter(example["target"]["timeOffset"] for example in examples).items())),
        "unitCounts": dict(sorted(Counter(item["unit"] for example in examples for item in example["target"]["items"]).items())),
        "inputLength": {"minimum": min(lengths), "maximum": max(lengths)},
        "calorieRange": [min(calories), max(calories)],
        "collisionRetries": collision_retries,
        "validationRetries": validation_retries,
        "modelTargetFields": ["items", "totalKcal", "mealType", "timeOffset"],
    }
    write_outputs(examples, manifest)
    print(f"Generated {len(examples)} multi-food examples")
    print(f"Item counts: {manifest['itemCountCounts']}")
    print(f"Unique combinations: {manifest['uniqueCombinationSignatures']}")
    print(f"Maximum combination reuse: {manifest['maximumCombinationReuse']}")
    print(f"Validation retries: {validation_retries}; collision retries: {collision_retries}")
    print(f"Input length: {manifest['inputLength']}; calorie range: {manifest['calorieRange']}")


if __name__ == "__main__":
    main()
