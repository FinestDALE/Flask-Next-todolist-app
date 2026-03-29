# Todo App Architecture Guide

This document describes the architecture that the project should follow today.
It is written to match the current codebase, not the older manual Flask pattern.

## Overview

This project is a full-stack todo application with:

- a Next.js client in `client/`
- a Flask API in `server/`
- MongoDB for users, sessions, and tasks
- generated Flask routes built from business methods in `ApiRequest.py`

The most important architectural rule is this:

```text
ApiRequest.py defines the business actions
AppCreator.py generates the Flask runtime app
app.py is generated output and should not be edited manually
Object.py defines the shared data language
```

## High-Level Flow

```text
Developer edits ApiRequest.py methods and decorates them with @route_config
        |
        v
Developer runs: python server/AppCreator.py
        |
        v
AppCreator.py inspects decorated methods and generates server/app.py
        |
        v
Runtime starts from server/app.py
        |
        v
Client calls /api/* endpoints
        |
        v
Generated route handlers call ApiRequests business methods
        |
        v
Repositories read/write MongoDB
```

## Project Structure

```text
client/
  app/
    globals.css
    layout.tsx
    page.tsx

server/
  ApiRequest.py
  AppCreator.py
  Object.py
  app.py
  route_config.py
  requirements.txt
  pytest.ini
  tests/
    test_app.py

start-dev.bat
guide.md
MIGRATION_GUIDE.md
ARCHITECTURE_GUIDE.md
```

## Backend Architecture

### `server/route_config.py`

This file provides the `@route_config(...)` decorator.

Its job is simple:

- attach route metadata to an action method
- declare the HTTP method
- declare whether authentication is required
- declare whether a successful response should set a session cookie
- optionally provide a success message

The decorator is metadata only. It does not register Flask routes by itself.

### `server/ApiRequest.py`

This is the main application layer.

It contains:

- MongoDB connection setup
- repository classes
- service wiring
- task/session helper functions
- `ApiRequests`, the business action class used by the generator

`ApiRequests` methods should follow these rules:

- no `flask.request`
- no `flask.jsonify`
- no manual route registration
- explicit method parameters
- return plain Python data, usually `dict`
- rely on Pydantic models and repository helpers for validation and persistence

Example shape:

```python
@route_config(httpMethod="POST", jwtRequired=True, successMessage="Task created successfully")
def createTask(self, userId: str, title: str, notes: str = "") -> dict:
    ...
    return {"task": task.model_dump(mode="json"), **responsePayload(store)}
```

### `server/AppCreator.py`

This is a development-time code generator.

It does not run the Flask app directly.
Instead, it:

- imports `ApiRequests`
- finds methods decorated with `@route_config`
- reads their signatures
- maps each method to a route path
- generates `server/app.py`

The generator also centralizes HTTP concerns that should not live inside business methods:

- request JSON parsing
- cookie lookup
- auth/session checks
- response formatting
- success messages
- cookie setting for login/register
- cookie clearing for logout
- exception-to-HTTP-status mapping

### `server/app.py`

This file is generated output.

It is the actual Flask runtime entry point and should be treated as disposable build output:

- safe to regenerate
- not safe to hand-edit
- always derived from `ApiRequest.py` and `AppCreator.py`

It currently does these jobs:

- creates the Flask app
- configures CORS
- instantiates `ApiRequests`
- exposes `/api/*` routes
- handles auth/session cookie flow
- translates raised exceptions into JSON HTTP responses

### `server/Object.py`

This file is the domain model layer.

It contains:

- constants
- Pydantic models
- validation rules
- normalization helpers
- date/time helpers
- typed containers such as `MongoCollections`

This file should be the first place to edit when the data shape changes.

## Backend Data Model

### Auth and Session Models

Important models include:

- `SessionUser`
- `AuthenticatedSession`
- `AuthRegisterPayload`
- `AuthLoginPayload`
- `AuthChangePasswordPayload`

Important auth behavior:

- passwords are hashed with Werkzeug
- session tokens are stored in MongoDB
- sessions expire after `sessionDurationDays`
- the cookie name is `todo_session`

### Task Models

Important models include:

- `TaskBase`
- `Task`
- `TaskCreate`
- `TaskUpdate`
- `TaskStore`

Task fields currently used by both backend and frontend:

- `title`
- `notes`
- `completed`
- `category`
- `priority`
- `dueDate`
- `dueTime`
- `createdAt`
- `updatedAt`

Important note:

- the current contract uses `notes`, not `description`
- the current contract uses both `dueDate` and `dueTime`

## Persistence Layer

### MongoDB Collections

The backend uses three collections by default:

- `users`
- `sessions`
- `tasks`

Environment defaults come from `Object.py`:

```python
defaultMongoUri = "mongodb://127.0.0.1:27017"
defaultMongoDb = "todo_app"
defaultTaskCollection = "tasks"
defaultUserCollection = "users"
defaultSessionCollection = "sessions"
```

### `MongoAuthRepository`

Responsibilities:

- create user
- authenticate user
- change password
- create session
- fetch session by token
- delete session
- delete user

Important behavior:

- duplicate email raises `DuplicateEmailError`
- expired or invalid sessions are cleaned up
- session lookup loads the linked user

### `MongoTaskRepository`

Responsibilities:

- load a user task store
- save a user task store

Current storage model:

- tasks are stored as one document per task
- each task document includes `ownerId`
- the repository rebuilds a `TaskStore` from those task documents

This is important because some older docs described the tasks collection as one giant embedded array. That is not how the current code works.

## API Surface

