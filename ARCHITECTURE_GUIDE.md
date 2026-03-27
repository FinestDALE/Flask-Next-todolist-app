# Todo App Architecture Guide

This guide describes the architecture that matches the current app, not the old sales-system template. It is written around the real flow of this project: authentication first, then a per-user task dashboard backed by MongoDB.

## What This App Does

This app is a personal task dashboard with:

- Email/password registration and login
- Server-side session cookies
- Per-user task storage
- Task creation, editing, completion, deletion, and clearing
- Password change for authenticated users
- A single-page Next.js dashboard UI

## Core Architecture

The backend now follows a simple three-core structure:

```text
server.py        -> thin entrypoint / compatibility layer
AppCreator.py    -> app composition core
ApiRequest.py    -> request + service + repository flow
Object.py        -> data models, validation, shared constants/helpers
```

That maps to responsibilities like this:

```text
Browser UI
   -> fetch('/api/...')
Next.js page.tsx
   -> Flask app from AppCreator
ApiRequests methods
   -> services / repositories
MongoDB collections
```

## Why This Structure

This app does not need a large generated framework. It benefits more from a small, explicit architecture:

- `AppCreator.py` owns app creation and global Flask behavior
- `ApiRequest.py` owns application flow and persistence logic
- `Object.py` owns data shape, validation, and shared defaults
- `server.py` stays tiny so the app can be booted and tested consistently

This keeps the code easy to reason about and makes it clear where each change belongs.

## Request Flow

Here is the actual request lifecycle in this app:

```text
1. The user loads the Next.js page
2. The frontend checks /api/auth/session
3. If authenticated, the frontend requests /api/tasks
4. Flask receives the request through the app built by AppCreator
5. ApiRequests resolves the current session from the cookie
6. ApiRequests validates input using Pydantic models from Object.py
7. Repositories in ApiRequest.py read/write MongoDB
8. ApiRequests returns normalized JSON
9. The frontend updates local React state and re-renders
```

## Backend Layers

### 1. `server/AppCreator.py`

This is the composition root of the backend.

Responsibilities:

- Create the Flask app
- Register global error handling
- Register request hooks like CORS and `OPTIONS`
- Attach all API routes by calling `ApiRequests.register(app)`

Think of it as the shell of the backend. It should know how to assemble the app, but not contain business-specific task logic.

### 2. `server/ApiRequest.py`

This is the application layer.

Responsibilities:

- Define repositories:
  - `MongoDatabase`
  - `MongoAuthRepository`
  - `MongoTaskRepository`
- Define `ApplicationServices`
- Build cached services with `getServices()`
- Define request handlers in `ApiRequests`
- Translate validated input into repository operations
- Build HTTP responses and session cookies

This file is the main flow engine of the app.

Important sections:

- Database setup and indexes
- Auth repository methods:
  - create user
  - authenticate user
  - change password
  - create/get/delete session
- Task repository methods:
  - load a user task store
  - save a user task store
- Request handlers:
  - health
  - session
  - register
  - login
  - logout
  - change password
  - get/create/update/delete/clear tasks

### 3. `server/Object.py`

This is the model and validation layer.

Responsibilities:

- Define shared defaults and constants
- Define request payload models
- Define domain models
- Normalize and validate input
- Provide helper functions used across the backend

Important models:

- `Task`
- `TaskCreate`
- `TaskUpdate`
- `TaskStore`
- `SessionUser`
- `AuthRegisterPayload`
- `AuthLoginPayload`
- `AuthChangePasswordPayload`
- `AuthenticatedSession`

Important helpers:

- `ensureUtcAwareDateTime()`
- `validateDueDate()`
- `validateDueDateTime()`
- `defaultStore()`

## Entry Point

### `server/server.py`

This file should stay thin.

Responsibilities:

- Ensure local imports resolve cleanly
- Re-export important names for compatibility and tests
- Build `app` by calling `AppCreator(...).create_app()`
- Start the app in local development

This file is intentionally not where the architecture lives. It should remain the doorway, not the house.

## Frontend Architecture

The frontend is currently a single-page Next.js app in:

```text
client/app/page.tsx
```

### Frontend flow

The page owns:

- auth state
- task state
- filters and search
- create/edit task forms
- theme toggle
- account security dialog state

The frontend talks to the backend through a small local `request()` helper that:

