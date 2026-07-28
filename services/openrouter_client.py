import requests
import streamlit as st
import json

ALLOWED_CATEGORIES = {
    "work", "study", "personal", "health", "finance",
    "shopping", "household", "communication", "travel", "other"
}
ALLOWED_PRIORITIES = {"low", "medium", "high"}


def get_api_key():
    return st.secrets.get("OPENROUTER_API_KEY")


def get_model_name():
    return st.secrets.get("OPENROUTER_MODEL")


def extract_json_response(content: str) -> dict:
    cleaned_content = content.strip()
    if cleaned_content.startswith("```"):
        cleaned_content = cleaned_content.replace("```json", "")
        cleaned_content = cleaned_content.replace("```", "")
        cleaned_content = cleaned_content.strip()
    return json.loads(cleaned_content)


def validate_ai_response(data: dict) -> dict:
    category = data.get("category")
    if category not in ALLOWED_CATEGORIES:
        category = "other"

    priority = data.get("priority")
    if priority not in ALLOWED_PRIORITIES:
        priority = "medium"

    try:
        minutes = int(data.get("estimated_minutes", 30))
    except (ValueError, TypeError):
        minutes = 30
    minutes = max(5, min(480, minutes))

    tags = data.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    tags = [t for t in tags if isinstance(t, str) and t.strip()][:3]

    subtasks = data.get("subtasks", [])
    if not isinstance(subtasks, list):
        subtasks = []
    subtasks = [s for s in subtasks if isinstance(s, str) and s.strip()][:3]

    reason = data.get("reason", "")
    if not isinstance(reason, str):
        reason = ""
    reason = reason[:300]

    rewritten = data.get("rewritten_task", "")
    if not isinstance(rewritten, str):
        rewritten = ""

    return {
        "rewritten_task": rewritten,
        "category": category,
        "priority": priority,
        "estimated_minutes": minutes,
        "tags": tags,
        "subtasks": subtasks,
        "reason": reason,
    }


def analyse_task(task_text: str) -> dict:
    api_key = get_api_key()
    model_name = get_model_name()

    if not api_key or not model_name:
        return {
            "success": False,
            "error_type": "missing_key",
            "message": "AI analysis was unavailable. The task was saved without AI metadata."
        }

    from prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_PROMPT_TEMPLATE.format(sanitized_task=task_text)}
    ]

    response = None
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "X-OpenRouter-Title": "AI Task Coach"
            },
            json={
                "model": model_name,
                "messages": messages,
                "temperature": 0.1,
                "max_tokens": 2000,
                "provider": {"sort": "throughput"}
            },
            timeout=30
        )
        resp_json = response.json()
        msg = resp_json["choices"][0]["message"]
        print("FINISH REASON:", resp_json["choices"][0].get("finish_reason"))
        print("CONTENT LENGTH:", len(msg.get("content") or ""))
        print("CONTENT:", repr(msg.get("content"))[:500])
        response.raise_for_status()

        content = response.json()["choices"][0]["message"].get("content")
        if not content:
            raise KeyError("empty content")
        parsed = extract_json_response(content)
        validated = validate_ai_response(parsed)

        return {
            "success": True,
            "data": validated
        }

    except requests.exceptions.Timeout:
        return {"success": False, "error_type": "timeout", "message": "AI analysis was unavailable. The task was saved without AI metadata."}

    except requests.exceptions.HTTPError:
        return {"success": False, "error_type": "http_error", "message": "AI analysis was unavailable. The task was saved without AI metadata."}

    except requests.exceptions.RequestException:
        return {"success": False, "error_type": "connection_error", "message": "AI analysis was unavailable. The task was saved without AI metadata."}

    except json.JSONDecodeError:
        return {"success": False, "error_type": "invalid_json", "message": "AI analysis was unavailable. The task was saved without AI metadata."}

    except KeyError:
        error_detail = ""
        if response is not None:
            try:
                error_detail = f" ({response.json().get('error', {}).get('message', '')})"
            except Exception:
                pass
        return {"success": False, "error_type": "unexpected_response", "message": f"Chat is unavailable — unexpected response.{error_detail}"}

