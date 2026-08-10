import sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
sys.path.insert(0, str(Path(__file__).parent.parent))
from api.auth import init_db
from api.routes import router

app = FastAPI(title="OutClaw Legal AI", version="1.0.0")

@app.on_event("startup")
def startup():
    init_db()

@app.get("/health")
def health():
    return {"status": "ok"}

app.include_router(router, prefix="/api")

STATIC_DIR = Path(__file__).parent.parent / "dashboard" / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
def index():
    f = STATIC_DIR / "index.html"
    return FileResponse(str(f)) if f.exists() else {"msg": "no index yet"}

@app.get("/success")
def success():
    return FileResponse(str(STATIC_DIR / "success.html"))

@app.get("/cancel")
def cancel_page():
    return FileResponse(str(STATIC_DIR / "cancel.html"))
import sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
sys.path.insert(0, str(Path(__file__).parent.parent))
from api.auth import init_db
from api.routes import router

app = FastAPI(title="OutClaw Legal AI", version="1.0.0")

@app.on_event("startup")
def startup():
    init_db()

@app.get("/health")
def health():
    return {"status": "ok"}

app.include_router(router, prefix="/api")

STATIC_DIR = Path(__file__).parent.parent / "dashboard" / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
def index():
    f = STATIC_DIR / "index.html"
    return FileResponse(str(f)) if f.exists() else {"msg": "no index yet"}

@app.get("/success")
def success():
    return FileResponse(str(STATIC_DIR / "success.html"))

@app.get("/cancel")
def cancel_page():
    return FileResponse(str(STATIC_DIR / "cancel.html"))
