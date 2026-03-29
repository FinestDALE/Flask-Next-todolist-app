# Todo App Architecture Guide

This guide describes the architecture that matches the current app. It is written around the real flow of this project: authentication first, then a per-user task dashboard backed by MongoDB.

## What This App Does

This app is a personal task management dashboard with:

- **Authentication**: Email/password registration and login with secure password hashing
- **Session Management**: Server-side session tokens stored in MongoDB with 14-day expiration
- **Per-user Storage**: Each authenticated user has their own isolated task store in MongoDB
- **Task Operations**: Create, read, update, delete tasks, plus bulk clear completed tasks
- **Task Metadata**: Title, notes/description, priority (low/medium/high), category, due date/time, completion status, creation/update timestamps
- **Account Security**: Password change for authenticated users
- **Frontend**: Single-page Next.js (React) dashboard UI with real-time updates

## Core Architecture

The backend follows a simple four-file structure:

```text
server.py        -> thin entrypoint and Flask app instantiation
AppCreator.py    -> Flask app composition, CORS, and global routing
ApiRequest.py    -> request handlers, repositories, and service layer
Object.py        -> Pydantic models, validation, data defaults, and helpers
```

## Technology Stack

**Backend:**
- Flask (3.0+) - Web framework
- Pydantic (2.7+) - Data validation and serialization
- PyMongo (4.8+) - MongoDB driver
- Werkzeug - Password hashing (bcrypt-compatible)
- Flask-CORS - Cross-Origin Resource Sharing

**Frontend:**
- Next.js (TypeScript) - React-based framework
- React Hooks - State management (no Redux/Context API)
- CSS Modules - Styling

**Database:**
- MongoDB - NoSQL document database
- Collections: `users`, `sessions`, `tasks` (in `todo_app` database by default)

## Why This Structure

This app prioritizes clarity and simplicity:

- **AppCreator.py**: Handles Flask setup, CORS configuration, and route registration - the "infrastructure" layer
- **ApiRequest.py**: Contains all request handlers, repositories, and services - the "application flow" layer
- **Object.py**: Defines data shapes, validates input, and centralizes constants - the "domain" layer
- **server.py**: Instantiates the app and provides a consistent entry point for local dev and testing

This approach makes it clear where each responsibility belongs and keeps business logic separate from infrastructure.

## API Endpoints

All endpoints are prefixed with `/api`:

### Health & Session
- `GET /api/health` - Returns `{"status": "ok", "time": ISO8601}`
- `GET /api/auth/session` - Returns user session; 401 if not authenticated

### Authentication
- `POST /api/auth/register` - Create account and start session
  - Body: `{name, email, password}`
  - Response: 201 with session cookie and user data
- `POST /api/auth/login` - Authenticate and start session
  - Body: `{email, password}`
  - Response: 200 with session cookie and user data
- `POST /api/auth/logout` - End session and clear cookie
  - Response: 200 with cleared session cookie
- `POST /api/auth/change-password` - Update password (requires auth)
  - Body: `{currentPassword, newPassword}`
  - Response: 200 on success, 400 if current password wrong

### Tasks (all require authentication)
- `GET /api/tasks` - Fetch all tasks for user
  - Response: `{tasks, summary, categories}`
- `POST /api/tasks` - Create new task
  - Body: Task fields (title required, others optional)
  - Response: 201 with new task and updated store
- `PATCH /api/tasks/<taskId>` - Update specific task
  - Body: Partial task fields (all optional)
  - Response: 200 with updated task and store, 404 if not found
- `DELETE /api/tasks/<taskId>` - Delete specific task
  - Response: 200 with updated store, 404 if not found
- `DELETE /api/tasks` - Clear all completed tasks
  - Response: 200 with updated store

## Request Lifecycle

Here's how a typical request flows through the system:

1. Browser makes request to `/api/tasks`
2. **AppCreator** routes request to correct handler in **ApiRequests**
3. **ApiRequests** extracts session token from cookies
4. **MongoAuthRepository** validates token and loads user from MongoDB
5. **ApiRequests** validates input JSON using Pydantic models from **Object.py**
6. **MongoTaskRepository** reads/writes task data to MongoDB
7. **Object** helpers normalize and transform data
8. **ApiRequests** returns JSON response with set-cookie headers if needed
9. Frontend receives response and updates local React state

