from fastapi import FastAPI
from dotenv import load_dotenv

from server.routers.ingest_service import router as ingest_router
from server.routers.grok_router import router as grok_router

load_dotenv()

app = FastAPI(title="LunarTech Assignment API", version="0.1.0")
app.include_router(ingest_router)
app.include_router(grok_router)
