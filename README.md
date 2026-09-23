# jev-ouija

Jev is marketed as a model that cannot hallucinate, because it only chooses from options you supply.

jev-ouija offers Jev the alphabet as options, one request per character. It appends each chosen character to the answer and asks again. The answer grows like a message on an ouija board.

Now Jev too can hallucinate. Or at least, it has the means.

```
            prompt + answer so far + 77 options
 jev-ouija ─────────────────────────────────────► Jev  POST /v1/systemone
     ▲                                             │
     │              probability per option         │
     └─────────────────────────────────────────────┘

 highest option is a character  →  print it, append it, ask again
 highest option is STOP         →  finish, exit 0
 character or time limit        →  finish, exit 2
```

---

## Install

jev-ouija needs Python 3.11 or later. It has no third-party dependencies.

```sh
python -m pip install -e .
```

This installs the `jev-ouija` command. On Windows, pip can put it in a user `Scripts` directory that is not on `PATH`. `python -m jev_ouija` works in every case.

---

## Usage

```sh
export JEV_API_KEY="<your TypeSafe API key>"
jev-ouija --base-url https://api.typesafe.ai --trace run.jsonl "Who discovered penicillin?"
```

| Input | Default | Behaviour |
|---|---|---|
| `prompt` | required | The question or instruction. It must not be empty. |
| `--base-url` | required | The API origin. jev-ouija appends `/v1/systemone`. It must be `http` or `https` and must not contain credentials. |
| `--model` | `jev-latest` | The model name sent in each request. |
| `--api-key-env` | `JEV_API_KEY` | The environment variable that holds the bearer token. |
| `--max-chars` | `300` | The maximum number of emitted characters. |
| `--timeout` | `30` | The timeout for one request, in seconds. |
| `--max-seconds` | `300` | The time limit for the whole run, in seconds. Each request timeout is capped at the time that remains. |
| `--trace` | none | A new UTF-8 JSONL trace file. If the file exists or cannot be created, jev-ouija exits before it sends a request. |

Each character costs one request. A 300-character answer is up to 300 requests.

---

## How generation works

Each request sends one `choice` question named `next_character`:

```json
{
  "model": "jev-latest",
  "state": {"prompt": "Who discovered penicillin?", "answer_so_far": "Alexander Fl"},
  "questions": {
    "next_character": {
      "type": "choice",
      "instructions": "Compose an answer to state.prompt by continuing state.answer_so_far. ...",
      "criteria": {"LOWER_A": "Append lowercase a", "...": "...", "STOP": "End the answer without appending anything"}
    }
  }
}
```

The 77 options are, in this fixed order:

- `LOWER_A` to `LOWER_Z`, `UPPER_A` to `UPPER_Z` and `DIGIT_0` to `DIGIT_9`.
- `SPACE` and `NEWLINE`.
- Twelve punctuation marks: `. , ! ? : ; ' " - ( ) /`.
- `STOP`, which emits nothing.

jev-ouija checks every response before it uses it:

- The probability keys must equal the 77 option IDs exactly.
- Each value must be a finite number from 0 to 1.
- The values must total 1, within `1e-3`.
- Jev's `choice` must be one of the options with the highest probability.

jev-ouija selects the option with the highest probability. When options tie exactly, the one listed first wins, so any character beats STOP in a tie. Jev's own choice is kept in the trace.

A response that fails a check ends the run with exit 1. jev-ouija does not retry, repair a response, force a minimum length or suppress STOP.

---

## Outputs

- **stdout** receives only the answer characters. Each character is flushed as it arrives.
- **stderr** receives one progress line per request, then a summary line.

```
step 1 UPPER_A p=0.910 1.84s usage in=1740 out=12
```

- **The trace file** has one JSON object per line:

| Event | Fields |
|---|---|
| `start` | `schema_version`, `timestamp`, `prompt`, `base_url`, `model`, `limits`, `instructions`, `options`, `selection_rule`, `tie_rule`, `total_tolerance` |
| `step` | `step`, `prefix`, `probabilities`, `server_choice`, `confidence`, `selected`, `emitted`, `model`, `request_seconds`, `elapsed_seconds`, `usage` |
| `end` | `timestamp`, `reason`, `exit_code`, `answer`, `emitted_chars`, `requests`, `elapsed_seconds`, `error` |

The trace contains your prompt and the generated text. The API key is never written to stdout, stderr or the trace. If it appears in an error message, jev-ouija replaces it with `***`.

On an error or Ctrl+C, the characters already printed and the trace lines already written stay in place.

---

## Exit codes

| Code | Reason | Meaning |
|---|---|---|
| 0 | `stop` | Jev selected STOP. |
| 2 | `max_chars` | The character limit was reached. No further request is sent. |
| 2 | `max_seconds` | The whole-run time limit was reached. |
| 1 | `http_error`, `transport_error`, `request_timeout`, `invalid_response` | A configuration, HTTP, network or response error. |
| 130 | `interrupted` | Ctrl+C. |

A limit is a truncation. It is not an answer that Jev completed.

---

## Tests

```sh
python -m unittest discover -s tests
```

The 28 tests run against a local fake Jev endpoint. They need no network and no credentials.

---

## How to read a result

- A false factual claim in a trace is evidence of hallucination.
- Gibberish, an error or a request to write fiction is not.
- Jev's option probabilities are choice scores. They are not next-character language-model probabilities.
- A fluent answer or a high probability does not prove that the answer is correct.

---

## Licence

Copyright (c) 2026 Eren Sinecan. All rights reserved. See [LICENSE](LICENSE).
