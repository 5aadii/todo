import json
import os
from datetime import datetime, date

STORAGE_FILE = "tasks_data.json"


def _serialize_task(task: dict) -> dict:
    data = dict(task)
    for field in ("due_date", "created_at", "completed_at"):
        value = data.get(field)
        if isinstance(value, (datetime, date)):
            data[field] = value.isoformat()
    return data


def _deserialize_task(data: dict) -> dict:
    task = dict(data)
    if task.get("due_date"):
        task["due_date"] = date.fromisoformat(task["due_date"])
    if task.get("created_at"):
        task["created_at"] = datetime.fromisoformat(task["created_at"])
    if task.get("completed_at"):
        task["completed_at"] = datetime.fromisoformat(task["completed_at"])
    return task


def save_tasks(tasks: list) -> None:
    """Write all tasks to a local JSON file. Fails silently (best-effort)."""
    try:
        with open(STORAGE_FILE, "w", encoding="utf-8") as f:
            json.dump([_serialize_task(t) for t in tasks], f, indent=2)
    except OSError:
        pass


def load_tasks() -> list:
    """Load tasks from the local JSON file. Returns [] if missing or corrupt."""
    if not os.path.exists(STORAGE_FILE):
        return []
    try:
        with open(STORAGE_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return [_deserialize_task(t) for t in raw]
    except (OSError, json.JSONDecodeError):
        return []
