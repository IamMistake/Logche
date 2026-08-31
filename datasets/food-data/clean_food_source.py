#!/usr/bin/env python3
"""Clean USDA Foundation Foods and generate Logche meal shorthand."""

from __future__ import annotations

import csv
import io
import json
import random
import re
import unicodedata
import zipfile
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
SOURCE_PATH = HERE / "FoodData_Central_foundation_food_csv_2025-12-18.zip"
CLEAN_PATH = HERE / "food_records_clean.csv"
QUARANTINE_PATH = HERE / "food_quarantine.json"
TRAINING_PATH = HERE / "training.csv"
SHORTHAND_PATH = HERE / "food_shorthand.txt"
SEED = 20260830
KJ_PER_KCAL = Decimal("4.184")
MAX_KCAL_PER_100G = Decimal("900")

SOURCE_COLUMNS = {
    "food.csv": ("fdc_id", "data_type", "description", "food_category_id", "publication_date"),
    "nutrient.csv": ("id", "name", "unit_name", "nutrient_nbr", "rank"),
    "food_nutrient.csv": (
        "id", "fdc_id", "nutrient_id", "amount", "data_points", "derivation_id",
        "min", "max", "median", "footnote", "min_year_acquired",
    ),
    "food_portion.csv": (
        "id", "fdc_id", "seq_num", "amount", "measure_unit_id", "portion_description",
        "modifier", "gram_weight", "data_points", "footnote", "min_year_acquired",
    ),
    "measure_unit.csv": ("id", "name"),
    "food_category.csv": ("id", "code", "description"),
}

CLEAN_COLUMNS = (
    "sourceIndex", "fdcId", "name", "sourceCategory", "kcalPer100g",
    "energyNutrient", "quantity", "unit", "gramWeight", "portionSourceId",
)

TRAINING_COLUMNS = (
    "input", "itemName", "itemQuantity", "itemUnit", "itemKcal",
    "totalKcal", "mealType", "timeOffset",
)

# Foundation Foods can contain several definitions of energy. The first
# available value is selected, while kJ is converted only as a last resort.
ENERGY_PRIORITY = ("1008", "2048", "2047", "1062")
ENERGY_NAMES = {
    "1008": "Energy",
    "2048": "Energy (Atwater Specific Factors)",
    "2047": "Energy (Atwater General Factors)",
    "1062": "Energy",
}

UNIT_ALIASES = {
    "g": "g", "gram": "g", "grams": "g",
    "kg": "kg", "kilogram": "kg", "kilograms": "kg",
    "mg": "mg", "milligram": "mg", "milligrams": "mg",
    "ml": "ml", "milliliter": "ml", "milliliters": "ml",
    "l": "l", "liter": "l", "liters": "l",
    "slice": "slice", "slices": "slice",
    "piece": "piece", "pieces": "piece",
    "cup": "cup", "serving": "serving",
    "tablespoon": "tablespoon", "teaspoon": "teaspoon",
}
PORTION_PRIORITY = {
    "slice": 0, "slices": 0, "piece": 1, "pieces": 1,
    "cup": 2, "serving": 3, "milliliter": 4, "liter": 5,
    "tablespoon": 6, "teaspoon": 7, "g": 8, "gram": 8, "grams": 8,
    "kg": 9, "kilogram": 9, "mg": 10, "milligram": 10,
}


def decimal_value(value: str, field: str) -> Decimal:
    try:
        parsed = Decimal(value.strip())
    except (InvalidOperation, AttributeError) as exc:
        raise ValueError(f"{field} is not numeric: {value!r}") from exc
    if not parsed.is_finite():
        raise ValueError(f"{field} is not finite: {value!r}")
    return parsed


def number(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def json_number(value: Decimal) -> int | float:
    rounded = value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    if rounded == rounded.to_integral_value():
        return int(rounded)
    return float(rounded)


def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).replace("\u00a0", " ")
    return " ".join(value.casefold().split()).strip(" ,;")


