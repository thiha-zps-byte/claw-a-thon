"""API integration tests (Starlette TestClient, LLM mocked).

Covers happy paths, the unified error envelope, limits, and the §9 edge cases
(missing UID, deleted bot, empty message, oversized/unsupported upload).
"""

from __future__ import annotations

H = {"X-UID": "owner-1"}


def test_create_list_get_delete_bot(client):
    r = client.post("/api/bots", json={"name": "ZingSpeed", "player_term": "tay đua"}, headers=H)
    assert r.status_code == 201
    bot = r.json()["bot"]
    assert bot["player_term"] == "tay đua"

    r = client.get("/api/bots", headers=H)
    assert r.status_code == 200
    assert any(b["id"] == bot["id"] for b in r.json()["bots"])

    r = client.get(f"/api/bots/{bot['id']}", headers=H)
    assert r.status_code == 200
    assert "documents" in r.json()["bot"]

    r = client.delete(f"/api/bots/{bot['id']}", headers=H)
    assert r.status_code == 200


def test_create_bot_requires_name(client):
    r = client.post("/api/bots", json={"name": "  "}, headers=H)
    assert r.status_code == 400
    body = r.json()
    assert body["error"] == "validation_error"
    assert "message" in body and body["message"]


def test_create_bot_defaults_to_escalate_skill(client):
    # Skills aren't user-selectable: no skills sent → fixed default (escalate only).
    r = client.post("/api/bots", json={"name": "NoSkills"}, headers=H)
    assert r.json()["bot"]["enabled_skills"] == ["escalate_to_human"]
    # A removed/unknown skill id must not be kept; falls back to the default.
    r = client.post(
        "/api/bots", json={"name": "OldSkill", "enabled_skills": ["check_transaction"]}, headers=H
    )
    assert r.json()["bot"]["enabled_skills"] == ["escalate_to_human"]


def test_missing_uid_rejected(client):
    r = client.get("/api/bots")
    assert r.status_code == 400
    assert r.json()["error"] == "validation_error"


def test_owner_scoping(client):
    r = client.post("/api/bots", json={"name": "Secret"}, headers={"X-UID": "alice"})
    bot_id = r.json()["bot"]["id"]
    # bob cannot see alice's bot
    r = client.get(f"/api/bots/{bot_id}", headers={"X-UID": "bob"})
    assert r.status_code == 404


def test_upload_markdown_then_list(client, sample_bot):
    bot_id = sample_bot["id"]
    files = {"files": ("faq.md", b"# Quen mat khau\nVao khoi phuc tai khoan.", "text/markdown")}
    r = client.post(f"/api/bots/{bot_id}/documents", files=files, headers=H)
    assert r.status_code == 201
    docs = r.json()["documents"]
    assert docs[0]["status"] == "ready"

    r = client.get(f"/api/bots/{bot_id}/documents", headers=H)
    assert len(r.json()["documents"]) == 1


def test_document_raw_returns_original_bytes(client, sample_bot):
    bot_id = sample_bot["id"]
    body = b"# Quen mat khau\nVao khoi phuc tai khoan."
    files = {"files": ("faq.md", body, "text/markdown")}
    doc_id = client.post(f"/api/bots/{bot_id}/documents", files=files, headers=H).json()[
        "documents"
    ][0]["id"]
    r = client.get(f"/api/bots/{bot_id}/documents/{doc_id}/raw", headers=H)
    assert r.status_code == 200
    assert r.content == body
    assert "markdown" in r.headers["content-type"]
    # Unknown doc id → 404; another user → 404.
    assert client.get(f"/api/bots/{bot_id}/documents/nope/raw", headers=H).status_code == 404
    assert (
        client.get(f"/api/bots/{bot_id}/documents/{doc_id}/raw", headers={"X-UID": "intruder"}).status_code
        == 404
    )


def test_upload_too_large(client, sample_bot):
    bot_id = sample_bot["id"]
    big = b"x" * (2 * 1024 * 1024)  # 2MB > 1MB limit
    files = {"files": ("big.txt", big, "text/plain")}
    r = client.post(f"/api/bots/{bot_id}/documents", files=files, headers=H)
    assert r.status_code == 413
    assert r.json()["error"] == "upload_too_large"


def test_upload_unsupported_format(client, sample_bot):
    bot_id = sample_bot["id"]
    files = {"files": ("virus.exe", b"data", "application/octet-stream")}
    r = client.post(f"/api/bots/{bot_id}/documents", files=files, headers=H)
    assert r.status_code == 400
    assert r.json()["error"] == "unsupported_format"


def test_chat_routes_to_service(client, sample_bot, monkeypatch):
    from app.services.agent_service import TurnResult, agent_service

    async def fake_turn(bot, documents, message, uid, session_id):
        return TurnResult(reply=f"Chào {bot.player_term}!", category="greeting", delay=0.7)

    monkeypatch.setattr(agent_service, "run_turn", fake_turn)
    r = client.post("/api/chat", json={"bot_id": sample_bot["id"], "message": "alo"}, headers=H)
    assert r.status_code == 200
    body = r.json()
    assert "tay đua" in body["reply"]
    assert body["category"] == "greeting"


def test_chat_idor_blocked(client):
    # alice's bot must not be drivable via /api/chat by another user (bob).
    bot_id = client.post(
        "/api/bots", json={"name": "Alice Bot"}, headers={"X-UID": "alice"}
    ).json()["bot"]["id"]
    r = client.post(
        "/api/chat", json={"bot_id": bot_id, "message": "alo"}, headers={"X-UID": "bob"}
    )
    assert r.status_code == 404


def test_chat_missing_bot(client):
    r = client.post("/api/chat", json={"bot_id": "nope", "message": "hi"}, headers=H)
    assert r.status_code == 404
    assert "chọn bot khác" in r.json()["message"].lower() or r.json()["error"] == "not_found"


def test_chat_empty_message(client, sample_bot):
    r = client.post("/api/chat", json={"bot_id": sample_bot["id"], "message": "   "}, headers=H)
    assert r.status_code == 400


def test_delete_document(client, sample_bot):
    bot_id = sample_bot["id"]
    files = {"files": ("a.md", b"noi dung", "text/markdown")}
    doc_id = client.post(f"/api/bots/{bot_id}/documents", files=files, headers=H).json()["documents"][0]["id"]
    r = client.delete(f"/api/bots/{bot_id}/documents/{doc_id}", headers=H)
    assert r.status_code == 200
    assert r.json()["deleted"] is True


def test_skills_endpoint(client):
    r = client.get("/api/skills", headers=H)
    assert r.status_code == 200
    skills = r.json()["skills"]
    ids = {s["id"] for s in skills}
    # Skills are now a single hidden default — the bot has no access to game systems,
    # so the lookup tools were removed (knowledge comes from documents).
    assert ids == {"escalate_to_human"}
    for removed in ("check_transaction", "lookup_account", "get_event_info"):
        assert removed not in ids
    by_id = {s["id"]: s for s in skills}
    assert by_id["escalate_to_human"]["label"] == "Chuyển hỗ trợ viên"
