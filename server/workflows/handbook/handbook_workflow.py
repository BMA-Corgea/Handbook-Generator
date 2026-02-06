"""Handbook workflow (LongWriter-inspired).

Implements a simple:
- Plan step (outline with targets)
- Write step (iterative subsection generation with retrieval)

This is the core place to:
- enforce word targets
- track progress
- store partial outputs
"""

from __future__ import annotations
import json
from typing import List, Dict, Any
from server.models.schemas import HandbookRequest, HandbookResponse, Citation
from server.retrieval.retrieval_service import retrieve_context
from server.services.grok_client import GrokClient
from server.workflows.handbook.prompts import PLAN_PROMPT, WRITE_PROMPT
from server.utils.word_count import count_words
from server.utils.output_store import save_handbook_markdown

async def _plan_outline(client: GrokClient, topic: str, context: str) -> Dict[str, Any]:
    messages = [
        {"role": "system", "content": PLAN_PROMPT},
        {"role": "user", "content": f"Topic: {topic}\n\nSOURCE CONTEXT:\n{context}"},
    ]
    raw = await client.chat(messages, temperature=0.2, max_tokens=2000)
    # Expecting JSON; keep a fallback to avoid crashes during demo.
    try:
        return json.loads(raw)
    except Exception:
        return {"title": topic, "toc": [{"section": "Overview", "subsections": [{"heading": "Introduction", "goal": "Introduce topic", "target_words": 1200}]}]}

async def generate_handbook(req: HandbookRequest) -> HandbookResponse:
    client = GrokClient()

    # Broad retrieval to seed plan
    seed_context, seed_cites = await retrieve_context(document_id=req.document_id, query=req.topic, k=12)
    plan = await _plan_outline(client, req.topic, seed_context)

    title = plan.get("title") or req.topic
    toc = plan.get("toc") or []
    markdown_parts: List[str] = [f"# {title}\n"]

    all_citations: List[Citation] = []
    all_citations.extend(seed_cites)

    # Iteratively generate subsections until target words met
    for section in toc:
        section_name = section.get("section") or section.get("heading") or "Section"
        markdown_parts.append(f"\n## {section_name}\n")
        subsections = section.get("subsections") or []
        for sub in subsections:
            heading = sub.get("heading") or "Subsection"
            goal = sub.get("goal") or ""
            target_words = int(sub.get("target_words") or 800)

            # Retrieve context specifically for this subsection
            ctx, cites = await retrieve_context(
                document_id=req.document_id,
                query=f"{req.topic} - {section_name} - {heading}",
                k=10,
            )
            all_citations.extend(cites)

            prior = "\n".join(markdown_parts)
            # Keep prior text bounded to avoid runaway context.
            prior_tail = prior[-6000:]

            messages = [
                {"role": "system", "content": WRITE_PROMPT},
                {"role": "user", "content": json.dumps({
                    "title": title,
                    "heading": heading,
                    "goal": goal,
                    "target_words": target_words,
                    "context": ctx,
                    "previous_text_tail": prior_tail,
                })},
            ]
            subsection_md = await client.chat(messages, temperature=0.4, max_tokens=2000)
            markdown_parts.append(subsection_md.strip() + "\n")

            current_wc = count_words("\n".join(markdown_parts))
            if current_wc >= req.target_words:
                break
        if count_words("\n".join(markdown_parts)) >= req.target_words:
            break

    handbook_md = "\n".join(markdown_parts).strip()
    wc = count_words(handbook_md)

    # Store artifact for demo/repro
    save_handbook_markdown(document_id=req.document_id, title=title, markdown=handbook_md)

    return HandbookResponse(
        title=title,
        word_count=wc,
        handbook_markdown=handbook_md,
        citations=all_citations,
    )
