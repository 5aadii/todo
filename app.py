import streamlit as st
import pandas as pd
import re
from datetime import datetime, date
from uuid import uuid4
from streamlit_calendar import calendar

from cleaning import clean_text
from services.openrouter_client import analyse_task, get_focus_plan, chat_task_turn, suggest_reschedule, get_mood_picks, get_api_key, get_model_name, ALLOWED_CATEGORIES
from services.storage_service import save_tasks, load_tasks
from utils.task_ops import delete_task, mark_completed, mark_reopened, edit_task, is_duplicate, is_overdue, filter_tasks, sort_by_priority_desc

CATEGORIES = ["work", "study", "personal", "health", "finance", "shopping", "household", "other"]
PRIORITIES = ["low", "medium", "high"]
PRIORITY_COLORS = {"high": "#e74c3c", "medium": "#f39c12", "low": "#27ae60"}

def priority_badge(priority):
    color = PRIORITY_COLORS.get(priority, "#888")
    return f'<span style="background-color:{color}22; color:{color}; padding:2px 8px; border-radius:12px; font-size:0.8em; font-weight:600;">{priority.upper()}</span>'

def highlight_task_text(task):
    text = task["raw"]
    tags = task.get("final_tags") or task.get("ai_tags") or []
    for tag in tags:
        tag = (tag or "").strip()
        if not tag:
            continue
        pattern = re.compile(rf"\b({re.escape(tag)})\b", re.IGNORECASE)
        highlighted, count = pattern.subn(
            r'<mark style="background-color:#6C5CE7; color:white; padding:0 3px; border-radius:4px;">\1</mark>',
            text, count=1
        )
        if count:
            return highlighted
    return text

st.set_page_config(page_title="AI Task Coach", layout="wide")
st.title("AI Task Coach")
st.caption("A task manager that also collects human-reviewed AI training data.")

AI_CONFIGURED = bool(get_api_key() and get_model_name())
if not AI_CONFIGURED:
    st.info("No OpenRouter API key configured — AI features are disabled. Add one to `.streamlit/secrets.toml` to enable them.")


