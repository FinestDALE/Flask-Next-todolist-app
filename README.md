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
py -3 -m flask --app server.py run
```

Client:

```powershell
cd client
cmd /c npm run dev
```
