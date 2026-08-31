#!/usr/bin/env python3
"""Clean the Kaggle money source and generate Logche money examples."""

from __future__ import annotations

import csv
import json
import random
import re
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


HERE = Path(__file__).resolve().parent
INPUT_PATH = HERE / "expenses_income_summary.csv"
OUTPUT_PATH = HERE / "expenses_income_summary_clean.csv"
QUARANTINE_PATH = HERE / "money_quarantine.json"
TRAINING_PATH = HERE / "training.csv"
SHORTHAND_PATH = HERE / "money_shorthand.txt"
SEED = 20260830

OUTPUT_COLUMNS = (
    "date",
    "title",
    "category",
    "account",
    "amount",
    "currency",
    "type",
    "transfer_amount",
    "transfer_currency",
    "to_account",
    "receive_amount",
    "receive_currency",
)

CURRENCY_RATES_FROM_INR = {
    "EUR": Decimal("90"),
    "MKD": Decimal("1.46"),
    "USD": Decimal("83"),
}

PSEUDONYMS = {
    "karthik": "person_a",
    "baba": "family_member_a",
    "maa": "family_member_b",
    "mom": "family_member_b",
    "chotu": "person_b",
    "sid": "person_c",
    "sriya": "person_d",
    "sujith": "person_e",
    "priyanka": "person_f",
    "shrenik": "person_g",
    "nidhish": "person_h",
    "goje": "person_i",
    "bhagwat": "person_j",
}

CURRENCY_FORMS = {
    "EUR": ("e", "eur", "€", "EUR"),
    "MKD": ("mkd", "den", "ден", "MKD"),
    "USD": ("usd", "dollar", "$", "USD"),
}


def money(value: str | Decimal) -> Decimal:
    return Decimal(str(value).replace(",", "").strip()).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def number(value: Decimal) -> str:
    text = format(value, "f").rstrip("0").rstrip(".")
    return text or "0"


def json_number(value: Decimal) -> int | float:
    return int(value) if value == value.to_integral_value() else float(value)


def convert_from_inr(value: str, currency: str) -> Decimal:
    return (money(value) / CURRENCY_RATES_FROM_INR[currency]).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def selected_currency(source_index: int) -> str:
    """Use EUR by default, with deterministic MKD and USD examples."""
    rng = random.Random(SEED + source_index * 7919)
    roll = rng.random()
    if roll < 0.15:
        return "MKD"
    if roll < 0.25:
        return "USD"
    return "EUR"


def has_any(title: str, terms: tuple[str, ...]) -> bool:
    return any(term in title for term in terms)


def pseudonymize_title(title: str) -> str:
    for original, replacement in PSEUDONYMS.items():
        title = re.sub(rf"\b{re.escape(original)}\b", replacement, title, flags=re.IGNORECASE)
    return title


def category_for(title: str, transaction_type: str) -> str:
    """Map the noisy source labels to a compact Logche taxonomy."""
    value = " ".join(title.lower().split())

    if transaction_type == "transfer":
        return "transfer"

    if transaction_type == "income":
        if "salary" in value:
            return "salary"
        if "pocket money" in value:
            return "family_support"
        if "scholarship" in value:
            return "scholarship"
        if "interest" in value:
            return "interest"
        if has_any(value, ("reward", "cashback")):
            return "rewards"
        if has_any(value, ("stonks", "investment")):
            return "investment_income"
        if has_any(value, ("refund", "return")):
            return "refund"
        if has_any(value, ("baba", "maa", "mom", "family")):
            return "family_support"
        if has_any(value, ("adjust", "add", "init")):
            return "balance_adjustment"
        return "other_income"

    if has_any(value, ("adjust", "init", "change")):
        return "balance_adjustment"
    if has_any(value, ("payback", "payup", "paid", "sent", "help")):
        return "peer_transfer"
    if has_any(value, ("baba", "maa", "mom", "chotu", "sid", "sriya", "sujith", "priyanka", "shrenik")):
        return "peer_transfer"
    if has_any(value, ("aloo bhujia", "breakfast", "biryani", "bonda", "burger", "burrito", "cake", "chai", "chicken", "chips", "coffee", "coke", "curd", "drink", "egg roll", "fried rice", "frooti", "goli soda", "haldiram", "ice cream", "jalebi", "juice", "lunch", "maggi", "manchuria", "noodles", "pastry", "pizza", "rb", "samosa", "snack", "shawarma", "tea", "treat", "water", "🍰")):
        return "food_drink"
    if has_any(value, ("grocery", "bread", "milk", "maida", "oil")):
        return "groceries"
    if has_any(value, ("petrol", "fuel")):
        return "fuel"
    if has_any(value, ("tire", "tyre", "brake")):
        return "vehicle_maintenance"
    if has_any(value, ("bus", "auto", "bike", "cab", "ferry", "metro", "rapido", "rta", "atr", "btr", "htp", "pta", "toto", "train", "transport")):
        return "transport"
    if "parking" in value:
        return "parking"
    if has_any(value, ("medic", "bandage", "doc", "glasses", "gym")):
        return "health"
    if has_any(value, ("haircut", "shampoo", "shave")):
        return "personal_care"
    if has_any(value, ("electricity", "internet", "mobile", "dish tv", "dishtv", "recharge", "domain", "card maintenance")):
        return "utilities"
    if has_any(value, ("rent",)):
        return "housing"
    if has_any(value, ("book", "exam", "print", "xerox", "stationary", "record book", "seminar", "pen")):
        return "education"
    if has_any(value, ("netflix", "fancode", "play store", "museum", "party", "entry fee", "ticket", "tickets", "gala", "fest")):
        return "entertainment"
    if has_any(value, ("clothes", "shirt", "pants", "pant", "suit", "shoes", "amazon", "computer", "laptop", "screen", "stickers")):
        return "shopping"
    if has_any(value, ("gift", "birthday")):
        return "gifts"
    if has_any(value, ("decline", "insufficient", "pos", "license", "capt. payment", "payment", "gpay", "upi", "stonks")):
        return "financial"
    if has_any(value, ("refund",)):
        return "refund"
    return "other"


