from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from flask import Flask, jsonify, make_response, request
from pydantic import BaseModel, Field, ValidationError, field_validator

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
STORE_PATH = DATA_DIR / "tasks.json"
ALLOWED_DEV_ORIGINS = {
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
}

Priority = Literal["low", "medium", "high"]


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now_utc().isoformat()


class TaskBase(BaseModel):
    title: str = "Untitled task"
    notes: str = ""
    completed: bool = False
    category: str = "General"
    priority: Priority = "medium"
    due_date: date | None = None

    @field_validator("title", "notes", "category", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @field_validator("priority", mode="before")
    @classmethod
    def normalize_priority(cls, value: object) -> str:
        return str(value or "medium").strip().lower()

    @field_validator("due_date", mode="before")
    @classmethod
    def normalize_due_date(cls, value: object) -> object:
        if value in ("", None):
            return None
        return value

    @field_validator("category")
    @classmethod
    def ensure_category(cls, value: str) -> str:
        return value or "General"


class Task(TaskBase):
    id: str
    created_at: datetime
    updated_at: datetime

    @field_validator("title")
    @classmethod
    def ensure_title(cls, value: str) -> str:
        return value or "Untitled task"


class TaskCreate(TaskBase):
    title: str

    @field_validator("title")
    @classmethod
    def require_title(cls, value: str) -> str:
        if not value:
            raise ValueError("Task title is required.")
        return value


class TaskUpdate(BaseModel):
    title: str | None = None
    notes: str | None = None
    completed: bool | None = None
    category: str | None = None
    priority: Priority | None = None
    due_date: date | None = None

    @field_validator("title", "notes", "category", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        if value is None:
            return None
        return str(value).strip()

    @field_validator("priority", mode="before")
    @classmethod
    def normalize_optional_priority(cls, value: object) -> object:
        if value is None:
            return None
        return str(value).strip().lower()

    @field_validator("due_date", mode="before")
    @classmethod
    def normalize_optional_due_date(cls, value: object) -> object:
        if value in ("", None):
            return None
        return value

    @field_validator("title")
    @classmethod
    def fill_blank_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value or "Untitled task"

    @field_validator("category")
    @classmethod
    def fill_blank_category(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value or "General"


class TaskStore(BaseModel):
    tasks: list[Task] = Field(default_factory=list)


def default_store() -> TaskStore:
    today = datetime.now().date()
    return TaskStore(
        tasks=[
            Task(
                id=str(uuid4()),
                title="Plan the week",
                notes="Capture the top three priorities.",
                completed=False,
                category="Personal",
                priority="high",
                due_date=today,
                created_at=now_utc(),
                updated_at=now_utc(),
            ),
            Task(
                id=str(uuid4()),
                title="Ship the landing page",
                notes="Polish the final responsive pass.",
                completed=False,
                category="Work",
                priority="medium",
                due_date=None,
                created_at=now_utc(),
                updated_at=now_utc(),
            ),
        ]
    )


def ensure_store() -> TaskStore:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not STORE_PATH.exists():
        store = default_store()
        save_store(store)
        return store
    return TaskStore.model_validate_json(STORE_PATH.read_text(encoding="utf-8"))


def save_store(store: TaskStore) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STORE_PATH.write_text(json.dumps(store.model_dump(mode="json"), indent=2), encoding="utf-8")


def sort_tasks(tasks: list[Task]) -> list[Task]:
    return sorted(tasks, key=lambda task: task.created_at, reverse=True)


def build_summary(tasks: list[Task]) -> dict[str, int]:
    completed = sum(1 for task in tasks if task.completed)
    today = datetime.now().date()
    due_today = sum(1 for task in tasks if not task.completed and task.due_date == today)
    return {
        "total": len(tasks),
        "completed": completed,
        "open": len(tasks) - completed,
        "due_today": due_today,
    }


def response_payload(store: TaskStore) -> dict:
    tasks = sort_tasks(store.tasks)
    categories = sorted({task.category for task in tasks})
    return {
        "tasks": [task.model_dump(mode="json") for task in tasks],
        "summary": build_summary(tasks),
        "categories": categories,
    }


def validation_error_response(error: ValidationError):
    first_error = error.errors()[0]
    message = first_error.get("msg", "Invalid request.")
    return jsonify({"error": message}), 400


def create_task_record(payload: TaskCreate) -> Task:
    current_time = now_utc()
    return Task(
        id=str(uuid4()),
        created_at=current_time,
        updated_at=current_time,
        **payload.model_dump(),
    )


def apply_task_updates(current: Task, updates: TaskUpdate) -> Task:
    merged = current.model_dump()
    merged.update(updates.model_dump(exclude_unset=True))
    merged["updated_at"] = now_utc()
    return Task.model_validate(merged)


@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin", "")
    if origin in ALLOWED_DEV_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
    else:
        response.headers["Access-Control-Allow-Origin"] = "http://localhost:3000"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
    return response


@app.before_request
def handle_options():
    if request.method == "OPTIONS":
        return make_response("", 204)
    return None


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "time": now_iso()})


@app.get("/api/tasks")
def get_tasks():
    return jsonify(response_payload(ensure_store()))


@app.post("/api/tasks")
def create_task():
    store = ensure_store()
    payload = request.get_json(silent=True) or {}
    try:
        new_task = create_task_record(TaskCreate.model_validate(payload))
    except ValidationError as error:
        return validation_error_response(error)

    store.tasks.append(new_task)
    save_store(store)
    return jsonify({"task": new_task.model_dump(mode="json"), **response_payload(store)}), 201


@app.patch("/api/tasks/<task_id>")
def update_task(task_id: str):
    store = ensure_store()
    payload = request.get_json(silent=True) or {}

    try:
        updates = TaskUpdate.model_validate(payload)
    except ValidationError as error:
        return validation_error_response(error)

    for index, task in enumerate(store.tasks):
        if task.id == task_id:
            updated = apply_task_updates(task, updates)
            store.tasks[index] = updated
            save_store(store)
            return jsonify({"task": updated.model_dump(mode="json"), **response_payload(store)})

    return jsonify({"error": "Task not found."}), 404


@app.delete("/api/tasks/<task_id>")
def delete_task(task_id: str):
    store = ensure_store()
    next_tasks = [task for task in store.tasks if task.id != task_id]
    if len(next_tasks) == len(store.tasks):
        return jsonify({"error": "Task not found."}), 404

    store.tasks = next_tasks
    save_store(store)
    return jsonify(response_payload(store))


@app.delete("/api/tasks")
def clear_completed():
    store = ensure_store()
    store.tasks = [task for task in store.tasks if not task.completed]
    save_store(store)
    return jsonify(response_payload(store))


if __name__ == "__main__":
    app.run(debug=True)