# --- Session state setup (loads from disk on first run) ---
def initialize_session_state():
    defaults = {
        "tasks": load_tasks(),
        "editing_task_id": None,
        "ai_cache": {},
        "focus_plan": None,
        "confirm_clear": False,
        "chat_messages": [],
        "chat_draft": None,
        "reschedule_suggestions": {},
        "mood_picks": None,
        "chat_multi_draft": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

initialize_session_state()


def new_task_dict(raw_text, category, priority, due_date, due_time=None):
    cleaned = clean_text(raw_text)
    return {
        "raw": cleaned["raw_task"],
        "sanitized": cleaned["sanitized_task"],
        "token_ready": cleaned["token_ready_text"],
        "done": False,
        "task_id": str(uuid4()),
        "category": category,
        "priority": priority,
        "due_date": due_date,
        "due_time": due_time,
        "created_at": datetime.now(),
        "completed_at": None,
        "ai_status": "not_analyzed",
        "ai_last_error": None,
        "ai_rewritten_task": None,
        "ai_category": None,
        "ai_priority": None,
        "ai_estimated_minutes": None,
        "ai_tags": [],
        "ai_subtasks": [],
        "ai_reason": None,
        "ai_accepted": None,
        "human_edited": False,
        "human_verified": False,
        "final_task_text": None,
        "final_category": None,
        "final_priority": None,
        "final_estimated_minutes": None,
        "final_tags": None,
        "final_subtasks": None,
    }


def run_ai_analysis(task, force=False):
    cache_key = task["sanitized"].strip().lower()

    if not force and cache_key in st.session_state.ai_cache:
        result = st.session_state.ai_cache[cache_key]
    else:
        with st.spinner("Analysing task..."):
            result = analyse_task(task["sanitized"])
        st.session_state.ai_cache[cache_key] = result

    if result["success"]:
        data = result["data"]
        task["ai_status"] = "success"
        task["ai_rewritten_task"] = data.get("rewritten_task")
        task["ai_category"] = data.get("category")
        task["ai_priority"] = data.get("priority")
        task["ai_estimated_minutes"] = data.get("estimated_minutes")
        task["ai_tags"] = data.get("tags", [])
        task["ai_subtasks"] = data.get("subtasks", [])
        task["ai_reason"] = data.get("reason")
        task["ai_last_error"] = None
        # A fresh analysis means any prior human review no longer applies
        task["human_verified"] = False
    else:
        task["ai_status"] = "failed"
        task["ai_last_error"] = f"{result['message']} (type: {result.get('error_type')})"




def render_task_row(task, show_ai_status=True):
    """Task-management row: checkbox, text, edit/delete. No AI controls here — those live in the AI Task Coach tab."""
    col1, col2, col3 = st.columns([0.1, 0.7, 0.2])

    with col1:
        was_done = task["done"]
        task["done"] = st.checkbox(
            "Done", value=task["done"], key=f"check_{task['task_id']}",
            label_visibility="collapsed"
        )
        if task["done"] and not was_done:
            mark_completed(task)
        elif not task["done"] and was_done:
            mark_reopened(task)

    with col2:
        if st.session_state.editing_task_id == task["task_id"]:
            new_raw = st.text_input("Edit task text", value=task["raw"], key=f"edit_text_{task['task_id']}")
            new_category = st.selectbox(
                "Edit category", CATEGORIES,
                index=CATEGORIES.index(task["category"]),
                key=f"edit_cat_{task['task_id']}"
            )
            new_priority = st.selectbox(
                "Edit priority", PRIORITIES,
                index=PRIORITIES.index(task["priority"]),
                key=f"edit_pri_{task['task_id']}"
            )

            if st.button("Save", key=f"save_{task['task_id']}"):
                edit_task(task, new_raw, new_category, new_priority, clean_text)
                st.session_state.editing_task_id = None
                st.rerun()

            if st.button("Cancel", key=f"cancel_{task['task_id']}"):
                st.session_state.editing_task_id = None
                st.rerun()

        else:
            if task["done"]:
                st.markdown(f"~~{task['raw']}~~")
            else:
                due_display = str(task['due_date'])
                if task.get("due_time"):
                    due_display += f" {task['due_time']}"
                st.markdown(
                    f"{highlight_task_text(task)}  \n{priority_badge(task['priority'])} &nbsp; *{task['category']} · Due {due_display}*",
                    unsafe_allow_html=True
                    )
            if task.get("due_date") and task["due_date"] < date.today():
                if AI_CONFIGURED:
                    if st.button("🔄 Suggest new date", key=f"snooze_{task['task_id']}"):
                        result = suggest_reschedule(task)
                        if result["success"]:
                            st.session_state.reschedule_suggestions[task["task_id"]] = result
                        else:
                            st.warning(result["message"])

                    if task["task_id"] in st.session_state.reschedule_suggestions:
                        sug = st.session_state.reschedule_suggestions[task["task_id"]]
                        st.info(f"Suggested: **{sug['new_due_date']}** — {sug['reason']}")
                        col_a, col_b = st.columns(2)
                        with col_a:
                            if st.button("Use this date", key=f"accept_snooze_{task['task_id']}"):
                                task["due_date"] = sug["new_due_date"]
                                del st.session_state.reschedule_suggestions[task["task_id"]]
                                st.rerun()
                        with col_b:
                            if st.button("Dismiss", key=f"dismiss_snooze_{task['task_id']}"):
                                del st.session_state.reschedule_suggestions[task["task_id"]]
                                st.rerun()
                
            if show_ai_status:
                if task["ai_status"] == "not_analyzed":
                    st.caption("⏳ Not yet analysed by AI")
                elif task["ai_status"] == "failed":
                    st.caption("❌ AI analysis failed")
                elif task["ai_status"] == "success" and not task["human_verified"]:
                    st.caption("🤖 AI analysed — awaiting your review in the AI Task Coach tab")
                elif task["human_verified"]:
                    st.caption(
                        f"✅ Verified — Final: {task['final_category']} | "
                        f"{task['final_priority']} | {task['final_estimated_minutes']} min "
                        f"({'AI accepted as-is' if task['ai_accepted'] else 'human-corrected'})"
                    )

    with col3:
        if st.button("Edit", key=f"edit_{task['task_id']}"):
            st.session_state.editing_task_id = task["task_id"]
            st.rerun()

        if st.button("Delete", key=f"delete_{task['task_id']}"):
            st.session_state.tasks = delete_task(st.session_state.tasks, task["task_id"])
            st.rerun()


page = st.radio(
    "Navigate",
    ["Tasks", "AI Task Coach", "Calendar", "Dataset Explorer", "Dashboard"],
    horizontal=True,
    label_visibility="collapsed",
)
# ============================================================
# TAB 1: TASKS
# ============================================================
if page == "Tasks":
    st.subheader("Chat to Add a Task")

    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    chat_text = st.chat_input(
        "Say hi, or tell me what you need to do...",
        disabled=not AI_CONFIGURED
    )
    if not AI_CONFIGURED:
        st.caption("Chat needs an API key configured — use the form below instead.")

    if chat_text:
        st.session_state.chat_messages.append({"role": "user", "content": chat_text})

        with st.spinner("Thinking..."):
            pending_for_chat = [t for t in st.session_state.tasks if not t["done"]]
            result = chat_task_turn(chat_text, st.session_state.chat_draft, st.session_state.chat_multi_draft, pending_for_chat)
        if result["success"]:
            st.session_state.chat_messages.append({"role": "assistant", "content": result["reply"]})

            if result["action"] == "propose":
                st.session_state.chat_draft = result["draft"]

            

            
            elif result["action"] == "confirmed_create":
                draft = result["draft"]
                task = new_task_dict(
                    raw_text=draft["task_text"],
                    category=draft["category"],
                    priority=draft["priority"],
                    due_date=draft["due_date"],
                    due_time=draft["due_time"],
                )
                if task["sanitized"]:
                    task["ai_status"] = "success"
                    task["ai_rewritten_task"] = draft["task_text"]
                    task["ai_category"] = draft["category"]
                    task["ai_priority"] = draft["priority"]
                    task["ai_estimated_minutes"] = draft["estimated_minutes"]
                    task["ai_tags"] = draft["tags"]
                    task["ai_subtasks"] = draft["subtasks"]
                    task["ai_reason"] = draft["reason"]
                    task["final_task_text"] = draft["task_text"]
                    task["final_category"] = draft["category"]
                    task["final_priority"] = draft["priority"]
                    task["final_estimated_minutes"] = draft["estimated_minutes"]
                    task["final_tags"] = draft["tags"]
                    task["final_subtasks"] = draft["subtasks"]
                    task["ai_accepted"] = True
                    task["human_edited"] = False
                    task["human_verified"] = True
                    st.session_state.tasks.append(task)
                st.session_state.chat_draft = None
                

            elif result["action"] == "query":
                filt = result["query_filter"]
                matches = filter_tasks(
                    st.session_state.tasks,
                    status=filt["status"],
                    due_before_date=filt["due_before_date"],
                    due_before_time=filt["due_before_time"],
                )
                matches = sort_by_priority_desc(matches)
                if matches:
                    lines = []
                    for t in matches:
                        due_bit = ""
                        if t["due_date"]:
                            due_bit = f" (due {t['due_date']}"
                            due_bit += f" {t['due_time']})" if t.get("due_time") else ")"
                        lines.append(f"- **{t['priority'].capitalize()}** — {t['raw']}{due_bit}")
                    listing = "\n".join(lines)
                else:
                    listing = "Nothing matches that — you're all clear!"
                st.session_state.chat_messages.append({"role": "assistant", "content": result["reply"] + "\n\n" + listing})

            elif result["action"] == "complete":
                target = next((t for t in st.session_state.tasks if t["task_id"] == result["complete_task_id"]), None)
                if target:
                    mark_completed(target)
                    st.session_state.chat_messages.append({"role": "assistant", "content": result["reply"]})
                else:
                    st.session_state.chat_messages.append({"role": "assistant", "content": "I couldn't find that task — could you tell me the name again?"})

            elif result["action"] == "complete_multi":
                for tid in result["complete_task_ids"]:
                    target = next((t for t in st.session_state.tasks if t["task_id"] == tid), None)
                    if target:
                        mark_completed(target)
                st.session_state.chat_messages.append({"role": "assistant", "content": result["reply"]})
            
            elif result["action"] == "propose_multi":
                st.session_state.chat_multi_draft = result["drafts"]

            elif result["action"] == "confirmed_create_multi":
                for draft in result["drafts"]:
                    task = new_task_dict(
                        raw_text=draft["task_text"], category=draft["category"],
                        priority=draft["priority"], due_date=draft["due_date"], due_time=draft["due_time"],
                    )
                    if task["sanitized"]:
                        task["ai_status"] = "success"
                        task["ai_rewritten_task"] = draft["task_text"]
                        task["ai_category"] = draft["category"]
                        task["ai_priority"] = draft["priority"]
                        task["ai_estimated_minutes"] = draft["estimated_minutes"]
                        task["ai_tags"] = draft["tags"]
                        task["ai_subtasks"] = draft["subtasks"]
                        task["ai_reason"] = draft["reason"]
                        task["final_task_text"] = draft["task_text"]
                        task["final_category"] = draft["category"]
                        task["final_priority"] = draft["priority"]
                        task["final_estimated_minutes"] = draft["estimated_minutes"]
                        task["final_tags"] = draft["tags"]
                        task["final_subtasks"] = draft["subtasks"]
                        task["ai_accepted"] = True
                        task["human_edited"] = False
                        task["human_verified"] = True
                        st.session_state.tasks.append(task)
                st.session_state.chat_multi_draft = None
            
        else:
            st.session_state.chat_messages.append({"role": "assistant", "content": result["message"]})

        st.rerun()

    if st.session_state.chat_messages and st.button("Clear Chat"):
        st.session_state.chat_messages = []
        st.session_state.chat_draft = None
        st.session_state.chat_multi_draft = None
        st.rerun()

    st.divider()
    st.subheader("Add a Task")
    with st.form("add_task_form", clear_on_submit=True):
        new_task_text = st.text_input("Task:")
        category = st.selectbox("Category", CATEGORIES)
        priority = st.selectbox("Priority", PRIORITIES)
        due_date = st.date_input("Due date")
        submitted = st.form_submit_button("Add Task")

        if submitted and new_task_text.strip() != "":
            cleaned_preview = clean_text(new_task_text)

            if not cleaned_preview["sanitized_task"]:
                st.warning("This task has no meaningful content after cleaning. Please try again.")
            else:
                if is_duplicate(st.session_state.tasks, cleaned_preview["sanitized_task"]):
                    st.warning("Heads up — a very similar task already exists. Added it anyway.")

                st.session_state.tasks.append(
                    new_task_dict(new_task_text, category, priority, due_date)
                )
                st.success(f"Added: {new_task_text}")

    st.subheader("Your Tasks")

    if not st.session_state.tasks:
        st.write("No tasks yet.")

    search_query = st.text_input("Search tasks:")

    col_a, col_b, col_c = st.columns(3)
    sort_by = st.selectbox("Sort by", ["Creation date", "Due date", "Priority", "Estimated duration"])

    with col_a:
        status_filter = st.selectbox("Status", ["all", "pending", "completed"])
    with col_b:
        category_filter = st.selectbox("Category", ["all"] + CATEGORIES)
    with col_c:
        priority_filter = st.selectbox("Priority", ["all"] + PRIORITIES)

    filtered_tasks = st.session_state.tasks

    if search_query:
        filtered_tasks = [t for t in filtered_tasks if search_query.lower() in t["raw"].lower()]

    if status_filter != "all":
        if status_filter == "completed":
            filtered_tasks = [t for t in filtered_tasks if t["done"]]
        else:
            filtered_tasks = [t for t in filtered_tasks if not t["done"]]

    if category_filter != "all":
        filtered_tasks = [t for t in filtered_tasks if t["category"] == category_filter]

    if priority_filter != "all":
        filtered_tasks = [t for t in filtered_tasks if t["priority"] == priority_filter]

    priority_order = {"low": 0, "medium": 1, "high": 2}

    if sort_by == "Creation date":
        filtered_tasks = sorted(filtered_tasks, key=lambda t: t["created_at"])
    elif sort_by == "Due date":
        filtered_tasks = sorted(filtered_tasks, key=lambda t: t["due_date"])
    elif sort_by == "Priority":
        filtered_tasks = sorted(filtered_tasks, key=lambda t: priority_order[t["priority"]], reverse=True)
    elif sort_by == "Estimated duration":
        filtered_tasks = sorted(filtered_tasks, key=lambda t: t["final_estimated_minutes"] or t["ai_estimated_minutes"] or 0)

    pending_tasks = [t for t in filtered_tasks if not t["done"]]
    completed_tasks = [t for t in filtered_tasks if t["done"]]

    st.markdown("### Pending")
    if not pending_tasks:
        st.caption("Nothing pending.")
    for task in pending_tasks:
        render_task_row(task)

    st.markdown("### Completed")
    if not completed_tasks:
        st.caption("Nothing completed yet.")
    for task in completed_tasks:
        render_task_row(task)

    if any(t["done"] for t in st.session_state.tasks):
        st.divider()
        if not st.session_state.confirm_clear:
            if st.button("Clear All Completed Tasks"):
                st.session_state.confirm_clear = True
                st.rerun()
        else:
            st.warning("This will permanently delete all completed tasks. Are you sure?")
            col_yes, col_no = st.columns(2)
            with col_yes:
                if st.button("Yes, clear them"):
                    st.session_state.tasks = [t for t in st.session_state.tasks if not t["done"]]
                    st.session_state.confirm_clear = False
                    st.rerun()
            with col_no:
                if st.button("Cancel"):
                    st.session_state.confirm_clear = False
                    st.rerun()


# ============================================================
# TAB 2: AI TASK COACH
# ============================================================
if page == "AI Task Coach":
    st.subheader("AI Analysis")

    pending_only = [t for t in st.session_state.tasks if not t["done"]]

    needs_analysis = [t for t in pending_only if t["ai_status"] in ("not_analyzed", "failed")]
    already_reviewed = [t for t in pending_only if t["human_verified"]]

    if not pending_only:
        st.caption("No pending tasks. Add one in the Tasks tab first.")

    if needs_analysis:
        st.markdown("#### Not yet categorized")
        st.caption("These were added manually. Describe them in the chat on the Tasks tab to get AI categorization.")
        for task in needs_analysis:
            st.write(f"- {task['raw']}")
    if already_reviewed:
        st.markdown("#### Already reviewed (pending tasks)")
        for task in already_reviewed:
            st.write(
                f"**{task['raw']}** — Final: {task['final_category']} | {task['final_priority']} | "
                f"{task['final_estimated_minutes']} min"
            )
            if st.button("Force Reanalyse", key=f"coach_force_{task['task_id']}", disabled=not AI_CONFIGURED):
                run_ai_analysis(task, force=True)
                st.rerun()

    st.divider()
    st.subheader("AI Daily Focus Plan")

    if st.button("Plan My Focus Session", disabled=not AI_CONFIGURED):
        if not pending_only:
            st.warning("No pending tasks to plan.")
        else:
            with st.spinner("Planning your focus session..."):
                result = get_focus_plan(pending_only)
            if result["success"]:
                st.session_state.focus_plan = result["data"]
            else:
                st.warning(result["message"])
                st.session_state.focus_plan = None

    if st.session_state.focus_plan:
        plan = st.session_state.focus_plan
        st.write(plan["summary"])

        tasks_by_id = {t["task_id"]: t for t in st.session_state.tasks}
        for item in sorted(plan["focus_plan"], key=lambda x: x.get("position", 99)):
            task = tasks_by_id.get(item["task_id"])
            if task:
                st.write(f"**{item.get('position')}. {task['raw']}** — {item.get('reason')}")

    st.divider()
    st.subheader("How are you feeling?")
    mood = st.selectbox("Mood", ["Energetic", "Focused", "Tired", "Overwhelmed", "Bored"])
    available_time = st.selectbox("Time available", ["15 minutes", "30 minutes", "1 hour", "A few hours", "All day"])

    if st.button("Pick tasks for me", disabled=not AI_CONFIGURED):
        mood_pending = [t for t in st.session_state.tasks if not t["done"]]
        if not mood_pending:
            st.warning("No pending tasks to pick from.")
        else:
            with st.spinner("Matching tasks to how you feel..."):
                result = get_mood_picks(mood_pending, mood, available_time)
            if result["success"]:
                st.session_state.mood_picks = result["data"]
            else:
                st.warning(result["message"])
                st.session_state.mood_picks = None

    if st.session_state.mood_picks:
        mood_data = st.session_state.mood_picks
        st.write(mood_data["summary"])
        tasks_by_id_mood = {t["task_id"]: t for t in st.session_state.tasks}
        for pick in mood_data["picks"]:
            task = tasks_by_id_mood.get(pick["task_id"])
            if task:
                render_task_row(task, show_ai_status=False)
                st.caption(f"💭 {pick['reason']}")




if page == "Calendar":
    st.subheader("Calendar")

    events = []
    for t in st.session_state.tasks:
        if not t["due_date"]:
            continue
        start = str(t["due_date"])
        if t.get("due_time"):
            start += f"T{t['due_time']}:00"

        events.append({
            "title": ("✅ " if t["done"] else "") + (t["final_task_text"] or t["raw"]),
            "start": start,
            "color": PRIORITY_COLORS.get(t["priority"], "#3788d8"),
        })

    calendar_options = {
        "initialView": "dayGridMonth",
        "headerToolbar": {
            "left": "prev,next today",
            "center": "title",
            "right": "dayGridMonth,timeGridWeek,listMonth",
        },
        "height": 650,
    }

    clicked = calendar(events=events, options=calendar_options, key="task_calendar")

    if clicked.get("eventClick"):
        st.info(f"Clicked: {clicked['eventClick']['event']['title']}")


# ============================================================
# TAB 3: DATASET EXPLORER
# ============================================================
if page == "Dataset Explorer":
    st.subheader("Training Dataset")

    if not st.session_state.tasks:
        st.write("No tasks yet.")
    else:
        df = pd.DataFrame(st.session_state.tasks)
        st.dataframe(df)

        st.subheader("Data Quality")

        total_rows = len(df)
        duplicate_raw = df["raw"].duplicated().sum()
        duplicate_sanitized = df["sanitized"].duplicated().sum()
        empty_raw = (df["raw"].str.strip() == "").sum()
        empty_sanitized = (df["sanitized"].str.strip() == "").sum()
        missing_category = df["category"].isnull().sum()
        missing_priority = df["priority"].isnull().sum()
        not_verified = (~df["human_verified"]).sum()
        failed_ai = (df["ai_status"] == "failed").sum()
        analysed = (df["ai_status"] == "success").sum()
        verified = df["human_verified"].sum()

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total rows", total_rows)
        col2.metric("AI-analysed", analysed)
        col3.metric("Human-verified", verified)
        col4.metric("Failed AI analyses", failed_ai)

        col5, col6, col7, col8 = st.columns(4)
        col5.metric("Duplicate raw", duplicate_raw)
        col6.metric("Duplicate sanitized", duplicate_sanitized)
        col7.metric("Empty raw", empty_raw)
        col8.metric("Empty sanitized", empty_sanitized)

        verified_df = df[df["human_verified"] == True]
        acceptance_rate = (verified_df["ai_accepted"].mean() * 100) if not verified_df.empty else 0
        st.metric("AI suggestions accepted unchanged", f"{acceptance_rate:.0f}%")

        if st.button("Show Problematic Records"):
            problem_mask = (
                (df["raw"].str.strip() == "") |
                (df["sanitized"].str.strip() == "") |
                df["category"].isnull() |
                df["priority"].isnull() |
                (df["ai_status"] == "failed")
            )
            st.dataframe(df[problem_mask])

        csv = df.to_csv(index=False)
        st.download_button(
            label="Download Dataset as CSV",
            data=csv,
            file_name="task_training_dataset.csv",
            mime="text/csv"
        )

        jsonl = df.to_json(orient="records", lines=True, force_ascii=False)
        st.download_button(
            label="Download Dataset as JSONL",
            data=jsonl,
            file_name="task_training_dataset.jsonl",
            mime="application/json"
        )


# ============================================================
# TAB 4: DASHBOARD
# ============================================================
if page == "Dashboard":
    st.subheader("Dashboard")

    tasks = st.session_state.tasks
    if not tasks:
        st.write("No tasks yet.")
    else:
        total = len(tasks)
        completed = sum(1 for t in tasks if t["done"])
        pending = total - completed
        completion_pct = (completed / total * 100) if total else 0
        overdue = sum(1 for t in tasks if is_overdue(t, date.today()))

        durations = [t["final_estimated_minutes"] or t["ai_estimated_minutes"] for t in tasks if (t["final_estimated_minutes"] or t["ai_estimated_minutes"])]
        avg_duration = sum(durations) / len(durations) if durations else 0

        verified = [t for t in tasks if t["human_verified"]]
        acceptance_rate = (sum(1 for t in verified if t["ai_accepted"]) / len(verified) * 100) if verified else 0

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total tasks", total)
        col2.metric("Pending", pending)
        col3.metric("Completed", completed)
        col4.metric("Completion %", f"{completion_pct:.0f}%")

        col5, col6, col7 = st.columns(3)
        col5.metric("Avg. estimated duration", f"{avg_duration:.0f} min" if durations else "—")
        col6.metric("AI acceptance rate", f"{acceptance_rate:.0f}%" if verified else "—")
        col7.metric("Overdue tasks", overdue)

        st.markdown("#### Tasks by category")
        by_category = pd.Series([t["category"] for t in tasks]).value_counts()
        st.bar_chart(by_category)

        st.markdown("#### Tasks by priority")
        by_priority = pd.Series([t["priority"] for t in tasks]).value_counts()
        st.bar_chart(by_priority)


# --- Persist state to disk on every rerun (best-effort, doesn't touch API keys) ---
save_tasks(st.session_state.tasks)
