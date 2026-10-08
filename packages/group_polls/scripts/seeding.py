"""Pure helpers for seed.py: validate seed questions, build poll documents."""

import secrets

# Same limits and code alphabet as the app and firestore.rules.
QUESTION_MAX = 120
ANSWER_MAX = 30
CODE_ALPHABET = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 12
SEED_CREATOR = "seed"
SEED_NAME = "¿Qué votáis?"


def load(data: dict) -> list[dict]:
    """The question list, or ValueError naming the first invalid entry."""
    questions = data["questions"]
    for i, q in enumerate(questions):
        for language in ("es", "en"):
            question, red, blue = q[language]
            if not 5 <= len(question) <= QUESTION_MAX:
                raise ValueError(f"#{i} {language}: question length")
            if not (0 < len(red) <= ANSWER_MAX and 0 < len(blue) <= ANSWER_MAX):
                raise ValueError(f"#{i} {language}: answer length")
            if red.lower() == blue.lower():
                raise ValueError(f"#{i} {language}: same answers")
    return questions


def next_batch(questions: list[dict], done: set[int], n: int) -> list[tuple[int, dict]]:
    """The next n questions, in file order, not published yet."""
    return [(i, q) for i, q in enumerate(questions) if i not in done][:n]


def new_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def poll_document(question: dict, language: str) -> tuple[str, dict]:
    """A public 7-day poll in the app's schema (createdAt is set by the caller)."""
    text, red, blue = question[language]
    return new_code(), {
        "visibility": "public",
        "question": text,
        "red": red,
        "blue": blue,
        "creatorId": SEED_CREATOR,
        "creatorName": SEED_NAME,
        "language": language,
        "durationDays": 7,
        "closedAt": None,
        "redVotes": 0,
        "blueVotes": 0,
        "reports": 0,
        "hidden": False,
    }