def validate_chat_draft(data: dict, fallback_text: str = "") -> dict:
    import re
    from datetime import date

    if not isinstance(data, dict):
        data = {}

    task_text = data.get("task_text")
    if not isinstance(task_text, str) or not task_text.strip():
        task_text = fallback_text

    category = data.get("category")
    if category not in ALLOWED_CATEGORIES:
        category = "other"

    priority = data.get("priority")
    if priority not in ALLOWED_PRIORITIES:
        priority = "medium"

    due_date = data.get("due_date")
    if isinstance(due_date, str):
        try:
            due_date = date.fromisoformat(due_date)
        except ValueError:
            due_date = None
    else:
        due_date = None

    due_time = data.get("due_time")
    if not (isinstance(due_time, str) and re.fullmatch(r"[0-2]\d:[0-5]\d", due_time)):
        due_time = None

    try:
        minutes = int(data.get("estimated_minutes", 30))
    except (ValueError, TypeError):
        minutes = 30
    minutes = max(5, min(480, minutes))

    tags = data.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    tags = [t for t in tags if isinstance(t, str) and t.strip()][:3]

    subtasks = data.get("subtasks", [])
    if not isinstance(subtasks, list):
        subtasks = []
    subtasks = [s for s in subtasks if isinstance(s, str) and s.strip()][:3]

    reason = data.get("reason", "")
    if not isinstance(reason, str):
        reason = ""
    reason = reason[:300]

    return {
        "task_text": task_text,
        "category": category,
        "priority": priority,
        "due_date": due_date,
        "due_time": due_time,
        "estimated_minutes": minutes,
        "tags": tags,
        "subtasks": subtasks,
        "reason": reason,
    }
def chat_task_turn(user_text: str, current_draft: dict, current_multi_draft: list, pending_tasks: list) -> dict:
    from datetime import date

    api_key = get_api_key()
    model_name = get_model_name()

    if not api_key or not model_name:
        return {
            "success": False,
            "error_type": "missing_key",
            "message": "Chat is unavailable — no API key configured."
        }

    from prompts import CHAT_SYSTEM_TEMPLATE, CHAT_CONTEXT_TEMPLATE

    draft_for_prompt = None
    if current_draft:
        draft_for_prompt = dict(current_draft)
        if draft_for_prompt.get("due_date"):
            draft_for_prompt["due_date"] = str(draft_for_prompt["due_date"])

    multi_draft_for_prompt = None
    if current_multi_draft:
        multi_draft_for_prompt = []
        for d in current_multi_draft:
            d = dict(d)
            if d.get("due_date"):
                d["due_date"] = str(d["due_date"])
            multi_draft_for_prompt.append(d)

    task_list = "\n".join(
        f"- {t['task_id']} | {t['final_task_text'] or t['raw']} | "
        f"due {t['due_date'] or 'none'} {t['due_time'] or ''} | {t['priority']}"
        for t in pending_tasks
    ) or "(no pending tasks)"

    messages = [
        {"role": "system", "content": CHAT_SYSTEM_TEMPLATE.format(today=date.today().isoformat())},
        {"role": "user", "content": CHAT_CONTEXT_TEMPLATE.format(
            draft_json=json.dumps(draft_for_prompt),
            multi_draft_json=json.dumps(multi_draft_for_prompt),
            task_list=task_list, text=user_text
        )}
    ]

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "X-OpenRouter-Title": "AI Task Coach"
            },
            json={"model": model_name, "messages": messages, "temperature": 0.2, "max_tokens": 2000, "provider": {"sort": "throughput"}},
            timeout=30
        )
        resp_json = response.json()
        msg = resp_json["choices"][0]["message"]
        print("FINISH REASON:", resp_json["choices"][0].get("finish_reason"))
        print("CONTENT LENGTH:", len(msg.get("content") or ""))
        print("CONTENT:", repr(msg.get("content"))[:500])
        response.raise_for_status()


        content = response.json()["choices"][0]["message"].get("content")
        if not content:
            raise KeyError("empty content")
        parsed = extract_json_response(content)

        reply = parsed.get("reply")
        if not isinstance(reply, str) or not reply.strip():
            reply = "Sorry, I didn't quite catch that — could you say it again?"

        action = parsed.get("action")
        valid_actions = ("chat", "propose", "confirmed_create", "propose_multi",
                          "confirmed_create_multi", "query", "complete", "complete_multi")
        if action not in valid_actions:
            action = "chat"

        draft = None
        if action in ("propose", "confirmed_create"):
            draft = validate_chat_draft(parsed.get("draft"), fallback_text=user_text)

        drafts = None
        if action in ("propose_multi", "confirmed_create_multi"):
            raw_drafts = parsed.get("drafts") or []
            drafts = [validate_chat_draft(d, fallback_text=user_text) for d in raw_drafts if d]

        query_filter = None
        if action == "query":
            qf = parsed.get("query_filter") or {}
            query_filter = {
                "due_before_date": qf.get("due_before_date"),
                "due_before_time": qf.get("due_before_time"),
                "status": qf.get("status") if qf.get("status") in ("pending", "completed", "all") else "pending",
            }

        complete_task_id = None
        if action == "complete":
            complete_task_id = parsed.get("complete_task_id")

        complete_task_ids = None
        if action == "complete_multi":
            ids = parsed.get("complete_task_ids") or []
            complete_task_ids = [i for i in ids if isinstance(i, str)]

        return {
            "success": True, "reply": reply, "action": action,
            "draft": draft, "drafts": drafts,
            "query_filter": query_filter,
            "complete_task_id": complete_task_id,
            "complete_task_ids": complete_task_ids,
        }

    except requests.exceptions.Timeout:
        return {"success": False, "error_type": "timeout", "message": "Chat is unavailable — request timed out."}
    except requests.exceptions.HTTPError:
        return {"success": False, "error_type": "http_error", "message": "Chat is unavailable — API error."}
    except requests.exceptions.RequestException:
        return {"success": False, "error_type": "connection_error", "message": "Chat is unavailable — connection issue."}
    except json.JSONDecodeError:
        return {"success": False, "error_type": "invalid_json", "message": "Chat is unavailable — invalid response."}
    except KeyError:
        return {"success": False, "error_type": "unexpected_response", "message": "Chat is unavailable — unexpected response."}


