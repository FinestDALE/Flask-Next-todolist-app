from __future__ import annotations

import os
import secrets
import sys
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from flask import jsonify, request
from pydantic import ValidationError
from pymongo import ASCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError
from werkzeug.security import check_password_hash, generate_password_hash

SERVER_DIR = Path(__file__).resolve().parent
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from Object import (
    AuthChangePasswordPayload,
    AuthLoginPayload,
    AuthRegisterPayload,
    AuthenticatedSession,
    MongoCollections,
    SessionUser,
    Task,
    TaskCreate,
    TaskStore,
    TaskUpdate,
    defaultMongoDb,
    defaultMongoUri,
    defaultSessionCollection,
    defaultStore,
    defaultTaskCollection,
    defaultUserCollection,
    ensureUtcAwareDateTime,
    nowIso,
    nowUtc,
    sessionCookieName,
    sessionDurationDays,
)


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

    def changePassword(self, userId: str, payload: AuthChangePasswordPayload) -> None:
        document = self.collections.users.find_one({"_id": userId})
        if not document or not check_password_hash(str(document["passwordHash"]), payload.currentPassword):
            raise ValueError("Current password is incorrect.")
        self.collections.users.update_one(
            {"_id": userId},
            {"$set": {"passwordHash": generate_password_hash(payload.newPassword)}},
        )

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
        self.collection: Collection = database.collections.tasks

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
    return ApplicationServices(MongoAuthRepository(database), MongoTaskRepository(database))


def ensureStore(services: ApplicationServices, userId: str) -> TaskStore:
    return services.tasks.loadStore(userId)


def saveStore(services: ApplicationServices, userId: str, store: TaskStore) -> None:
    services.tasks.saveStore(userId, store)


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


class ApiRequests:
    def __init__(self, services_provider=getServices) -> None:
        self._services_provider = services_provider

    @property
    def services(self) -> ApplicationServices:
        return self._services_provider()

    def currentSession(self) -> AuthenticatedSession | None:
        token = request.cookies.get(sessionCookieName, "")
        return self.services.auth.getSession(token)

    def requireSession(self):
        session = self.currentSession()
        if session is None:
            return None, (jsonify({"error": "Authentication required."}), 401)
        return session, None

    def register(self, app) -> None:
        app.add_url_rule("/api/health", "health", self.health, methods=["GET"])
        app.add_url_rule("/api/auth/session", "getSession", self.getSession, methods=["GET"])
        app.add_url_rule("/api/auth/register", "register", self.registerUser, methods=["POST"])
        app.add_url_rule("/api/auth/login", "login", self.login, methods=["POST"])
        app.add_url_rule("/api/auth/logout", "logout", self.logout, methods=["POST"])
        app.add_url_rule("/api/auth/change-password", "changePassword", self.changePassword, methods=["POST"])
        app.add_url_rule("/api/tasks", "getTasks", self.getTasks, methods=["GET"])
        app.add_url_rule("/api/tasks", "createTask", self.createTask, methods=["POST"])
        app.add_url_rule("/api/tasks", "clearCompleted", self.clearCompleted, methods=["DELETE"])
        app.add_url_rule("/api/tasks/<taskId>", "updateTask", self.updateTask, methods=["PATCH"])
        app.add_url_rule("/api/tasks/<taskId>", "deleteTask", self.deleteTask, methods=["DELETE"])

    def health(self):
        return jsonify({"status": "ok", "time": nowIso()})

    def getSession(self):
        session = self.currentSession()
        if session is None:
            return jsonify({"user": None}), 401
        return jsonify(sessionPayload(session))

    def registerUser(self):
        payload = request.get_json(silent=True) or {}
        user = None
        try:
            registerPayload = AuthRegisterPayload.model_validate(payload)
            user = self.services.auth.createUser(registerPayload)
        except ValidationError as error:
            return validationErrorResponse(error)
        except ValueError as error:
            return jsonify({"error": str(error)}), 409

        try:
            saveStore(self.services, user.id, defaultStore())
            session = self.services.auth.createSession(user)
        except Exception:
            if user is not None:
                self.services.auth.deleteUser(user.id)
            return jsonify({"error": "Could not finish account setup. Please try again."}), 500

        return buildSessionResponse(session, 201)

    def login(self):
        payload = request.get_json(silent=True) or {}
        try:
            loginPayload = AuthLoginPayload.model_validate(payload)
            user = self.services.auth.authenticateUser(loginPayload)
            session = self.services.auth.createSession(user)
        except ValidationError as error:
            return validationErrorResponse(error)
        except ValueError as error:
            return jsonify({"error": str(error)}), 401
        return buildSessionResponse(session)

    def logout(self):
        token = request.cookies.get(sessionCookieName, "")
        self.services.auth.deleteSession(token)
        response = jsonify({"ok": True})
        return clearSessionCookie(response)

    def changePassword(self):
        session, errorResponse = self.requireSession()
        if errorResponse:
            return errorResponse

        payload = request.get_json(silent=True) or {}
        try:
            changePasswordPayload = AuthChangePasswordPayload.model_validate(payload)
            self.services.auth.changePassword(session.user.id, changePasswordPayload)
        except ValidationError as error:
            return validationErrorResponse(error)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        return jsonify({"ok": True, "message": "Password updated successfully."})

    def getTasks(self):
        session, errorResponse = self.requireSession()
        if errorResponse:
            return errorResponse
        return jsonify(responsePayload(ensureStore(self.services, session.user.id)))

    def createTask(self):
        session, errorResponse = self.requireSession()
        if errorResponse:
            return errorResponse

        store = ensureStore(self.services, session.user.id)
        payload = request.get_json(silent=True) or {}
        try:
            newTask = createTaskRecord(TaskCreate.model_validate(payload))
        except ValidationError as error:
            return validationErrorResponse(error)

        store.tasks.append(newTask)
        saveStore(self.services, session.user.id, store)
        return jsonify({"task": newTask.model_dump(mode="json"), **responsePayload(store)}), 201

    def updateTask(self, taskId: str):
        session, errorResponse = self.requireSession()
        if errorResponse:
            return errorResponse

        store = ensureStore(self.services, session.user.id)
        payload = request.get_json(silent=True) or {}
        try:
            updates = TaskUpdate.model_validate(payload)
        except ValidationError as error:
            return validationErrorResponse(error)

        for index, task in enumerate(store.tasks):
            if task.id == taskId:
                updated = applyTaskUpdates(task, updates)
                store.tasks[index] = updated
                saveStore(self.services, session.user.id, store)
                return jsonify({"task": updated.model_dump(mode="json"), **responsePayload(store)})
        return jsonify({"error": "Task not found."}), 404

    def deleteTask(self, taskId: str):
        session, errorResponse = self.requireSession()
        if errorResponse:
            return errorResponse

        store = ensureStore(self.services, session.user.id)
        nextTasks = [task for task in store.tasks if task.id != taskId]
        if len(nextTasks) == len(store.tasks):
            return jsonify({"error": "Task not found."}), 404

        store.tasks = nextTasks
        saveStore(self.services, session.user.id, store)
        return jsonify(responsePayload(store))

    def clearCompleted(self):
        session, errorResponse = self.requireSession()
        if errorResponse:
            return errorResponse

        store = ensureStore(self.services, session.user.id)
        store.tasks = [task for task in store.tasks if not task.completed]
        saveStore(self.services, session.user.id, store)
        return jsonify(responsePayload(store))