def read_csv_files() -> dict[str, list[dict[str, str]]]:
    with zipfile.ZipFile(SOURCE_PATH) as archive:
        result: dict[str, list[dict[str, str]]] = {}
        for filename, expected_columns in SOURCE_COLUMNS.items():
            members = [name for name in archive.namelist() if name.endswith(f"/{filename}")]
            if len(members) != 1:
                raise ValueError(f"expected one {filename} in source archive")
            with archive.open(members[0]) as handle:
                reader = csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8-sig"))
                if tuple(reader.fieldnames or ()) != expected_columns:
                    raise ValueError(
                        f"unexpected {filename} columns: {reader.fieldnames}"
                    )
                result[filename] = list(reader)
        return result


def chosen_energy(
    energy_rows: list[dict[str, str]],
) -> tuple[Decimal, str] | tuple[None, str]:
    by_nutrient: dict[str, list[Decimal]] = defaultdict(list)
    for row in energy_rows:
        nutrient_id = row["nutrient_id"]
        if nutrient_id not in ENERGY_PRIORITY:
            continue
        by_nutrient[nutrient_id].append(decimal_value(row["amount"], "calorie amount"))

    for nutrient_id in ENERGY_PRIORITY:
        values = by_nutrient.get(nutrient_id, [])
        if not values:
            continue
        if len(set(values)) != 1:
            raise ValueError(f"conflicting {ENERGY_NAMES[nutrient_id]} values")
        value = values[0]
        if nutrient_id == "1062":
            value = (value / KJ_PER_KCAL).quantize(
                Decimal("0.000001"), rounding=ROUND_HALF_UP
            )
        return value, nutrient_id
    return None, ""


def portion_for(
    portions: list[dict[str, str]], measure_units: dict[str, str],
) -> dict[str, str] | None:
    candidates: list[tuple[int, Decimal, Decimal, str, dict[str, str]]] = []
    for portion in portions:
        raw_unit = measure_units.get(portion["measure_unit_id"], "").casefold().strip()
        if raw_unit not in PORTION_PRIORITY:
            continue
        try:
            amount = decimal_value(portion["amount"], "portion amount")
            gram_weight = decimal_value(portion["gram_weight"], "portion gram weight")
        except ValueError:
            continue
        if amount <= 0 or gram_weight <= 0:
            continue
        candidates.append(
            (
                PORTION_PRIORITY[raw_unit], amount, gram_weight,
                portion["id"], {**portion, "normalizedUnit": UNIT_ALIASES[raw_unit]},
            )
        )
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[:4])
    return candidates[0][4]


def quarantine_entry(
    quarantined: list[dict[str, Any]], source_index: int,
    reasons: list[str], record: dict[str, str],
) -> None:
    quarantined.append(
        {
            "sourceIndex": source_index,
            "reasons": sorted(set(reasons)),
            "originalRecord": record,
        }
    )