def get_mood_picks(pending_tasks: list, mood: str, available_time: str) -> dict:
    api_key = get_api_key()
    model_name = get_model_name()

    if not api_key or not model_name:
        return {"success": False, "error_type": "missing_key", "message": "Mood picker unavailable — no API key configured."}

    from prompts import MOOD_SYSTEM_PROMPT, MOOD_USER_TEMPLATE

    valid_ids = {t["task_id"] for t in pending_tasks}

    task_lines = "\n".join(
        f"- task_id: {t['task_id']}, task: {t['final_task_text'] or t['raw']}, "
        f"priority: {t['final_priority'] or t['priority']}, "
        f"estimated_minutes: {t['final_estimated_minutes'] or 'unknown'}, due: {t['due_date']}"
        for t in pending_tasks
    ) or "(no pending tasks)"

    messages = [
        {"role": "system", "content": MOOD_SYSTEM_PROMPT},
        {"role": "user", "content": MOOD_USER_TEMPLATE.format(mood=mood, available_time=available_time, task_list=task_lines)}
    ]

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "X-OpenRouter-Title": "AI Task Coach"},
            json={"model": model_name, "messages": messages, "temperature": 0.2, "max_tokens": 2000},
            timeout=30
        )
        resp_json = response.json()
        msg = resp_json["choices"][0]["message"]
        print("FINISH REASON:", resp_json["choices"][0].get("finish_reason"))
        print("CONTENT LENGTH:", len(msg.get("content") or ""))
        print("CONTENT:", repr(msg.get("content"))[:500])
        response.raise_for_status()
        

        content = response.json()["choices"][0]["message"].get("content")
        if not content:
            raise KeyError("empty content")
        parsed = extract_json_response(content)

        raw_picks = parsed.get("picks", [])
        if not isinstance(raw_picks, list):
            raw_picks = []

        clean_picks = [
            item for item in raw_picks
            if isinstance(item, dict) and item.get("task_id") in valid_ids
        ][:3]

        summary = parsed.get("summary", "")
        if not isinstance(summary, str):
            summary = ""

        return {"success": True, "data": {"picks": clean_picks, "summary": summary}}

    except requests.exceptions.Timeout:
        return {"success": False, "error_type": "timeout", "message": "Mood picker unavailable — request timed out."}
    except requests.exceptions.HTTPError:
        return {"success": False, "error_type": "http_error", "message": "Mood picker unavailable — API error."}
    except requests.exceptions.RequestException:
        return {"success": False, "error_type": "connection_error", "message": "Mood picker unavailable — connection issue."}
    except json.JSONDecodeError:
        return {"success": False, "error_type": "invalid_json", "message": "Mood picker unavailable — invalid response."}
    except KeyError:
        return {"success": False, "error_type": "unexpected_response", "message": "Mood picker unavailable — unexpected response."}


