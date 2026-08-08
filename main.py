import os
import secrets
import sqlite3
import string
from datetime import datetime

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="PyBin")
DB_PATH = os.getenv("DB_PATH", "pastes.db")

# ── DB ──
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pastes (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                language TEXT DEFAULT 'text',
                created_at TEXT
            )
        """)
        conn.commit()

init_db()

def gen_id(length: int = 8) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))

# ── API ──
from pydantic import BaseModel

class PasteIn(BaseModel):
    content: str
    language: str = "text"

@app.post("/api/pastes")
async def create_paste(data: PasteIn):
    pid = gen_id()
    now = datetime.utcnow().isoformat()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO pastes (id, content, language, created_at) VALUES (?,?,?,?)",
            (pid, data.content, data.language, now),
        )
        conn.commit()
    return {"id": pid, "content": data.content, "language": data.language, "created_at": now}

# ── Frontend ──
@app.get("/")
@app.get("/p/{paste_id}")
async def serve_spa(paste_id: str = None):
    return FileResponse("static/index.html")

app.mount("/static", StaticFiles(directory="static"), name="static")
