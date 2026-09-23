import math
from dataclasses import dataclass

from .options import ORDER, QUESTION_ID

TOTAL_TOLERANCE = 1e-3


class ResponseError(Exception):
    pass


@dataclass
class Choice:
    probabilities: dict
    server_choice: str
    confidence: float
    selected: str
    model: str
    usage: dict | None


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def select(probabilities):
    best = max(probabilities.values())
    return min((key for key, value in probabilities.items() if value == best), key=ORDER.__getitem__)


def validate_response(payload):
    if not isinstance(payload, dict):
        raise ResponseError("response body is not an object")
    model = payload.get("model")
    if not isinstance(model, str):
        raise ResponseError("response model is missing or not a string")
    answers = payload.get("answers")
    if not isinstance(answers, dict) or QUESTION_ID not in answers:
        raise ResponseError(f"response has no answer for {QUESTION_ID}")
    answer = answers[QUESTION_ID]
    if not isinstance(answer, dict) or answer.get("type") != "choice":
        raise ResponseError("answer type is not choice")
    probabilities = answer.get("probabilities")
    if not isinstance(probabilities, dict):
        raise ResponseError("probabilities are missing or not an object")
    offered = set(ORDER)
    returned = set(probabilities)
    missing = sorted(offered - returned, key=ORDER.__getitem__)
    extra = sorted(returned - offered)
    if missing or extra:
        raise ResponseError(f"probability keys differ from options: missing={missing} extra={extra}")
    for key, value in probabilities.items():
        if not _is_number(value) or not math.isfinite(value) or value < 0 or value > 1:
            raise ResponseError(f"probability for {key} is not a finite number in [0, 1]: {value!r}")
    total = math.fsum(probabilities.values())
    if total <= 0 or abs(total - 1) > TOTAL_TOLERANCE:
        raise ResponseError(f"probabilities sum to {total!r}, outside 1 +/- {TOTAL_TOLERANCE}")
    confidence = answer.get("confidence")
    if not _is_number(confidence) or not math.isfinite(confidence):
        raise ResponseError(f"confidence is not a finite number: {confidence!r}")
    server_choice = answer.get("choice")
    best = max(probabilities.values())
    if server_choice not in probabilities or probabilities[server_choice] != best:
        raise ResponseError(f"server choice {server_choice!r} is not an offered maximum")
    usage = payload.get("usage")
    usage = usage if isinstance(usage, dict) else None
    ordered = {key: probabilities[key] for key in sorted(probabilities, key=ORDER.__getitem__)}
    return Choice(ordered, server_choice, confidence, select(ordered), model, usage)
