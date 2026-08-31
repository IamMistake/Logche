"""Model extraction contracts and fields owned by deterministic app code."""

CONTRACTS = {
    "food": {
        "fields": {"items", "mealType"},
        "item_fields": {"name", "quantity", "unit"},
        "derived_fields": {"totalKcal", "timeOffset"},
    },
    "gym": {
        "fields": {"exercise", "setNumber", "reps", "weightKg"},
        "item_fields": set(),
        "derived_fields": set(),
    },
    "movement": {
        "fields": {
            "activityName", "averageHeartRate", "kcal", "distance",
            "elevationGain", "poolLength", "steps", "swimLengths",
        },
        "item_fields": set(),
        "derived_fields": {"distanceUnit", "duration", "pace", "speed", "poolLengthUnit"},
    },
    "money": {
        "fields": {"transactionType", "amount", "currency", "category", "description", "fromAccount", "toAccount"},
        "item_fields": set(),
        "derived_fields": {"timeOffset"},
    },
    "media": {
        "fields": {"mediaType", "title", "rating", "favorite"},
        "item_fields": set(),
        "derived_fields": {"timeOffset"},
    },
}


def category_for_dataset(dataset_id):
    name = dataset_id.removesuffix(".csv").removesuffix("-data")
    return "food" if name == "multi-food" else name


def contract_for_dataset(dataset_id):
    category = category_for_dataset(dataset_id)
    try:
        return CONTRACTS[category]
    except KeyError as exc:
        raise ValueError(f"unsupported dataset category: {category}") from exc


def extraction_view(value, contract):
    """Keep only values the model is responsible for extracting."""
    if not isinstance(value, dict):
        return value
    result = {key: value[key] for key in contract["fields"] if key in value}
    if "items" in result and isinstance(result["items"], list):
        item_fields = contract["item_fields"]
        result["items"] = [
            {key: item[key] for key in item_fields if key in item}
            for item in result["items"]
            if isinstance(item, dict)
        ]
    return result
