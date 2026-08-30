#!/usr/bin/env python3
"""Prepare Strong sets and generate set-level Logche gym examples."""

from __future__ import annotations

import csv
import json
import random
from collections import OrderedDict, defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
INPUT_PATH = HERE / "strong.csv"
SETS_JSON_PATH = HERE / "gym_sets.json"
SETS_CSV_PATH = HERE / "gym_sets.csv"
OUTPUT_PATH = HERE / "gym_shorthand.txt"
TRAINING_CSV_PATH = HERE / "training.csv"
QUARANTINE_PATH = HERE / "gym_quarantine.json"
EXCLUDED_PATH = HERE / "gym_excluded.json"
MANIFEST_PATH = HERE / "gym_examples_manifest.json"
SEED = 20260829
MAX_INPUT_LENGTH = 49
OMIT_EXERCISE_PROBABILITY = 0.35
CONTEXT_SHORT_PROBABILITY = 0.35
CROSS_EXERCISE_CONTEXT_PROBABILITY = 0.35

SOURCE_COLUMNS = (
    "Date",
    "Workout Name",
    "Duration",
    "Exercise Name",
    "Set Order",
    "Weight",
    "Reps",
    "Distance",
    "Seconds",
    "Notes",
    "Workout Notes",
    "RPE",
)

EXCLUDED_ACTIVITIES = {"Aerobics", "Swimming"}

# The source names are retained in the raw Strong export. Model targets use
# shortnames so later personal shorthand can converge on the same vocabulary.
EXERCISE_SHORTNAMES = {
    "Bench Press (Barbell)": "bench",
    "Clean (Barbell)": "clean",
    "Clean Pull": "clean_pull",
    "Clean and Jerk (Barbell)": "clean_and_jerk",
    "Crunch": "crunch",
    "Deadlift (Barbell)": "deadlift",
    "Front Squat (Barbell)": "front_squat",
    "Good Morning (Barbell)": "good_morning",
    "Hang Clean (Barbell)": "hang_clean",
    "Hang Snatch (Barbell)": "hang_snatch",
    "Overhead Press (Barbell)": "ohp",
    "Power Clean": "power_clean",
    "Power Snatch (Barbell)": "power_snatch",
    "Push Up": "push_up",
    "Snatch (Barbell)": "snatch",
    "Snatch Ballance": "snatch_balance",
    "Snatch Pull (Barbell)": "snatch_pull",
    "Split Jerk (Barbell)": "split_jerk",
    "Squat (Barbell)": "squat",
    "Strict Military Press (Barbell)": "military_press",
}

EXERCISE_ALIASES = {
    "bench": ("bench", "bp"),
    "clean": ("clean",),
    "clean_pull": ("cpull",),
    "clean_and_jerk": ("cj",),
    "crunch": ("crunch", "abs", "ab"),
    "deadlift": ("deadlift", "dl"),
    "front_squat": ("fs",),
    "good_morning": ("gm",),
    "hang_clean": ("hclean",),
    "hang_snatch": ("hsnatch",),
    "ohp": ("ohp", "press"),
    "power_clean": ("pclean",),
    "power_snatch": ("psnatch",),
    "push_up": ("pushup", "pu"),
    "snatch": ("snatch",),
    "snatch_balance": ("sb",),
    "snatch_pull": ("spull",),
    "split_jerk": ("sj",),
    "squat": ("squat",),
    "military_press": ("mp",),
}


@dataclass(frozen=True)
class SetRecord:
    source_index: int
    session_id: int
    exercise: str
    set_number: int
    weight_kg: Decimal | None
    reps: int


def decimal_value(value: str, field: str) -> Decimal:
    try:
        return Decimal(value.strip())
    except (InvalidOperation, AttributeError) as exc:
        raise ValueError(f"invalid {field}: {value!r}") from exc


def number(value: Decimal | int | float, decimals: int = 2) -> str:
    text = f"{float(value):.{decimals}f}".rstrip("0").rstrip(".")
    return text or "0"


