"""Context budgeting tests — the knowledge portion is bounded and truncation flagged."""

from __future__ import annotations

from app.db.models import Document
from app.services.context import build_doc_context, estimate_tokens


def _doc(text: str, status: str = "ready") -> Document:
    return Document(bot_id="b", filename="d.md", extracted_text=text, char_count=len(text), status=status)


def test_small_docs_fit():
    ctx = build_doc_context([_doc("Quên mật khẩu: vào khôi phục.")], token_budget=1000)
    assert not ctx.truncated
    assert "Quên mật khẩu" in ctx.text
    assert ctx.used_docs == 1


def test_large_docs_truncated_with_notice():
    big = "A" * 20000
    ctx = build_doc_context([_doc(big)], token_budget=1000)
    assert ctx.truncated
    assert "cắt bớt" in ctx.text


def test_failed_docs_excluded():
    ctx = build_doc_context([_doc("x", status="failed")], token_budget=1000)
    assert ctx.text == ""
    assert ctx.total_docs == 0


def test_estimate_tokens_monotonic():
    assert estimate_tokens("a" * 400) > estimate_tokens("a" * 40)
