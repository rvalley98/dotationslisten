"""Every page of the navigation renders, and the help page only links to pages that exist."""

import re

from fastapi.testclient import TestClient


def test_navigation_and_help_links(data_dir, monkeypatch):
    monkeypatch.setenv("WORKER", "0")
    from app import main

    with TestClient(main.app) as client:
        start = client.get("/").text
        nav = re.findall(r'<a href="(/[a-z]*)" class="small"', start)
        assert {"/", "/verwendungsnachweis", "/raumkosten", "/hilfe"} <= set(nav)
        for path in nav:
            assert client.get(path).status_code == 200, path
        hilfe = client.get("/hilfe").text
        assert "Anleitung" in hilfe and "Häufige Fragen" in hilfe
        for path in set(re.findall(r'href="(/[a-z]+)"', hilfe)):
            assert client.get(path).status_code == 200, path
        assert "issues/new?body=" in start  # "Fehler melden"
