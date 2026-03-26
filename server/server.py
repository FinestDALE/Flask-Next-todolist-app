from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from typing import Literal
from uuid import uuid4

from flask import Flask, jsonify, make_response, request
from werkzeug.exceptions import HTTPException
from pymongo import ASCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)

allowedDevOrigins = {
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
}
defaultTitle = "Untitled task"
defaultCategory = "General"
defaultPriority = "medium"
defaultMongoUri = "mongodb://127.0.0.1:27017"
defaultMongoDb = "todo_app"
defaultTaskCollection = "tasks"
defaultUserCollection = "users"
defaultSessionCollection = "sessions"
sessionCookieName = "todo_session"
sessionDurationDays = 14

Priority = Literal["low", "medium", "high"]


def nowUtc() -> datetime:
    return datetime.now(timezone.utc)


def nowIso() -> str:
    return nowUtc().isoformat()


def ensureUtcAwareDateTime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


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


def validateDueDate(value: date | None) -> date | None:
    if value is None:
        return None

    if value < datetime.now().date():
        raise ValueError("Task date is invalid. Due date cannot be earlier than today.")

    return value


def validateDueDateTime(dueDate: date | None, dueTime: time | None) -> tuple[date | None, time | None]:
    if dueDate is None and dueTime is None:
        return dueDate, dueTime

    if dueDate is None or dueTime is None:
        raise ValueError("Task date is invalid. Please choose both a due date and due time.")

    currentDate = datetime.now().date()
    currentTime = datetime.now().time()

    if dueDate < currentDate:
        raise ValueError("Task date is invalid. Due date cannot be earlier than today.")

    if dueDate == currentDate and dueTime < currentTime:
        raise ValueError("Task time is invalid. Due time cannot be earlier than the current time.")

    return dueDate, dueTime


def normalizeEmailValue(value: object) -> str:
    return str(value or "").strip().lower()


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
        return normalizeTextValue(value) or ""

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

    @field_validator("dueDate")
    @classmethod
    def ensureFutureDueDate(cls, value: date | None) -> date | None:
        return validateDueDate(value)

    @model_validator(mode="after")
    def ensureValidDeadline(self) -> "TaskCreate":
        validateDueDateTime(self.dueDate, self.dueTime)
        return self


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

    @field_validator("dueDate")
    @classmethod
    def ensureFutureDueDate(cls, value: date | None) -> date | None:
        return validateDueDate(value)

    @model_validator(mode="after")
    def ensureValidDeadline(self) -> "TaskUpdate":
        validateDueDateTime(self.dueDate, self.dueTime)
        return self


class SessionUser(BaseModel):
    id: str
    name: str
    email: str
    createdAt: datetime = Field(validation_alias=AliasChoices("createdAt", "created_at"))


