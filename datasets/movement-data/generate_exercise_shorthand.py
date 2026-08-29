#!/usr/bin/env python3
"""Generate realistic shorthand examples from the cleaned exercise records."""

from __future__ import annotations

import json
import random
import re
import csv
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


HERE = Path(__file__).resolve().parent
INPUT_PATH = HERE / "exercises.json"
OUTPUT_PATH = HERE / "exercise_shorthand.txt"
TRAINING_CSV_PATH = HERE / "training.csv"
QUARANTINE_PATH = HERE / "exercise_quarantine.json"
SEED = 20260829

ACTIVITY_FIELDS = {
    "Aerobic Workout": ("duration", "calories", "averageHeartRate", "steps"),
    "Bike": ("duration", "distance", "calories", "averageHeartRate", "elevationGain"),
    "Circuit Training": ("duration", "calories", "averageHeartRate", "steps", "elevationGain"),
    "Cross Country Skiing": (
        "duration",
        "distance",
        "calories",
        "averageHeartRate",
        "steps",
        "elevationGain",
    ),
    "Dancing": ("duration", "calories", "averageHeartRate", "steps"),
    "Hike": (
        "duration",
        "distance",
        "calories",
        "averageHeartRate",
        "steps",
        "elevationGain",
    ),
    "Hockey": ("duration", "calories", "steps"),
    "Outdoor Bike": ("duration", "calories", "averageHeartRate", "elevationGain"),
    "Run": (
        "duration",
        "distance",
        "calories",
        "averageHeartRate",
        "steps",
        "elevationGain",
    ),
    "Skiing": (
        "duration",
        "distance",
        "calories",
        "averageHeartRate",
        "steps",
        "elevationGain",
    ),
    "Sport": ("duration", "calories", "averageHeartRate", "steps"),
    "Swim": (
        "duration",
        "distance",
        "calories",
        "poolLength",
        "swimLengths",
    ),
    "Tennis": (
        "duration",
        "distance",
        "calories",
        "averageHeartRate",
        "steps",
        "elevationGain",
    ),
    "Treadmill": (
        "duration",
        "distance",
        "calories",
        "averageHeartRate",
        "steps",
        "elevationGain",
    ),
    "Walk": (
        "duration",
        "distance",
        "calories",
        "averageHeartRate",
        "steps",
        "elevationGain",
    ),
    "Yoga": ("duration", "calories", "averageHeartRate", "steps", "elevationGain"),
}

OUTPUT_FIELDS = (
    "activityName",
    "averageHeartRate",
    "kcal",
    "distance",
    "distanceUnit",
    "duration",
    "elevationGain",
    "pace",
    "poolLength",
    "poolLengthUnit",
    "speed",
    "steps",
    "swimLengths",
)


def round2(value: float | int) -> int | float:
    """Round with decimal half-up semantics and avoid unnecessary .0 values."""
    rounded = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if rounded == rounded.to_integral_value():
        return int(rounded)
    return float(rounded)


def number(value: float | int, decimals: int = 2) -> str:
    """Format a number without trailing zeroes."""
    text = f"{float(value):.{decimals}f}".rstrip("0").rstrip(".")
    return text or "0"


def present(row: dict, field: str) -> bool:
    value = row.get(field)
    if value is None:
        return False
    if field in {"distance", "steps", "elevationGain", "poolLength", "swimLengths"}:
        return float(value) > 0
    if field == "duration":
        return float(value) > 0
    return True


def choose_fields(row: dict, rng: random.Random) -> list[str]:
    """Choose the measurements a user might actually include in one entry."""
    available = [
        field
        for field in ACTIVITY_FIELDS[row["activityName"]]
        if present(row, field)
    ]
    if not available:
        return []

    # Most users give duration; a smaller group gives only a distance or result.
    selected: list[str] = []
    if "duration" in available and rng.random() >= 0.10:
        selected.append("duration")

    if "distance" in available and rng.random() < 0.72:
        selected.append("distance")
    elif "duration" not in selected and "duration" in available and rng.random() < 0.70:
        selected.append("duration")

    detail_roll = rng.random()
    if detail_roll < 0.20:
        target_count = min(2, len(available))
    elif detail_roll < 0.78:
        target_count = min(rng.choice((3, 4)), len(available))
    else:
        target_count = len(available)

    # Prefer core measurements, but allow optional heart rate, steps and elevation.
    weights = {
        "duration": 5,
        "distance": 5,
        "calories": 4,
        "averageHeartRate": 3,
        "steps": 2,
        "elevationGain": 1,
        "poolLength": 3,
        "swimLengths": 3,
    }
    while len(selected) < target_count:
        remaining = [field for field in available if field not in selected]
        if not remaining:
            break
        selected.append(rng.choices(remaining, [weights[field] for field in remaining])[0])

    return selected


