from __future__ import annotations

import json
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from flask import Flask, jsonify, make_response, request
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError, field_validator

app = Flask(__name__)

baseDir = Path(__file__).resolve().parent
dataDir = baseDir / "data"
storePath = dataDir / "tasks.json"
allowedDevOrigins = {
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
}
defaultTitle = "Untitled task"
defaultCategory = "General"
defaultPriority = "medium"

Priority = Literal["low", "medium", "high"]


def nowUtc() -> datetime:
    return datetime.now(timezone.utc)


def nowIso() -> str:
    return nowUtc().isoformat()


def normalizeTextValue(value: object, *, allowNone: bool = False) -> str | None:
    if value is None:
        return None if allowNone else ""
    return str(value).strip()


def normalizePriorityValue(value: object, *, allowNone: bool = False) -> str | None:
    if value is None:
        return None if allowNone else defaultPriority
    normalized = str(value).strip().lower()
    return normalized or (None if allowNone else defaultPriority)


def normalizeDueValue(value: object) -> object:
    if value in ("", None):
        return None
    return value


def fallbackValue(value: str | None, default: str, *, allowNone: bool = False) -> str | None:
    if value is None:
        return None if allowNone else default
    return value or default


def ensureDataDir() -> None:
    dataDir.mkdir(parents=True, exist_ok=True)


class TaskBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str = defaultTitle
    notes: str = ""
    completed: bool = False
    category: str = defaultCategory
    priority: Priority = defaultPriority
    dueDate: date | None = Field(default=None, validation_alias=AliasChoices("dueDate", "due_date"))
    dueTime: time | None = Field(default=None, validation_alias=AliasChoices("dueTime", "due_time"))

    @field_validator("title", "notes", "category", mode="before")
    @classmethod
    def normalizeText(cls, value: object) -> str:
        return normalizeTextValue(value)

    @field_validator("priority", mode="before")
    @classmethod
    def normalizePriority(cls, value: object) -> str:
        return normalizePriorityValue(value) or defaultPriority

    @field_validator("dueDate", "dueTime", mode="before")
    @classmethod
    def normalizeDueFields(cls, value: object) -> object:
        return normalizeDueValue(value)

    @field_validator("category")
    @classmethod
    def ensureCategory(cls, value: str) -> str:
        return fallbackValue(value, defaultCategory) or defaultCategory


class Task(TaskBase):
    id: str
    createdAt: datetime = Field(validation_alias=AliasChoices("createdAt", "created_at"))
    updatedAt: datetime = Field(validation_alias=AliasChoices("updatedAt", "updated_at"))

    @field_validator("title")
    @classmethod
    def ensureTitle(cls, value: str) -> str:
        return fallbackValue(value, defaultTitle) or defaultTitle


class TaskCreate(TaskBase):
    title: str

    @field_validator("title")
    @classmethod
    def requireTitle(cls, value: str) -> str:
        if not value:
            raise ValueError("Task title is required.")
        return value


class TaskUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str | None = None
    notes: str | None = None
    completed: bool | None = None
    category: str | None = None
    priority: Priority | None = None
    dueDate: date | None = Field(default=None, validation_alias=AliasChoices("dueDate", "due_date"))
    dueTime: time | None = Field(default=None, validation_alias=AliasChoices("dueTime", "due_time"))

    @field_validator("title", "notes", "category", mode="before")
    @classmethod
    def normalizeOptionalText(cls, value: object) -> object:
        return normalizeTextValue(value, allowNone=True)

    @field_validator("priority", mode="before")
    @classmethod
    def normalizeOptionalPriority(cls, value: object) -> object:
        return normalizePriorityValue(value, allowNone=True)

    @field_validator("dueDate", "dueTime", mode="before")
    @classmethod
    def normalizeOptionalDueFields(cls, value: object) -> object:
        return normalizeDueValue(value)

    @field_validator("title")
    @classmethod
    def fillBlankTitle(cls, value: str | None) -> str | None:
        return fallbackValue(value, defaultTitle, allowNone=True)

    @field_validator("category")
    @classmethod
    def fillBlankCategory(cls, value: str | None) -> str | None:
        return fallbackValue(value, defaultCategory, allowNone=True)


class TaskStore(BaseModel):
    tasks: list[Task] = Field(default_factory=list)


