"""CSV extraction — flatten rows into readable text for context stuffing."""

from __future__ import annotations

import csv
import io

from app.ingest.text import extract_text


def extract_csv(content: bytes) -> str:
    raw = extract_text(content)
    if not raw:
        return ""
    reader = csv.reader(io.StringIO(raw))
    lines: list[str] = []
    header: list[str] | None = None
    for i, row in enumerate(reader):
        if i == 0:
            header = row
            continue
        if header and len(header) == len(row):
            lines.append(" | ".join(f"{h}: {c}" for h, c in zip(header, row, strict=False) if c.strip()))
        else:
            lines.append(" | ".join(c for c in row if c.strip()))
    return "\n".join(lines).strip()
