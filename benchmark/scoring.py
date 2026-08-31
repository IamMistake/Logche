from .contracts import extraction_view


def _leaves(value, prefix=""):
    if isinstance(value, dict):
        result = {}
        for key, child in value.items():
            result.update(_leaves(child, f"{prefix}.{key}" if prefix else key))
        return result
    if isinstance(value, list):
        result = {}
        for index, child in enumerate(value):
            result.update(_leaves(child, f"{prefix}[{index}]"))
        return result
    return {prefix: value}


def score(expected, actual):
    if actual is None:
        return {"validJson": False, "exactMatch": False, "fieldPrecision": 0.0, "fieldRecall": 0.0, "fieldF1": 0.0, "hallucinatedFields": 0}
    gold, prediction = _leaves(expected), _leaves(actual)
    matching = sum(key in gold and gold[key] == value for key, value in prediction.items())
    precision = matching / len(prediction) if prediction else 0.0
    recall = matching / len(gold) if gold else (1.0 if not prediction else 0.0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"validJson": True, "exactMatch": expected == actual, "fieldPrecision": precision, "fieldRecall": recall, "fieldF1": f1, "hallucinatedFields": len(set(prediction) - set(gold))}


def score_layers(expected, actual, contract):
    """Score extraction responsibility separately from the final object."""
    extraction_expected = _project(expected, contract)
    extraction_actual = _project(actual, contract) if actual is not None else None
    extraction = score(extraction_expected, extraction_actual)
    end_to_end = score(expected, actual)
    return {"extraction": extraction, "endToEnd": end_to_end}


def _project(value, contract):
    if value is None:
        return None
    return extraction_view(value, contract)