All routes are prefixed with `/api`.

### Health

- `GET /api/health`

Returns:

```json
{
  "status": "ok",
  "time": "2026-03-29T15:15:26.958328+00:00"
}
```

### Auth

- `GET /api/auth/session`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `POST /api/auth/change-password`

Behavior:

- `register` creates a user, seeds starter tasks, creates a session, and sets the session cookie
- `login` authenticates and sets the session cookie
- `session` reads the session cookie and returns the authenticated user
- `logout` deletes the session and clears the cookie
- `change-password` requires authentication and validates `currentPassword`, `newPassword`, and `confirmPassword`

### Tasks

- `GET /api/tasks`
- `POST /api/tasks`
- `PATCH /api/tasks/<taskId>`
- `DELETE /api/tasks/<taskId>`
- `DELETE /api/tasks`

Behavior:

- all task routes require authentication
- task responses return normalized task data plus summary/category state
- create/update routes validate input through `TaskCreate` and `TaskUpdate`

## Request Lifecycle

### Authenticated Task Request

Example: `PATCH /api/tasks/<taskId>`

```text
Client sends request with session cookie
-> generated app.py route reads JSON body
-> generated app.py reads todo_session cookie
-> auth repository resolves the session
-> generated route injects current userId into ApiRequests.updateTask(...)
-> TaskUpdate validates the partial payload
-> task repository loads the user's tasks
-> task is updated and saved
-> generated route returns JSON response
```

### Login Request

```text
Client sends email/password
-> generated route extracts payload
-> ApiRequests.login validates via AuthLoginPayload
-> auth repository authenticates user
-> auth repository creates session
-> generated route sets todo_session cookie
-> response returns user + token + message
```

## Frontend Architecture

The frontend currently lives mostly in [page.tsx](c:/Users/glenndel/OneDrive/Desktop/Flask/Flask-Next-todolist-app/client/app/page.tsx).

It is a single client-side React page that manages:

- bootstrapping auth state
- loading task data
- auth forms
- task creation
- task editing
- filtering/search
- password change modal
- theme state

### Frontend Request Contract

The page uses a shared `request()` helper that:

- prefixes the base API URL
- sends `Content-Type: application/json`
- includes cookies with `credentials: "include"`
- parses JSON
- throws on non-OK responses

The server must therefore always return JSON for normal API usage.

### Frontend State Shape

Important frontend types include:

- `Task`
- `User`
- `ApiState`
- `ApiPayload`
- `SessionPayload`

The client expects:

- `notes`
- `priority`
- `dueDate`
- `dueTime`
- `summary.total`
- `summary.completed`
- `summary.open`
- `summary.dueToday`

Any backend contract change should be reflected carefully in both `Object.py` and `client/app/page.tsx`.

## Testing Architecture

Backend tests currently live in [test_app.py](c:/Users/glenndel/OneDrive/Desktop/Flask/Flask-Next-todolist-app/server/tests/test_app.py).

The tests use:

- Flask test client
- fake in-memory auth repository
- fake in-memory task repository
- dependency replacement by swapping `app.api_requests`

This means:

- tests do not require MongoDB
- tests exercise the generated Flask routes
- tests verify the current request/response contract

Current coverage includes:

- health endpoint
- auth-required session route
- register flow
- login + session restore
- task CRUD flow
- password change validation
- logout behavior

## Development Workflow

### When Changing the API

If you add or change an endpoint:

1. edit `server/ApiRequest.py`
2. update or add `@route_config(...)`
3. regenerate `server/app.py` with `python server/AppCreator.py`
4. update tests
5. run `pytest`

### When Changing Data Shape

If you add or change task/auth fields:

1. update `server/Object.py`
2. update `server/ApiRequest.py`
3. update `client/app/page.tsx`
4. regenerate `server/app.py` if method signatures changed
5. update tests

### When Changing Flask Runtime Behavior

If you want to change centralized route behavior such as:

- auth injection
- cookie policy
- exception mapping
- response wrapping
- route generation rules

edit `server/AppCreator.py`, then regenerate `server/app.py`.

## Run Commands

### Install Backend Dependencies

```powershell
cd server
python -m pip install -r requirements.txt
```

### Generate the Runtime App

```powershell
cd server
python AppCreator.py
```

### Run the Backend

```powershell
cd server
python app.py
```

### Run the Frontend

```powershell
cd client
npm install
npm run dev
```

### Run Both on Windows

```powershell
start-dev.bat
```

### Run Tests

```powershell
cd server
pytest -q
```

## Environment Variables

The backend supports:

```text
MONGODB_URI
MONGODB_DB
MONGODB_COLLECTION
MONGODB_USERS_COLLECTION
MONGODB_SESSIONS_COLLECTION
```

The frontend supports:

```text
NEXT_PUBLIC_API_BASE
```

## Common Rules

### Do

- edit `ApiRequest.py` for business behavior
- edit `Object.py` for data shape and validation
- edit `AppCreator.py` for generated Flask behavior
- regenerate `app.py` after route/signature changes
- treat tests as route-contract protection

### Do Not

- do not hand-edit `server/app.py`
- do not put `request` or `jsonify` in `ApiRequests` methods
- do not reintroduce manual `add_url_rule()` registration
- do not change frontend field names without changing the backend contract too

## Architecture Summary

If you want the shortest accurate mental model for this codebase, use this:

```text
Object.py defines the shapes
ApiRequest.py defines the business actions
AppCreator.py generates the HTTP layer
app.py runs the server
page.tsx consumes the API
test_app.py protects the contract
```