def distance_token(
    kilometers: float,
    rng: random.Random,
    avoid_bare_k: bool = False,
) -> tuple[str, float, float]:
    """Return a distance token and its value converted back to kilometers."""
    unit = rng.choices(("km", "mi", "m"), (6, 2, 2))[0]
    if unit == "mi":
        displayed = round2(kilometers / 1.609344)
        calculation_distance = float(displayed) * 1.609344
        normalized = round2(calculation_distance)
        forms = (
            f"{number(displayed)}mi",
            f"{number(displayed)} mi",
            f"mi{number(displayed)}",
        )
    elif unit == "m":
        displayed = max(1, int(round(kilometers * 1000)))
        calculation_distance = displayed / 1000
        normalized = round2(calculation_distance)
        forms = (
            f"{displayed}m",
            f"{displayed} m",
            f"m{displayed}",
        )
    else:
        displayed = round2(kilometers)
        normalized = displayed
        calculation_distance = float(displayed)
        forms = [
            f"{number(displayed)}km",
            f"{number(displayed)} km",
            f"km{number(displayed)}",
        ]
        if not avoid_bare_k:
            forms.extend((f"k{number(displayed)}", f"{number(displayed)}k"))
    return rng.choice(forms), float(normalized), calculation_distance


def duration_token(
    milliseconds: float,
    rng: random.Random,
    allow_bare: bool = False,
) -> tuple[str, int]:
    """Return a duration token and its value in milliseconds."""
    source_seconds = max(1, int(round(milliseconds / 1000)))
    styles = ["decimal_min", "integer_min", "hms", "seconds", "compact_spaced"]
    if allow_bare:
        styles.append("bare_min")
    style = rng.choice(styles)

    if style == "decimal_min":
        minutes = round(source_seconds / 60, 1)
        seconds = max(1, int(round(minutes * 60)))
        return f"{number(minutes, 1)}min", seconds * 1000
    if style == "integer_min":
        minutes = max(1, int(round(source_seconds / 60)))
        return rng.choice((f"{minutes}min", f"{minutes} min", f"min{minutes}")), minutes * 60 * 1000
    if style == "seconds":
        return rng.choice((f"{source_seconds}s", f"{source_seconds}sec", f"sec{source_seconds}")), source_seconds * 1000
    if style == "bare_min":
        minutes = round(source_seconds / 60, 1)
        return number(minutes, 1), max(1, int(round(minutes * 60))) * 1000

    hours, remainder = divmod(source_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if style == "compact_spaced":
        parts = []
        if hours:
            parts.append(f"{hours}h")
        if minutes or hours:
            parts.append(f"{minutes}min")
        if seconds or not parts:
            parts.append(f"{seconds}sec")
        return " ".join(parts), source_seconds * 1000

    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes or hours:
        parts.append(f"{minutes}m")
    if seconds or not parts:
        parts.append(f"{seconds}s")
    if not hours and not seconds:
        return f"{minutes}min", source_seconds * 1000
    return "".join(parts), source_seconds * 1000


def calories_token(calories: float | int, rng: random.Random) -> tuple[str, int | float]:
    value = round2(calories)
    text = number(value)
    forms = (f"{text}kcal", f"kcal{text}")
    return rng.choice(forms), value


def steps_token(steps: float | int, rng: random.Random) -> tuple[str, int]:
    value = int(round(steps))
    if value >= 1000 and rng.random() < 0.45:
        displayed = round2(value / 1000)
        normalized = int(round(float(displayed) * 1000))
        text = number(displayed)
        forms = (f"{text}ksteps", f"{text}k steps", f"steps{text}k")
        return rng.choice(forms), normalized
    forms = [f"{value}steps", f"{value} steps", f"step{value}", f"steps{value}"]
    return rng.choice(forms), value


def heart_rate_token(heart_rate: float | int, rng: random.Random) -> tuple[str, int | float]:
    value = round2(heart_rate)
    text = number(value)
    forms = (
        f"bpm{text}",
        f"{text}bpm",
        f"{text} bpm",
        f"{text}hr",
        f"hr{text}",
        f"{text}b",
        f"b{text}",
        f"avg{text}",
    )
    return rng.choice(forms), value


def elevation_token(elevation: float | int, rng: random.Random) -> tuple[str, float | int]:
    value = round2(elevation)
    text = number(value)
    forms = (
        f"+{text}m",
        f"{text}m gain",
        f"gain{text}m",
        f"elev{text}m",
        f"up{text}m",
    )
    return rng.choice(forms), value


def pool_length_token(pool_length: float | int, rng: random.Random) -> tuple[str, int | float]:
    value = round2(pool_length)
    text = number(value)
    forms = (f"{text}m pool", f"pool{text}m", f"pool {text}m")
    return rng.choice(forms), value


def swim_lengths_token(lengths: float | int, rng: random.Random) -> tuple[str, int]:
    value = int(round(lengths))
    forms = (
        f"{value}l",
        f"{value}laps",
        f"{value} laps",
        f"laps{value}",
    )
    return rng.choice(forms), value


def quarantine_reasons(row: dict) -> list[str]:
    """Return reasons that make a source row unsafe for normal training."""
    reasons: list[str] = []
    activity = row["activityName"]
    duration_hours = float(row.get("duration", 0)) / 3_600_000
    duration_seconds = float(row.get("duration", 0)) / 1000
    distance = float(row.get("distance", 0) or 0)
    speed = distance / duration_hours if distance > 0 and duration_hours > 0 else None
    heart_rate = row.get("averageHeartRate")

    if heart_rate is not None and not 30 <= float(heart_rate) <= 220:
        reasons.append(f"averageHeartRate outside 30-220: {heart_rate}")

    if activity == "Run":
        if duration_seconds < 60:
            reasons.append(f"run shorter than 60 sec: {round2(duration_seconds)}")
        if duration_hours > 8:
            reasons.append(f"run longer than 8 h: {round2(duration_hours)}")
        if speed is not None and speed < 4.5:
            reasons.append(f"run speed below 4.5 km/h: {round2(speed)}")
    elif activity == "Treadmill":
        if duration_hours > 4:
            reasons.append(f"treadmill longer than 4 h: {round2(duration_hours)}")
        if speed is not None and speed < 1:
            reasons.append(f"treadmill speed below 1 km/h: {round2(speed)}")
    elif activity == "Walk":
        if duration_hours > 18:
            reasons.append(f"walk longer than 18 h: {round2(duration_hours)}")
        if speed is not None and speed < 1:
            reasons.append(f"walk speed below 1 km/h: {round2(speed)}")

    return reasons


def validate_example(input_text: str, output: dict) -> list[str]:
    """Reject ambiguous or non-canonical generated examples."""
    errors: list[str] = []
    long_units = r"\b(kilometers?|meters?|miles?|seconds?|minutes?|hours?|calories)\b"
    if re.search(long_units, input_text, flags=re.IGNORECASE):
        errors.append("contains a long-form unit")
    if "k-step" in input_text:
        errors.append("contains k-step")
    if re.search(r"\b\d+(?:\.\d+)?\s+kcal\s+\d", input_text):
        errors.append("contains ambiguous NUMBER kcal NUMBER binding")
    if any(value is None for value in output.values()):
        errors.append("contains null output value")
    if output.get("distanceUnit") not in {None, "km"}:
        errors.append("distanceUnit is not km")
    if output.get("poolLengthUnit") not in {None, "m"}:
        errors.append("poolLengthUnit is not m")
    if ("pace" in output or "speed" in output) and not {
        "distance",
        "duration",
    }.issubset(output):
        errors.append("derived field lacks distance or duration")
    return errors


def make_example(row: dict, rng: random.Random) -> tuple[str, dict]:
    selected = choose_fields(row, rng)
    tokens: list[str] = []
    values: dict[str, float | int] = {}
    calculation_distance: float | None = None

    for field in selected:
        if field == "duration":
            token, value = duration_token(
                row[field],
                rng,
                allow_bare="distance" in selected or "steps" in selected,
            )
        elif field == "distance":
            token, value, calculation_distance = distance_token(
                float(row[field]),
                rng,
                avoid_bare_k="steps" in selected,
            )
        elif field == "calories":
            token, value = calories_token(row[field], rng)
        elif field == "steps":
            token, value = steps_token(row[field], rng)
        elif field == "averageHeartRate":
            token, value = heart_rate_token(row[field], rng)
        elif field == "elevationGain":
            token, value = elevation_token(row[field], rng)
        elif field == "poolLength":
            token, value = pool_length_token(row[field], rng)
        elif field == "swimLengths":
            token, value = swim_lengths_token(row[field], rng)
        else:
            raise ValueError(f"Unsupported field: {field}")
        tokens.append(token)
        values[field] = value

    # The activity is always fully written and always comes first.
    rng.shuffle(tokens)
    input_text = " ".join([row["activityName"].lower(), *tokens])

    output: dict[str, float | int | str] = {"activityName": row["activityName"]}
    if "averageHeartRate" in values:
        output["averageHeartRate"] = values["averageHeartRate"]
    if "calories" in values:
        output["kcal"] = values["calories"]

    distance = values.get("distance")
    if distance is None and "poolLength" in values and "swimLengths" in values:
        calculation_distance = float(values["poolLength"]) * int(values["swimLengths"]) / 1000
        distance = round2(calculation_distance)
    if distance is not None:
        output["distance"] = distance
        output["distanceUnit"] = "km"

    duration = values.get("duration")
    if duration is not None:
        output["duration"] = duration
    if "elevationGain" in values:
        output["elevationGain"] = values["elevationGain"]
    if "poolLength" in values:
        output["poolLength"] = values["poolLength"]
        output["poolLengthUnit"] = "m"
    if "steps" in values:
        output["steps"] = values["steps"]
    if "swimLengths" in values:
        output["swimLengths"] = values["swimLengths"]

    if distance is not None and duration is not None and float(distance) > 0:
        seconds = float(duration) / 1000
        metric_distance = calculation_distance or float(distance)
        output["pace"] = round2(seconds / metric_distance)
        output["speed"] = round2(metric_distance / (seconds / 3600))

    output = {field: output[field] for field in OUTPUT_FIELDS if field in output}
    return input_text, output


def main() -> None:
    rows = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("exercises.json must contain an array")

    clean_rows: list[tuple[int, dict]] = []
    quarantined = []
    for source_index, row in enumerate(rows, start=1):
        reasons = quarantine_reasons(row)
        if reasons:
            quarantined.append(
                {"sourceIndex": source_index, "reasons": reasons, "record": row}
            )
        else:
            clean_rows.append((source_index, row))

    QUARANTINE_PATH.write_text(
        json.dumps(quarantined, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )

    examples: list[tuple[str, dict]] = []
    used_inputs: dict[str, str] = {}
    collision_attempts = 0
    validation_rejections = 0

    for index, (_, row) in enumerate(clean_rows):
        for attempt in range(100):
            rng = random.Random(SEED + index * 1009 + attempt * 7919)
            input_text, output = make_example(row, rng)
            errors = validate_example(input_text, output)
            if errors:
                validation_rejections += 1
                continue
            serialized_output = json.dumps(output, separators=(",", ":"), ensure_ascii=True)
            if input_text in used_inputs:
                collision_attempts += 1
                continue
            used_inputs[input_text] = serialized_output
            break
        else:
            raise RuntimeError(f"Could not generate a unique input for row {index}")
        examples.append((input_text, output))

    lines = []
    for input_text, output in examples:
        lines.append(f"Input: {input_text}")
        lines.append(f"Output: {json.dumps(output, separators=(',', ':'), ensure_ascii=True)}")
        lines.append("")
    OUTPUT_PATH.write_text("\n".join(lines), encoding="utf-8")

    with TRAINING_CSV_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("input", *OUTPUT_FIELDS),
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        for input_text, output in examples:
            writer.writerow({"input": input_text, **output})

    activity_counts: dict[str, int] = {}
    for _, row in clean_rows:
        activity_counts[row["activityName"]] = activity_counts.get(row["activityName"], 0) + 1

    print(f"Generated {len(examples)} examples in {OUTPUT_PATH}")
    print(f"Generated training file in {TRAINING_CSV_PATH}")
    print(f"Unique inputs: {len(used_inputs)}")
    print(f"Quarantined source rows: {len(quarantined)} in {QUARANTINE_PATH}")
    print(f"Input collision retries: {collision_attempts}")
    print(f"Validation retries: {validation_rejections}")
    print("Activity counts:")
    for activity, count in sorted(activity_counts.items()):
        print(f"  {activity}: {count}")


if __name__ == "__main__":
    main()
