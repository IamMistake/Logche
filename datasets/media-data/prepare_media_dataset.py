#!/usr/bin/env python3
"""Prepare movie and book ratings as Logche shorthand examples."""

from __future__ import annotations

import csv
import io
import json
import random
import re
import zipfile
from collections import Counter
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path


HERE = Path(__file__).resolve().parent
MOVIE_SOURCE = HERE / "ml-latest-small.zip"
BOOK_RATINGS_SOURCE = HERE / "goodbooks-ratings.csv"
BOOKS_SOURCE = HERE / "goodbooks-books.csv"
CLEAN_PATH = HERE / "media_records_clean.csv"
QUARANTINE_PATH = HERE / "media_quarantine.json"
TRAINING_PATH = HERE / "training.csv"
SHORTHAND_PATH = HERE / "media_shorthand.txt"
SEED = 20260830
SAMPLE_SIZE = 1000
MAX_TITLE_LENGTH = 60
MAX_INPUT_LENGTH = 100

CLEAN_COLUMNS = ("source", "media_type", "title", "rating", "favorite")
TRAINING_COLUMNS = ("input", "mediaType", "title", "rating", "favorite", "timeOffset")
FAVORITE_MARKERS = ("fav", "favorite", "favourite", "heart", "loved")
TIME_OFFSETS = {
    "": "PT0M",
    "yesterday": "-P1D",
    "ye": "-P1D",
    "yday": "-P1D",
    "-1d": "-P1D",
}


def normalize_title(value: str, media_type: str, keep_year: bool = False) -> str:
    value = value.replace("\ufffd", "").replace("â€™", "'").replace("â€“", "-")
    value = re.sub(r"\s+", " ", value).strip()
    if not value:
        raise ValueError("missing title")
    if media_type == "book":
        while " (" in value and re.search(r"(?:#\d+|\blevel\s+\d+)[^)]*\)$", value, flags=re.IGNORECASE):
            value = value[: value.rfind(" (")].rstrip()
    elif not keep_year:
        value = re.sub(r"\s+\(\d{4}\)$", "", value).strip()
    return value


def decimal_rating(value: str, scale: Decimal) -> Decimal:
    try:
        rating = Decimal(value.strip())
    except (InvalidOperation, AttributeError):
        raise ValueError("invalid rating") from None
    if rating < 0 or rating > scale:
        raise ValueError("rating outside source scale")
    normalized = (rating * Decimal("10") / scale).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return normalized


def json_rating(value: Decimal) -> int | float:
    return int(value) if value == value.to_integral_value() else float(value)


def reservoir(rows: list[dict], limit: int, seed: int) -> list[dict]:
    chosen: list[dict] = []
    rng = random.Random(seed)
    for index, row in enumerate(rows):
        if index < limit:
            chosen.append(row)
        else:
            slot = rng.randint(0, index)
            if slot < limit:
                chosen[slot] = row
    return chosen


