from datetime import datetime, date

PRIORITY_ORDER = {"low": 0, "medium": 1, "high": 2}


def filter_tasks(tasks: list, status="pending", due_before_date=None, due_before_time=None) -> list:
    if isinstance(due_before_date, str):
        due_before_date = date.fromisoformat(due_before_date)

    result = []
    for t in tasks:
        if status == "pending" and t["done"]:
            continue
        if status == "completed" and not t["done"]:
            continue
        if due_before_date:
            if not t.get("due_date"):
                continue
            if t["due_date"] > due_before_date:
                continue
            if t["due_date"] == due_before_date and due_before_time and t.get("due_time"):
                if t["due_time"] > due_before_time:
                    continue
        result.append(t)
    return result


def sort_by_priority_desc(tasks: list) -> list:
    return sorted(tasks, key=lambda t: PRIORITY_ORDER.get(t["priority"], 0), reverse=True)


def delete_task(tasks: list, task_id: str) -> list:
    """Remove one task by ID. Must not affect any other task."""
    return [t for t in tasks if t["task_id"] != task_id]


def mark_completed(task: dict) -> dict:
    task["done"] = True
    task["completed_at"] = datetime.now()
    return task


def mark_reopened(task: dict) -> dict:
    task["done"] = False
    task["completed_at"] = None
    return task


def edit_task(task: dict, new_raw: str, new_category: str, new_priority: str, clean_fn) -> dict:
    """Update a task's text/category/priority in place. task_id is never touched."""
    cleaned = clean_fn(new_raw)
    task["raw"] = new_raw
    task["sanitized"] = cleaned["sanitized_task"]
    task["token_ready"] = cleaned["token_ready_text"]
    task["category"] = new_category
    task["priority"] = new_priority
    return task


def is_duplicate(tasks: list, sanitized_text: str) -> bool:
    return any(t["sanitized"] == sanitized_text for t in tasks)


def is_overdue(task: dict, today) -> bool:
    if task["done"] or not task.get("due_date"):
        return False
    return task["due_date"] < today


