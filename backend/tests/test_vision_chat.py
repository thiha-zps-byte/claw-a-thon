"""Image attachments (Messenger DM + Page comment) are read by vision and answered.

The image is downloaded, turned into text via the vision model, merged into the
message, and run through the normal chat pipeline. All FB/vision/LLM I/O mocked.
"""

from __future__ import annotations

import hashlib
import hmac
import json

H = {"X-UID": "owner-1"}
PAGE_ID = "PAGE1"
APP_SECRET = "s3cret"
IMG_DESC = "ảnh chụp màn hình lỗi nạp thẻ"


def _make_bot(client) -> str:
    bot_id = client.post("/api/bots", json={"name": "FB Bot"}, headers=H).json()["bot"]["id"]
    client.patch(
        f"/api/bots/{bot_id}",
        json={
            "messenger_enabled": True,
            "messenger_page_id": PAGE_ID,
            "messenger_page_token": "ptok",
            "messenger_app_secret": APP_SECRET,
        },
        headers=H,
    )
    return bot_id


def _mock_turn(monkeypatch) -> list:
    """Capture the message text the chat pipeline received."""
    from app.services.agent_service import TurnResult, agent_service

    seen: list = []

    async def fake_turn(bot, documents, message, uid, session_id):
        seen.append(message)
        return TurnResult(reply=f"echo: {message}", category="other", delay=0.1)

    monkeypatch.setattr(agent_service, "run_turn", fake_turn)
    return seen


def _mock_vision(monkeypatch, *, raises=False):
    async def fake_download(url):
        return b"imgbytes", "image/jpeg"

    def fake_extract(content, mime):
        if raises:
            raise RuntimeError("vision down")
        return IMG_DESC

    monkeypatch.setattr("app.api.webhooks._download", fake_download)
    monkeypatch.setattr("app.ingest.image_vision.extract_image", fake_extract)


def _mute_sends(monkeypatch) -> dict:
    calls: dict = {"text": [], "private": []}

    async def fake_text(page_token, psid, text):
        calls["text"].append(text)
        return True

    async def fake_typing(page_token, psid):
        return True

    async def fake_private(page_token, comment_id, text):
        calls["private"].append(text)
        return True

    monkeypatch.setattr("app.channels.messenger.send_text", fake_text)
    monkeypatch.setattr("app.channels.messenger.send_typing", fake_typing)
    monkeypatch.setattr("app.channels.messenger.private_reply", fake_private)
    return calls


def _dm(page_id, *, text=None, image_url=None):
    msg: dict = {}
    if text is not None:
        msg["text"] = text
    if image_url:
        msg["attachments"] = [{"type": "image", "payload": {"url": image_url}}]
    return {"object": "page", "entry": [{"id": page_id, "messaging": [
        {"sender": {"id": "PSID1"}, "message": msg}]}]}


def _comment(page_id, *, text="", photo=None):
    value = {"item": "comment", "verb": "add", "comment_id": "c1",
             "from": {"id": "USER1"}, "message": text}
    if photo:
        value["photo"] = photo
    return {"object": "page", "entry": [{"id": page_id, "changes": [
        {"field": "feed", "value": value}]}]}


def _signed_post(client, body):
    raw = json.dumps(body).encode()
    sig = "sha256=" + hmac.new(APP_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    return client.post("/api/webhooks/messenger", content=raw,
                       headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig})


def test_dm_image_only_is_handled(client, monkeypatch):
    seen = _mock_turn(monkeypatch)
    _mock_vision(monkeypatch)
    calls = _mute_sends(monkeypatch)
    _make_bot(client)

    _signed_post(client, _dm(PAGE_ID, image_url="http://img/1"))
    assert len(seen) == 1
    assert IMG_DESC in seen[0] and "[Ảnh đính kèm]" in seen[0]
    assert calls["text"] and IMG_DESC in calls["text"][0]


def test_dm_text_plus_image(client, monkeypatch):
    seen = _mock_turn(monkeypatch)
    _mock_vision(monkeypatch)
    _mute_sends(monkeypatch)
    _make_bot(client)

    _signed_post(client, _dm(PAGE_ID, text="cái này bị gì", image_url="http://img/1"))
    assert "cái này bị gì" in seen[0] and IMG_DESC in seen[0]


def test_comment_with_photo(client, monkeypatch):
    seen = _mock_turn(monkeypatch)
    _mock_vision(monkeypatch)
    calls = _mute_sends(monkeypatch)
    _make_bot(client)

    _signed_post(client, _comment(PAGE_ID, text="lỗi gì đây shop", photo="http://img/c"))
    assert seen and IMG_DESC in seen[0]
    assert calls["private"] and IMG_DESC in calls["private"][0]


def test_vision_failure_still_replies(client, monkeypatch):
    seen = _mock_turn(monkeypatch)
    _mock_vision(monkeypatch, raises=True)
    calls = _mute_sends(monkeypatch)
    _make_bot(client)

    _signed_post(client, _dm(PAGE_ID, image_url="http://img/x"))
    assert len(seen) == 1
    assert "không đọc được ảnh" in seen[0]
    assert calls["text"]


def test_no_text_no_image_is_skipped(client, monkeypatch):
    seen = _mock_turn(monkeypatch)
    _mock_vision(monkeypatch)
    _mute_sends(monkeypatch)
    _make_bot(client)

    _signed_post(client, _dm(PAGE_ID))  # empty message
    assert seen == []
