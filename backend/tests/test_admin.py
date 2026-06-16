"""Admin login gate for the shared-bot 'admin' UI mode.

This is a convenience/discoverability gate (the backend still trusts X-UID); it just
verifies an optional ADMIN_TOKEN so the operator has a real entry point instead of
guessing UID=admin.
"""

from __future__ import annotations


def _set_admin_token(monkeypatch, value: str):
    monkeypatch.setattr("app.api.admin._admin_token", lambda: value)


def test_admin_login_ok_with_correct_token(client, monkeypatch):
    _set_admin_token(monkeypatch, "s3cret")
    r = client.post("/api/admin/login", json={"token": "s3cret"})
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_admin_login_rejects_wrong_token(client, monkeypatch):
    _set_admin_token(monkeypatch, "s3cret")
    r = client.post("/api/admin/login", json={"token": "nope"})
    assert r.status_code == 200
    assert r.json()["ok"] is False


def test_admin_login_unset_token_is_not_ok(client, monkeypatch):
    _set_admin_token(monkeypatch, "")
    r = client.post("/api/admin/login", json={"token": "anything"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body.get("reason") == "unset"
