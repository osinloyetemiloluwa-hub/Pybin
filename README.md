# PyBin

Simple pastebin clone. Like pastebin.com — no login, no API key, just paste and share.

## Features

- Paste text/code, get a shareable link
- Optional expiration: never, 10min, 1h, 1d, 1w, 1month
- Edit and delete with a token (given on creation, saved in browser)
- Raw text view
- Recent pastes list
- No login required
- Works on Render free tier

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/paste` | Create paste |
| GET | `/api/paste/{id}` | Get paste |
| GET | `/api/recent` | List recent |
| PUT | `/api/paste/{id}` | Edit (needs `X-Token` header) |
| DELETE | `/api/paste/{id}` | Delete (needs `X-Token` header) |
| GET | `/raw/{id}` | Raw text |

### Create a paste

```bash
curl -X POST https://your-app.onrender.com/api/paste \
  -H "Content-Type: application/json" \
  -d '{"content": "Hello world!", "syntax": "text", "expires": "never"}'
```

Response:
```json
{
  "id": "aB3xK9mL",
  "url": "/p/aB3xK9mL",
  "raw": "/raw/aB3xK9mL",
  "token": "xyz...",
  "expires": "never"
}
```

### Edit a paste

```bash
curl -X PUT https://your-app.onrender.com/api/paste/aB3xK9mL \
  -H "Content-Type: application/json" \
  -H "X-Token: xyz..." \
  -d '{"content": "Updated!", "expires": "1d"}'
```

## Deploy to Render (Free)

1. Push this code to GitHub
2. On Render: **New → PostgreSQL** (free tier)
3. **New → Web Service** → connect your repo
4. Render reads `render.yaml` automatically, or set:
   - Build: `pip install -r requirements.txt`
   - Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Add environment variable:
   - `DATABASE_URL` = your Postgres internal URL
6. Deploy!

**Note:** Without `DATABASE_URL`, it uses SQLite (fine for testing, but data resets on Render restart).

## Local Run

```bash
pip install -r requirements.txt
python main.py
# or: uvicorn main:app --reload
```

Open http://localhost:8000
