from tests.conftest import H


def test_health_and_seed(client):
    assert client.get("/api/health").json["status"] == "ok"
    d = client.get("/api/articles/latest?limit=50").json
    assert d["total"] == 44 and len(d["articles"]) == 44
    assert "content" not in d["articles"][0]


def test_home_payload(client):
    d = client.get("/api/articles/home").json
    assert d["hero"]["isFeatured"] and len(d["sideStories"]) == 3 and len(d["topStories"]) == 4
    assert len(d["latest"]) == 8 and len(d["trending"]) == 8 and len(d["mostRead"]) == 5 and len(d["sections"]) == 4


def test_breaking_trending_category_search(client):
    assert len(client.get("/api/articles/breaking").json["articles"]) >= 4
    t = client.get("/api/articles/trending?limit=5").json["articles"]
    assert len(t) == 5 and t[0]["trendingScore"] >= t[-1]["trendingScore"]
    c = client.get("/api/articles/category/technology").json
    assert c["total"] == 4 and all(a["category"] == "technology" for a in c["articles"])
    assert client.get("/api/articles/category/nope").status_code == 404
    s = client.get("/api/articles/search?q=chip").json
    assert s["total"] >= 1 and "chip" in s["articles"][0]["title"].lower() + " ".join(s["articles"][0]["tags"])
    assert client.get("/api/articles/search?q=zzzzqqq").json["total"] == 0
    assert client.get("/api/articles/search?q=a&sort=popular&category=sports").json["articles"]


def test_article_detail_and_views(client):
    aid = client.get("/api/articles/latest").json["articles"][0]["_id"]
    a1 = client.get(f"/api/articles/{aid}").json["article"]
    a2 = client.get(f"/api/articles/{aid}").json["article"]
    assert a2["views"] == a1["views"] + 1 and "content" in a1
    assert client.get("/api/articles/notanid").status_code == 404
    assert len(client.get(f"/api/articles/{aid}/related").json["articles"]) >= 3


def test_auth_flow(client):
    r = client.post("/api/auth/register", json={"name": "A", "email": "bad", "password": "x"}, headers=H)
    assert r.status_code == 400 and "errors" in r.json
    r = client.post("/api/auth/register", json={"name": "Ann Lee", "email": "ann@example.com", "password": "Passw0rdX"}, headers=H)
    assert r.status_code == 201 and r.json["token"] and "password" not in r.json["user"]
    assert client.get("/api/auth/me").json["user"]["email"] == "ann@example.com"
    assert client.post("/api/auth/register", json={"name": "Ann", "email": "ann@example.com", "password": "Passw0rdX"}, headers=H).status_code == 409
    client.post("/api/auth/logout", headers=H)
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/login", json={"email": "ann@example.com", "password": "wrongpass1"}, headers=H).status_code == 401
    ok = client.post("/api/auth/login", json={"email": "ann@example.com", "password": "Passw0rdX"}, headers=H)
    assert ok.status_code == 200
    # bearer token works without the cookie
    c2 = client.application.test_client()
    assert c2.get("/api/auth/me", headers={"Authorization": f"Bearer {ok.json['token']}"}).status_code == 200


def test_password_is_hashed(app, client):
    from extensions import get_db

    u = get_db()["users"].find_one({"email": "demo@newssphere.com"})
    assert u["password"].startswith("$2") and "Demo@12345" not in u["password"]


def test_csrf_header_required(demo):
    assert demo.post("/api/bookmarks/000000000000000000000000").status_code == 403


def test_like_bookmark_history(demo):
    arts = demo.get("/api/articles/latest?limit=5").json["articles"]
    a = arts[0]["_id"]
    r = demo.post(f"/api/articles/{a}/like", headers=H)
    assert r.status_code == 201 and r.json["liked"]
    likes = r.json["likes"]
    assert demo.post(f"/api/articles/{a}/like", headers=H).json["likes"] == likes  # idempotent
    assert demo.delete(f"/api/articles/{a}/like", headers=H).json["likes"] == likes - 1
    assert demo.post(f"/api/bookmarks/{a}", headers=H).status_code == 201
    assert a in [b for b in demo.get("/api/auth/me").json["user"]["bookmarks"]]
    assert a in [x["_id"] for x in demo.get("/api/bookmarks").json["articles"]]
    assert demo.delete(f"/api/bookmarks/{a}", headers=H).json["bookmarked"] is False
    n0 = demo.get("/api/history").json["total"]
    demo.post(f"/api/history/{a}", headers=H)
    demo.post(f"/api/history/{a}", headers=H)  # deduped within 30 min
    h = demo.get("/api/history").json
    assert h["total"] == n0 + 1 and h["byCategory"]
    assert demo.get("/api/likes").json["total"] >= 1
    demo.delete("/api/history", headers=H)
    assert demo.get("/api/history").json["total"] == 0


