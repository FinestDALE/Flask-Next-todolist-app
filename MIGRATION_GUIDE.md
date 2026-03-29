# Migration Guide

This guide explains the migration from the older manual Flask route pattern to the current generated `AppCreator` pattern used in this project.

It is meant to answer three questions:

1. what changed
2. why it changed
3. how to work correctly going forward

## Migration Summary

The backend has moved from:

- a hand-managed Flask route layer
- action methods that mixed HTTP concerns and business logic
- scattered response/error handling

to:

- a generated Flask runtime app
- action methods that focus on business logic only
- centralized route, cookie, auth, and error handling

## Before vs After

### Before

Old pattern characteristics:

- routes were wired manually
- business methods were tied directly to Flask request/response objects
- response formatting happened inside each handler
- cookie and auth flow could be duplicated across endpoints
- architecture docs tended to blur bootstrap code and application logic

Typical old code looked like this:

```python
def login(self):
    payload = request.get_json(silent=True) or {}
    ...
    return jsonify({...}), 200
```

### After

New pattern characteristics:

- route metadata lives on methods via `@route_config(...)`
- `AppCreator.py` generates the Flask route file
- `app.py` is generated output
- `ApiRequest.py` contains business logic
- `Object.py` contains models, validation, and shared constants

Typical new code looks like this:

```python
@route_config(
    httpMethod="POST",
    authRequired=False,
    createAccessToken=True,
    successMessage="Login successful",
    routePath="/api/auth/login",
)
def login(self, email: str, password: str) -> dict:
    payload = AuthLoginPayload(email=email, password=password)
    user = self.services.auth.authenticateUser(payload)
    session = self.services.auth.createSession(user)
    return sessionPayload(session)
```

## The New Source of Truth

These files now define the backend architecture:

- `server/Object.py`
- `server/route_config.py`
- `server/ApiRequest.py`
- `server/AppCreator.py`

This file is runtime output:

- `server/app.py`

That means:

- edit the source files above
- regenerate `server/app.py`
- never treat `server/app.py` as the primary place to implement business rules

## File-by-File Migration

### `server/route_config.py`

Added as the metadata layer for route generation.

Purpose:

- declare HTTP method
- declare auth requirement
- declare cookie-setting behavior
- declare success message
- optionally declare the generated route path

If a method should become an API endpoint, it should be decorated here.

Preferred metadata names now:

- `authRequired`
- `routePath`

`jwtRequired` is still supported for backward compatibility, but the app currently uses session-cookie auth and not a literal JWT decorator stack.

### `server/ApiRequest.py`

Refactored into the business action layer.

What changed:

- removed Flask request/response handling from action methods
- moved route behavior into generated handlers
- aligned method signatures with the real request payloads
- kept repository and service logic close to the action methods

Important current contract updates:

- tasks use `notes`, not `description`
- tasks support `priority`
- tasks support `dueDate` and `dueTime`
- password change expects `currentPassword`, `newPassword`, and `confirmPassword`
- logout deletes the active session token

### `server/AppCreator.py`

Changed from an app-construction concept into a code generator.

Current responsibilities:

- inspect `ApiRequests`
- find decorated methods
- map methods to route paths
- emit `server/app.py`
- centralize JSON parsing, cookie handling, auth checks, and error mapping
- centralize success payload and JSON error helpers

This file is now the place to change generated HTTP behavior.

### `server/app.py`

This is now generated and should be treated as build output.

Responsibilities at runtime:

- create the Flask app
- configure CORS
- instantiate `ApiRequests`
- expose `/api/*` handlers
- manage cookies and auth lookup
- return JSON responses

Important rule:

- do not manually edit `server/app.py`

If it looks wrong, fix:

- `server/ApiRequest.py`
- `server/AppCreator.py`

then regenerate it.

## Generated Route Behavior

The generated app currently handles:

- request JSON extraction
- path parameter extraction
- auth/session lookup from `todo_session`
- `401` when auth is missing
- `403` for explicit permission errors
- `400` for validation and value errors
- `409` for duplicate email
- setting cookie on login/register
- clearing cookie on logout

This is the biggest architectural shift in the migration:

