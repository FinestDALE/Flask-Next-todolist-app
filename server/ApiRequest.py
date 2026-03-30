from __future__ import annotations

import os
import secrets
import sys
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from pymongo import ASCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError
from werkzeug.security import check_password_hash, generate_password_hash

SERVER_DIR = Path(__file__).resolve().parent
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from route_config import route_config
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

class DuplicateEmailError(Exception):
    """Raised when trying to register with an email that already exists."""
    pass

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
            raise DuplicateEmailError("An account with that email already exists.") from error
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
        "token": session.token,
    }


class ApiRequests:
    def __init__(self, services_provider=getServices) -> None:
        self._services_provider = services_provider

    @property
    def services(self) -> ApplicationServices:
        return self._services_provider()

    @route_config(httpMethod="GET", authRequired=False, routePath="/api/health")
    def health(self) -> dict:
        return {"status": "ok", "time": nowIso()}

    @route_config(
        httpMethod="GET",
        authRequired=False,
        permissionErrorStatusCode=401,
        routePath="/api/auth/session",
    )
    def getSession(self, token: str = "") -> dict:
        """Get current session from token (passed as cookie by AppCreator)."""
        session = self.services.auth.getSession(token)
        if session is None:
            raise PermissionError("Authentication required.")
        return sessionPayload(session)

    @route_config(
        httpMethod="POST",
        authRequired=False,
        createAccessToken=True,
        statusCode=201,
        successMessage="Registration successful",
        routePath="/api/auth/register",
    )
    def registerUser(self, name: str, email: str, password: str) -> dict:
        """Register a new user."""
        registerPayload = AuthRegisterPayload(name=name, email=email, password=password)
        user = self.services.auth.createUser(registerPayload)
        try:
            saveStore(self.services, user.id, defaultStore())
            session = self.services.auth.createSession(user)
        except Exception:
            self.services.auth.deleteUser(user.id)
            raise Exception("Could not finish account setup. Please try again.")
        return sessionPayload(session)

    @route_config(
        httpMethod="POST",
        authRequired=False,
        createAccessToken=True,
        successMessage="Login successful",
        routePath="/api/auth/login",
    )
    def login(self, email: str, password: str) -> dict:
        """Log in a user."""
        loginPayload = AuthLoginPayload(email=email, password=password)
        user = self.services.auth.authenticateUser(loginPayload)
        session = self.services.auth.createSession(user)
        return sessionPayload(session)

    @route_config(
        httpMethod="POST",
        authRequired=True,
        deleteCookie=True,
        successMessage="Logged out successfully",
        routePath="/api/auth/logout",
    )
    def logout(self, userId: str, token: str = "") -> dict:
        """Log out the current user."""
        self.services.auth.deleteSession(token)
        return {"ok": True}

    @route_config(
        httpMethod="POST",
        authRequired=True,
        successMessage="Password updated successfully",
        routePath="/api/auth/change-password",
    )
    def changePassword(self, userId: str, currentPassword: str, newPassword: str, confirmPassword: str) -> dict:
        """Change password for the current user."""
        changePasswordPayload = AuthChangePasswordPayload(
            currentPassword=currentPassword,
            newPassword=newPassword,
            confirmPassword=confirmPassword,
        )
        self.services.auth.changePassword(userId, changePasswordPayload)
        return {"ok": True}

    @route_config(httpMethod="GET", authRequired=True, routePath="/api/tasks")
    def getTasks(self, userId: str) -> dict:
        """Get all tasks for the current user."""
        return responsePayload(ensureStore(self.services, userId))

    @route_config(
        httpMethod="POST",
        authRequired=True,
        statusCode=201,
        successMessage="Task created successfully",
        routePath="/api/tasks",
    )
    def createTask(
        self,
        userId: str,
        title: str,
        notes: str = "",
        category: str = "",
        priority: str = "medium",
        dueDate: str | None = None,
        dueTime: str | None = None,
        completed: bool = False,
    ) -> dict:
        """Create a new task."""
        store = ensureStore(self.services, userId)
        newTask = createTaskRecord(
            TaskCreate(
                title=title,
                notes=notes,
                category=category,
                priority=priority,
                dueDate=dueDate,
                dueTime=dueTime,
                completed=completed,
            )
        )
        store.tasks.append(newTask)
        saveStore(self.services, userId, store)
        return {"task": newTask.model_dump(mode="json"), **responsePayload(store)}

    @route_config(
        httpMethod="PATCH",
        authRequired=True,
        successMessage="Task updated successfully",
        routePath="/api/tasks/<taskId>",
    )
    def updateTask(
        self,
        userId: str,
        taskId: str,
        title: str | None = None,
        notes: str | None = None,
        category: str | None = None,
        priority: str | None = None,
        dueDate: str | None = None,
        dueTime: str | None = None,
        completed: bool | None = None,
    ) -> dict:
        """Update an existing task."""
        store = ensureStore(self.services, userId)
        updates_data = {}
        if title is not None:
            updates_data["title"] = title
        if notes is not None:
            updates_data["notes"] = notes
        if category is not None:
            updates_data["category"] = category
        if priority is not None:
            updates_data["priority"] = priority
        if dueDate is not None:
            updates_data["dueDate"] = dueDate
        if dueTime is not None:
            updates_data["dueTime"] = dueTime
        if completed is not None:
            updates_data["completed"] = completed
        updates = TaskUpdate.model_validate(updates_data) if updates_data else TaskUpdate()
        
        for index, task in enumerate(store.tasks):
            if task.id == taskId:
                updated = applyTaskUpdates(task, updates)
                store.tasks[index] = updated
                saveStore(self.services, userId, store)
                return {"task": updated.model_dump(mode="json"), **responsePayload(store)}
        raise ValueError("Task not found.")

    @route_config(
        httpMethod="DELETE",
        authRequired=True,
        successMessage="Task deleted successfully",
        routePath="/api/tasks/<taskId>",
    )
    def deleteTask(self, userId: str, taskId: str) -> dict:
        """Delete an existing task."""
        store = ensureStore(self.services, userId)
        nextTasks = [task for task in store.tasks if task.id != taskId]
        if len(nextTasks) == len(store.tasks):
            raise ValueError("Task not found.")
        store.tasks = nextTasks
        saveStore(self.services, userId, store)
        return responsePayload(store)

    @route_config(
        httpMethod="DELETE",
        authRequired=True,
        successMessage="Completed tasks cleared successfully",
        routePath="/api/tasks",
    )
    def clearCompleted(self, userId: str) -> dict:
        """Clear all completed tasks."""
        store = ensureStore(self.services, userId)
        store.tasks = [task for task in store.tasks if not task.completed]
        saveStore(self.services, userId, store)
        return responsePayload(store)
