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
@app.post("/api/pastes", response_model=dict)
async def create_paste(data: PasteIn):
    if MAX_SIZE > 0 and len(data.content) > MAX_SIZE:
        raise HTTPException(status_code=413, detail=f"Content exceeds {MAX_SIZE} bytes")

    db = SessionLocal()
    pid = gen_id()
    delete_token = gen_token()
    now = datetime.utcnow().isoformat()

    paste = Paste(
        id=pid,
        content=data.content,
        language=data.language,
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
            "language": data.language,
            "created_at": now,
        }
    }

@app.get("/api/pastes/{paste_id}", response_model=dict)
async def get_paste(paste_id: str):
    db = SessionLocal()
    paste = db.query(Paste).filter(Paste.id == paste_id).first()
    if not paste:
        db.close()
        raise HTTPException(status_code=404, detail="Paste not found")

    paste.views += 1
    db.commit()
    result = paste_to_dict(paste)
    db.close()
    return {"success": True, "data": result}

@app.get("/raw/{paste_id}")
async def get_raw(paste_id: str):
    db = SessionLocal()
    paste = db.query(Paste).filter(Paste.id == paste_id).first()
    db.close()
    if not paste:
        raise HTTPException(status_code=404, detail="Paste not found")
    return PlainTextResponse(content=paste.content)

@app.get("/download/{paste_id}")
async def download_paste(paste_id: str):
    db = SessionLocal()
    paste = db.query(Paste).filter(Paste.id == paste_id).first()
    db.close()
    if not paste:
        raise HTTPException(status_code=404, detail="Paste not found")

    ext_map = {
        "python": "py",
        "javascript": "js",
        "html": "html",
        "css": "css",
        "sql": "sql",
        "json": "json",
        "bash": "sh",
        "text": "txt",
    }
    ext = ext_map.get(paste.language, "txt")
    filename = f"{paste_id}.{ext}"

    return StreamingResponse(
        iter([paste.content.encode()]),
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

@app.put("/api/pastes/{paste_id}", response_model=dict)
async def update_paste(paste_id: str, data: PasteUpdate, x_delete_token: str = Header(...)):
    if MAX_SIZE > 0 and len(data.content) > MAX_SIZE:
        raise HTTPException(status_code=413, detail=f"Content exceeds {MAX_SIZE} bytes")

    db = SessionLocal()
    paste = db.query(Paste).filter(Paste.id == paste_id).first()
    if not paste:
        db.close()
        raise HTTPException(status_code=404, detail="Paste not found")
    if paste.delete_token != x_delete_token:
        db.close()
        raise HTTPException(status_code=403, detail="Invalid delete token")

    paste.content = data.content
    paste.language = data.language
    db.commit()
    result = paste_to_dict(paste)
    db.close()
    return {"success": True, "data": result}

@app.delete("/api/pastes/{paste_id}", response_model=dict)
async def delete_paste(paste_id: str, x_delete_token: str = Header(...)):
    db = SessionLocal()
    paste = db.query(Paste).filter(Paste.id == paste_id).first()
    if not paste:
        db.close()
        raise HTTPException(status_code=404, detail="Paste not found")
    if paste.delete_token != x_delete_token:
        db.close()
        raise HTTPException(status_code=403, detail="Invalid delete token")

    db.delete(paste)
    db.commit()
    db.close()
    return {"success": True, "deleted": True, "id": paste_id}

@app.get("/api/pastes", response_model=dict)
async def list_pastes(limit: int = 20):
    db = SessionLocal()
    pastes = db.query(Paste).order_by(Paste.created_at.desc()).limit(limit).all()
    result = [
        {"id": p.id, "language": p.language, "created_at": p.created_at, "views": p.views}
        for p in pastes
    ]
    db.close()
    return {"success": True, "count": len(result), "data": result}

# ── Frontend ──
@app.get("/")
@app.get("/p/{paste_id}")
async def serve_spa(paste_id: str = None):
    return FileResponse("static/index.html")

app.mount("/static", StaticFiles(directory="static"), name="static")