def defaultStore() -> TaskStore:
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
                dueDate=today,
                dueTime=time(hour=9, minute=0),
                createdAt=nowUtc(),
                updatedAt=nowUtc(),
            ),
            Task(
                id=str(uuid4()),
                title="Ship the landing page",
                notes="Polish the final responsive pass.",
                completed=False,
                category="Work",
                priority="medium",
                dueDate=None,
                dueTime=None,
                createdAt=nowUtc(),
                updatedAt=nowUtc(),
            ),
        ]
    )


def ensureStore() -> TaskStore:
    ensureDataDir()
    if not storePath.exists():
        store = defaultStore()
        saveStore(store)
        return store
    return TaskStore.model_validate_json(storePath.read_text(encoding="utf-8"))


def saveStore(store: TaskStore) -> None:
    ensureDataDir()
    storePath.write_text(json.dumps(store.model_dump(mode="json"), indent=2), encoding="utf-8")


def sortTasks(tasks: list[Task]) -> list[Task]:
    return sorted(tasks, key=lambda task: task.createdAt, reverse=True)


def buildSummary(tasks: list[Task]) -> dict[str, int]:
    completed = sum(1 for task in tasks if task.completed)
    today = datetime.now().date()
    dueToday = sum(1 for task in tasks if not task.completed and task.dueDate == today)
    return {
        "total": len(tasks),
        "completed": completed,
        "open": len(tasks) - completed,
        "dueToday": dueToday,
    }


def responsePayload(store: TaskStore) -> dict:
    tasks = sortTasks(store.tasks)
    categories = sorted({task.category for task in tasks})
    return {
        "tasks": [task.model_dump(mode="json") for task in tasks],
        "summary": buildSummary(tasks),
        "categories": categories,
    }


def validationErrorResponse(error: ValidationError):
    firstError = error.errors()[0]
    message = firstError.get("msg", "Invalid request.")
    return jsonify({"error": message}), 400


def createTaskRecord(payload: TaskCreate) -> Task:
    currentTime = nowUtc()
    return Task(
        id=str(uuid4()),
        createdAt=currentTime,
        updatedAt=currentTime,
        **payload.model_dump(),
    )


def applyTaskUpdates(current: Task, updates: TaskUpdate) -> Task:
    merged = current.model_dump()
    merged.update(updates.model_dump(exclude_unset=True))
    merged["updatedAt"] = nowUtc()
    return Task.model_validate(merged)


@app.after_request
def addCorsHeaders(response):
    origin = request.headers.get("Origin", "")
    if origin in allowedDevOrigins:
        response.headers["Access-Control-Allow-Origin"] = origin
    else:
        response.headers["Access-Control-Allow-Origin"] = "http://localhost:3000"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
    return response


@app.before_request
def handleOptions():
    if request.method == "OPTIONS":
        return make_response("", 204)
    return None


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "time": nowIso()})


@app.get("/api/tasks")
def getTasks():
    return jsonify(responsePayload(ensureStore()))


@app.post("/api/tasks")
def createTask():
    store = ensureStore()
    payload = request.get_json(silent=True) or {}
    try:
        newTask = createTaskRecord(TaskCreate.model_validate(payload))
    except ValidationError as error:
        return validationErrorResponse(error)

    store.tasks.append(newTask)
    saveStore(store)
    return jsonify({"task": newTask.model_dump(mode="json"), **responsePayload(store)}), 201


@app.patch("/api/tasks/<taskId>")
def updateTask(taskId: str):
    store = ensureStore()
    payload = request.get_json(silent=True) or {}

    try:
        updates = TaskUpdate.model_validate(payload)
    except ValidationError as error:
        return validationErrorResponse(error)

    for index, task in enumerate(store.tasks):
        if task.id == taskId:
            updated = applyTaskUpdates(task, updates)
            store.tasks[index] = updated
            saveStore(store)
            return jsonify({"task": updated.model_dump(mode="json"), **responsePayload(store)})

    return jsonify({"error": "Task not found."}), 404


@app.delete("/api/tasks/<taskId>")
def deleteTask(taskId: str):
    store = ensureStore()
    nextTasks = [task for task in store.tasks if task.id != taskId]
    if len(nextTasks) == len(store.tasks):
        return jsonify({"error": "Task not found."}), 404

    store.tasks = nextTasks
    saveStore(store)
    return jsonify(responsePayload(store))


@app.delete("/api/tasks")
def clearCompleted():
    store = ensureStore()
    store.tasks = [task for task in store.tasks if not task.completed]
    saveStore(store)
    return jsonify(responsePayload(store))


if __name__ == "__main__":
    app.run(debug=True)