class AuthRegisterPayload(BaseModel):
    name: str
    email: str
    password: str

    @field_validator("name", mode="before")
    @classmethod
    def normalizeName(cls, value: object) -> str:
        return normalizeTextValue(value) or ""

    @field_validator("email", mode="before")
    @classmethod
    def normalizeEmail(cls, value: object) -> str:
        return normalizeEmailValue(value)

    @field_validator("password", mode="before")
    @classmethod
    def normalizePassword(cls, value: object) -> str:
        return str(value or "")

    @field_validator("name")
    @classmethod
    def validateName(cls, value: str) -> str:
        if len(value) < 2:
            raise ValueError("Name must be at least 2 characters long.")
        return value

    @field_validator("email")
    @classmethod
    def validateEmail(cls, value: str) -> str:
        if "@" not in value or "." not in value.split("@")[-1]:
            raise ValueError("Please provide a valid email address.")
        return value

    @field_validator("password")
    @classmethod
    def validatePassword(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        return value


class AuthLoginPayload(BaseModel):
    email: str
    password: str

    @field_validator("email", mode="before")
    @classmethod
    def normalizeEmail(cls, value: object) -> str:
        return normalizeEmailValue(value)

    @field_validator("password", mode="before")
    @classmethod
    def normalizePassword(cls, value: object) -> str:
        return str(value or "")

    @field_validator("email")
    @classmethod
    def validateEmail(cls, value: str) -> str:
        if not value:
            raise ValueError("Email is required.")
        return value

    @field_validator("password")
    @classmethod
    def validatePassword(cls, value: str) -> str:
        if not value:
            raise ValueError("Password is required.")
        return value


class AuthenticatedSession(BaseModel):
    token: str
    user: SessionUser
    expiresAt: datetime = Field(validation_alias=AliasChoices("expiresAt", "expires_at"))


class TaskStore(BaseModel):
    tasks: list[Task] = Field(default_factory=list)


def defaultStore() -> TaskStore:
    today = datetime.now().date()
    return TaskStore(
        tasks=[
            Task(
                id=str(uuid4()),
                title="Welcome to your workspace",
                notes="Create your first task or adjust this starter item.",
                completed=False,
                category="Getting Started",
                priority="high",
                dueDate=today,
                dueTime=time(hour=9, minute=0),
                createdAt=nowUtc(),
                updatedAt=nowUtc(),
            ),
            Task(
                id=str(uuid4()),
                title="Review your next priority",
                notes="Use categories and due dates to keep the board tidy.",
                completed=False,
                category="Planning",
                priority="medium",
                dueDate=None,
                dueTime=None,
                createdAt=nowUtc(),
                updatedAt=nowUtc(),
            ),
        ]
    )


@dataclass(frozen=True)
class MongoCollections:
    users: Collection
    sessions: Collection
    tasks: Collection


class MongoDatabase:
    def __init__(self, uri: str, databaseName: str, userCollection: str, sessionCollection: str, taskCollection: str) -> None:
        self.client = MongoClient(uri, serverSelectionTimeoutMS=3000, tz_aware=True)
        self.client.admin.command("ping")
        database = self.client[databaseName]
        self.collections = MongoCollections(
            users=database[userCollection],
            sessions=database[sessionCollection],
            tasks=database[taskCollection],
        )
        self._ensureIndexes()

    def _ensureIndexes(self) -> None:
        self.collections.users.create_index([("email", ASCENDING)], unique=True)
        self.collections.sessions.create_index([("token", ASCENDING)], unique=True)
        self.collections.sessions.create_index([("expiresAt", ASCENDING)], expireAfterSeconds=0)
        self.collections.tasks.create_index([("ownerId", ASCENDING), ("createdAt", ASCENDING)])


class MongoAuthRepository:
    def __init__(self, database: MongoDatabase) -> None:
        self.collections = database.collections

    def createUser(self, payload: AuthRegisterPayload) -> SessionUser:
        currentTime = nowUtc()
        userId = str(uuid4())
        document = {
            "_id": userId,
            "name": payload.name,
            "email": payload.email,
            "passwordHash": generate_password_hash(payload.password),
            "createdAt": currentTime,
        }

        try:
            self.collections.users.insert_one(document)
        except DuplicateKeyError as error:
            raise ValueError("An account with that email already exists.") from error

        return self._documentToUser(document)

    def authenticateUser(self, payload: AuthLoginPayload) -> SessionUser:
        document = self.collections.users.find_one({"email": payload.email})
        if not document or not check_password_hash(str(document["passwordHash"]), payload.password):
            raise ValueError("Invalid email or password.")
        return self._documentToUser(document)

    def createSession(self, user: SessionUser) -> AuthenticatedSession:
        currentTime = nowUtc()
        token = secrets.token_urlsafe(32)
        expiresAt = currentTime + timedelta(days=sessionDurationDays)
        document = {
            "_id": str(uuid4()),
            "token": token,
            "userId": user.id,
            "createdAt": currentTime,
            "expiresAt": expiresAt,
        }
        self.collections.sessions.insert_one(document)
        return AuthenticatedSession(token=token, user=user, expiresAt=expiresAt)

    def getSession(self, token: str) -> AuthenticatedSession | None:
        if not token:
            return None

        document = self.collections.sessions.find_one({"token": token})
        if not document:
            return None

        expiresAt = document.get("expiresAt")
        if not isinstance(expiresAt, datetime):
            self.collections.sessions.delete_one({"_id": document["_id"]})
            return None

        normalizedExpiresAt = ensureUtcAwareDateTime(expiresAt)
        if normalizedExpiresAt <= nowUtc():
            self.collections.sessions.delete_one({"_id": document["_id"]})
            return None

        userDocument = self.collections.users.find_one({"_id": document["userId"]})
        if not userDocument:
            self.collections.sessions.delete_one({"_id": document["_id"]})
            return None

        return AuthenticatedSession(
            token=str(document["token"]),
            user=self._documentToUser(userDocument),
            expiresAt=normalizedExpiresAt,
        )

    def deleteSession(self, token: str) -> None:
        if token:
            self.collections.sessions.delete_one({"token": token})

    def deleteUser(self, userId: str) -> None:
        if userId:
            self.collections.users.delete_one({"_id": userId})
            self.collections.sessions.delete_many({"userId": userId})

    @staticmethod
    def _documentToUser(document: dict[str, object]) -> SessionUser:
        createdAt = document.get("createdAt")
        return SessionUser.model_validate(
            {
                "id": str(document["_id"]),
                "name": document["name"],
                "email": document["email"],
                "createdAt": ensureUtcAwareDateTime(createdAt) if isinstance(createdAt, datetime) else createdAt,
            }
        )


class MongoTaskRepository:
    def __init__(self, database: MongoDatabase) -> None:
        self.collection = database.collections.tasks

    def loadStore(self, userId: str) -> TaskStore:
        tasks = [self._documentToTask(document) for document in self.collection.find({"ownerId": userId})]
        return TaskStore(tasks=tasks)

    def saveStore(self, userId: str, store: TaskStore) -> None:
        taskIds = [task.id for task in store.tasks]

        for task in store.tasks:
            document = self._taskToDocument(userId, task)
            self.collection.replace_one({"_id": document["_id"], "ownerId": userId}, document, upsert=True)

        if taskIds:
            self.collection.delete_many({"ownerId": userId, "_id": {"$nin": taskIds}})
        else:
            self.collection.delete_many({"ownerId": userId})

    @staticmethod
    def _taskToDocument(userId: str, task: Task) -> dict[str, object]:
        document = task.model_dump(mode="json")
        document["_id"] = task.id
        document["ownerId"] = userId
        return document

    @staticmethod
    def _documentToTask(document: dict[str, object]) -> Task:
        taskData = {key: value for key, value in document.items() if key not in {"_id", "ownerId"}}
        for fieldName in ("createdAt", "updatedAt"):
            fieldValue = taskData.get(fieldName)
            if isinstance(fieldValue, datetime):
                taskData[fieldName] = ensureUtcAwareDateTime(fieldValue)
        taskData.setdefault("id", str(document["_id"]))
        return Task.model_validate(taskData)


class ApplicationServices:
    def __init__(self, authRepository: MongoAuthRepository, taskRepository: MongoTaskRepository) -> None:
        self.auth = authRepository
        self.tasks = taskRepository


@lru_cache(maxsize=1)
def getServices() -> ApplicationServices:
    mongoUri = os.getenv("MONGODB_URI", defaultMongoUri).strip() or defaultMongoUri
    mongoDbName = os.getenv("MONGODB_DB", defaultMongoDb).strip() or defaultMongoDb
    taskCollectionName = os.getenv("MONGODB_COLLECTION", defaultTaskCollection).strip() or defaultTaskCollection
    userCollectionName = os.getenv("MONGODB_USERS_COLLECTION", defaultUserCollection).strip() or defaultUserCollection
    sessionCollectionName = os.getenv("MONGODB_SESSIONS_COLLECTION", defaultSessionCollection).strip() or defaultSessionCollection

    database = MongoDatabase(
        mongoUri,
        mongoDbName,
        userCollectionName,
        sessionCollectionName,
        taskCollectionName,
    )
    app.logger.info("Using MongoDB for auth and task storage.")
    return ApplicationServices(MongoAuthRepository(database), MongoTaskRepository(database))


def ensureStore(userId: str) -> TaskStore:
    return getServices().tasks.loadStore(userId)


def saveStore(userId: str, store: TaskStore) -> None:
    getServices().tasks.saveStore(userId, store)


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


def responsePayload(store: TaskStore) -> dict[str, object]:
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


def sessionPayload(session: AuthenticatedSession) -> dict[str, object]:
    return {
        "user": session.user.model_dump(mode="json"),
        "expiresAt": session.expiresAt.isoformat(),
    }


def buildSessionResponse(session: AuthenticatedSession, statusCode: int = 200):
    response = jsonify(sessionPayload(session))
    response.status_code = statusCode
    response.set_cookie(
        sessionCookieName,
        session.token,
        httponly=True,
        samesite="Lax",
        secure=False,
        max_age=sessionDurationDays * 24 * 60 * 60,
    )
    return response


def clearSessionCookie(response):
    response.set_cookie(
        sessionCookieName,
        "",
        httponly=True,
        samesite="Lax",
        secure=False,
        expires=0,
        max_age=0,
    )
    return response


def currentSession() -> AuthenticatedSession | None:
    token = request.cookies.get(sessionCookieName, "")
    return getServices().auth.getSession(token)


def requireSession():
    session = currentSession()
    if session is None:
        return None, (jsonify({"error": "Authentication required."}), 401)
    return session, None


@app.errorhandler(Exception)
def handleUnexpectedError(error: Exception):
    if isinstance(error, HTTPException):
        return jsonify({"error": error.description}), error.code
    app.logger.exception("Unhandled application error: %s", error)
    return jsonify({"error": "Something went wrong on the server. Please try again."}), 500


@app.after_request
def addCorsHeaders(response):
    origin = request.headers.get("Origin", "")
    if origin in allowedDevOrigins:
        response.headers["Access-Control-Allow-Origin"] = origin
    else:
        response.headers["Access-Control-Allow-Origin"] = "http://localhost:3000"
    response.headers["Access-Control-Allow-Credentials"] = "true"
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


@app.get("/api/auth/session")
def getSession():
    session = currentSession()
    if session is None:
        return jsonify({"user": None}), 401
    return jsonify(sessionPayload(session))


@app.post("/api/auth/register")
def register():
    payload = request.get_json(silent=True) or {}
    user = None
    try:
        registerPayload = AuthRegisterPayload.model_validate(payload)
        user = getServices().auth.createUser(registerPayload)
    except ValidationError as error:
        return validationErrorResponse(error)
    except ValueError as error:
        return jsonify({"error": str(error)}), 409

    try:
        saveStore(user.id, defaultStore())
        session = getServices().auth.createSession(user)
    except Exception:
        if user is not None:
            getServices().auth.deleteUser(user.id)
        app.logger.exception("Failed to finish registration setup.")
        return jsonify({"error": "Could not finish account setup. Please try again."}), 500

    return buildSessionResponse(session, 201)


@app.post("/api/auth/login")
def login():
    payload = request.get_json(silent=True) or {}
    try:
        loginPayload = AuthLoginPayload.model_validate(payload)
        user = getServices().auth.authenticateUser(loginPayload)
        session = getServices().auth.createSession(user)
    except ValidationError as error:
        return validationErrorResponse(error)
    except ValueError as error:
        return jsonify({"error": str(error)}), 401

    return buildSessionResponse(session)


@app.post("/api/auth/logout")
def logout():
    token = request.cookies.get(sessionCookieName, "")
    getServices().auth.deleteSession(token)
    response = jsonify({"ok": True})
    return clearSessionCookie(response)


@app.get("/api/tasks")
def getTasks():
    session, errorResponse = requireSession()
    if errorResponse:
        return errorResponse
    return jsonify(responsePayload(ensureStore(session.user.id)))


@app.post("/api/tasks")
def createTask():
    session, errorResponse = requireSession()
    if errorResponse:
        return errorResponse

    store = ensureStore(session.user.id)
    payload = request.get_json(silent=True) or {}
    try:
        newTask = createTaskRecord(TaskCreate.model_validate(payload))
    except ValidationError as error:
        return validationErrorResponse(error)

    store.tasks.append(newTask)
    saveStore(session.user.id, store)
    return jsonify({"task": newTask.model_dump(mode="json"), **responsePayload(store)}), 201


@app.patch("/api/tasks/<taskId>")
def updateTask(taskId: str):
    session, errorResponse = requireSession()
    if errorResponse:
        return errorResponse

    store = ensureStore(session.user.id)
    payload = request.get_json(silent=True) or {}

    try:
        updates = TaskUpdate.model_validate(payload)
    except ValidationError as error:
        return validationErrorResponse(error)

    for index, task in enumerate(store.tasks):
        if task.id == taskId:
            updated = applyTaskUpdates(task, updates)
            store.tasks[index] = updated
            saveStore(session.user.id, store)
            return jsonify({"task": updated.model_dump(mode="json"), **responsePayload(store)})

    return jsonify({"error": "Task not found."}), 404


@app.delete("/api/tasks/<taskId>")
def deleteTask(taskId: str):
    session, errorResponse = requireSession()
    if errorResponse:
        return errorResponse

    store = ensureStore(session.user.id)
    nextTasks = [task for task in store.tasks if task.id != taskId]
    if len(nextTasks) == len(store.tasks):
        return jsonify({"error": "Task not found."}), 404

    store.tasks = nextTasks
    saveStore(session.user.id, store)
    return jsonify(responsePayload(store))


@app.delete("/api/tasks")
def clearCompleted():
    session, errorResponse = requireSession()
    if errorResponse:
        return errorResponse

    store = ensureStore(session.user.id)
    store.tasks = [task for task in store.tasks if not task.completed]
    saveStore(session.user.id, store)
    return jsonify(responsePayload(store))


if __name__ == "__main__":
    app.run(debug=True)
