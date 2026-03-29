from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import pytest

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import app as app_module
from ApiRequest import ApiRequests, ApplicationServices, DuplicateEmailError
from Object import (
    AuthChangePasswordPayload,
    AuthLoginPayload,
    AuthRegisterPayload,
    AuthenticatedSession,
    SessionUser,
    TaskStore,
    nowUtc,
    sessionCookieName,
)


class FakeAuthRepository:
    def __init__(self) -> None:
        self.users_by_email: dict[str, dict[str, object]] = {}
        self.users_by_id: dict[str, dict[str, object]] = {}
        self.sessions_by_token: dict[str, AuthenticatedSession] = {}
        self.deleted_sessions: list[str] = []
        self.next_user_id = 1
        self.next_token_id = 1

    def createUser(self, payload: AuthRegisterPayload) -> SessionUser:
        if payload.email in self.users_by_email:
            raise DuplicateEmailError("An account with that email already exists.")

        user = SessionUser(
            id=f"user-{self.next_user_id}",
            name=payload.name,
            email=payload.email,
            createdAt=nowUtc(),
        )
        self.next_user_id += 1
        record = {
            "user": user,
            "password": payload.password,
        }
        self.users_by_email[user.email] = record
        self.users_by_id[user.id] = record
        return user

    def authenticateUser(self, payload: AuthLoginPayload) -> SessionUser:
        record = self.users_by_email.get(payload.email)
        if not record or record["password"] != payload.password:
            raise ValueError("Invalid email or password.")
        return record["user"]

    def changePassword(self, userId: str, payload: AuthChangePasswordPayload) -> None:
        record = self.users_by_id.get(userId)
        if not record or record["password"] != payload.currentPassword:
            raise ValueError("Current password is incorrect.")
        record["password"] = payload.newPassword

    def createSession(self, user: SessionUser) -> AuthenticatedSession:
        token = f"token-{self.next_token_id}"
        self.next_token_id += 1
        session = AuthenticatedSession(
            token=token,
            user=user,
            expiresAt=nowUtc() + timedelta(days=14),
        )
        self.sessions_by_token[token] = session
        return session

    def getSession(self, token: str) -> AuthenticatedSession | None:
        return self.sessions_by_token.get(token)

    def deleteSession(self, token: str) -> None:
        self.deleted_sessions.append(token)
        self.sessions_by_token.pop(token, None)

    def deleteUser(self, userId: str) -> None:
        record = self.users_by_id.pop(userId, None)
        if not record:
            return
        user = record["user"]
        self.users_by_email.pop(user.email, None)
        for token, session in list(self.sessions_by_token.items()):
            if session.user.id == userId:
                self.sessions_by_token.pop(token, None)


class FakeTaskRepository:
    def __init__(self) -> None:
        self.stores: dict[str, TaskStore] = {}

    def loadStore(self, userId: str) -> TaskStore:
        store = self.stores.get(userId)
        if store is None:
            return TaskStore()
        return TaskStore.model_validate(store.model_dump(mode="json"))

    def saveStore(self, userId: str, store: TaskStore) -> None:
        self.stores[userId] = TaskStore.model_validate(store.model_dump(mode="json"))


@pytest.fixture()
def client():
    auth = FakeAuthRepository()
    tasks = FakeTaskRepository()
    services = ApplicationServices(auth, tasks)

    original_api_requests = app_module.api_requests
    app_module.api_requests = ApiRequests(services_provider=lambda: services)
    app_module.app.config["TESTING"] = True

    with app_module.app.test_client() as test_client:
        yield test_client

    app_module.api_requests = original_api_requests


def test_health_endpoint_returns_ok(client) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


def test_auth_session_requires_cookie(client) -> None:
    response = client.get("/api/auth/session")

    assert response.status_code == 401
    assert response.get_json() == {"error": "Authentication required."}


