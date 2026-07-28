import sys
import os
from datetime import date
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.task_ops import delete_task, mark_completed, mark_reopened, edit_task, is_duplicate, is_overdue
from cleaning import clean_text


def make_task(task_id, raw="sample task", done=False, due_date=None):
    return {
        "task_id": task_id,
        "raw": raw,
        "sanitized": raw.lower(),
        "token_ready": raw.lower(),
        "done": done,
        "category": "work",
        "priority": "medium",
        "due_date": due_date,
        "completed_at": None,
    }


def test_deleting_one_task_does_not_affect_another():
    tasks = [make_task("a"), make_task("b"), make_task("c")]
    result = delete_task(tasks, "b")
    ids = [t["task_id"] for t in result]
    assert ids == ["a", "c"]


def test_editing_task_preserves_id():
    task = make_task("keep-this-id", raw="old text")
    edit_task(task, "new text", "personal", "high", clean_text)
    assert task["task_id"] == "keep-this-id"
    assert task["raw"] == "new text"
    assert task["category"] == "personal"
    assert task["priority"] == "high"


def test_completing_task_adds_completion_timestamp():
    task = make_task("x")
    mark_completed(task)
    assert task["done"] is True
    assert task["completed_at"] is not None


def test_reopening_task_removes_completion_timestamp():
    task = make_task("x", done=True)
    mark_completed(task)
    mark_reopened(task)
    assert task["done"] is False
    assert task["completed_at"] is None


def test_is_duplicate_detects_matching_sanitized_text():
    tasks = [make_task("a", raw="buy milk")]
    assert is_duplicate(tasks, "buy milk") is True
    assert is_duplicate(tasks, "buy bread") is False


def test_overdue_task_detected_correctly():
    task = make_task("x", due_date=date(2020, 1, 1))
    assert is_overdue(task, date(2026, 1, 1)) is True


def test_completed_task_is_never_overdue():
    task = make_task("x", done=True, due_date=date(2020, 1, 1))
    assert is_overdue(task, date(2026, 1, 1)) is False


def test_task_with_no_due_date_is_not_overdue():
    task = make_task("x", due_date=None)
    assert is_overdue(task, date(2026, 1, 1)) is False