def clean_source() -> tuple[list[dict[str, str]], list[dict[str, Any]], dict[str, Any]]:
    tables = read_csv_files()
    foods = [
        (source_index, row)
        for source_index, row in enumerate(tables["food.csv"], start=2)
        if row["data_type"] == "foundation_food"
    ]
    categories = {row["id"]: normalize_name(row["description"]) for row in tables["food_category.csv"]}
    measure_units = {row["id"]: row["name"] for row in tables["measure_unit.csv"]}
    nutrients_by_food: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in tables["food_nutrient.csv"]:
        nutrients_by_food[row["fdc_id"]].append(row)
    portions_by_food: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in tables["food_portion.csv"]:
        portions_by_food[row["fdc_id"]].append(row)

    clean_rows: list[dict[str, str]] = []
    quarantined: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    duplicate_count = 0
    raw_energy_values: list[Decimal] = []
    raw_unit_counts: Counter[str] = Counter()

    for source_index, raw in foods:
        reasons: list[str] = []
        name = normalize_name(raw["description"])
        if not name:
            reasons.append("missing food name")

        try:
            kcal_per_100g, energy_nutrient = chosen_energy(nutrients_by_food[raw["fdc_id"]])
        except ValueError as exc:
            kcal_per_100g, energy_nutrient = None, ""
            reasons.append(str(exc))
        if kcal_per_100g is None:
            reasons.append("missing or non-numeric calorie value")
        else:
            raw_energy_values.append(kcal_per_100g)
            if kcal_per_100g < 0:
                reasons.append("calories below zero")
            elif kcal_per_100g == 0:
                reasons.append("zero calories are not useful for food examples")
            elif kcal_per_100g > MAX_KCAL_PER_100G:
                reasons.append(
                    f"calorie density exceeds documented maximum {MAX_KCAL_PER_100G} kcal/100g"
                )

        raw_portions = portions_by_food[raw["fdc_id"]]
        for portion in raw_portions:
            raw_unit = measure_units.get(portion["measure_unit_id"], "unknown").casefold()
            raw_unit_counts[raw_unit] += 1
        portion = portion_for(raw_portions, measure_units)

        if reasons:
            quarantine_entry(quarantined, source_index, reasons, raw)
            continue

        assert kcal_per_100g is not None
        if portion is None:
            quantity = Decimal("100")
            unit = "g"
            gram_weight = quantity
            portion_source_id = ""
        else:
            quantity = decimal_value(portion["amount"], "portion amount")
            unit = portion["normalizedUnit"]
            gram_weight = decimal_value(portion["gram_weight"], "portion gram weight")
            portion_source_id = portion["id"]

        record = {
            "sourceIndex": str(source_index),
            "fdcId": raw["fdc_id"],
            "name": name,
            "sourceCategory": categories.get(raw["food_category_id"], ""),
            "kcalPer100g": number(kcal_per_100g),
            "energyNutrient": energy_nutrient,
            "quantity": number(quantity),
            "unit": unit,
            "gramWeight": number(gram_weight),
            "portionSourceId": portion_source_id,
        }
        dedupe_key = tuple(record[field] for field in CLEAN_COLUMNS if field not in {"sourceIndex", "fdcId"})
        if dedupe_key in seen:
            duplicate_count += 1
            continue
        seen.add(dedupe_key)
        clean_rows.append(record)

    with CLEAN_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CLEAN_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(clean_rows)
    QUARANTINE_PATH.write_text(
        json.dumps(quarantined, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )

    stats = {
        "sourceRows": len(foods),
        "sourceTableRows": {name: len(rows) for name, rows in tables.items()},
        "sourceColumns": {name: list(columns) for name, columns in SOURCE_COLUMNS.items()},
        "sourceNullCounts": {
            name: {
                column: sum(not row[column].strip() for row in rows)
                for column in SOURCE_COLUMNS[name]
            }
            for name, rows in tables.items()
        },
        "rawUnitCounts": dict(sorted(raw_unit_counts.items())),
        "rawEnergyRange": [number(min(raw_energy_values)), number(max(raw_energy_values))]
        if raw_energy_values else [],
        "cleanRows": len(clean_rows),
        "quarantinedRows": len(quarantined),
        "exactCleanDuplicatesRemoved": duplicate_count,
    }
    return clean_rows, quarantined, stats


def meal_phrase(rng: random.Random) -> tuple[str, str]:
    roll = rng.random()
    if roll < 0.55:
        return "", "unknown"
    if roll < 0.65:
        return rng.choice(("breakfast", "bf")), "breakfast"
    if roll < 0.77:
        return "lunch", "lunch"
    if roll < 0.87:
        return "dinner", "dinner"
    if roll < 0.95:
        return "snack", "snack"
    return rng.choice(("late night", "ln")), "late_night"


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
        "tablespoon": (f"{value}tbsp", f"{value} tablespoon", f"tbsp{value}"),
        "teaspoon": (f"{value}tsp", f"{value} teaspoon", f"tsp{value}"),
    }
    return rng.choice(forms[unit])


def calorie_token(kcal: int, rng: random.Random) -> str:
    text = str(kcal)
    return rng.choice((f"{text}kcal", f"kcal{text}", f"{text} kcal", f"{text}cal", f"cal{text}"))


def generated_quantity(record: dict[str, str], rng: random.Random) -> Decimal:
    source_quantity = Decimal(record["quantity"])
    if record["unit"] == "g":
        return rng.choice(tuple(Decimal(value) for value in ("50", "100", "150", "200", "250")))
    if record["unit"] in {"kg", "mg", "ml", "l"}:
        return source_quantity * rng.choice((Decimal("1"), Decimal("2")))
    if record["unit"] in {"slice", "piece"}:
        return source_quantity * rng.choice((Decimal("1"), Decimal("2"), Decimal("3")))
    return source_quantity * rng.choice((Decimal("1"), Decimal("2")))


