"""Ingestion tests — one per format plus failure modes."""

from __future__ import annotations

import io

from app.ingest import extract, is_supported


def test_markdown_and_text():
    res = extract("a.md", "# Tiêu đề\nNội dung tiếng Việt có dấu.".encode())
    assert res.status == "ready"
    assert "Nội dung" in res.text
    assert res.char_count > 0


def test_csv_flattened():
    raw = b"cau_hoi,tra_loi\nquen mat khau,vao khoi phuc\n"
    res = extract("faq.csv", raw)
    assert res.status == "ready"
    assert "quen mat khau" in res.text


def test_docx():
    from docx import Document as Docx

    buf = io.BytesIO()
    doc = Docx()
    doc.add_paragraph("Hướng dẫn nạp thẻ chính thức.")
    doc.save(buf)
    res = extract("huongdan.docx", buf.getvalue())
    assert res.status == "ready"
    assert "nạp thẻ" in res.text


def test_empty_file_failed():
    res = extract("empty.txt", b"")
    assert res.status == "failed"
    assert "rỗng" in res.note.lower()


def test_unsupported_format_raises():
    import pytest

    from app.core.errors import AppError

    with pytest.raises(AppError):
        extract("malware.exe", b"data")


def test_image_failure_is_flagged(monkeypatch):
    """A failing vision call flags the doc, never raises out of ingest."""
    from app.core.errors import llm_unavailable

    def boom(*_a, **_k):
        raise llm_unavailable()

    monkeypatch.setattr("app.ingest.image_vision.llm.read_image", boom)
    res = extract("screenshot.png", b"\x89PNG fake bytes", "image/png")
    assert res.status == "failed"
    assert res.note


def test_corrupt_docx_gives_friendly_note_not_raw_exception():
    """A broken .docx must flag the doc with a human note — never leak 'KeyError' etc."""
    # A .docx is a zip; random bytes make python-docx raise an internal exception.
    res = extract("broken.docx", b"PK\x03\x04 not really a docx")
    assert res.status == "failed"
    assert res.note  # has a friendly message
    # No raw Python exception class names leaked to the UI.
    for leak in ("KeyError", "Error:", "Traceback", "Exception"):
        assert leak not in res.note


def test_is_supported():
    assert is_supported("a.pdf")
    assert is_supported("b.PNG")
    assert not is_supported("c.exe")
