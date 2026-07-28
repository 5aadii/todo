import sys
import os
import json
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.openrouter_client import validate_ai_response, extract_json_response, validate_chat_draft


# --- validate_ai_response ---

def test_invalid_category_becomes_other():
    result = validate_ai_response({"category": "not_a_real_category"})
    assert result["category"] == "other"


def test_invalid_priority_becomes_medium():
    result = validate_ai_response({"priority": "urgent"})
    assert result["priority"] == "medium"


def test_duration_as_string_is_converted():
    result = validate_ai_response({"estimated_minutes": "45"})
    assert result["estimated_minutes"] == 45


def test_duration_above_max_is_clamped():
    result = validate_ai_response({"estimated_minutes": 999})
    assert result["estimated_minutes"] == 480


def test_duration_non_numeric_falls_back_to_default():
    result = validate_ai_response({"estimated_minutes": "not a number"})
    assert result["estimated_minutes"] == 30


def test_tags_over_three_are_truncated():
    result = validate_ai_response({"tags": ["a", "b", "c", "d", "e"]})
    assert len(result["tags"]) == 3


def test_missing_subtasks_defaults_to_empty_list():
    result = validate_ai_response({})
    assert result["subtasks"] == []


def test_subtasks_over_three_are_truncated():
    result = validate_ai_response({"subtasks": ["1", "2", "3", "4"]})
    assert len(result["subtasks"]) == 3


# --- extract_json_response ---

def test_json_inside_code_fence_is_parsed():
    content = '```json\n{"category": "work"}\n```'
    result = extract_json_response(content)
    assert result["category"] == "work"


def test_plain_json_without_fence_is_parsed():
    content = '{"category": "personal"}'
    result = extract_json_response(content)
    assert result["category"] == "personal"


def test_invalid_json_raises_decode_error():
    content = "this is not json at all"
    with pytest.raises(json.JSONDecodeError):
        extract_json_response(content)


def test_empty_response_raises_decode_error():
    content = ""
    with pytest.raises(json.JSONDecodeError):
        extract_json_response(content)


# --- validate_quick_add ---

def test_quick_add_valid_date_is_parsed():
    result = validate_chat_draft({"task_text": "cook dinner", "due_date": "2026-07-28"}, "original")
    assert str(result["due_date"]) == "2026-07-28"


def test_quick_add_invalid_date_falls_back_to_none():
    result = validate_chat_draft({"task_text": "cook dinner", "due_date": "not a date"}, "original")
    assert result["due_date"] is None


def test_quick_add_missing_task_text_falls_back_to_original():
    result = validate_chat_draft({}, "cook dinner tomorrow")
    assert result["task_text"] == "cook dinner tomorrow"


def test_quick_add_valid_time_is_kept():
    result = validate_chat_draft({"due_time": "20:30"}, "original")
    assert result["due_time"] == "20:30"


def test_quick_add_malformed_time_becomes_none():
    result = validate_chat_draft({"due_time": "8:30pm"}, "original")
    assert result["due_time"] is None


def test_quick_add_invalid_category_becomes_other():
    result = validate_chat_draft({"category": "nonsense"}, "original")
    assert result["category"] == "other"
