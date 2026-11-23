import httpx

from app import updates


def test_version_compare():
    assert updates.is_newer("1.0.1", "1.0.0")
    assert updates.is_newer("v1.10", "1.9.9")
    assert not updates.is_newer("1.0", "1.0.0")
    assert not updates.is_newer("1.0.0", "1.2.0")
    assert not updates.is_newer("nightly", "1.0.0")
    assert not updates.is_newer(None, "1.0.0")


def test_check(monkeypatch):
    def fake_get(url, **kw):
        return httpx.Response(200, json={"tag_name": "v9.0.0", "html_url": "https://example/rel", "draft": False,
                                         "prerelease": False}, request=httpx.Request("GET", url))
    monkeypatch.setattr(updates.httpx, "get", fake_get)
    monkeypatch.setitem(updates.state, "latest", None)
    updates.check()
    assert updates.info() == {"version": "9.0.0", "url": "https://example/rel"}

    monkeypatch.setattr(updates.httpx, "get", lambda url, **kw: httpx.Response(404, request=httpx.Request("GET", url)))
    updates.check()
    assert updates.info() is None

    def offline(url, **kw):
        raise httpx.ConnectError("offline")
    monkeypatch.setattr(updates.httpx, "get", offline)
    updates.check()  # no exception
    assert updates.info() is None
