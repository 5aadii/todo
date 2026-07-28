# AI Task Coach

A Streamlit task manager that also uses an AI model (via OpenRouter) to analyse
tasks and — with human review — collects labeled data suitable for training or
evaluating future task-classification models.

## Project purpose

**Task management:** add, edit, complete, reopen, delete tasks. Search, filter
(status/category/priority), and sort. Data survives app restarts via a local
JSON file.

**Training-data collection:** every task is cleaned into three text
representations (raw / sanitized / token-ready), then optionally sent to an AI
model, which suggests a category, priority, duration, tags, and subtasks. A
human then accepts or corrects those suggestions. Both the AI's original
prediction and the human's final answer are stored side by side — the
difference between them is the useful training signal.

## Installation

```bash
python -m venv venv
```

Windows:
```bash
venv\Scripts\activate
```
Linux or macOS:
```bash
source venv/bin/activate
```

Install packages:
```bash
pip install -r requirements.txt
```

Run:
```bash
streamlit run app.py
```

## API configuration

Create `.streamlit/secrets.toml` (this file is gitignored and must never be
committed):

```toml
OPENROUTER_API_KEY = "your-real-key"
OPENROUTER_MODEL = "provider/model-name"
```

A safe placeholder version is provided at `.streamlit/secrets.toml.example` —
copy it and fill in your real key locally. If no key is configured, the app
still works as a normal task manager; AI-related buttons are simply disabled.

## Cleaning pipeline

Every task is stored in three forms (see `cleaning.py`):

- **Raw text** — exactly what the user typed. Never overwritten.
- **Sanitized text** — lowercased, extra whitespace collapsed, special
  characters/emoji stripped, but negation words (`not`, `no`, `never`,
  `don't`) and numbers/times are preserved. This is what gets sent to the AI.
- **Token-ready text** — sanitized text with common stop words removed
  (negation words are never removed), intended for future tokenization/search
  rather than for the AI prompt.

## AI workflow

1. **Local cleaning** — `clean_text()` produces the three representations above.
2. **OpenRouter request** — `services/openrouter_client.py` sends the
   sanitized text to the model using a fixed system prompt
   (`prompts.py`, `PROMPT_VERSION`), a low temperature (predictable
   classification, not creative writing), and a 30s timeout.
3. **Response validation** — `validate_ai_response()` never trusts the model's
   output directly: unknown categories fall back to `"other"`, invalid
   priorities fall back to `"medium"`, duration is clamped to 5–480 minutes,
   and tags/subtasks are capped at three non-empty items each.
4. **Human review** — the AI Task Coach tab shows an editable form. The user
   can Accept All Suggestions or Save My Corrections (including
   rejecting/editing individual subtasks). Either way, the original `ai_*`
   fields stay untouched and a separate `final_*` field records what the
   human approved.
5. **Dataset update** — the task's row now carries both the AI's prediction
   and the human's final answer, plus `ai_accepted`, `human_edited`, and
   `human_verified` flags.

## Failure handling

If the API key is missing, the model is unavailable, the request times out,
the response isn't valid JSON, or expected fields are missing —
`analyse_task()` catches it and returns `{"success": False, "error_type": ...,
"message": ...}`. The task itself is always saved regardless of whether AI
analysis succeeded. `ai_status` is set to `"failed"`, a friendly message is
shown (never a raw traceback or the API key), and a **Retry AI Analysis**
button lets the user try again. Category/priority can always be set manually.

## Avoiding unnecessary API calls

Streamlit reruns the whole script on every widget interaction. To avoid
re-calling the API on every rerun, results are cached in
`st.session_state.ai_cache` keyed by the sanitized task text. The API is only
called when the user explicitly presses Analyse, Retry, Force Reanalyse, or
Plan My Focus Session.

## Dataset schema

Exported as CSV and JSONL (`task_training_dataset.csv` /
`task_training_dataset.jsonl`). Key columns:

| Column | Meaning |
|---|---|
| `task_id` | Stable UUID, not a list position |
| `raw` / `sanitized` / `token_ready` | The three cleaned text forms |
| `ai_category` / `final_category` | AI prediction vs. human-approved value |
| `ai_priority` / `final_priority` | same pattern |
| `ai_estimated_minutes` / `final_estimated_minutes` | same pattern |
| `ai_tags` / `final_tags` | same pattern |
| `ai_subtasks` / `final_subtasks` | same pattern |
| `ai_status` | `not_analyzed` / `success` / `failed` |
| `ai_accepted` | True if the human accepted the AI's output unchanged |
| `human_edited` | True if the human changed anything |
| `human_verified` | True once a human has reviewed the task at all |

No API keys, full HTTP responses, or internal tracebacks are ever written to
the exported dataset.

## Why this matters for training data

Keeping raw and cleaned text separate preserves the original signal while
still giving a normalized, model-ready version. Validating AI output stops a
single bad or malformed response from corrupting the dataset or crashing the
app. Recording both the AI's guess and the human's correction is exactly the
supervised-learning signal needed to later fine-tune or evaluate a
classification model — the gap between the two columns is where the model was
wrong.

## Tests

```bash
pytest -v
```

Covers text cleaning (`tests/test_cleaning.py`), AI response validation and
JSON parsing (`tests/test_ai_validation.py`), and task-management operations
like delete/edit/complete/reopen (`tests/test_task_management.py`). None of
these tests call the real OpenRouter API — `validate_ai_response` and
`extract_json_response` are pure functions, so they're tested directly
without mocking network calls at all.