- prefixes paths with `NEXT_PUBLIC_API_BASE`
- sends JSON
- includes cookies with `credentials: "include"`
- parses JSON responses
- normalizes API errors into thrown `Error` objects

### Current UI sections

The dashboard is organized around:

- auth screen for login/register
- top bar for refresh/theme/security/logout
- summary strip
- left sidebar for quick capture and filters
- center list for visible tasks
- right detail panel for task editing
- modal dialog for password change

## Data Flow By Feature

### Registration flow

```text
Frontend register form
-> POST /api/auth/register
-> AuthRegisterPayload validates input
-> MongoAuthRepository.createUser()
-> defaultStore() seeds starter tasks
-> session is created
-> cookie is returned
-> frontend loads tasks
```

### Login flow

```text
Frontend login form
-> POST /api/auth/login
-> AuthLoginPayload validates input
-> MongoAuthRepository.authenticateUser()
-> session is created
-> cookie is returned
-> frontend loads tasks
```

### Session restore flow

```text
Page load
-> GET /api/auth/session
-> session cookie is read
-> MongoAuthRepository.getSession()
-> frontend either stays signed out or loads tasks
```

### Task flow

```text
Create/update/delete task
-> authenticated endpoint
-> validate payload with TaskCreate or TaskUpdate
-> load store for current user
-> mutate store
-> save store for current user
-> return fresh task list + summary + categories
```

### Password change flow

```text
Security dialog submit
-> POST /api/auth/change-password
-> require active session
-> AuthChangePasswordPayload validates input
-> current password is verified
-> new password hash is stored
-> frontend shows success and closes dialog
```

## MongoDB Layout

This app currently uses three collections:

- `todo_app.users`
- `todo_app.sessions`
- `todo_app.tasks`

### Users

Stores:

- account id
- name
- email
- password hash
- created timestamp

### Sessions

Stores:

- session token
- user id
- created timestamp
- expiry timestamp

Session expiration is enforced with a TTL index on `expiresAt`.

### Tasks

Stores:

- task id
- owner id
- title
- notes
- category
- priority
- due date/time
- completion status
- created/updated timestamps

## Design Rules For Future Changes

To keep this architecture clean, use these rules:

### If you add or change data shape

Edit `server/Object.py`.

Examples:

- new task fields
- new auth payload fields
- validation rules
- defaults

### If you add or change request flow

Edit `server/ApiRequest.py`.

Examples:

- new endpoint
- new repository logic
- new auth flow
- new summary calculation

### If you add global Flask behavior

Edit `server/AppCreator.py`.

Examples:

- middleware-like hooks
- CORS policy
- error handling
- app factory setup

### If you need bootstrapping only

Edit `server/server.py`.

Examples:

- app startup
- compatibility exports
- local run behavior

## Frontend Change Rules

### If you change API usage

Update `client/app/page.tsx` request flow and local state transitions.

### If you change layout or styling

Update:

- `client/app/page.tsx`
- `client/app/globals.css`

### If the frontend starts growing

The next clean step would be:

```text
client/app/page.tsx
-> split into:
   - app/lib/api.ts
   - app/lib/auth.ts
   - app/components/auth/*
   - app/components/dashboard/*
   - app/components/tasks/*
   - app/components/account/*
```

That is not required yet, but it is the natural next architecture milestone.

## Testing Strategy

Current backend tests live in:

```text
server/tests/test_server.py
```

These tests validate:

- health endpoint
- registration
- duplicate registration protection
- auth-required task access
- login flow
- password change flow
- basic task creation
- datetime normalization

The tests patch `getServices()` so the app can be tested without real MongoDB access.

That is a good pattern and should be kept.

## Run Commands

### Backend

```powershell
cd server
py -3 -m pip install -r requirements.txt
$env:MONGODB_URI="mongodb://127.0.0.1:27017"
$env:MONGODB_DB="todo_app"
$env:MONGODB_COLLECTION="tasks"
py -3 -m flask --app server.py run
```

### Frontend

```powershell
cd client
cmd /c npm run dev
```

### Tests

```powershell
cd server
pytest
```

## Architecture Summary

If you remember only one thing, remember this:

```text
AppCreator builds the app
ApiRequest runs the app flow
Object defines the app language
server.py only starts the app
```

That is the architecture base for this project.