## Backend Components

### 1. `server/AppCreator.py` - Flask Setup

**Purpose**: Composes the Flask application and configures global middleware.

**Responsibilities**:
- Creates Flask app instance
- Configures CORS (Cross-Origin Resource Sharing) for allowed frontend origins
- Disables JSON key sorting for predictable output
- Registers all routes by calling `ApiRequests.register(app)`

**Key Methods**:
- `create_app()` - Builds and returns configured Flask app
- `build_app_file_content()` - Generates the code for `app.py` (helper for bootstrapping)

**Allowed CORS Origins** (from Object.py):
```
http://localhost:3000
http://127.0.0.1:3000
http://localhost:3001
http://127.0.0.1:3001
```

This file should stay focused on infrastructure concerns, not business logic.

### 2. `server/ApiRequest.py` - Application Logic

**Purpose**: Handles all request/response logic, database access, and business rules.

**Key Classes**:

#### `MongoDatabase`
Manages MongoDB connection and ensures indexes:
- Creates/maintains indexes on `email` (unique), `token` (unique), `expiresAt` (TTL)
- Pings MongoDB on startup to verify connectivity
- Exposes `MongoCollections` with references to users, sessions, tasks collections

#### `MongoAuthRepository`
Authentication and session management:
- `createUser(payload)` - Register new user, returns SessionUser
- `authenticateUser(payload)` - Validate credentials
- `changePassword(userId, payload)` - Update password
- `createSession(user)` - Generate 14-day session token, store in MongoDB
- `getSession(token)` - Load session, validate expiration, return AuthenticatedSession
- `deleteSession(token)` - Clear session on logout
- `deleteUser(userId)` - Remove user and all sessions

#### `MongoTaskRepository`
Task persistence (manages entire task store per user):
- `loadUserStore(userId)` - Fetch all user tasks as TaskStore
- `saveUserStore(userId, store)` - Write entire task store to MongoDB

#### `ApplicationServices`
Caches repositories for a request:
- `auth` - MongoAuthRepository instance
- `tasks` - MongoTaskRepository instance

#### `ApiRequests`
HTTP request handlers:
- Validates session from cookies
- Implements all `/api/` endpoints
- Returns normalized JSON responses
- Sets/clears session cookies

**Helper Functions**:
- `buildSummary(tasks)` - Calculate total and completed count
- `buildSessionResponse(session, statusCode)` - Create response with session cookie
- `clearSessionCookie(response)` - Expire session cookie
- `createTaskRecord(payload)` - Generate new Task with UUID and timestamps
- `applyTaskUpdates(current, updates)` - Merge updates into existing task
- `ensureStore(services, userId)` - Load or create empty task store
- `saveStore(services, userId, store)` - Persist task store to MongoDB
- `responsePayload(store)` - Format tasks/summary/categories for JSON
- `validationErrorResponse(error)` - Format Pydantic validation errors as JSON
- `nextCacheKey(offset)` - Generate cache key for pagination

**MongoDB Collections Schema**:

**users** (unique index on email):
```json
{
  "_id": "uuid",
  "name": "string",
  "email": "string (unique)",
  "passwordHash": "bcrypt hash",
  "createdAt": "datetime"
}
```

**sessions** (unique index on token, TTL index on expiresAt):
```json
{
  "_id": "uuid",
  "token": "string (unique)",
  "userId": "uuid",
  "createdAt": "datetime",
  "expiresAt": "datetime (auto-expires after 14 days)"
}
```

**tasks** (compound index on ownerId + createdAt):
```json
{
  "_id": "uuid",
  "ownerId": "uuid",
  "tasks": [
    {
      "id": "uuid",
      "title": "string",
      "notes": "string",
      "completed": "boolean",
      "category": "string",
      "priority": "low|medium|high",
      "dueDate": "date (optional)",
      "dueTime": "time (optional)",
      "createdAt": "datetime",
      "updatedAt": "datetime"
    }
  ]
}
```

