import string

QUESTION_ID = "next_character"
STOP = "STOP"

INSTRUCTIONS = (
    "Compose an answer to state.prompt by continuing state.answer_so_far. "
    "Select exactly the next character to append, considering the entire prefix. "
    "Select STOP when the answer is complete. "
    "You may express uncertainty or reject a false premise in the answer. "
    "Use only the available characters."
)

PUNCTUATION = [
    ("PERIOD", ".", "period"),
    ("COMMA", ",", "comma"),
    ("EXCLAMATION", "!", "exclamation mark"),
    ("QUESTION", "?", "question mark"),
    ("COLON", ":", "colon"),
    ("SEMICOLON", ";", "semicolon"),
    ("APOSTROPHE", "'", "apostrophe"),
    ("QUOTE", '"', "double quotation mark"),
    ("HYPHEN", "-", "hyphen"),
    ("LEFT_PAREN", "(", "opening parenthesis"),
    ("RIGHT_PAREN", ")", "closing parenthesis"),
    ("SLASH", "/", "slash"),
]


def _build():
    options = []
    for c in string.ascii_lowercase:
        options.append((f"LOWER_{c.upper()}", c, f"Append lowercase {c}"))
    for c in string.ascii_uppercase:
        options.append((f"UPPER_{c}", c, f"Append uppercase {c}"))
    for c in string.digits:
        options.append((f"DIGIT_{c}", c, f"Append digit {c}"))
    options.append(("SPACE", " ", "Append one space"))
    options.append(("NEWLINE", "\n", "Append one line break"))
    for option_id, char, name in PUNCTUATION:
        options.append((option_id, char, f"Append {name} {char}"))
    options.append((STOP, None, "End the answer without appending anything"))
    return tuple(options)


OPTIONS = _build()
OPTION_IDS = tuple(option_id for option_id, _, _ in OPTIONS)
CHAR_BY_ID = {option_id: char for option_id, char, _ in OPTIONS}
ORDER = {option_id: index for index, option_id in enumerate(OPTION_IDS)}


def criteria():
    return {option_id: description for option_id, _, description in OPTIONS}


def mapping():
    return [{"id": option_id, "char": char} for option_id, char, _ in OPTIONS]


def build_request(model, prompt, answer_so_far):
    return {
        "model": model,
        "state": {"prompt": prompt, "answer_so_far": answer_so_far},
        "questions": {
            QUESTION_ID: {
                "type": "choice",
                "instructions": INSTRUCTIONS,
                "criteria": criteria(),
            }
        },
    }
