"""Handbook endpoint.

Responsibilities:
- Receive a handbook request (topic + optional constraints)
- Run LongWriter-style orchestration:
    1) Plan: outline with targets
    2) Write: sequentially generate sections with retrieval per section
- Return the assembled handbook (and optionally store to outputs/)
"""

from fastapi import APIRouter
from server.models.schemas import HandbookRequest, HandbookResponse
from server.workflows.handbook.handbook_workflow import generate_handbook

router = APIRouter()

@router.post("/handbook", response_model=HandbookResponse)
async def handbook(req: HandbookRequest):
    return await generate_handbook(req)