### 3. `server/Object.py` - Data Models & Validation

**Purpose**: Defines data shapes, validation rules, and shared constants.

**Key Constants**:
```python
defaultMongoUri = "mongodb://127.0.0.1:27017"
defaultMongoDb = "todo_app"
defaultTaskCollection = "tasks"
defaultUserCollection = "users"
defaultSessionCollection = "sessions"
sessionCookieName = "todo_session"
sessionDurationDays = 14
defaultTitle = "Untitled task"
defaultCategory = "General"
defaultPriority = "medium"
```

**Pydantic Models** (inherit from `BaseModel` for validation):

#### `TaskBase`
Base fields shared by Task, TaskCreate, TaskUpdate:
- `title: str` - Task name (required for creates)
- `notes: str` - Description/notes
- `completed: bool` - Completion status
- `category: str` - Category grouping
- `priority: "low"|"medium"|"high"` - Priority level
- `dueDate: date | None` - Optional due date
- `dueTime: time | None` - Optional due time

Validators normalize input:
- Text fields: stripped and non-empty
- Category: defaults to "General" if empty
- Priority: lowercased, defaults to "medium"
- Due fields: mapped from snake_case or camelCase aliases

#### `Task` (extends `TaskBase`)
Complete task record with metadata:
- All TaskBase fields
- `id: str` - UUID
- `createdAt: datetime` - Creation timestamp (UTC)
- `updatedAt: datetime` - Last update timestamp (UTC)

Validators ensure title is non-empty.

#### `TaskCreate` (extends `TaskBase`)
Input model for creating tasks - same as TaskBase but title is required.
Validates due date is not in the past.

#### `TaskUpdate` (extends `TaskBase`)
Input model for partial updates - all fields optional.

#### `TaskStore`
Wrapper for user's complete set of tasks:
```python
@dataclass
class TaskStore:
    tasks: list[Task]
```

#### `SessionUser`
Minimal user info in session:
- `id: str` - User ID
- `name: str` - Display name
- `email: str` - Email address
- `createdAt: datetime` - Account creation time

#### `AuthenticatedSession`
Complete session info returned after login/register:
- `token: str` - Session token
- `user: SessionUser` - User info
- `expiresAt: datetime` - UTC expiration time

#### Auth Payload Models
- `AuthRegisterPayload` - name, email, password for registration
- `AuthLoginPayload` - email, password for login
- `AuthChangePasswordPayload` - currentPassword, newPassword

**Helper Functions**:

**Date/Time**:
- `nowUtc()` - Get current UTC datetime
- `nowIso()` - Get current time as ISO 8601 string
- `ensureUtcAwareDateTime(value)` - Ensure datetime has UTC timezone

**Text Normalization**:
- `normalizeTextValue(value, allowNone=False)` - Strip whitespace, return empty string or None
- `normalizePriorityValue(value, allowNone=False)` - Lowercase, default to "medium"
- `normalizeDueValue(value)` - Convert empty string to None
- `normalizeEmailValue(value)` - Lowercase and strip

**Validation**:
- `validateDueDate(value)` - Ensure date is today or later
- `validateDueDateTime(dueDate, dueTime)` - Ensure both or neither are set, time not in past
- `fallbackValue(value, default, allowNone=False)` - Use default if empty

**Data Structures**:
- `MongoCollections` - Dataclass wrapping user/session/task collections
- `Priority` - Type alias for priority levels

### 4. `server/server.py` - Entry Point

**Purpose**: Provides a consistent launch point for the Flask app.

**Responsibilities**:
- Set up Python path so imports resolve correctly
- Import and re-export key names (AppCreator, ApiRequests, Object items)
- Create Flask app by instantiating `AppCreator`
- Export `app` for WSGI servers (e.g., Gunicorn)
- Run Flask dev server with debug enabled if executed directly

**Why keep it thin?**
- Makes it easy to test (can import and use `app` object)
- Makes it easy to deploy (WSGI servers can find the `app` object)
- Makes local development consistent (always `python server.py`)
- Ensures architecture lives in ApiRequest/AppCreator, not here