def suggest_reschedule(task: dict) -> dict:
    api_key = get_api_key()
    model_name = get_model_name()

    if not api_key or not model_name:
        return {"success": False, "error_type": "missing_key", "message": "Reschedule unavailable — no API key configured."}

    from prompts import RESCHEDULE_SYSTEM_PROMPT, RESCHEDULE_USER_TEMPLATE
    from datetime import date

    messages = [
        {"role": "system", "content": RESCHEDULE_SYSTEM_PROMPT.format(today=date.today().isoformat())},
        {"role": "user", "content": RESCHEDULE_USER_TEMPLATE.format(
            task_text=task["final_task_text"] or task["raw"],
            priority=task["priority"],
            due_date=task["due_date"],
            estimated_minutes=task.get("final_estimated_minutes") or task.get("ai_estimated_minutes") or "unknown",
        )}
    ]

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "X-OpenRouter-Title": "AI Task Coach"
            },
            json={"model": model_name, "messages": messages, "temperature": 0.2, "max_tokens": 2000, "provider": {"sort": "throughput"}},
            timeout=30
        )
        resp_json = response.json()
        msg = resp_json["choices"][0]["message"]
        print("FINISH REASON:", resp_json["choices"][0].get("finish_reason"))
        print("CONTENT LENGTH:", len(msg.get("content") or ""))
        print("CONTENT:", repr(msg.get("content"))[:500])
        response.raise_for_status()
       

        content = response.json()["choices"][0]["message"].get("content")
        if not content:
            raise KeyError("empty content")
        parsed = extract_json_response(content)

        try:
            new_due_date = date.fromisoformat(parsed.get("new_due_date"))
        except (TypeError, ValueError):
            new_due_date = None

        if not new_due_date:
            return {"success": False, "error_type": "invalid_response", "message": "Reschedule unavailable — invalid date returned."}

        reason = parsed.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            reason = "Rescheduled based on priority."

        return {"success": True, "new_due_date": new_due_date, "reason": reason}

    except requests.exceptions.Timeout:
        return {"success": False, "error_type": "timeout", "message": "Reschedule unavailable — request timed out."}
    except requests.exceptions.HTTPError:
        return {"success": False, "error_type": "http_error", "message": "Reschedule unavailable — API error."}
    except requests.exceptions.RequestException:
        return {"success": False, "error_type": "connection_error", "message": "Reschedule unavailable — connection issue."}
    except json.JSONDecodeError:
        return {"success": False, "error_type": "invalid_json", "message": "Reschedule unavailable — invalid response."}
    except KeyError:
        return {"success": False, "error_type": "unexpected_response", "message": "Reschedule unavailable — unexpected response."}




def get_focus_plan(pending_tasks: list) -> dict:
    api_key = get_api_key()
    model_name = get_model_name()

    if not api_key or not model_name:
        return {
            "success": False,
            "error_type": "missing_key",
            "message": "Focus plan unavailable — no API key configured."
        }

    from prompts import FOCUS_PLAN_SYSTEM_PROMPT, FOCUS_PLAN_USER_TEMPLATE

    valid_ids = {t["task_id"] for t in pending_tasks}

    task_lines = "\n".join(
        f"- task_id: {t['task_id']}, task: {t['final_task_text'] or t['raw']}, "
        f"priority: {t['final_priority'] or t['priority']}, "
        f"due: {t['due_date']}, estimated_minutes: {t['final_estimated_minutes'] or 'unknown'}"
        for t in pending_tasks
    )

    messages = [
        {"role": "system", "content": FOCUS_PLAN_SYSTEM_PROMPT},
        {"role": "user", "content": FOCUS_PLAN_USER_TEMPLATE.format(task_list=task_lines)}
    ]

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "X-OpenRouter-Title": "AI Task Coach"
            },
            json={"model": model_name, "messages": messages, "temperature": 0.1, "max_tokens": 2000, "provider": {"sort": "throughput"}},
            timeout=30
        )
        resp_json = response.json()
        msg = resp_json["choices"][0]["message"]
        print("FINISH REASON:", resp_json["choices"][0].get("finish_reason"))
        print("CONTENT LENGTH:", len(msg.get("content") or ""))
        print("CONTENT:", repr(msg.get("content"))[:500])

        response.raise_for_status()

        content = response.json()["choices"][0]["message"].get("content")
        if not content:
            raise KeyError("empty content")
        parsed = extract_json_response(content)

        raw_plan = parsed.get("focus_plan", [])
        if not isinstance(raw_plan, list):
            raw_plan = []

        # Only keep entries whose task_id actually exists — ignore invented ones
        clean_plan = [
            item for item in raw_plan
            if isinstance(item, dict) and item.get("task_id") in valid_ids
        ][:3]

        summary = parsed.get("summary", "")
        if not isinstance(summary, str):
            summary = ""

        return {
            "success": True,
            "data": {"focus_plan": clean_plan, "summary": summary}
        }

    except requests.exceptions.Timeout:
        return {"success": False, "error_type": "timeout", "message": "Focus plan unavailable — request timed out."}
    except requests.exceptions.HTTPError:
        return {"success": False, "error_type": "http_error", "message": "Focus plan unavailable — API error."}
    except requests.exceptions.RequestException:
        return {"success": False, "error_type": "connection_error", "message": "Focus plan unavailable — connection issue."}
    except json.JSONDecodeError:
        return {"success": False, "error_type": "invalid_json", "message": "Focus plan unavailable — invalid response."}
    except KeyError:
        return {"success": False, "error_type": "unexpected_response", "message": "Focus plan unavailable — unexpected response."}
