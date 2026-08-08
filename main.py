import os
import secrets
import string
from datetime import datetime

from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import PlainTextResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, String, Integer
from sqlalchemy.orm import declarative_base, sessionmaker

# ── Config ──
DATABASE_URL = os.getenv("DATABASE_URL")
MAX_SIZE = int(os.getenv("MAX_SIZE", "0"))  # 0 = unlimited

# ── DB ──
Base = declarative_base()

class Paste(Base):
    __tablename__ = "pastes"
    id = Column(String, primary_key=True)
    content = Column(String, nullable=False)
    language = Column(String, default="text")
    created_at = Column(String)
    views = Column(Integer, default=0)
    delete_token = Column(String)

# Neon / PostgreSQL or SQLite fallback
if DATABASE_URL:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
else:
    engine = create_engine("sqlite:///pastes.db", connect_args={"check_same_thread": False})

Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)

# ── App ──
app = FastAPI(title="PyBin v5")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def gen_id(length: int = 8) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))

def gen_token(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))

# ── Schemas ──
class PasteIn(BaseModel):
    content: str
    language: str = "text"

class PasteUpdate(BaseModel):
    content: str
    language: str = "text"

# ── Helpers ──
def paste_to_dict(p):
    return {
        "id": p.id,
        "content": p.content,
        "language": p.language,
        "created_at": p.created_at,
        "views": p.views,
    }

# ── API ──
from urllib.parse import parse_qs  # Add this at the top
from fastapi import Request  # Make sure this is imported

@app.post("/api/pastes")
async def create_paste(request: Request):
    content = ""
    language = "text"
    max_size = 0
    
    content_type = request.headers.get("content-type", "")
    
    if "application/json" in content_type:
        try:
            body = await request.json()
            content = body.get("content", "")
            language = body.get("language", "text")
            max_size = body.get("max_size", 0)
        except Exception:
            pass
    else:
        # Form data or raw body
        try:
            form = await request.form()
            content = form.get("content", "")
            language = form.get("language", "text")
            max_size = int(form.get("max_size", 0) or 0)
        except Exception:
            try:
                raw = await request.body()
                text = raw.decode()
                parsed = parse_qs(text)
                content = parsed.get("content", [""])[0]
                language = parsed.get("language", ["text"])[0]
                max_size = int(parsed.get("max_size", [0])[0] or 0)
            except Exception:
                pass
    
    if not content:
        raise HTTPException(status_code=422, detail="content is required")
    
    check_size(content, max_size)
    
    db = SessionLocal()
    pid = gen_id()
    delete_token = gen_token()
    now = datetime.utcnow().isoformat()
    
    paste = Paste(
        id=pid,
        content=content,
        language=language,
        created_at=now,
        views=0,
        delete_token=delete_token
    )
    db.add(paste)
    db.commit()
    db.close()
    
    return {
        "success": True,
        "data": {
            "id": pid,
            "url": f"https://pybin.onrender.com/p/{pid}",
            "raw_url": f"https://pybin.onrender.com/raw/{pid}",
            "download_url": f"https://pybin.onrender.com/download/{pid}",
            "delete_token": delete_token,
            "language": language,
            "created_at": now,
        }
    }


@app.put("/api/pastes/{paste_id}")
async def update_paste(paste_id: str, request: Request, x_delete_token: str = Header(...)):
    content = ""
    language = "text"
    max_size = 0
    
    content_type = request.headers.get("content-type", "")
    
    if "application/json" in content_type:
        try:
            body = await request.json()
            content = body.get("content", "")
            language = body.get("language", "text")
            max_size = body.get("max_size", 0)
        except Exception:
            pass
    else:
        try:
            form = await request.form()
            content = form.get("content", "")
            language = form.get("language", "text")
            max_size = int(form.get("max_size", 0) or 0)
        except Exception:
            try:
                raw = await request.body()
                text = raw.decode()
                parsed = parse_qs(text)
                content = parsed.get("content", [""])[0]
                language = parsed.get("language", ["text"])[0]
                max_size = int(parsed.get("max_size", [0])[0] or 0)
            except Exception:
                pass
    
    if not content:
        raise HTTPException(status_code=422, detail="content is required")
    
    check_size(content, max_size)
    
    db = SessionLocal()
    paste = db.query(Paste).filter(Paste.id == paste_id).first()
    if not paste:
        db.close()
        raise HTTPException(status_code=404, detail="Paste not found")
    if paste.delete_token != x_delete_token:
        db.close()
        raise HTTPException(status_code=403, detail="Invalid delete token")
    
    paste.content = content
    paste.language = language
    db.commit()
    result = paste_to_dict(paste)
    db.close()
    return {"success": True, "data": result}
# ── Frontend ──
@app.get("/")
@app.get("/p/{paste_id}")
async def serve_spa(paste_id: str = None):
    return FileResponse("static/index.html")

app.mount("/static", StaticFiles(directory="static"), name="static")
