"""Shared "công khai" bot: everyone previews it read-only; only UID `admin` edits.

The bot is seeded on startup (idempotent) and loads the bundled sample docs.
Viewing/chat is open; every write path stays owner-scoped (admin only).
"""

from __future__ import annotations

import pytest

from app.core.errors import AppError

H_ADMIN = {"X-UID": "admin"}
H_USER = {"X-UID": "khach-1"}
SHARED_NAME = "Trợ lý CSKH Claw A Thon Game"


def _seed(client):
    """Trigger the startup seed and return the shared bot id."""
    from app.services import bot_service

    bot_service.seed_shared_bot()
    from app.db.database import get_session
    from app.db.repository import BotRepository

    with get_session() as session:
        shared = BotRepository(session).list_shared()
        return shared[0].id


def _mock_turn(monkeypatch):
    from app.services.agent_service import TurnResult, agent_service

    async def fake_turn(bot, documents, message, uid, session_id):
        return TurnResult(reply=f"echo: {message}", category="khác", delay=0.1)

    monkeypatch.setattr(agent_service, "run_turn", fake_turn)


# --- seeding ------------------------------------------------------------------


def test_seed_is_idempotent_and_loads_samples(client):
    from app.services import bot_service

    bot_service.seed_shared_bot()
    bot_service.seed_shared_bot()  # second call must not create a duplicate

    from app.db.database import get_session
    from app.db.repository import BotRepository

    with get_session() as session:
        repo = BotRepository(session)
        shared = repo.list_shared()
        assert len(shared) == 1
        bot = shared[0]
        assert bot.owner_uid == "admin"
        assert bot.is_shared is True
        assert bot.name == SHARED_NAME
        assert len(repo.documents_of(bot.id)) >= 1  # sample docs attached


# --- visibility (read) --------------------------------------------------------


def test_stranger_sees_shared_bot_in_list(client):
    _seed(client)
    bots = client.get("/api/bots", headers=H_USER).json()["bots"]
    shared = [b for b in bots if b["name"] == SHARED_NAME]
    assert len(shared) == 1
    assert shared[0]["is_shared"] is True
    assert shared[0]["owner_uid"] == "admin"


def test_stranger_can_view_detail_and_docs(client):
    bot_id = _seed(client)
    detail = client.get(f"/api/bots/{bot_id}", headers=H_USER)
    assert detail.status_code == 200
    docs = client.get(f"/api/bots/{bot_id}/documents", headers=H_USER)
    assert docs.status_code == 200
    assert len(docs.json()["documents"]) >= 1


def test_stranger_can_chat_shared_bot(client, monkeypatch):
    _mock_turn(monkeypatch)
    bot_id = _seed(client)
    r = client.post("/api/chat", json={"bot_id": bot_id, "message": "thử"}, headers=H_USER)
    assert r.status_code == 200
    assert r.json()["reply"] == "echo: thử"


def test_stranger_can_view_stats(client):
    bot_id = _seed(client)
    r = client.get(f"/api/bots/{bot_id}/stats/overview?range=all", headers=H_USER)
    assert r.status_code == 200
    assert "totals" in r.json()


# --- write paths are admin-only ----------------------------------------------


def test_stranger_cannot_edit_or_delete(client):
    bot_id = _seed(client)
    assert client.patch(f"/api/bots/{bot_id}", json={"description": "hack"},
                        headers=H_USER).status_code == 404
    assert client.delete(f"/api/bots/{bot_id}", headers=H_USER).status_code == 404


def test_stranger_cannot_add_or_remove_docs(client):
    from app.services import bot_service

    bot_id = _seed(client)
    with pytest.raises(AppError):
        bot_service.add_documents("khach-1", bot_id, [("x.txt", b"hi", "text/plain")])
    with pytest.raises(AppError):
        bot_service.add_sample_documents("khach-1", bot_id, ["00-tong-quan-game"])


def test_admin_can_edit(client):
    bot_id = _seed(client)
    r = client.patch(f"/api/bots/{bot_id}", json={"description": "đã chỉnh"}, headers=H_ADMIN)
    assert r.status_code == 200
    assert r.json()["bot"]["description"] == "đã chỉnh"


def test_shared_bot_cannot_be_deleted_even_by_admin(client):
    # The shared bot is a managed fixture (it would respawn on seed anyway) — deleting
    # it is rejected, so admin edits it rather than removes it.
    bot_id = _seed(client)
    r = client.delete(f"/api/bots/{bot_id}", headers=H_ADMIN)
    assert r.status_code == 400
    assert client.get(f"/api/bots/{bot_id}", headers=H_ADMIN).status_code == 200


# --- private bots stay private (no regression) --------------------------------


def test_private_bot_still_owner_scoped(client, monkeypatch):
    _mock_turn(monkeypatch)
    # alice's private bot
    bot_id = client.post("/api/bots", json={"name": "Riêng của Alice"},
                         headers={"X-UID": "alice"}).json()["bot"]["id"]
    bob = {"X-UID": "bob"}
    assert client.get(f"/api/bots/{bot_id}", headers=bob).status_code == 404
    assert client.post("/api/chat", json={"bot_id": bot_id, "message": "hi"},
                       headers=bob).status_code == 404
    # and it does not show up in bob's list
    names = [b["name"] for b in client.get("/api/bots", headers=bob).json()["bots"]]
    assert "Riêng của Alice" not in names
