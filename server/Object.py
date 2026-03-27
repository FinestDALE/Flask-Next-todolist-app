from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Literal
from uuid import uuid4

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

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
allowedDevOrigins = {
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
}

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


class AuthChangePasswordPayload(BaseModel):
    currentPassword: str = Field(validation_alias=AliasChoices("currentPassword", "current_password"))
    newPassword: str = Field(validation_alias=AliasChoices("newPassword", "new_password"))
    confirmPassword: str = Field(validation_alias=AliasChoices("confirmPassword", "confirm_password"))

    @field_validator("currentPassword", "newPassword", "confirmPassword", mode="before")
    @classmethod
    def normalizePassword(cls, value: object) -> str:
        return str(value or "")

    @field_validator("currentPassword")
    @classmethod
    def validateCurrentPassword(cls, value: str) -> str:
        if not value:
            raise ValueError("Current password is required.")
        return value

    @field_validator("newPassword")
    @classmethod
    def validateNewPassword(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("New password must be at least 8 characters long.")
        return value

    @field_validator("confirmPassword")
    @classmethod
    def validateConfirmPassword(cls, value: str) -> str:
        if not value:
            raise ValueError("Please confirm your new password.")
        return value

    @model_validator(mode="after")
    def validatePasswordChange(self) -> "AuthChangePasswordPayload":
        if self.currentPassword == self.newPassword:
            raise ValueError("New password must be different from your current password.")
        if self.newPassword != self.confirmPassword:
            raise ValueError("New password and confirmation do not match.")
        return self


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
    users: object
    sessions: object
    tasks: object
