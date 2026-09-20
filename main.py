"""
PyBin - Simple Pastebin Clone
Like pastebin.com: paste text, get link, share. No login. No API key.
"""
import os
import secrets
import string
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import Column, String, Text, DateTime, create_engine, delete as sql_delete
from sqlalchemy.orm import declarative_base, sessionmaker

app = FastAPI(title="PyBin", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Database ────────────────────────────────────────────────────────────────

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]

Base = declarative_base()

if DATABASE_URL:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
else:
    engine = create_engine("sqlite:///./pastes.db", connect_args={"check_same_thread": False})

Session = sessionmaker(bind=engine)


class Paste(Base):
    __tablename__ = "pastes"
    id = Column(String(12), primary_key=True)
    content = Column(Text, nullable=False)
    syntax = Column(String(30), default="text")
    title = Column(String(200), default="")
    created = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires = Column(DateTime, nullable=True)  # None = never
    views = Column(String(10), default="0")
    token = Column(String(50), nullable=False)  # edit/delete token


Base.metadata.create_all(engine)

# ─── Helpers ─────────────────────────────────────────────────────────────────

EXPIRES = {
    "never": None,
    "10m": 600,
    "1h": 3600,
    "1d": 86400,
    "1w": 604800,
    "1M": 2592000,
}


def new_id():
    chars = string.ascii_letters + string.digits
    return "".join(secrets.choice(chars) for _ in range(8))


def new_token():
    return secrets.token_urlsafe(24)


def clean_expired(db):
    """Delete expired pastes (called on every request)."""
    now = datetime.now(timezone.utc)
    db.execute(sql_delete(Paste).where(Paste.expires.isnot(None), Paste.expires <= now))
    db.commit()


def get_paste_or_404(db, paste_id):
    paste = db.query(Paste).filter(Paste.id == paste_id).first()
    if not paste:
        raise HTTPException(404, "Paste not found")
    if paste.expires and paste.expires <= datetime.now(timezone.utc):
        db.delete(paste)
        db.commit()
        raise HTTPException(404, "Paste not found")
    return paste


# ─── API (like Pastebin's API) ───────────────────────────────────────────────

class NewPaste(BaseModel):
    content: str
    syntax: str = "text"
    title: str = ""
    expires: str = "never"


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "PyBin"}


@app.post("/api/paste", status_code=201)
def create_paste(data: NewPaste):
    """Create a paste. Returns id, url, and admin token."""
    if not data.content.strip():
        raise HTTPException(400, "Content is empty")
    if data.expires not in EXPIRES:
        raise HTTPException(400, f"expires must be one of: {', '.join(EXPIRES)}")

    db = Session()
    try:
        clean_expired(db)
        paste_id = new_id()
        while db.query(Paste).filter(Paste.id == paste_id).first():
            paste_id = new_id()

        now = datetime.now(timezone.utc)
        seconds = EXPIRES[data.expires]
        paste = Paste(
            id=paste_id,
            content=data.content,
            syntax=data.syntax if data.syntax else "text",
            title=data.title[:200],
            created=now,
            expires=now + timedelta(seconds=seconds) if seconds else None,
            views="0",
            token=new_token(),
        )
        db.add(paste)
        db.commit()

        return {
            "id": paste.id,
            "url": f"/p/{paste.id}",
            "raw": f"/raw/{paste.id}",
            "token": paste.token,  # keep this to edit/delete
            "expires": paste.expires.isoformat() if paste.expires else "never",
        }
    finally:
        db.close()


@app.get("/api/paste/{paste_id}")
def read_paste(paste_id: str):
    """Get a paste by ID (increments view count)."""
    db = Session()
    try:
        clean_expired(db)
        paste = get_paste_or_404(db, paste_id)
        paste.views = str(int(paste.views) + 1)
        db.commit()
        return {
            "id": paste.id,
            "content": paste.content,
            "syntax": paste.syntax,
            "title": paste.title,
            "created": paste.created.isoformat(),
            "expires": paste.expires.isoformat() if paste.expires else None,
            "views": int(paste.views),
        }
    finally:
        db.close()


@app.get("/api/recent")
def recent_pastes():
    """List recent public pastes (no content)."""
    db = Session()
    try:
        clean_expired(db)
        pastes = db.query(Paste).order_by(Paste.created.desc()).limit(20).all()
        return [
            {
                "id": p.id,
                "title": p.title,
                "syntax": p.syntax,
                "created": p.created.isoformat(),
                "expires": p.expires.isoformat() if p.expires else None,
                "views": int(p.views),
            }
            for p in pastes
        ]
    finally:
        db.close()


@app.put("/api/paste/{paste_id}")
def edit_paste(paste_id: str, data: NewPaste, x_token: str = Header(default="")):
    """Edit a paste. Requires the token from creation."""
    if not x_token:
        raise HTTPException(401, "Token required")
    db = Session()
    try:
        paste = get_paste_or_404(db, paste_id)
        if not secrets.compare_digest(paste.token, x_token):
            raise HTTPException(403, "Invalid token")
        if not data.content.strip():
            raise HTTPException(400, "Content is empty")
        if data.expires not in EXPIRES:
            raise HTTPException(400, "Invalid expiration")

        now = datetime.now(timezone.utc)
        seconds = EXPIRES[data.expires]
        paste.content = data.content
        paste.syntax = data.syntax
        paste.title = data.title[:200]
        paste.expires = now + timedelta(seconds=seconds) if seconds else None
        db.commit()
        return {"id": paste.id, "updated": True}
    finally:
        db.close()


@app.delete("/api/paste/{paste_id}")
def remove_paste(paste_id: str, x_token: str = Header(default="")):
    """Delete a paste. Requires the token from creation."""
    if not x_token:
        raise HTTPException(401, "Token required")
    db = Session()
    try:
        paste = get_paste_or_404(db, paste_id)
        if not secrets.compare_digest(paste.token, x_token):
            raise HTTPException(403, "Invalid token")
        db.delete(paste)
        db.commit()
        return {"id": paste_id, "deleted": True}
    finally:
        db.close()


@app.get("/raw/{paste_id}", response_class=PlainTextResponse)
def raw_paste(paste_id: str):
    """Get raw text (like pastebin's raw view)."""
    db = Session()
    try:
        clean_expired(db)
        paste = get_paste_or_404(db, paste_id)
        return PlainTextResponse(paste.content)
    finally:
        db.close()


# ─── Frontend ────────────────────────────────────────────────────────────────

@app.get("/")
def index():
    return FileResponse("static/index.html")


@app.get("/p/{paste_id}")
def view_page(paste_id: str):
    return FileResponse("static/index.html")


app.mount("/static", StaticFiles(directory="static"), name="static")
