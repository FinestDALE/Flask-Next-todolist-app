# Flask-Next-todolist-app

## Run both apps

From the project root on Windows:

```bat
start-dev.bat
```

That launches:
- Flask API at `http://127.0.0.1:5000`
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

Client:

```powershell
cd client
cmd /c npm run dev
```