def make_example(record: dict[str, str], rng: random.Random) -> tuple[str, dict[str, Any], str, str]:
    quantity = generated_quantity(record, rng)
    gram_weight = Decimal(record["gramWeight"]) * quantity / Decimal(record["quantity"])
    kcal = (Decimal(record["kcalPer100g"]) * gram_weight / Decimal("100")).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    if kcal <= 0:
        raise ValueError(f"generated calorie value is not positive for {record['name']}")
    unit = record["unit"]
    item = {
        "name": record["name"],
        "quantity": json_number(quantity),
        "unit": unit,
        "kcal": int(kcal),
    }
    meal_text, meal_type = meal_phrase(rng)
    time_text, time_offset = time_expression(rng)
    qty_text = quantity_token(quantity, unit, rng)
    calorie_text = calorie_token(int(kcal), rng) if rng.random() < 0.25 else ""
    base_forms = (
        f"{record['name']} {qty_text}",
        f"{qty_text} {record['name']}",
        f"ate {qty_text} {record['name']}",
    )
    input_text = rng.choice(base_forms)
    if calorie_text:
        input_text = f"{input_text} {calorie_text}"
    if meal_text:
        input_text = f"{input_text} {meal_text}"
    if time_text:
        input_text = f"{input_text} {time_text}"
    target = {
        "items": [item],
        "totalKcal": int(kcal),
        "mealType": meal_type,
        "timeOffset": time_offset,
    }
    return input_text, target, meal_type, time_offset


def validate_example(
    record: dict[str, str], input_text: str, target: dict[str, Any],
    meal_type: str, time_offset: str,
) -> list[str]:
    errors: list[str] = []
    if not input_text.strip():
        errors.append("empty input")
    if set(target) != {"items", "totalKcal", "mealType", "timeOffset"}:
        errors.append("missing or unsupported target field")
        return errors
    if len(target["items"]) != 1:
        errors.append("training rows must contain one source food item")
        return errors
    item = target["items"][0]
    if item["name"] != record["name"]:
        errors.append("food name is not grounded in source")
    if item["unit"] != record["unit"]:
        errors.append("unit is not canonical")
    if item["quantity"] <= 0 or item["kcal"] <= 0:
        errors.append("quantity and calories must be positive")
    if target["totalKcal"] != item["kcal"]:
        errors.append("totalKcal does not equal item kcal")
    if target["mealType"] != meal_type or meal_type not in {"breakfast", "lunch", "dinner", "snack", "late_night", "unknown"}:
        errors.append("invalid meal type")
    if target["timeOffset"] != time_offset:
        errors.append("invalid time offset")
    if record["name"] not in input_text.casefold():
        errors.append("food name missing from input")
    quantity_text = number(Decimal(str(item["quantity"])))
    unit_forms = {
        "g": ("g", "gram", "grams", "gr"),
        "kg": ("kg",), "mg": ("mg",), "ml": ("ml",), "l": ("l",),
        "slice": ("slice", "slices"), "piece": ("piece", "pieces"),
        "cup": ("cup", "cups"), "serving": ("serving",),
        "tablespoon": ("tbsp", "tablespoon"), "teaspoon": ("tsp", "teaspoon"),
    }[item["unit"]]
    quantity_pattern = rf"(?<![a-z0-9])(?:{re.escape(quantity_text)}\s*(?:{'|'.join(unit_forms)})|(?:{'|'.join(unit_forms)})\s*{re.escape(quantity_text)})(?![a-z0-9])"
    if not re.search(quantity_pattern, input_text.casefold()):
        errors.append("quantity or unit missing from input")
    if re.search(r"\b(?:\d+(?:\.\d+)?\s*(?:kcal|cal)|(?:kcal|cal)\s*\d+)\b", input_text, re.I):
        numbers = re.findall(r"(?:kcal|cal)\s*(\d+)|(?<![a-z])([0-9]+)(?:\s*)(?:kcal|cal)", input_text, re.I)
        if any(int(value or other) != item["kcal"] for value, other in numbers):
            errors.append("calorie token disagrees with output")
    if time_offset == "PT0M" and any(token in input_text.casefold().split() for token in ("yesterday", "ye", "tmr", "tomorrow")):
        errors.append("unexpected time phrase")
    if target["mealType"] == "unknown" and any(token in input_text.casefold() for token in ("breakfast", "bf", "lunch", "dinner", "snack", "ln")):
        errors.append("unexpected meal phrase")
    gram_weight = Decimal(record["gramWeight"]) * Decimal(str(item["quantity"])) / Decimal(record["quantity"])
    expected_kcal = (Decimal(record["kcalPer100g"]) * gram_weight / Decimal("100")).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    if item["kcal"] != int(expected_kcal):
        errors.append("calorie calculation cannot be reproduced")
    return errors


