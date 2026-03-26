# Flask-Next-todolist-app

This project now includes:
- MongoDB-backed user registration and login
- Server-side session cookies for authentication
- Per-user task storage so each account sees its own board
- A redesigned Next.js interface with login/register and a cleaner dashboard

## Run both apps

From the project root on Windows:

```bat
start-dev.bat
```

That launches:
- Flask API at `http://localhost:5000`
- Next.js app at `http://localhost:3000`

## Run manually

Server:

```powershell
cd server
py -3 -m pip install -r requirements.txt
$env:MONGODB_URI="mongodb://127.0.0.1:27017"
$env:MONGODB_DB="todo_app"
$env:MONGODB_COLLECTION="tasks"
py -3 -m flask --app server.py run
```

MongoDB is required. The Flask server now reads and writes tasks only from `todo_app.tasks`.

Optional collection overrides:

```powershell
$env:MONGODB_USERS_COLLECTION="users"
$env:MONGODB_SESSIONS_COLLECTION="sessions"
```

The default collections are:
- `todo_app.tasks`
- `todo_app.users`
- `todo_app.sessions`

Run server tests with pytest:

```powershell
cd server
pytest
```

Client:

```powershell
cd client
cmd /c npm run dev
```
