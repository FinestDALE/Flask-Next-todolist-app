from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from flask import Flask, jsonify, make_response, request

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
STORE_PATH = DATA_DIR / "tasks.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_store() -> dict:
    return {
        "tasks": [
            {
                "id": str(uuid4()),
                "title": "Plan the week",
                "notes": "Capture the top three priorities.",
                "completed": False,
                "category": "Personal",
                "priority": "high",
                "due_date": datetime.now().date().isoformat(),
                "created_at": now_iso(),
                "updated_at": now_iso(),
            },
            {
                "id": str(uuid4()),
                "title": "Ship the landing page",
                "notes": "Polish the final responsive pass.",
                "completed": False,
                "category": "Work",
                "priority": "medium",
                "due_date": "",
                "created_at": now_iso(),
                "updated_at": now_iso(),
            },
        ]
    }


def ensure_store() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not STORE_PATH.exists():
        store = default_store()
        STORE_PATH.write_text(json.dumps(store, indent=2), encoding="utf-8")
        return store
    return json.loads(STORE_PATH.read_text(encoding="utf-8"))


def save_store(store: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STORE_PATH.write_text(json.dumps(store, indent=2), encoding="utf-8")


def normalize_task(payload: dict, current: dict | None = None) -> dict:
    current = current or {}
    created_at = current.get("created_at", now_iso())
    return {
        "id": current.get("id") or str(uuid4()),
        "title": str(payload.get("title", current.get("title", ""))).strip() or "Untitled task",
        "notes": str(payload.get("notes", current.get("notes", ""))).strip(),
        "completed": bool(payload.get("completed", current.get("completed", False))),
        "category": str(payload.get("category", current.get("category", "General"))).strip() or "General",
        "priority": str(payload.get("priority", current.get("priority", "medium"))).lower(),
        "due_date": str(payload.get("due_date", current.get("due_date", ""))).strip(),
        "created_at": created_at,
        "updated_at": now_iso(),
    }


def sort_tasks(tasks: list[dict]) -> list[dict]:
    return sorted(tasks, key=lambda task: (task["completed"], task["due_date"] or "9999-12-31", task["created_at"]))


def build_summary(tasks: list[dict]) -> dict:
    completed = sum(1 for task in tasks if task["completed"])
    today = datetime.now().date().isoformat()
    due_today = sum(1 for task in tasks if not task["completed"] and task["due_date"] == today)
    return {
        "total": len(tasks),
        "completed": completed,
        "open": len(tasks) - completed,
        "due_today": due_today,
    }


def response_payload(store: dict) -> dict:
    tasks = sort_tasks(store["tasks"])
    categories = sorted({task["category"] for task in tasks})
    return {
        "tasks": tasks,
        "summary": build_summary(tasks),
        "categories": categories,
    }


@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin", "")
    if origin in {"http://localhost:3000", "http://127.0.0.1:3000"}:
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
    if not str(payload.get("title", "")).strip():
        return jsonify({"error": "Task title is required."}), 400

    task = normalize_task(payload)
    store["tasks"].append(task)
    save_store(store)
    return jsonify({"task": task, **response_payload(store)}), 201


@app.patch("/api/tasks/<task_id>")
def update_task(task_id: str):
    store = ensure_store()
    payload = request.get_json(silent=True) or {}

    for index, task in enumerate(store["tasks"]):
        if task["id"] == task_id:
            updated = normalize_task(payload, task)
            store["tasks"][index] = updated
            save_store(store)
            return jsonify({"task": updated, **response_payload(store)})

    return jsonify({"error": "Task not found."}), 404


@app.delete("/api/tasks/<task_id>")
def delete_task(task_id: str):
    store = ensure_store()
    next_tasks = [task for task in store["tasks"] if task["id"] != task_id]
    if len(next_tasks) == len(store["tasks"]):
        return jsonify({"error": "Task not found."}), 404

    store["tasks"] = next_tasks
    save_store(store)
    return jsonify(response_payload(store))


@app.delete("/api/tasks")
def clear_completed():
    store = ensure_store()
    store["tasks"] = [task for task in store["tasks"] if not task["completed"]]
    save_store(store)
    return jsonify(response_payload(store))


if __name__ == "__main__":
    app.run(debug=True)
