import time
from dataclasses import dataclass, field

from .options import CHAR_BY_ID, INSTRUCTIONS, STOP, build_request, mapping
from .trace import SCHEMA_VERSION, utc_now
from .transport import TransportError
from .validate import TOTAL_TOLERANCE, ResponseError, validate_response

EXIT_STOP = 0
EXIT_ERROR = 1
EXIT_LIMIT = 2
EXIT_INTERRUPT = 130

SELECTION_RULE = "greedy: select the option with the highest reported probability"
TIE_RULE = "exact ties go to the option listed first in the fixed option order; STOP is last"


@dataclass
class Config:
    prompt: str
    base_url: str
    model: str
    max_chars: int
    timeout: float
    max_seconds: float
    secrets: tuple = ()


@dataclass
class Result:
    reason: str
    exit_code: int
    answer: str
    requests: int
    elapsed: float
    error: str | None = None
    models: list = field(default_factory=list)


def _scrub(text, secrets):
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text


def _usage_text(usage):
    if not usage:
        return "usage unknown"
    return f"usage in={usage.get('input_tokens', '?')} out={usage.get('output_tokens', '?')}"


def run(config, post, trace, out, err, clock=time.monotonic):
    trace.write(
        "start",
        schema_version=SCHEMA_VERSION,
        timestamp=utc_now(),
        prompt=config.prompt,
        base_url=config.base_url,
        model=config.model,
        limits={"max_chars": config.max_chars, "timeout": config.timeout, "max_seconds": config.max_seconds},
        instructions=INSTRUCTIONS,
        options=mapping(),
        selection_rule=SELECTION_RULE,
        tie_rule=TIE_RULE,
        total_tolerance=TOTAL_TOLERANCE,
    )
    start = clock()
    answer = []
    requests = 0
    models = []
    reason = None
    exit_code = EXIT_ERROR
    error = None
    try:
        while True:
            elapsed = clock() - start
            if len(answer) >= config.max_chars:
                reason, exit_code = "max_chars", EXIT_LIMIT
                break
            remaining = config.max_seconds - elapsed
            if remaining <= 0:
                reason, exit_code = "max_seconds", EXIT_LIMIT
                break
            request_timeout = min(config.timeout, remaining)
            capped = request_timeout < config.timeout
            prefix = "".join(answer)
            body = build_request(config.model, config.prompt, prefix)
            sent = clock()
            requests += 1
            try:
                payload = post(body, request_timeout)
            except TransportError as failure:
                if failure.reason == "request_timeout" and capped:
                    reason, exit_code = "max_seconds", EXIT_LIMIT
                else:
                    reason, exit_code = failure.reason, EXIT_ERROR
                error = _scrub(str(failure), config.secrets)
                break
            request_seconds = clock() - sent
            try:
                choice = validate_response(payload)
            except ResponseError as failure:
                reason, exit_code = "invalid_response", EXIT_ERROR
                error = _scrub(str(failure), config.secrets)
                break
            models.append(choice.model)
            emitted = CHAR_BY_ID[choice.selected]
            elapsed = clock() - start
            trace.write(
                "step",
                step=requests,
                prefix=prefix,
                probabilities=choice.probabilities,
                server_choice=choice.server_choice,
                confidence=choice.confidence,
                selected=choice.selected,
                emitted=emitted,
                model=choice.model,
                request_seconds=round(request_seconds, 4),
                elapsed_seconds=round(elapsed, 4),
                usage=choice.usage,
            )
            err.write(
                f"step {requests} {choice.selected} p={choice.probabilities[choice.selected]:.3f} "
                f"{elapsed:.2f}s {_usage_text(choice.usage)}\n"
            )
            err.flush()
            if choice.selected == STOP:
                reason, exit_code = "stop", EXIT_STOP
                break
            answer.append(emitted)
            out.write(emitted)
            out.flush()
    except KeyboardInterrupt:
        reason, exit_code = "interrupted", EXIT_INTERRUPT
    elapsed = clock() - start
    text = "".join(answer)
    trace.write(
        "end",
        timestamp=utc_now(),
        reason=reason,
        exit_code=exit_code,
        answer=text,
        emitted_chars=len(text),
        requests=requests,
        elapsed_seconds=round(elapsed, 4),
        error=error,
    )
    return Result(reason, exit_code, text, requests, elapsed, error, models)