**How to run**:
```bash
cd server
python server.py              # Local dev (debug mode)
# or
flask --app server.py run    # Flask CLI (better for watching)
```

**Environment Variables**:
```bash
MONGODB_URI="mongodb://127.0.0.1:27017"              # MongoDB connection string
MONGODB_DB="todo_app"                                 # Database name
MONGODB_COLLECTION="tasks"                           # Default tasks collection
MONGODB_USERS_COLLECTION="users"                     # Optional override
MONGODB_SESSIONS_COLLECTION="sessions"               # Optional override
```

## Frontend Architecture

The frontend is a single-page Next.js 15+ application written in TypeScript/React.

**Location**: `client/app/page.tsx` (main component)

**Technology**:
- Next.js 15+ with TypeScript
- React 18+ Hooks (useState, useEffect, useMemo, useRef)
- Server-side rendering disabled (`"use client"`)
- CSS Modules for styling
- No external state management (Redux/Context not needed for this scale)

### Frontend State

The main page component manages:
```typescript
{
  // Authentication
  user: User | null,
  isLoading: boolean,
  
  // Tasks
  tasks: Task[],
  categories: string[],
  summary: { total: number, completed: number },
  
  // UI
  filterCategory: string,
  searchTerm: string,
  showCreateForm: boolean,
  showSecurityDialog: boolean,
  theme: "light" | "dark",
  
  // Editing
  editingTaskId: string | null,
  editFormData: Partial<Task>
}
```

### API Communication

Single `request()` helper function:
- Prepends API base URL from `NEXT_PUBLIC_API_BASE` environment variable
- Sets `Content-Type: application/json`
- Includes cookies with `credentials: "include"`
- Parses JSON responses
- Converts HTTP errors to thrown `Error` objects

### Data Types

**User**:
```typescript
{
  id: string;
  name: string;
  email: string;
  createdAt: string; // ISO 8601
}
```

**Task**:
```typescript
{
  id: string;
  title: string;
  notes: string;
  completed: boolean;
  category: string;
  priority: "low" | "medium" | "high";
  dueDate: string | null; // ISO date
  dueTime: string | null; // HH:mm format
  createdAt: string; // ISO 8601
  updatedAt: string; // ISO 8601
}
```

**ApiState** (response format):
```typescript
{
  tasks: Task[];
  summary: { total: number; completed: number };
  categories: string[];
}
```

### Frontend Flow

1. Component mounts → fetch `/api/auth/session` to restore session
2. If authenticated → fetch `/api/tasks` to load user's tasks
3. User can:
   - Create task → `POST /api/tasks` → merge response into state
   - Update task → `PATCH /api/tasks/:id` → replace task in state
   - Delete task → `DELETE /api/tasks/:id` → remove from state
   - Clear completed → `DELETE /api/tasks` → filter local state
   - Change password → `POST /api/auth/change-password` → show confirmation