def json_number(value: Decimal | int | float) -> int | float:
    rounded = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if rounded == rounded.to_integral_value():
        return int(rounded)
    return float(rounded)


def parse_source_set(raw: dict[str, str], source_index: int, session_id: int) -> SetRecord:
    source_name = raw["Exercise Name"].strip()
    if source_name not in EXERCISE_SHORTNAMES:
        raise ValueError(f"unsupported exercise: {source_name!r}")

    try:
        set_number = int(raw["Set Order"].strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid set number: {raw['Set Order']!r}") from exc
    if set_number < 1:
        raise ValueError(f"set number must be positive: {set_number}")

    try:
        reps = int(raw["Reps"].strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid reps: {raw['Reps']!r}") from exc
    if reps < 1:
        raise ValueError(f"reps must be positive: {reps}")

    weight = decimal_value(raw["Weight"], "weight")
    if weight < 0:
        raise ValueError(f"weight must not be negative: {weight}")

    # Strong uses zero for bodyweight movements. Omit it from the target.
    normalized_weight = None if weight == 0 else weight
    return SetRecord(
        source_index=source_index,
        session_id=session_id,
        exercise=EXERCISE_SHORTNAMES[source_name],
        set_number=set_number,
        weight_kg=normalized_weight,
        reps=reps,
    )


def suspicious_record(record: SetRecord) -> str | None:
    # This catches the observed Hang Snatch cluster without inventing a broad
    # strength limit. It remains reviewable in the quarantine artifact.
    if record.exercise == "hang_snatch" and record.weight_kg is not None:
        if record.weight_kg <= 5 and record.reps >= 30:
            return "hang snatch weight <= 5 kg with >= 30 reps"
    return None


def target_for(record: SetRecord) -> dict[str, int | float | str]:
    target: dict[str, int | float | str] = {
        "exercise": record.exercise,
        "setNumber": record.set_number,
        "reps": record.reps,
    }
    if record.weight_kg is not None:
        target["weightKg"] = json_number(record.weight_kg)
    return target


def add_quarantine(
    quarantine: list[dict[str, Any]],
    rows: list[dict[str, str]],
    source_index: int,
    reasons: list[str],
) -> None:
    quarantine.append(
        {
            "sourceIndex": source_index,
            "reasons": sorted(set(reasons)),
            "record": rows[source_index - 1],
        }
    )


def clean_source() -> tuple[
    list[dict[str, str]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, int],
]:
    with INPUT_PATH.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != SOURCE_COLUMNS:
            raise ValueError(f"unexpected Strong columns: {reader.fieldnames}")
        rows = list(reader)

    # Timestamp and workout name identify the source session only. Neither is
    # copied into a model-facing artifact.
    session_ids: OrderedDict[tuple[str, str], int] = OrderedDict()
    session_rows: OrderedDict[int, list[int]] = OrderedDict()
    for source_index, row in enumerate(rows, start=1):
        key = (row["Date"].strip(), row["Workout Name"].strip())
        session_id = session_ids.setdefault(key, len(session_ids) + 1)
        session_rows.setdefault(session_id, []).append(source_index)

    quarantine: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    clean_sets: list[dict[str, Any]] = []
    valid_exercise_groups = 0

    for session_id, source_indices in session_rows.items():
        source_groups: dict[str, list[tuple[int, dict[str, str]]]] = defaultdict(list)
        for source_index in source_indices:
            row = rows[source_index - 1]
            source_name = row["Exercise Name"].strip()
            if source_name in EXCLUDED_ACTIVITIES:
                excluded.append(
                    {
                        "sourceIndex": source_index,
                        "reason": f"excluded activity: {source_name}",
                        "record": row,
                    }
                )
                continue
            source_groups[source_name].append((source_index, row))

        for source_name, raw_group in source_groups.items():
            parsed: list[SetRecord] = []
            row_errors: dict[int, str] = {}
            for source_index, row in raw_group:
                try:
                    record = parse_source_set(row, source_index, session_id)
                except ValueError as exc:
                    row_errors[source_index] = str(exc)
                    continue
                suspicious = suspicious_record(record)
                if suspicious:
                    row_errors[source_index] = suspicious
                    continue
                parsed.append(record)

            set_numbers = [record.set_number for record in parsed]
            expected_numbers = list(range(1, len(set_numbers) + 1))
            sequence_invalid = set_numbers != expected_numbers or len(set(set_numbers)) != len(set_numbers)
            if row_errors or sequence_invalid:
                for source_index, _ in raw_group:
                    reasons = []
                    if source_index in row_errors:
                        reasons.append(row_errors[source_index])
                    if row_errors and source_index not in row_errors:
                        reasons.append("exercise set contains a rejected source row")
                    if sequence_invalid:
                        reasons.append("set numbers must be contiguous and unique")
                    add_quarantine(quarantine, rows, source_index, reasons)
                continue

            parsed.sort(key=lambda record: record.set_number)
            valid_exercise_groups += 1
            for record in parsed:
                clean_sets.append(
                    {
                        "sessionId": record.session_id,
                        "sourceIndex": record.source_index,
                        "exercise": record.exercise,
                        "setNumber": record.set_number,
                        "reps": record.reps,
                        **(
                            {"weightKg": json_number(record.weight_kg)}
                            if record.weight_kg is not None
                            else {}
                        ),
                    }
                )

    stats = {
        "sourceRows": len(rows),
        "sourceSessions": len(session_rows),
        "strengthSourceRows": len(rows) - len(excluded),
        "cleanSetRows": len(clean_sets),
        "validExerciseGroups": valid_exercise_groups,
        "excludedRows": len(excluded),
        "quarantineEntries": len(quarantine),
        "quarantinedRows": len(quarantine),
    }
    return rows, clean_sets, quarantine, excluded, stats


def set_records(clean_sets: list[dict[str, Any]]) -> list[SetRecord]:
    return [
        SetRecord(
            source_index=int(row["sourceIndex"]),
            session_id=int(row["sessionId"]),
            exercise=str(row["exercise"]),
            set_number=int(row["setNumber"]),
            weight_kg=Decimal(str(row["weightKg"])) if "weightKg" in row else None,
            reps=int(row["reps"]),
        )
        for row in clean_sets
    ]


def set_marker(set_number: int, rng: random.Random) -> str:
    return rng.choice((f"s{set_number}", f"set{set_number}", f"#{set_number}"))


def repetition_token(reps: int, rng: random.Random) -> str:
    return rng.choice((str(reps), f"r{reps}", f"{reps}r", f"{reps}reps"))


def absolute_weight_token(weight: Decimal, reps: int, rng: random.Random) -> str:
    weight_text = number(weight)
    reps_text = repetition_token(reps, rng)
    return rng.choice(
        (
            f"{weight_text}x{reps}",
            f"{weight_text}kgx{reps}",
            f"{weight_text} {reps_text}",
        )
    )


def relative_weight_token(
    previous_weight: Decimal, current_weight: Decimal, reps: int, rng: random.Random
) -> str:
    delta = current_weight - previous_weight
    sign = "+" if delta > 0 else "-"
    amount = number(abs(delta))
    base = number(previous_weight)
    reps_text = repetition_token(reps, rng)
    return rng.choice(
        (
            f"{base}{sign}{amount}x{reps}",
            f"{base} {sign}{amount} {reps_text}",
            f"{base}kg {sign}{amount}kg x{reps}",
            f"{base}{sign}{amount} {reps_text}",
        )
    )


def make_set_example(
    record: SetRecord, previous: SetRecord | None, rng: random.Random
) -> tuple[str, dict[str, Any], str, str]:
    alias = rng.choice(EXERCISE_ALIASES[record.exercise])
    marker = set_marker(record.set_number, rng)

    if record.weight_kg is None:
        payload = repetition_token(record.reps, rng)
        mode = "bodyweight"
    elif (
        previous is not None
        and previous.weight_kg is not None
        and record.weight_kg != previous.weight_kg
        and rng.random() < 0.55
    ):
        payload = relative_weight_token(previous.weight_kg, record.weight_kg, record.reps, rng)
        mode = "relative"
    else:
        payload = absolute_weight_token(record.weight_kg, record.reps, rng)
        mode = "absolute"

    context_input = " ".join((alias, marker, payload))
    context_short = (
        previous is not None
        and record.weight_kg is not None
        and rng.random() < CONTEXT_SHORT_PROBABILITY
    )
    if context_short:
        if previous.weight_kg is not None and record.weight_kg != previous.weight_kg:
            delta = record.weight_kg - previous.weight_kg
            sign = "+" if delta > 0 else "-"
            payload = f"{sign}{number(abs(delta))} x{record.reps}"
        else:
            payload = f"{number(record.weight_kg)}x{record.reps}"
        input_text = payload
    else:
        # Later sets may rely on the active exercise context, as users often do
        # when logging consecutive sets of the same movement.
        omit_exercise = record.set_number > 1 and rng.random() < OMIT_EXERCISE_PROBABILITY
        input_text = " ".join((marker, payload) if omit_exercise else (alias, marker, payload))
    if len(input_text) >= MAX_INPUT_LENGTH + 1:
        # All aliases are intentionally short, but keep a deterministic
        # fallback if a future source adds a longer exercise name.
        input_text = " ".join((EXERCISE_ALIASES[record.exercise][0], f"s{record.set_number}", payload))
    if len(input_text) >= MAX_INPUT_LENGTH + 1:
        raise AssertionError(f"input exceeds {MAX_INPUT_LENGTH} characters: {input_text}")

    return input_text, target_for(record), mode, context_input


def previous_sets(records: list[SetRecord]) -> dict[int, SetRecord | None]:
    grouped: dict[tuple[int, str], list[SetRecord]] = defaultdict(list)
    for record in records:
        grouped[(record.session_id, record.exercise)].append(record)

    previous: dict[int, SetRecord | None] = {}
    for group in grouped.values():
        group.sort(key=lambda record: record.set_number)
        last: SetRecord | None = None
        for record in group:
            previous[record.source_index] = last
            last = record
    return previous


def previous_session_sets(records: list[SetRecord]) -> dict[int, SetRecord | None]:
    grouped: dict[int, list[SetRecord]] = defaultdict(list)
    for record in records:
        grouped[record.session_id].append(record)

    previous: dict[int, SetRecord | None] = {}
    for group in grouped.values():
        group.sort(key=lambda record: record.source_index)
        last: SetRecord | None = None
        for record in group:
            previous[record.source_index] = last
            last = record
    return previous


def write_clean_sets(clean_sets: list[dict[str, Any]]) -> None:
    SETS_JSON_PATH.write_text(
        json.dumps(clean_sets, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    with SETS_CSV_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("sessionId", "sourceIndex", "exercise", "setNumber", "reps", "weightKg"),
            lineterminator="\n",
        )
        writer.writeheader()
        for row in clean_sets:
            writer.writerow(row)


def write_training(
    examples: list[tuple[str, str, dict[str, Any], str, int]],
    source_stats: dict[str, int],
) -> None:
    lines: list[str] = []
    for previous_input, input_text, target, _, _ in examples:
        if previous_input:
            lines.append(f"Previous: {previous_input}")
        lines.append(f"Input: {input_text}")
        lines.append(json.dumps(target, separators=(",", ":"), ensure_ascii=True))
        lines.append("")
    OUTPUT_PATH.write_text("\n".join(lines), encoding="utf-8")

    with TRAINING_CSV_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("previousInput", "input", "exercise", "setNumber", "reps", "weightKg"),
            lineterminator="\n",
        )
        writer.writeheader()
        for previous_input, input_text, target, _, _ in examples:
            writer.writerow(
                {
                    "previousInput": previous_input,
                    "input": input_text,
                    "exercise": target["exercise"],
                    "setNumber": target["setNumber"],
                    "reps": target["reps"],
                    "weightKg": target.get("weightKg", ""),
                }
            )

    mode_counts: dict[str, int] = defaultdict(int)
    for _, _, _, mode, _ in examples:
        mode_counts[mode] += 1
    input_lengths = [len(input_text) for _, input_text, _, _, _ in examples]
    MANIFEST_PATH.write_text(
        json.dumps(
            {
                "seed": SEED,
                "maxInputCharacters": MAX_INPUT_LENGTH,
                "modelColumns": ["previousInput", "input", "exercise", "setNumber", "reps", "weightKg"],
                "excludedModelFields": ["sessionTimestamp", "duration", "workoutName"],
                "source": "Strong App Analytics strong.csv",
                "sourceStats": source_stats,
                "trainingRows": len(examples),
                "inputModeCounts": dict(sorted(mode_counts.items())),
                "inputLength": {"minimum": min(input_lengths), "maximum": max(input_lengths)},
            },
            indent=2,
            ensure_ascii=True,
        )
        + "\n",
        encoding="utf-8",
    )


def validate_examples(examples: list[tuple[str, str, dict[str, Any], str, int]]) -> None:
    if not examples:
        raise AssertionError("no training examples generated")
    for previous_input, input_text, target, _, _ in examples:
        if not input_text.strip() or len(input_text) > MAX_INPUT_LENGTH:
            raise AssertionError(f"invalid input length: {input_text!r}")
        if previous_input and len(previous_input) > MAX_INPUT_LENGTH:
            raise AssertionError(f"invalid previous input length: {previous_input!r}")
        if set(target) - {"exercise", "setNumber", "reps", "weightKg"}:
            raise AssertionError(f"unexpected target fields: {target}")
        if set(target) not in (
            {"exercise", "setNumber", "reps"},
            {"exercise", "setNumber", "reps", "weightKg"},
        ):
            raise AssertionError(f"missing target fields: {target}")
        if target["exercise"] not in EXERCISE_ALIASES:
            raise AssertionError(f"unknown exercise shortname: {target['exercise']}")
        if int(target["setNumber"]) < 1 or int(target["reps"]) < 1:
            raise AssertionError(f"invalid set target: {target}")


def main() -> None:
    _, clean_sets, quarantine, excluded, source_stats = clean_source()
    write_clean_sets(clean_sets)
    QUARANTINE_PATH.write_text(
        json.dumps(quarantine, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    EXCLUDED_PATH.write_text(
        json.dumps(excluded, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )

    records = set_records(clean_sets)
    previous = previous_sets(records)
    previous_session = previous_session_sets(records)
    examples: list[tuple[str, str, dict[str, Any], str, int]] = []
    generated_context_inputs: dict[int, str] = {}
    for record in records:
        rng = random.Random(SEED + record.source_index * 7919)
        input_text, target, mode, context_input = make_set_example(
            record, previous[record.source_index], rng
        )
        previous_input = (
            generated_context_inputs[previous[record.source_index].source_index]
            if previous[record.source_index] is not None
            else ""
        )
        if not previous_input:
            prior_session_record = previous_session[record.source_index]
            if (
                prior_session_record is not None
                and rng.random() < CROSS_EXERCISE_CONTEXT_PROBABILITY
            ):
                previous_input = generated_context_inputs[prior_session_record.source_index]
        examples.append((previous_input, input_text, target, mode, record.source_index))
        generated_context_inputs[record.source_index] = context_input

    validate_examples(examples)
    write_training(examples, source_stats)

    print(f"Cleaned {source_stats['cleanSetRows']} strength sets from {source_stats['sourceRows']} source rows")
    print(f"Generated {len(examples)} set-level training examples")
    print(f"Excluded non-strength rows: {source_stats['excludedRows']}")
    print(f"Quarantined rows: {source_stats['quarantinedRows']}")
    print(f"Maximum input length: {max(len(input_text) for _, input_text, _, _, _ in examples)}")
    print(f"Wrote {TRAINING_CSV_PATH}")


if __name__ == "__main__":
    main()
