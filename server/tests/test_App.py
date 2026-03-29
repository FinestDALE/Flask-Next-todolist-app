from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

import pytest

# Add server to path so we can import App directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import App as server_module


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class FakeSession:
    token: str
    user: server_module.SessionUser
    expiresAt: datetime


class FakeAuthRepository:
    def __init__(self) -> None:
        self.usersByEmail: dict[str, dict[str, Any]] = {}
        self.sessionsByToken: dict[str, FakeSession] = {}
        self._nextUserId = 1
        self._nextSessionId = 1

    def createUser(self, payload: server_module.AuthRegisterPayload) -> server_module.SessionUser:
        if payload.email in self.usersByEmail:
            raise ValueError("An account with that email already exists.")

        user = server_module.SessionUser(
            id=f"user-{self._nextUserId}",
            name=payload.name,
            email=payload.email,
            createdAt=utc_now(),
        )
        self._nextUserId += 1
        self.usersByEmail[payload.email] = {"user": user, "password": payload.password}
        return user

    def authenticateUser(self, payload: server_module.AuthLoginPayload) -> server_module.SessionUser:
        record = self.usersByEmail.get(payload.email)
        if not record or record["password"] != payload.password:
            raise ValueError("Invalid email or password.")
        return record["user"]

    def changePassword(self, userId: str, payload: server_module.AuthChangePasswordPayload) -> None:
        for record in self.usersByEmail.values():
            if record["user"].id == userId:
                if record["password"] != payload.currentPassword:
                    raise ValueError("Current password is incorrect.")
                record["password"] = payload.newPassword
                return
        raise ValueError("Current password is incorrect.")

    def createSession(self, user: server_module.SessionUser) -> FakeSession:
        token = f"token-{self._nextSessionId}"
        self._nextSessionId += 1
        session = FakeSession(token=token, user=user, expiresAt=utc_now())
        self.sessionsByToken[token] = session
        return session

    def getSession(self, token: str) -> FakeSession | None:
        return self.sessionsByToken.get(token)

    def deleteSession(self, token: str) -> None:
        self.sessionsByToken.pop(token, None)

    def deleteUser(self, userId: str) -> None:
        for email, record in list(self.usersByEmail.items()):
            if record["user"].id == userId:
                self.usersByEmail.pop(email)
        for token, session in list(self.sessionsByToken.items()):
            if session.user.id == userId:
                self.sessionsByToken.pop(token)


class FakeTaskRepository:
    def __init__(self) -> None:
        self.stores: dict[str, server_module.TaskStore] = {}

    def loadStore(self, userId: str) -> server_module.TaskStore:
        store = self.stores.get(userId)
        if store is None:
            store = server_module.TaskStore()
            self.stores[userId] = store
        return server_module.TaskStore.model_validate(store.model_dump())

    def saveStore(self, userId: str, store: server_module.TaskStore) -> None:
        self.stores[userId] = server_module.TaskStore.model_validate(store.model_dump())


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch):
    fakeServices = server_module.ApplicationServices(FakeAuthRepository(), FakeTaskRepository())
    monkeypatch.setattr(server_module, "getServices", lambda: fakeServices)
    server_module.app.config["TESTING"] = True

    with server_module.app.test_client() as testClient:
        yield testClient


def register(client):
    return client.post(
        "/api/auth/register",
        json={
            "name": "Glenndel",
            "email": "glenndel@example.com",
            "password": "strongpass123",
        },
    )


def test_health_endpoint_returns_ok(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


def test_register_creates_session_and_starter_tasks(client):
    response = register(client)
    payload = response.get_json()

    assert response.status_code == 201
    assert payload["user"]["email"] == "glenndel@example.com"
    assert server_module.sessionCookieName in response.headers.get("Set-Cookie", "")

    tasksResponse = client.get("/api/tasks")
    tasksPayload = tasksResponse.get_json()

    assert tasksResponse.status_code == 200
    assert tasksPayload["summary"]["total"] == 2


def test_register_rejects_duplicate_email(client):
    firstResponse = register(client)
    secondResponse = register(client)

    assert firstResponse.status_code == 201
    assert secondResponse.status_code == 409
    assert secondResponse.get_json()["error"] == "An account with that email already exists."


def test_tasks_require_authentication(client):
    response = client.get("/api/tasks")

    assert response.status_code == 401
    assert response.get_json()["error"] == "Authentication required."


def test_login_allows_existing_user_to_access_tasks(client):
    register(client)
    logoutResponse = client.post("/api/auth/logout")
    assert logoutResponse.status_code == 200

    loginResponse = client.post(
        "/api/auth/login",
        json={
            "email": "glenndel@example.com",
            "password": "strongpass123",
        },
    )

    assert loginResponse.status_code == 200

    tasksResponse = client.get("/api/tasks")
    assert tasksResponse.status_code == 200


def test_change_password_updates_login_credentials(client):
    register(client)

    changeResponse = client.post(
        "/api/auth/change-password",
        json={
            "currentPassword": "strongpass123",
            "newPassword": "newstrongpass456",
            "confirmPassword": "newstrongpass456",
        },
    )

    assert changeResponse.status_code == 200
    assert changeResponse.get_json()["message"] == "Password updated successfully."

    logoutResponse = client.post("/api/auth/logout")
    assert logoutResponse.status_code == 200

    oldLoginResponse = client.post(
        "/api/auth/login",
        json={
            "email": "glenndel@example.com",
            "password": "strongpass123",
        },
    )
    assert oldLoginResponse.status_code == 401
    assert oldLoginResponse.get_json()["error"] == "Invalid email or password."

    newLoginResponse = client.post(
        "/api/auth/login",
        json={
            "email": "glenndel@example.com",
            "password": "newstrongpass456",
        },
    )
    assert newLoginResponse.status_code == 200


def test_change_password_rejects_wrong_current_password(client):
    register(client)

    response = client.post(
        "/api/auth/change-password",
        json={
            "currentPassword": "wrongpass123",
            "newPassword": "newstrongpass456",
            "confirmPassword": "newstrongpass456",
        },
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "Current password is incorrect."


def test_create_task_returns_json_payload(client):
    register(client)

    response = client.post(
        "/api/tasks",
        json={
            "title": "Finish dashboard polish",
            "category": "Work",
            "priority": "high",
            "dueDate": None,
            "dueTime": None,
        },
    )

    payload = response.get_json()

    assert response.status_code == 201
    assert payload["task"]["title"] == "Finish dashboard polish"
    assert payload["summary"]["total"] == 3


def test_ensure_utc_aware_datetime_converts_naive_value():
    naive = datetime(2026, 3, 26, 12, 0, 0)

    converted = server_module.ensureUtcAwareDateTime(naive)

    assert converted.tzinfo == timezone.utc
    assert converted.year == 2026
