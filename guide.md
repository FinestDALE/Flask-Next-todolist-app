# Guide: How to Apply `AppCreator.py` from InternSampleApp to the Todolist Project

## What You Did Wrong

You wrote a **simple app factory** (78 lines) that just creates a Flask app and hardcodes a template string for `App.py`. That's not what `AppCreator.py` is.

## What `AppCreator.py` Actually Is

`AppCreator.py` in the InternSampleApp is a **code generator** (589 lines). It does NOT create the Flask app at runtime. Instead, you **run it once** and it **generates the `app.py` file** by reading the methods in `ApiRequests.py`.

Here's the flow:

```
Developer writes action methods in ApiRequests.py with @route_config decorators
         |
         v
Developer runs: python server/AppCreator.py
         |
         v
AppCreator reads each method, inspects its:
  - @route_config decorator (httpMethod, jwtRequired, etc.)
  - Parameters and type hints
         |
         v
AppCreator GENERATES app.py with Flask route code for every method
         |
         v
app.py is the actual Flask server entry point (never edit manually)
```

## What You Need to Do (Step by Step)

### Step 1: Create `route_config.py`

Copy `route_config.py` from InternSampleApp into this project's `server/` folder. This is the decorator that goes on every action method. It attaches metadata like `httpMethod`, `jwtRequired`, `successMessage` to each function.

Adapt it for this project — remove the `roleAccess` and MongoDB/User import parts since this todolist app doesn't have roles.

### Step 2: Restructure `ApiRequests.py`

Right now, `ApiRequests` has methods that directly handle Flask `request`/`response` objects (calling `request.get_json()`, returning `jsonify(...)`, etc.). **That's wrong for the AppCreator pattern.**

In the AppCreator pattern, action methods should:
- **NOT** import or use `flask.request` or `flask.jsonify`
- **NOT** build HTTP responses themselves
- Just contain **business logic** and **return plain data** (dicts, Pydantic models, lists)
- Be decorated with `@route_config(...)`

**Example — current (wrong):**
```python
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
```

**Example — what it should look like:**
```python
@route_config(
    httpMethod='POST',
    jwtRequired=False,
    createAccessToken=True,
    successMessage='Login successful'
)
def login(self, email: str, password: str) -> dict:
    loginPayload = AuthLoginPayload.model_validate({"email": email, "password": password})
    user = self.services.auth.authenticateUser(loginPayload)
    session = self.services.auth.createSession(user)
    return {"user": session.user.model_dump(mode="json"), "token": session.token}
```

Notice:
- Parameters are **explicitly listed** in the function signature with **type hints** (not extracted from `request.get_json()` inside the function)
- The decorator has all the route metadata
- The method returns **plain data**, not a Flask response
- Error handling (`try/except`) is NOT in the method — AppCreator generates that in `app.py`

### Step 3: Copy and Adapt `AppCreator.py`

Copy the real `AppCreator.py` from InternSampleApp. Then adapt it:

1. **Remove PubSub stuff** — this project has no Pub/Sub. Remove all `appPubSub` references, `PubSubRequests` imports, and the `APP_PUBSUB_*` config.

2. **Remove TypeScript generation** — this project's Next.js client doesn't use generated `ServerRequests.ts`. Remove `generateTSFile()`, `generateTypeScriptSchemas()`, and all the TS helper methods. (You can add this back later if needed.)

3. **Update imports** — the InternSampleApp imports `from AppConfig import AppConfig` and other files that don't exist here. Update the `APP_IMPORTS` and `APP_FLASK_CONFIG` lists to match what this project actually uses.

4. **Update the `__main__` block** — it should only call `generateAPI('app')`, not TS or PubSub generation.

### Step 4: Verify the Generated `app.py`

After adapting, run:
```bash
python server/AppCreator.py
```

This should generate a new `server/app.py`. Open it and verify:
- Every `@route_config` method from `ApiRequests` has a corresponding `@app.route(...)` function
- Methods with `jwtRequired=True` have `@jwt_required()` decorator
- Methods with a `userId` parameter + `jwtRequired=True` have the check: `if userId != current_user`
- Parameters are extracted from `request.get_json()`
- Responses are wrapped in `ApiResponse`
- Error handling is present (PermissionError -> 403, Exception -> 400)

### Step 5: Delete the old manual route code

The whole `register()` method in `ApiRequests` (the one with all the `app.add_url_rule(...)` calls) should be **removed**. AppCreator generates the routes now — you don't register them manually anymore.

## Key Things to Remember

| Concept | Wrong (what you did) | Correct (what InternSampleApp does) |
|---|---|---|
| `AppCreator.py` purpose | Runtime app factory | Offline code generator |
| When it runs | Every time the server starts | Once, when developer changes routes |
| `app.py` | Written by hand | **Generated** — never edit manually |
| `ApiRequests` methods | Handle request/response directly | Pure business logic + `@route_config` |
| Route registration | Manual `add_url_rule()` | Auto-generated by AppCreator |
| Error handling | Written in each method | Generated by AppCreator |
| JWT checks | Not present | Auto-generated for `userId` params |

## Files You Need to Touch

1. **Create**: `server/route_config.py` (copy + adapt from InternSampleApp)
2. **Rewrite**: `server/AppCreator.py` (copy + adapt from InternSampleApp)
3. **Refactor**: `server/ApiRequest.py` -> action methods with `@route_config`, no Flask imports in methods
4. **Delete**: `server/App.py` (will be regenerated by AppCreator as `server/app.py`)

## How to Test

1. Run `python server/AppCreator.py` — it should generate `server/app.py` without errors
2. Run `python server/app.py` — the server should start
3. All existing endpoints should still work (test with the frontend or `curl`)
4. Run the existing tests: `cd server && pytest`