def test_register_creates_session_cookie_and_returns_user(client) -> None:
    response = client.post(
        "/api/auth/register",
        json={"name": "Glenn", "email": "glenn@example.com", "password": "password123"},
    )

    body = response.get_json()
    assert response.status_code == 201
    assert body["user"]["email"] == "glenn@example.com"
    assert body["message"] == "Registration successful"
    assert sessionCookieName in response.headers.get("Set-Cookie", "")


def test_login_then_get_session_returns_authenticated_user(client) -> None:
    client.post(
        "/api/auth/register",
        json={"name": "Glenn", "email": "glenn@example.com", "password": "password123"},
    )
    login_response = client.post(
        "/api/auth/login",
        json={"email": "glenn@example.com", "password": "password123"},
    )

    assert login_response.status_code == 200

    session_response = client.get("/api/auth/session")

    assert session_response.status_code == 200
    assert session_response.get_json()["user"]["email"] == "glenn@example.com"


def test_task_crud_flow_works_with_authenticated_client(client) -> None:
    client.post(
        "/api/auth/register",
        json={"name": "Glenn", "email": "glenn@example.com", "password": "password123"},
    )

    create_response = client.post(
        "/api/tasks",
        json={
            "title": "Ship tests",
            "notes": "Cover the generated app routes",
            "category": "Work",
            "priority": "high",
            "dueDate": None,
            "dueTime": None,
            "completed": False,
        },
    )
    create_body = create_response.get_json()
    task_id = create_body["task"]["id"]

    assert create_response.status_code == 201
    assert create_body["task"]["notes"] == "Cover the generated app routes"

    list_response = client.get("/api/tasks")
    assert list_response.status_code == 200
    assert any(task["id"] == task_id for task in list_response.get_json()["tasks"])

    update_response = client.patch(
        f"/api/tasks/{task_id}",
        json={"notes": "Updated", "completed": True},
    )
    assert update_response.status_code == 200
    assert update_response.get_json()["task"]["completed"] is True

    clear_response = client.delete("/api/tasks")
    assert clear_response.status_code == 200
    assert clear_response.get_json()["summary"]["completed"] == 0

    delete_missing_response = client.delete(f"/api/tasks/{task_id}")
    assert delete_missing_response.status_code == 400
    assert delete_missing_response.get_json()["error"] == "Task not found."


def test_change_password_requires_confirmation_and_updates_login(client) -> None:
    client.post(
        "/api/auth/register",
        json={"name": "Glenn", "email": "glenn@example.com", "password": "password123"},
    )

    bad_response = client.post(
        "/api/auth/change-password",
        json={
            "currentPassword": "password123",
            "newPassword": "newpassword123",
            "confirmPassword": "different123",
        },
    )

    assert bad_response.status_code == 400
    assert bad_response.get_json()["error"] == "Value error, New password and confirmation do not match."

    ok_response = client.post(
        "/api/auth/change-password",
        json={
            "currentPassword": "password123",
            "newPassword": "newpassword123",
            "confirmPassword": "newpassword123",
        },
    )

    assert ok_response.status_code == 200
    assert ok_response.get_json()["message"] == "Password updated successfully"

    logout_response = client.post("/api/auth/logout")
    assert logout_response.status_code == 200

    failed_login = client.post(
        "/api/auth/login",
        json={"email": "glenn@example.com", "password": "password123"},
    )
    assert failed_login.status_code == 400

    new_login = client.post(
        "/api/auth/login",
        json={"email": "glenn@example.com", "password": "newpassword123"},
    )
    assert new_login.status_code == 200


def test_logout_clears_cookie_and_blocks_future_authenticated_requests(client) -> None:
    client.post(
        "/api/auth/register",
        json={"name": "Glenn", "email": "glenn@example.com", "password": "password123"},
    )

    logout_response = client.post("/api/auth/logout")

    assert logout_response.status_code == 200
    assert "Expires=Thu, 01 Jan 1970" in logout_response.headers.get("Set-Cookie", "")

    tasks_response = client.get("/api/tasks")
    assert tasks_response.status_code == 401
