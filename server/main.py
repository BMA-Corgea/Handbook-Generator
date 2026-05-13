from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from dotenv import load_dotenv

from server.routers.ingest_service import router as ingest_router
from server.routers.grok_router import router as grok_router
from server.routers.lightrag_service import router as lightrag_router
from server.routers.supabase_router import router as supabase_router
from server.routers.dashboard_router import router as dashboard_router
from server.routers.longwrite_router import router as longwrite_router

load_dotenv()

app = FastAPI(title="Handbook Generator API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingest_router)
app.include_router(grok_router)
app.include_router(lightrag_router)
app.include_router(supabase_router)
app.include_router(dashboard_router)
app.include_router(longwrite_router)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
UI_DIR = PROJECT_ROOT / "ui"

# Serve UI assets at /ui/*
app.mount("/ui", StaticFiles(directory=str(UI_DIR), html=True), name="ui")

@app.get("/health")
def health():
    return {"status": "ok", "service": "handbook-generator"}

# Make / load the UI
@app.get("/", include_in_schema=False)
def ui_root():
    return FileResponse(str(UI_DIR / "index.html"))