def normalize_row(raw: dict[str, str], source_index: int) -> dict[str, str]:
    currency = selected_currency(source_index)
    if raw["currency"].strip().upper() != "INR":
        raise ValueError(f"unsupported source currency: {raw['currency']!r}")

    is_transfer = raw["type"].strip().upper() == "TRANSFER"
    source_amount = raw["transfer-amount"] if is_transfer else raw["amount"]
    amount = convert_from_inr(source_amount, currency)

    transaction_type = raw["type"].strip().lower()
    source_title = raw["title"]
    safe_title = pseudonymize_title(source_title)
    result = {
        "date": raw["Date"].strip(),
        "title": safe_title.strip(),
        "category": category_for(source_title, transaction_type),
        # Account values are source data and are intentionally not normalized.
        "account": raw["account"],
        "amount": number(amount),
        "currency": currency,
        "type": transaction_type,
        "transfer_amount": "",
        "transfer_currency": "",
        "to_account": raw["to-account"],
        "receive_amount": "",
        "receive_currency": "",
    }

    if is_transfer:
        result["transfer_amount"] = number(amount)
        result["transfer_currency"] = currency
        result["receive_amount"] = number(
            convert_from_inr(raw["receive-amount"], currency)
        )
        result["receive_currency"] = currency

    return result