4. Every state change causes re-render (React's batch updates)
5. Theme preference persisted to localStorage

### UI Sections

- **Auth Screen**: Login/register forms (shown if not authenticated)
- **Top Bar**: Refresh, theme toggle, security/account options, logout button
- **Summary Strip**: "5 tasks, 2 completed"
- **Left Sidebar**: 
  - Quick capture form
  - Category filter
  - Search input
- **Task List**: 
  - Shows filtered/searched tasks
  - Checkbox to complete
  - Click to edit details
  - Priority/due date indicators
  - Delete button
- **Security Dialog**: Password change form (modal)
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

## Development Workflow

### Local Development Setup

1. **Install MongoDB** locally or use MongoDB Atlas connection string
2. **Backend**:
   ```bash
   cd server
   py -3 -m pip install -r requirements.txt
   $env:MONGODB_URI="mongodb://127.0.0.1:27017"
   $env:MONGODB_DB="todo_app"
   py -3 -m flask --app server.py run
   ```
   Backend runs on `http://localhost:5000`

3. **Frontend**:
   ```bash
   cd client
   npm install
   npm run dev
   ```
   Frontend runs on `http://localhost:3000`

4. **Both together**:
   ```bash
   start-dev.bat    # Windows batch file that launches both in parallel
   ```

### Making Changes

**Backend change? Edit:**
- `server/ApiRequest.py` for request handlers
- `server/Object.py` for data models/constants
- `server/AppCreator.py` for Flask configuration
- `server/tests/test_server.py` for new tests

**Frontend change? Edit:**
- `client/app/page.tsx` for components/logic
- `client/app/globals.css` for styling
- `client/next.config.ts` for build config

**MongoDB schema/collection change?**
Only if necessary — consider how `MongoDatabase._ensureIndexes()` will handle the migration.

### Testing Locally

**Backend tests**:
```bash
cd server
pytest              # Run all tests
pytest -v           # Verbose output
pytest test_server.py -k test_name    # Run specific test
```

**Frontend**:
- Use browser DevTools
- Check Network tab for API requests
- Use React DevTools extension

### Common Local Issues

- **MongoDB connection refused?** Ensure MongoDB is running on localhost:27017
- **CORS errors?** Frontend must run on localhost:3000 or 3001 (see allowedDevOrigins)
- **Session cookie not set?** Ensure `credentials: "include"` is in fetch options
- **"Module not found"?** Reinstall: `pip install -r requirements.txt` or `npm install`
- **Port 5000 already in use?** Use `flask --app server.py run --port 5001`

## Deployment Considerations

### Backend Deployment

For production (Gunicorn, Docker, or serverless):

1. Set environment variables for production MongoDB:
   ```bash
   MONGODB_URI="mongodb+srv://user:pass@cluster.mongodb.net/"
   MONGODB_DB="todo_app_prod"
   ```

2. Use a WSGI server like Gunicorn:
   ```bash
   gunicorn -w 4 -b 0.0.0.0:5000 server:app
   ```

3. Consider:
   - SSL/HTTPS (secure=True in set_cookie)
   - Session cookie SameSite policy (currently Lax)
   - CORS allowed origins (update allowedDevOrigins)
   - MongoDB authentication and network access
   - Rate limiting on auth endpoints
   - Password requirements/complexity

### Frontend Deployment

Deploy `client/` to a static host (Vercel, Netlify, etc.):

1. Build:
   ```bash
   npm run build
   ```

2. Set `NEXT_PUBLIC_API_BASE` to production API URL
3. Deploy build output

### MongoDB Deployment

Use MongoDB Atlas (cloud) or self-hosted:

- Ensure TTL index on `sessions` collection expires old sessions
- Create unique index on `users.email` and `sessions.token`
- Consider backup strategy
- Keep enough disk space for task growth

## Performance Notes

### Bottlenecks to Watch

- **Fetching tasks**: Currently loads entire task store in one query. Fine for <10k tasks per user.
- **Updating tasks**: Writes entire store. Acceptable for todo apps; consider pagination if store grows large.
- **MongoDB indexes**: Properly indexed on ownerId + createdAt for task queries
- **Frontend re-renders**: React batches updates; should be fast for <1000 tasks

### Optimization Strategies (if needed)

- **Pagination**: Add `limit` and `offset` parameters to GET /api/tasks
- **Caching**: Add ETag or Last-Modified headers to task responses
- **Compression**: Enable gzip in Flask/Nginx
- **Database**: Use MongoDB aggregation pipeline for complex queries
- **Frontend**: Lazy-load task details, virtual scrolling for large lists

## Architecture Summary

If you remember only one thing, remember this:

```text
AppCreator builds the app
ApiRequest runs the app flow
Object defines the app language
server.py only starts the app
```

### File Responsibilities

| File | Role |
|------|------|
| `server.py` | Bootstrap ONLY |
| `AppCreator.py` | Flask setup ONLY |
| `ApiRequest.py` | All business logic |
| `Object.py` | All data shapes |
| `client/app/page.tsx` | React component + state |
| `tests/test_server.py` | Backend validation |

### Data Flow Summary

```
Browser Request
    ↓
Flask (AppCreator)
    ↓
ApiRequests (handler)
    ↓
Repository (MongoAuthRepository / MongoTaskRepository)
    ↓
MongoDB (collections)
    ↓
Object (Pydantic models for validation)
    ↓
JSON Response → Browser
    ↓
React state update → render
```

