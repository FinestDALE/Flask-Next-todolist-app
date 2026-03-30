# AppCreator & route_config Comparison: InternSampleApp vs Todolist

> **Tip:** Press `Ctrl + Shift + V` in VS Code to open the Markdown preview for a properly formatted view of the tables below.

---

## `route_config.py`

### Decorator Parameters

| Parameter | InternSampleApp | Todolist |
|---|:---:|:---:|
| `httpMethod` | Yes | Yes |
| `jwtRequired` | Yes | Yes |
| `authRequired` | -- | Yes (new) |
| `createAccessToken` | Yes | Yes |
| `successMessage` | Yes | Yes |
| `roleAccess` | Yes | -- |
| `statusCode` | -- | Yes (new) |
| `deleteCookie` | -- | Yes (new) |
| `permissionErrorStatusCode` | -- | Yes (new) |
| `routePath` | -- | Yes (new) |

### Decorator Behavior

| Behavior | InternSampleApp | Todolist |
|---|---|---|
| **How metadata is stored** | Direct attributes: `func.httpMethod` | Dict: `func.route_config["httpMethod"]` |
| **Validation** | Inside decorator, at import time | None -- moved to AppCreator |
| **Runtime wrapper (`@functools.wraps`)** | Yes -- does role-access checking at runtime | No -- pure metadata, no runtime behavior |
| **GET/HEAD param enforcement** | Yes -- raises error if method has params | No |
| **`createAccessToken` whitelist** | Only allowed on `loginWithGoogle`, `devLogin` | No restriction |
| **Role-based access control** | Yes -- `user.checkIfAuthorized(roleAccess)` | Not supported |

---

## `AppCreator.py`

### Core Comparison

| Aspect | InternSampleApp | Todolist |
|---|---|---|
| **Lines of code** | ~583 | 252 |
| **Auth system** | JWT (`flask_jwt_extended`) | Cookie-based sessions |
| **Route path convention** | Auto from function name: `/{functionName}` | Explicit via config: `routePath="/api/tasks/<taskId>"` |
| **Response envelope** | `ApiResponse` Pydantic model | Ad-hoc `build_api_response()` / `json_error()` |
| **ApiRequests instantiation** | Fresh per request: `ApiRequests().fn(...)` | Singleton at module level: `api_requests.fn(...)` |
| **Reads metadata via** | `getattr(func, 'httpMethod')` | `func.route_config["httpMethod"]` |

### Code Generation Features

| Feature | InternSampleApp | Todolist |
|---|:---:|:---:|
| Flask route generation (`app.py`) | Yes | Yes |
| PubSub route generation (`appPubSub.py`) | Yes | No |
| TypeScript client (`ServerRequests.ts`) | Yes | No |
| TypeScript schemas (Pydantic -> JSON -> TS) | Yes | No |

### Code Structure

| Aspect | InternSampleApp | Todolist |
|---|---|---|
| **Output assembly** | Separate methods: `_imports()` + `_flask_config()` + `_all_functions_code()` + `_main_function_block()` | Single f-string template in `generate_app_code()` |
| **Imports/config** | Class-level lists: `APP_IMPORTS`, `APP_FLASK_CONFIG` | Inline in the f-string |
| **Method discovery** | Walks `__mro__` across multiple action classes | `inspect.getmembers()` on a single class |
| **Validation** | `_validate_route_meta()` -- checks httpMethod, jwtRequired, createAccessToken | `_validate_route_config()` -- checks httpMethod, auth+token conflict, routePath, statusCode, permissionErrorStatusCode |

---

## Key Architectural Differences

### 1. Metadata pattern is fundamentally different

InternSampleApp stores metadata as **direct function attributes**:
```python
func.httpMethod = 'POST'
func.jwtRequired = True
```

Todolist stores it as a **single dict**:
```python
func.route_config = {"httpMethod": "POST", "jwtRequired": True, ...}
```

This means the AppCreator reads metadata differently too.

### 2. `route_config.py` does double duty in InternSampleApp

In InternSampleApp, it's both metadata storage AND a runtime wrapper (role-access checking with `@functools.wraps`). In the todolist, it's just metadata -- no runtime behavior at all.

### 3. No `ApiResponse` model

InternSampleApp uses a Pydantic `ApiResponse` class for a consistent response envelope. The todolist uses raw `jsonify()` with ad-hoc dict shapes.

### 4. The todolist added config params that don't exist in InternSampleApp

`statusCode`, `deleteCookie`, `permissionErrorStatusCode`, `routePath`. These were created to solve the hardcoded-method-name problem, which is a valid solution, but it diverges from the shared pattern.

### 5. Route naming convention is different

InternSampleApp: route = function name (`/getMySales`). Todolist: explicit REST paths (`/api/tasks/<taskId>`). This is why `routePath` was added -- but this breaks the convention where AppCreator derives everything from the function alone.
