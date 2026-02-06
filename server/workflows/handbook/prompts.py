"""Prompt templates for LongWriter-style generation.

These templates are intentionally straightforward and should be tuned
once you validate Grok's behavior and output limits.
"""

PLAN_PROMPT = """You are generating a long handbook strictly grounded in provided source context.
Create a detailed table of contents with sections and subsections.
For each subsection, include:
- a short goal sentence
- a target word count estimate

Return JSON with fields:
- title
- toc: list of sections, each with subsections containing {heading, goal, target_words}
"""

WRITE_PROMPT = """Write the next subsection of the handbook in Markdown.

Rules:
- Use the provided context. Do not invent citations.
- Keep consistent tone and definitions.
- Include a short citations line at end: 'Citations: chunk_...'

Inputs you will receive:
- Handbook title
- Current TOC subsection heading + goal + target_words
- Relevant context chunks
- Previously written text (may be truncated)

Output ONLY the markdown for this subsection, including a heading.
"""
