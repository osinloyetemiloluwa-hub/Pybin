import os
import secrets
import string
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, String, Text, DateTime, Integer, desc
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# Fix Render / Heroku postgres:// -> postgresql:// URL schema for SQLAlchemy 2.x
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./pybin.sqlite")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# If using PostgreSQL without explicit driver, SQLAlchemy 2.x defaults to 'psycopg' (v3).
# We have added 'psycopg[binary]' to requirements.txt to satisfy this.

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class PasteModel(Base):
    __tablename__ = "pastes"

    id = Column(String(12), primary_key=True, index=True)
    title = Column(String(200), nullable=False, default="Untitled")
    content = Column(Text, nullable=False)
    syntax = Column(String(50), nullable=False, default="plaintext")
    views = Column(String(10), nullable=False, default="0")  # Stored as string per original schema
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    edit_token = Column(String(32), nullable=False)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Pybin", description="Secure, minimalist pastebin")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="static")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def clean_expired(db: Session):
    now = datetime.now(timezone.utc)
    expired = db.query(PasteModel).filter(PasteModel.expires_at != None, PasteModel.expires_at < now).all()
    if expired:
        for p in expired:
            db.delete(p)
        db.commit()

class PasteCreate(BaseModel):
    title: str = Field(default="Untitled", max_length=200)
    content: str = Field(..., min_length=1)
    syntax: str = Field(default="plaintext", max_length=50)
    expiration: str = Field(default="never") # never, 10m, 1h, 1d, 1w

class PasteUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    content: Optional[str] = Field(None)
    syntax: Optional[str] = Field(None, max_length=50)
    edit_token: str

def generate_id(length=8):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/p/{paste_id}", response_class=HTMLResponse)
def read_paste_page(request: Request, paste_id: str):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/pastes", status_code=status.HTTP_201_CREATED)
def create_paste(payload: PasteCreate, db: Session = Depends(get_db)):
    clean_expired(db)
    
    paste_id = generate_id()
    while db.query(PasteModel).filter(PasteModel.id == paste_id).first():
        paste_id = generate_id()
        
    edit_token = secrets.token_hex(16)
    
    expires_at = None
    now = datetime.now(timezone.utc)
    from datetime import timedelta
    if payload.expiration == "10m":
        expires_at = now + timedelta(minutes=10)
    elif payload.expiration == "1h":
        expires_at = now + timedelta(hours=1)
    elif payload.expiration == "1d":
        expires_at = now + timedelta(days=1)
    elif payload.expiration == "1w":
        expires_at = now + timedelta(weeks=1)

    db_paste = PasteModel(
        id=paste_id,
        title=payload.title.strip() or "Untitled",
        content=payload.content,
        syntax=payload.syntax,
        views="0",
        expires_at=expires_at,
        edit_token=edit_token
    )
    db.add(db_paste)
    db.commit()
    db.refresh(db_paste)
    
    return {
        "id": db_paste.id,
        "title": db_paste.title,
        "syntax": db_paste.syntax,
        "expires_at": db_paste.expires_at.isoformat() if db_paste.expires_at else None,
        "created_at": db_paste.created_at.isoformat(),
        "edit_token": edit_token,
        "url": f"/p/{db_paste.id}"
    }

@app.get("/api/pastes/{paste_id}")
def get_paste(paste_id: str, db: Session = Depends(get_db)):
    clean_expired(db)
    paste = db.query(PasteModel).filter(PasteModel.id == paste_id).first()
    if not paste:
        raise HTTPException(status_code=404, detail="Paste not found or expired")
    
    # Safe view increment handling NULL views gracefully
    try:
        current_views = int(paste.views or "0")
    except ValueError:
        current_views = 0
    paste.views = str(current_views + 1)
    db.commit()
    
    return {
        "id": paste.id,
        "title": paste.title,
        "content": paste.content,
        "syntax": paste.syntax,
        "views": paste.views,
        "expires_at": paste.expires_at.isoformat() if paste.expires_at else None,
        "created_at": paste.created_at.isoformat()
    }

@app.delete("/api/pastes/{paste_id}")
def delete_paste(paste_id: str, payload: dict = {}, db: Session = Depends(get_db)):
    token = payload.get("edit_token")
    paste = db.query(PasteModel).filter(PasteModel.id == paste_id).first()
    if not paste:
        raise HTTPException(status_code=404, detail="Paste not found")
    
    if paste.edit_token != token:
        raise HTTPException(status_code=403, detail="Invalid edit token")
        
    db.delete(paste)
    db.commit()
    return {"status": "success", "message": "Paste deleted"}

@app.get("/api/recent")
def get_recent(db: Session = Depends(get_db)):
    clean_expired(db)
    pastes = db.query(PasteModel).order_by(desc(PasteModel.created_at)).limit(10).all()
    return [
        {
            "id": p.id,
            "title": p.title,
            "syntax": p.syntax,
            "views": p.views or "0",
            "created_at": p.created_at.isoformat()
        }
        for p in pastes
    ]