def test_recommendations_personalised(client, demo):
    anon = client.application.test_client().get("/api/recommendations?limit=8").json
    assert anon["personalized"] is False and len(anon["articles"]) == 8
    rec = demo.get("/api/recommendations?limit=12").json
    assert rec["personalized"] is True
    cats = [a["category"] for a in rec["articles"][:6]]
    assert sum(c in ("technology", "science", "gaming") for c in cats) >= 4  # interests drive the top of the feed
    assert rec["articles"][0]["reasons"] and rec["articles"][0]["recommendationScore"] > 0
    # already-read stories are penalised
    from extensions import get_db

    read = {str(h["articleId"]) for h in get_db()["readinghistories"].find()}
    top5 = [a["_id"] for a in rec["articles"][:5]]
    assert sum(t in read for t in top5) <= 2
    # a brand-new user: declared interests alone drive the feed (no behaviour yet)
    fresh = demo.application.test_client()
    fresh.post("/api/auth/register", json={"name": "New Reader", "email": "new@example.com", "password": "Passw0rd1"}, headers=H)
    assert fresh.get("/api/recommendations").json["personalized"] is False
    fresh.put("/api/users/preferences", json={"interests": ["travel"]}, headers=H)
    rec2 = fresh.get("/api/recommendations?limit=6").json
    assert rec2["personalized"] is True and sum(a["category"] == "travel" for a in rec2["articles"]) >= 3
    ex = rec2["articles"][0]["_id"]
    assert ex not in [a["_id"] for a in fresh.get(f"/api/recommendations?exclude={ex}").json["articles"]]


def test_profile_and_preferences(demo):
    p = demo.get("/api/users/profile").json
    assert p["stats"]["reads"] == 6 and p["stats"]["likes"] == 1 and p["stats"]["bookmarks"] == 1
    assert demo.put("/api/users/preferences", json={"interests": []}, headers=H).status_code == 400
    assert demo.put("/api/users/profile", json={"name": "X"}, headers=H).status_code == 400
    r = demo.put("/api/users/profile", json={"name": "Demo Person", "currentPassword": "Demo@12345", "newPassword": "NewPass123"}, headers=H)
    assert r.status_code == 200 and r.json["user"]["name"] == "Demo Person"
    assert demo.put("/api/users/profile", json={"newPassword": "NewPass123", "currentPassword": "bad"}, headers=H).status_code == 400


def test_newsletter(client):
    assert client.post("/api/newsletter", json={"email": "x"}, headers=H).status_code == 400
    assert client.post("/api/newsletter", json={"email": "n@e.com"}, headers=H).json["alreadySubscribed"] is False
    assert client.post("/api/newsletter", json={"email": "n@e.com"}, headers=H).json["alreadySubscribed"] is True


def test_admin_permissions_and_crud(client, demo):
    assert demo.get("/api/admin/stats").status_code == 403
    anon = client.application.test_client()
    assert anon.get("/api/admin/stats").status_code == 401
    adm = client.application.test_client()
    adm.post("/api/auth/login", json={"email": "admin@newssphere.com", "password": "Admin@12345"}, headers=H)
    s = adm.get("/api/admin/stats").json
    assert s["counts"]["articles"] == 44 and s["byCategory"] and s["topArticles"]
    bad = adm.post("/api/admin/articles", json={"title": "x"}, headers=H)
    assert bad.status_code == 400
    new = adm.post("/api/admin/articles", json={"title": "Hello world", "description": "d", "content": "one two three " * 100, "category": "travel", "source": "Me", "tags": "a, b"}, headers=H)
    assert new.status_code == 201 and new.json["article"]["readingTime"] == 2 and new.json["article"]["tags"] == ["a", "b"]
    nid = new.json["article"]["_id"]
    up = adm.put(f"/api/admin/articles/{nid}", json={"title": "Edited", "isBreaking": True}, headers=H)
    assert up.json["article"]["title"] == "Edited" and up.json["article"]["isBreaking"] is True
    assert adm.get("/api/admin/articles?q=Edited").json["total"] == 1
    assert adm.get("/api/admin/users").json["total"] == 2
    uid = [u for u in adm.get("/api/admin/users").json["users"] if u["email"] == "demo@newssphere.com"][0]["_id"]
    assert adm.patch(f"/api/admin/users/{uid}/role", json={"role": "admin"}, headers=H).json["user"]["role"] == "admin"
    me = adm.get("/api/auth/me").json["user"]["_id"]
    assert adm.delete(f"/api/admin/users/{me}", headers=H).status_code == 400
    assert adm.delete(f"/api/admin/articles/{nid}", headers=H).json["deleted"]
    assert adm.get(f"/api/admin/articles/{nid}").status_code == 404
    assert adm.post("/api/admin/import", headers=H).json["errors"]  # nothing configured -> reported, not crashed
