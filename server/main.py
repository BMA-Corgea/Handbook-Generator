"""FastAPI app entrypoint.

Wires up:
- /api/upload    (PDF ingestion)
- /api/chat      (RAG chat)
- /api/handbook  (LongWriter orchestration)
"""

from fastapi import FastAPI
from server.api.upload import router as upload_router
from server.api.chat import router as chat_router
from server.api.handbook import router as handbook_router

app = FastAPI(title="LunarTech Handbook Generator", version="0.1.0")

app.include_router(upload_router, prefix="/api", tags=["upload"])
app.include_router(chat_router, prefix="/api", tags=["chat"])
app.include_router(handbook_router, prefix="/api", tags=["handbook"])

@app.get("/health")
def health():
    return {"status": "ok"}