def write_training(rows: list[dict[str, str]]) -> dict[str, Any]:
    examples: list[tuple[str, dict[str, Any]]] = []
    used_inputs: set[str] = set()
    collisions = 0
    validation_retries = 0
    for index, record in enumerate(rows):
        for attempt in range(100):
            rng = random.Random(SEED + index * 1009 + attempt * 7919)
            input_text, target, meal_type, time_offset = make_example(record, rng)
            errors = validate_example(record, input_text, target, meal_type, time_offset)
            if errors:
                validation_retries += 1
                continue
            if input_text in used_inputs:
                collisions += 1
                continue
            used_inputs.add(input_text)
            examples.append((input_text, target))
            break
        else:
            raise RuntimeError(f"could not generate a unique input for row {index}")

    with TRAINING_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=TRAINING_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for input_text, target in examples:
            item = target["items"][0]
            writer.writerow({
                "input": input_text,
                "itemName": item["name"],
                "itemQuantity": item["quantity"],
                "itemUnit": item["unit"],
                "itemKcal": item["kcal"],
                "totalKcal": target["totalKcal"],
                "mealType": target["mealType"],
                "timeOffset": target["timeOffset"],
            })

    lines: list[str] = []
    for input_text, target in examples:
        lines.append(f"Input: {input_text}")
        lines.append(json.dumps(target, separators=(",", ":"), ensure_ascii=True))
        lines.append("")
    SHORTHAND_PATH.write_text("\n".join(lines), encoding="utf-8")

    meal_counts = Counter(target["mealType"] for _, target in examples)
    time_counts = Counter(target["timeOffset"] for _, target in examples)
    unit_counts = Counter(target["items"][0]["unit"] for _, target in examples)
    calories = [target["totalKcal"] for _, target in examples]
    lengths = [len(input_text) for input_text, _ in examples]
    return {
        "trainingRows": len(examples),
        "foodCounts": dict(Counter(row["name"] for row in rows)),
        "unitCounts": dict(sorted(unit_counts.items())),
        "mealTypeCounts": dict(sorted(meal_counts.items())),
        "timeOffsetModeCounts": dict(sorted(time_counts.items())),
        "inputLength": {"minimum": min(lengths), "maximum": max(lengths)},
        "calorieRange": [min(calories), max(calories)],
        "collisionRetries": collisions,
        "validationRetries": validation_retries,
    }


def main() -> None:
    rows, quarantined, source_stats = clean_source()
    training_stats = write_training(rows)
    print(f"Source rows: {source_stats['sourceRows']}")
    print(f"Clean rows: {source_stats['cleanRows']}")
    print(f"Quarantined rows: {source_stats['quarantinedRows']}")
    print(f"Exact cleaned duplicates removed: {source_stats['exactCleanDuplicatesRemoved']}")
    print(f"Training rows: {training_stats['trainingRows']}")
    print(f"Food counts: {training_stats['foodCounts']}")
    print(f"Unit counts: {training_stats['unitCounts']}")
    print(f"Meal-type counts: {training_stats['mealTypeCounts']}")
    print(f"Time-offset mode counts: {training_stats['timeOffsetModeCounts']}")
    print(f"Input length: {training_stats['inputLength']}")
    print(f"Calorie range: {training_stats['calorieRange']}")
    print(f"Input collision retries: {training_stats['collisionRetries']}")
    print(f"Validation retries: {training_stats['validationRetries']}")
    print(f"Source table rows: {source_stats['sourceTableRows']}")
    print(f"Source null counts: {source_stats['sourceNullCounts']}")
    print(f"Source unit distribution: {source_stats['rawUnitCounts']}")
    print(f"Source calorie range: {source_stats['rawEnergyRange']}")
    print(f"Wrote {CLEAN_PATH.name}, {QUARANTINE_PATH.name}, {TRAINING_PATH.name}, and {SHORTHAND_PATH.name}")


if __name__ == "__main__":
    main()
