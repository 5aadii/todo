import re

STOP_WORDS = frozenset([
    "a", "an", "the", "is", "are", "was", "were", "to", "of", "in", "on",
    "at", "for", "and", "or", "but", "with", "this", "that", "it", "as",
    "be", "by", "from", "up", "down", "so", "my", "me", "i"
])
# "not", "no", "never", "don't" intentionally excluded — negation matters.


def sanitize_text(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9\s'/:.-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def remove_stop_words(text: str) -> str:
    return " ".join(w for w in text.split() if w not in STOP_WORDS)


def clean_text(raw_text: str) -> dict:
    sanitized = sanitize_text(raw_text)
    return {
        "raw_task": raw_text,
        "sanitized_task": sanitized,
        "token_ready_text": remove_stop_words(sanitized),
    }
