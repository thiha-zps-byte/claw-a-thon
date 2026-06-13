"""Context budgeting for document stuffing.

Concatenates document text into the agent instruction within a token budget. The
safety + xưng hô blocks live in the persona prompt and are never trimmed here — this
module only bounds the *knowledge* portion, truncating with a visible notice so the
agent can tell the player the answer is based on the available material.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.db.models import Document


def estimate_tokens(text: str) -> int:
    """Cheap heuristic: ~4 chars per token. Good enough for budgeting."""
    return max(1, len(text) // 4)


@dataclass
class DocContext:
    text: str
    truncated: bool
    used_docs: int
    total_docs: int


def build_doc_context(documents: list[Document], token_budget: int) -> DocContext:
    """Join ready documents into a single context string within the budget."""
    ready = [d for d in documents if d.status == "ready" and d.extracted_text.strip()]
    char_budget = token_budget * 4
    parts: list[str] = []
    used = 0
    truncated = False
    spent = 0
    for doc in ready:
        header = f"\n### Tài liệu: {doc.filename}\n"
        body = doc.extracted_text.strip()
        chunk = header + body
        if spent + len(chunk) > char_budget:
            remaining = char_budget - spent - len(header)
            if remaining > 400:  # worth including a partial slice
                parts.append(header + body[:remaining] + "\n…(cắt bớt do giới hạn ngữ cảnh)")
                used += 1
            truncated = True
            break
        parts.append(chunk)
        spent += len(chunk)
        used += 1
    if used < len(ready):
        truncated = True
    return DocContext(
        text="\n".join(parts).strip(),
        truncated=truncated,
        used_docs=used,
        total_docs=len(ready),
    )
