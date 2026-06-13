"""Sample-doc catalogue + path-safety tests."""

from __future__ import annotations

from app import sample_docs


def test_list_samples_nonempty_with_titles():
    items = sample_docs.list_samples()
    assert items, "bundled samples should be discoverable"
    first = items[0]
    assert {"id", "filename", "title", "char_count"} <= first.keys()
    assert first["char_count"] > 0


def test_get_sample_returns_content():
    sid = sample_docs.list_samples()[0]["id"]
    s = sample_docs.get_sample(sid)
    assert s and s["content"]


def test_resolve_rejects_path_traversal():
    assert sample_docs.get_sample("../config") is None
    assert sample_docs.get_sample("../../app/config") is None
    assert sample_docs.read_sample_bytes("..%2f..%2fsecret") is None
    assert sample_docs.get_sample("does-not-exist") is None


def test_sample_raw_endpoint(client):
    sid = sample_docs.list_samples()[0]["id"]
    r = client.get(f"/api/samples/{sid}/raw", headers={"X-UID": "u1"})
    assert r.status_code == 200
    assert r.content  # original bytes
    assert "markdown" in r.headers["content-type"]  # samples are .md
    # Path traversal id → 404.
    assert client.get("/api/samples/..%2f..%2fconfig/raw", headers={"X-UID": "u1"}).status_code == 404