HTTP behavior is now centralized instead of handwritten per action.

## API Contract Changes to Remember

These are the fields and flows that matter now.

### Auth

Register:

```json
{
  "name": "Glenn",
  "email": "glenn@example.com",
  "password": "password123"
}
```

Login:

```json
{
  "email": "glenn@example.com",
  "password": "password123"
}
```

Change password:

```json
{
  "currentPassword": "oldpassword",
  "newPassword": "newpassword123",
  "confirmPassword": "newpassword123"
}
```

### Tasks

Task payloads now align with the frontend and Pydantic models:

```json
{
  "title": "Ship tests",
  "notes": "Cover the generated app routes",
  "category": "Work",
  "priority": "high",
  "dueDate": null,
  "dueTime": null,
  "completed": false
}
```

## How to Add or Change an Endpoint Now

### Step 1: Edit `ApiRequest.py`

Create or modify a method on `ApiRequests`.

Rules:

- add `@route_config(...)`
- define explicit parameters
- use models from `Object.py`
- return plain data

### Step 2: Regenerate `app.py`

```powershell
cd server
python AppCreator.py
```

### Step 3: Test It

```powershell
cd server
pytest -q
```

### Step 4: Run the App

```powershell
cd server
python app.py
```

## What You Should Edit Going Forward

Edit `server/Object.py` when:

- adding fields
- changing validation
- changing defaults
- changing model aliases

Edit `server/ApiRequest.py` when:

- adding business behavior
- adding endpoints
- changing auth logic at the action level
- changing repository behavior

Edit `server/AppCreator.py` when:

- changing route generation
- changing centralized auth injection
- changing cookie behavior
- changing exception mapping
- changing route path generation

Edit `client/app/page.tsx` when:

- changing frontend API usage
- changing payload shape
- changing response expectations

Do not edit `server/app.py` except for temporary debugging, and even then it should be regenerated afterward.

## Testing Migration

The old tests were no longer present as runnable `.py` files, so the test layer was rebuilt around the generated app.

Current backend tests live in:

- `server/tests/test_app.py`

Current testing strategy:

- use Flask test client
- replace real services with in-memory fakes
- avoid requiring MongoDB for route tests
- validate the current generated route contract

Current coverage includes:

- health endpoint
- session auth requirement
- register flow
- login + session restore
- task CRUD flow
- password change flow
- logout behavior

Run tests with:

```powershell
cd server
pytest -q
```

## Common Migration Mistakes

### Mistake: editing `server/app.py`

Problem:

- your changes will be lost on regeneration

Correct approach:

- edit `ApiRequest.py` or `AppCreator.py`
- regenerate `app.py`

### Mistake: using Flask objects inside `ApiRequests`

Problem:

- mixes transport logic back into business logic

Correct approach:

- accept explicit method parameters
- return plain `dict`

### Mistake: changing frontend field names only

Problem:

- backend and frontend drift apart

Correct approach:

- update `Object.py`
- update `ApiRequest.py`
- update `page.tsx`
- update tests

### Mistake: forgetting to regenerate routes

Problem:

- method changes are not reflected in `app.py`

Correct approach:

```powershell
cd server
python AppCreator.py
```

## Operational Commands

Install backend dependencies:

```powershell
cd server
python -m pip install -r requirements.txt
```

Generate the app:

```powershell
cd server
python AppCreator.py
```

Run the backend:

```powershell
cd server
python app.py
```

Run tests:

```powershell
cd server
pytest -q
```

Run full dev workflow on Windows:

```powershell
start-dev.bat
```

## Final Migration State

The migration is considered complete when these statements are true:

- `ApiRequests` methods are business-only
- route metadata is declared with `@route_config`
- `AppCreator.py` generates the runtime app
- `server/app.py` is treated as generated code
- the frontend uses the current payload field names
- backend tests run against the generated app

## Short Version

If you only want the practical rule set, use this:

```text
Edit Object.py for shapes
Edit ApiRequest.py for behavior
Edit AppCreator.py for generated HTTP behavior
Generate app.py after route changes
Run pytest after backend changes
Do not hand-edit app.py
```