def clean_source() -> tuple[list[dict[str, str]], list[dict[str, object]]]:
    with INPUT_PATH.open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        expected = {
            "Date",
            "title",
            "category",
            "account",
            "amount",
            "currency",
            "type",
            "transfer-amount",
            "transfer-currency",
            "to-account",
            "receive-amount",
            "receive-currency",
            "description",
            "due-date",
            "id",
        }
        columns = set(reader.fieldnames or ())
        if columns != expected:
            raise ValueError(f"unexpected source columns: {sorted(columns)}")

        clean_rows: list[dict[str, str]] = []
        quarantined: list[dict[str, object]] = []
        for source_index, raw in enumerate(reader, start=2):
            if not raw["title"].strip():
                quarantined.append(
                    {
                        "sourceIndex": source_index,
                        "reasons": ["title is null or blank"],
                        "record": raw,
                    }
                )
                continue
            clean_rows.append(normalize_row(raw, source_index))

    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(clean_rows)

    QUARANTINE_PATH.write_text(
        json.dumps(quarantined, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    return clean_rows, quarantined


def amount_token(amount: str, currency: str, sign: str, rng: random.Random) -> str:
    value = number(money(amount))
    forms = {
        "EUR": (f"{sign}{value}e", f"{sign}{value} eur", f"{sign}€{value}", f"{sign}{value}€"),
        "MKD": (f"{sign}{value}mkd", f"{sign}{value} den", f"{sign}{value} ден", f"{sign}{value} MKD"),
        "USD": (f"{sign}{value}usd", f"{sign}${value}", f"{sign}{value} USD", f"{sign}{value} dollar"),
    }[currency]
    return rng.choice(forms)


def transfer_description(row: dict[str, str]) -> str:
    destination = row["to_account"].casefold()
    if destination == "cash":
        return "Withdraw"
    if destination == "metro card":
        return "Recharge"
    return "Transfer"


def time_expression(rng: random.Random) -> tuple[str, str]:
    """Return a user phrase and its canonical ISO-8601 duration offset."""
    roll = rng.random()
    if roll < 0.55:
        return "", "PT0M"
    if roll < 0.75:
        hours = rng.randint(1, 23)
        phrase = rng.choice((f"-{hours}h", f"{hours}h ago", f"{hours} hours ago"))
        return phrase, f"-PT{hours}H"
    if roll < 0.95:
        days = rng.randint(1, 30)
        if days == 1:
            phrase = rng.choice(("yesterday", "ye", "yday", "-1d", "1d ago"))
        else:
            phrase = rng.choice((f"-{days}d", f"{days}d ago", f"{days} days ago"))
        return phrase, f"-P{days}D"
    phrase = rng.choice(("tmr", "tomorrow", "+1d", "in 1d"))
    return phrase, "P1D"


def make_input(row: dict[str, str], source_index: int) -> str:
    rng = random.Random(SEED + source_index * 104729)
    title = row["title"].strip().lower()
    amount = row["amount"]
    currency = row["currency"]
    time_phrase, _ = time_expression(rng)
    if row["type"] == "income":
        signed = amount_token(amount, currency, "+", rng)
        variants = [
            f"{title} {signed}",
            f"{signed} {title}",
            f"got {signed} {title}",
        ]
    elif row["type"] == "expense":
        signed = amount_token(amount, currency, "-", rng)
        unsigned = amount_token(amount, currency, "", rng)
        variants = [
            f"{title} {signed}",
            f"{title} {unsigned}",
            f"spent {unsigned} {title}",
        ]
    else:
        source = row["account"].lower()
        destination = row["to_account"].lower()
        signed = amount_token(amount, currency, "", rng)
        description = transfer_description(row).lower()
        variants = [
            f"{description} {signed} {source} to {destination}",
            f"{description} {source} {signed} to {destination}",
        ]
    if time_phrase:
        return f"{rng.choice(variants)} {time_phrase}"
    return rng.choice(variants)


def generated_time_offset(row: dict[str, str], source_index: int) -> str:
    rng = random.Random(SEED + source_index * 104729)
    _, offset = time_expression(rng)
    return offset


def write_training(rows: list[dict[str, str]]) -> tuple[int, int]:
    fields = (
        "input",
        "transactionType",
        "amount",
        "currency",
        "category",
        "description",
        "timeOffset",
        "fromAccount",
        "toAccount",
    )
    examples: list[dict[str, str | int | float]] = []
    null_category_rows = 0

    for source_index, row in enumerate(rows, start=2):
        if money(row["amount"]) <= 0:
            continue
        if not row["category"]:
            null_category_rows += 1
        examples.append(
            {
                "input": make_input(row, source_index),
                "transactionType": row["type"],
                "amount": json_number(money(row["amount"])),
                "currency": row["currency"],
                "category": row["category"] or None,
                "description": (
                    transfer_description(row)
                    if row["type"] == "transfer"
                    else row["title"]
                ),
                "timeOffset": generated_time_offset(row, source_index),
                "fromAccount": row["account"] if row["type"] == "transfer" else "",
                "toAccount": row["to_account"] if row["type"] == "transfer" else "",
            }
        )

    with TRAINING_PATH.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(examples)

    lines: list[str] = []
    for example in examples:
        target = {key: example[key] for key in fields if key != "input"}
        lines.append(f"Input: {example['input']}")
        lines.append(json.dumps(target, separators=(",", ":"), ensure_ascii=True))
        lines.append("")
    SHORTHAND_PATH.write_text("\n".join(lines), encoding="utf-8")
    return len(examples), null_category_rows


def main() -> None:
    rows, quarantined = clean_source()
    training_rows, null_category_rows = write_training(rows)
    print(f"Read {len(rows) + len(quarantined)} source rows")
    print(f"Wrote {OUTPUT_PATH.name} with {len(rows)} rows and {len(OUTPUT_COLUMNS)} columns")
    print(f"Quarantined blank-title rows: {len(quarantined)}")
    print(f"Training source rows with null category: {null_category_rows}")
    print(f"Generated training examples: {training_rows}")


if __name__ == "__main__":
    main()
