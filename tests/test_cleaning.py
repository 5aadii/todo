import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cleaning import clean_text, sanitize_text, remove_stop_words


def test_buy_milk_sanitized():
    result = clean_text("  Buy MILK!!! 🥛  ")
    assert result["sanitized_task"] == "buy milk"


def test_negation_preserved():
    result = clean_text("Do NOT cancel the 5 PM meeting.")
    assert "not" in result["sanitized_task"]
    assert "5" in result["sanitized_task"]
    assert "pm" in result["sanitized_task"]


def test_repeated_spaces_collapsed():
    result = clean_text("Call    Ahmed      tomorrow")
    assert result["sanitized_task"] == "call ahmed tomorrow"


def test_emoji_only_task_is_empty():
    result = clean_text("🎉🎉🎉")
    assert result["sanitized_task"] == ""


def test_stop_words_removed_but_not_negation():
    result = remove_stop_words("do not cancel the meeting")
    assert "not" in result
    assert "the" not in result
