"""Server-rendered pages: every route renders real articles from the database."""
import json
import re

import pytest

from tests.conftest import H


def first_title(app):
    from extensions import ARTICLES, get_db
    with app.app_context():
        return get_db()[ARTICLES].find_one({}, sort=[("publishedAt", -1)])["title"]


@pytest.mark.parametrize("path", ["/", "/latest", "/trending", "/categories", "/category/technology", "/category/world?sort=popular",
                                  "/for-you", "/search", "/search?q=ai", "/login", "/register", "/page/about", "/page/privacy"])
def test_public_pages_render(client, path):
    r = client.get(path)
    assert r.status_code == 200, path
    html = r.get_data(as_text=True)
    assert "NewsSphere" in html and "/static/css/styles.css" in html and "/static/js/app.js" in html
    assert "react" not in html.lower() and "vite" not in html.lower()


def test_home_shows_seeded_articles(client, app):
    html = client.get("/").get_data(as_text=True)
    assert "Top Stories" in html and "Trending Now" in html and "Picked For You" in html and "Latest News" in html and "Most Read" in html
    assert len(re.findall(r'<article', html)) >= 15
    assert 'role="marquee"' in html  # ticker
    from html import escape
    assert escape(first_title(app)) in html or first_title(app) in html


def test_theme_and_navbar_hooks(client):
    html = client.get("/").get_data(as_text=True)
    for hook in ["data-theme-toggle", "data-search-open", "data-drawer", "ns-theme", "Sign in"]:
        assert hook in html


def test_article_detail_and_view_counter(client, app):
    from extensions import ARTICLES, get_db
    with app.app_context():
        a = get_db()[ARTICLES].find_one({"category": "technology"})
    before = a["views"]
    r = client.get(f"/article/{a['_id']}")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "prose-article" in html and "You may also like" in html and "data-like" in html
    with app.app_context():
        assert get_db()[ARTICLES].find_one({"_id": a["_id"]})["views"] == before + 1


def test_404s(client):
    assert client.get("/article/nope").status_code == 404
    assert client.get("/category/nope").status_code == 404
    r = client.get("/definitely-missing")
    assert r.status_code == 404 and "gone to press" in r.get_data(as_text=True)


def test_partials_for_load_more(client):
    r = client.get("/latest?partial=1&page=2&limit=10")
    d = r.get_json()
    assert d["total"] > 10 and "<article" in d["html"] and isinstance(d["hasMore"], bool)
    d = client.get("/category/technology?partial=1&page=2&limit=3").get_json()
    assert "<article" in d["html"]


def test_search_page_results_and_highlight(client):
    html = client.get("/search?q=climate").get_data(as_text=True)
    assert "<mark" in html and "results" in html
    assert "No articles found" in client.get("/search?q=zzzzqqq").get_data(as_text=True)


def test_protected_pages_redirect_when_logged_out(client):
    for p in ["/bookmarks", "/history", "/profile", "/onboarding", "/for-you-x"]:
        r = client.get(p)
        assert r.status_code in (302, 404)
        if r.status_code == 302:
            assert "/login" in r.headers["Location"]
    assert client.get("/admin").status_code in (302, 403)


def test_logged_in_pages_and_personalisation(client, demo):
    for p in ["/", "/for-you", "/bookmarks", "/history", "/profile", "/latest"]:
        r = client.get(p)
        assert r.status_code == 200, p
    html = client.get("/profile").get_data(as_text=True)
    assert "Your interests" in html and "demo@newssphere.com" in html
    assert "Sign in</a>" not in client.get("/").get_data(as_text=True).split("<main")[0]


def test_bookmark_state_is_server_rendered(client, demo, app):
    from extensions import ARTICLES, get_db
    with app.app_context():
        a = get_db()[ARTICLES].find_one({})
    assert client.post(f"/api/bookmarks/{a['_id']}", headers=H).status_code in (200, 201)
    html = client.get("/bookmarks").get_data(as_text=True)
    assert a["title"] in html.replace("&#39;", "'").replace("&amp;", "&") or str(a["_id"]) in html
    assert f'data-bookmark="{a["_id"]}" aria-pressed="true"' in client.get(f"/article/{a['_id']}").get_data(as_text=True)


def test_history_page_after_reading(client, demo, app):
    from extensions import ARTICLES, get_db
    with app.app_context():
        a = get_db()[ARTICLES].find_one({"category": "science"})
    client.get(f"/article/{a['_id']}")
    html = client.get("/history").get_data(as_text=True)
    assert "Today" in html and str(a["_id"]) in html


def test_admin_pages(client, app):
    # not admin -> blocked
    assert client.get("/admin").status_code in (302, 403)
    r = client.post("/api/auth/login", json={"email": "admin@newssphere.com", "password": "Admin@12345"}, headers=H)
    assert r.status_code == 200
    for p, needle in [("/admin", "Overview"), ("/admin/articles", "New article"), ("/admin/users", "registered readers"), ("/admin/articles?new=1", "data-open-new=\"true\"")]:
        res = client.get(p)
        assert res.status_code == 200, p
        assert needle in res.get_data(as_text=True)


def test_onboarding_flow_pages(client):
    r = client.post("/api/auth/register", json={"name": "Page Tester", "email": "pt@example.com", "password": "Passw0rdX"}, headers=H)
    assert r.status_code in (200, 201)
    assert "What topics are you interested in?" in client.get("/onboarding").get_data(as_text=True)
    client.put("/api/users/preferences", json={"interests": ["science", "health"]}, headers=H)
    html = client.get("/for-you").get_data(as_text=True)
    assert "Curated for Page" in html and "Science" in html