def read_movies(quarantine: list[dict]) -> tuple[int, list[dict]]:
    rows: list[dict] = []
    with zipfile.ZipFile(MOVIE_SOURCE) as archive:
        names = set(archive.namelist())
        required = {"ml-latest-small/movies.csv", "ml-latest-small/ratings.csv"}
        if not required <= names:
            raise ValueError("MovieLens archive is missing required files")
        with archive.open("ml-latest-small/movies.csv") as handle:
            raw_movies = {row["movieId"]: row["title"] for row in csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8"))}
            movie_bases = Counter(re.sub(r"\s+\(\d{4}\)$", "", normalize_title(title, "movie")) for title in raw_movies.values())
        with archive.open("ml-latest-small/ratings.csv") as handle:
            reader = csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8"))
            if set(reader.fieldnames or ()) != {"userId", "movieId", "rating", "timestamp"}:
                raise ValueError("unexpected MovieLens rating columns")
            source_rows = 0
            valid: list[dict] = []
            for source_index, raw in enumerate(reader, start=2):
                source_rows += 1
                reasons: list[str] = []
                title = raw_movies.get(raw["movieId"])
                if title is None:
                    reasons.append("missing joined metadata")
                try:
                    normalized_title = normalize_title(title or "", "movie")
                    year = re.search(r"\((\d{4})\)$", title or "")
                    base = re.sub(r"\s+\(\d{4}\)$", "", normalized_title)
                    clean_title = normalize_title(title or "", "movie", movie_bases[base] > 1)
                except ValueError as error:
                    reasons.append(str(error))
                    clean_title = ""
                try:
                    rating = decimal_rating(raw["rating"], Decimal("5"))
                except ValueError as error:
                    reasons.append(str(error))
                    rating = Decimal("0")
                if len(clean_title) > MAX_TITLE_LENGTH:
                    continue
                if reasons:
                    quarantine.append({"sourceIndex": source_index, "reasons": sorted(set(reasons)), "record": {}})
                else:
                    valid.append({"source": "MovieLens ml-latest-small", "media_type": "movie", "title": clean_title, "rating": rating})
    return source_rows, reservoir(valid, SAMPLE_SIZE, SEED + 1)


def read_books(quarantine: list[dict]) -> tuple[int, list[dict]]:
    with BOOKS_SOURCE.open(newline="", encoding="utf-8") as handle:
        books_reader = csv.DictReader(handle)
        if set(books_reader.fieldnames or ()) != {"book_id", "goodreads_book_id", "best_book_id", "work_id", "books_count", "isbn", "isbn13", "authors", "original_publication_year", "original_title", "title", "language_code", "average_rating", "ratings_count", "work_ratings_count", "work_text_reviews_count", "ratings_1", "ratings_2", "ratings_3", "ratings_4", "ratings_5", "image_url", "small_image_url"}:
            raise ValueError("unexpected Goodbooks metadata columns")
        books = {row["book_id"]: row["title"] for row in books_reader}

    valid: list[dict] = []
    source_rows = 0
    with BOOK_RATINGS_SOURCE.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if set(reader.fieldnames or ()) != {"user_id", "book_id", "rating"}:
            raise ValueError("unexpected Goodbooks rating columns")
        for source_index, raw in enumerate(reader, start=2):
            source_rows += 1
            reasons: list[str] = []
            title = books.get(raw["book_id"])
            if title is None:
                reasons.append("missing joined metadata")
            try:
                clean_title = normalize_title(title or "", "book")
            except ValueError as error:
                reasons.append(str(error))
                clean_title = ""
            try:
                    rating = decimal_rating(raw["rating"], Decimal("5"))
            except ValueError as error:
                reasons.append(str(error))
                rating = Decimal("0")
            if len(clean_title) > MAX_TITLE_LENGTH:
                continue
            if reasons:
                quarantine.append({"sourceIndex": source_index, "reasons": sorted(set(reasons)), "record": {}})
            else:
                valid.append({"source": "Goodbooks-10k", "media_type": "book", "title": clean_title, "rating": rating})
    return source_rows, reservoir(valid, SAMPLE_SIZE, SEED + 2)


def time_expression(rng: random.Random) -> tuple[str, str]:
    roll = rng.random()
    if roll < 0.65:
        return "", "PT0M"
    if roll < 0.80:
        hours = rng.randint(1, 23)
        long_form = f"{hours} hour{'s' if hours != 1 else ''} ago"
        return rng.choice((f"-{hours}h", f"{hours}h ago", long_form)), f"-PT{hours}H"
    days = rng.randint(1, 30)
    if days == 1:
        phrase = rng.choice(tuple(TIME_OFFSETS))
        return phrase, TIME_OFFSETS[phrase]
    return rng.choice((f"-{days}d", f"{days}d ago", f"{days} days ago")), f"-P{days}D"


def make_example(row: dict, index: int) -> tuple[str, dict]:
    rng = random.Random(SEED + index * 104729)
    cue = rng.choice(("watched", "movie", "film", "saw")) if row["media_type"] == "movie" else rng.choice(("read", "book", "novel", "finished"))
    rating = row["rating"]
    rating_text = rng.choice((str(json_rating(rating)), f"{json_rating(rating)}/10")) if rng.random() < 0.55 else f"{(rating / Decimal('2')).normalize()} {'star' if rating == Decimal('2') else 'stars'}"
    favorite = rng.random() < 0.18
    marker = rng.choice(FAVORITE_MARKERS) if favorite else ""
    time_text, offset = time_expression(rng)
    input_text = " ".join(part for part in (cue, row["title"].lower(), rating_text, marker, time_text) if part)
    output = {"mediaType": row["media_type"], "title": row["title"], "rating": json_rating(rating), "favorite": favorite, "timeOffset": offset}
    return input_text, output


def validate(input_text: str, output: dict) -> None:
    lowered = input_text.casefold()
    cues = ("watched", "movie", "film", "saw") if output["mediaType"] == "movie" else ("read", "book", "novel", "finished")
    if not input_text or not any(re.search(rf"\b{re.escape(cue)}\b", lowered) for cue in cues):
        raise ValueError("media type is not grounded")
    if len(output["title"]) > MAX_TITLE_LENGTH or len(input_text) > MAX_INPUT_LENGTH:
        raise ValueError("title or input is too long")
    if output["title"].casefold() not in lowered:
        raise ValueError("title is absent")
    if not 0 <= output["rating"] <= 10:
        raise ValueError("rating outside 0-10")
    without_title = lowered.replace(output["title"].casefold(), "", 1)
    marked = any(re.search(rf"\b{re.escape(marker)}\b", without_title) for marker in FAVORITE_MARKERS)
    if output["favorite"] != marked:
        raise ValueError("favorite marker mismatch")
    if output["timeOffset"] == "PT0M" and re.search(r"(?:\b(?:ago|yesterday|ye|yday)\b|-\d+[hd])", lowered):
        raise ValueError("relative time mismatch")


def main() -> None:
    quarantine: list[dict] = []
    movie_source_rows, movies = read_movies(quarantine)
    book_source_rows, books = read_books(quarantine)
    sampled = movies + books
    deduped: list[dict] = []
    seen: set[tuple[str, str, Decimal]] = set()
    duplicate_count = 0
    for row in sampled:
        key = (row["media_type"], row["title"], row["rating"])
        if key in seen:
            duplicate_count += 1
            continue
        seen.add(key)
        row["favorite"] = False
        deduped.append(row)
    examples: list[tuple[str, dict]] = []
    for index, row in enumerate(deduped):
        input_text, output = make_example(row, index)
        validate(input_text, output)
        examples.append((input_text, output))

    with CLEAN_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CLEAN_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for row, (_, output) in zip(deduped, examples):
            writer.writerow({"source": row["source"], "media_type": row["media_type"], "title": row["title"], "rating": json_rating(row["rating"]), "favorite": output["favorite"]})
    QUARANTINE_PATH.write_text(json.dumps(quarantine, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    with TRAINING_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=TRAINING_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for input_text, output in examples:
            writer.writerow({"input": input_text, **output})
    lines = []
    for input_text, output in examples:
        lines.extend((f"Input: {input_text}", json.dumps(output, separators=(",", ":"), ensure_ascii=True), ""))
    SHORTHAND_PATH.write_text("\n".join(lines), encoding="utf-8")

    inputs = [item[0] for item in examples]
    ratings = Counter(str(item[1]["rating"]) for item in examples)
    favorites = sum(item[1]["favorite"] for item in examples)
    offsets = Counter(item[1]["timeOffset"] for item in examples)
    counts = Counter(item[1]["mediaType"] for item in examples)
    print(f"Movie source rows: {movie_source_rows}")
    print(f"Book source rows: {book_source_rows}")
    print(f"Clean rows: {len(deduped)}")
    print(f"Quarantined rows: {len(quarantine)}")
    print(f"Training rows: {len(examples)}")
    print(f"Movie/book counts: {dict(sorted(counts.items()))}")
    print(f"Rating distribution: {dict(sorted(ratings.items(), key=lambda item: float(item[0])))}")
    print(f"Favorite count: {favorites}")
    print(f"Relative-time mode counts: {dict(sorted(offsets.items()))}")
    print(f"Duplicate count: {duplicate_count}")
    print(f"Input length: minimum={min(map(len, inputs))}, maximum={max(map(len, inputs))}")


if __name__ == "__main__":
    main()
