"""JSON API – same endpoints, payloads and status codes as the original Express routes (routes/index.js).
The browser JavaScript (static/js/app.js) talks to these; they also work for any API client."""
from flask import Blueprint, jsonify, request

from extensions import (ARTICLES, BOOKMARKS, HISTORY, LIKES, SUBSCRIBERS, USERS, get_db)
from models import articles as A
from models import interactions as I
from models import users as U
from services import feed
from services.news import import_external_news
from services.recommendation import get_recommendations
from services.trending import get_trending
from utils.auth import (api_admin_required, api_login_required, current_user, hash_password, login_user,
                        logout_user, make_token, rate_limit, verify_password)
from utils.constants import CATEGORY_SLUGS
from utils.helpers import (ApiError, assert_valid, clear_cache, is_email, jsonable, now, page_params,
                           regex_escape, sanitize_interests, to_oid, valid_oid, validate_login, validate_register)

bp = Blueprint("api", __name__, url_prefix="/api")


def out(data, status=200):
    return jsonify(jsonable(data)), status


def body():
    return request.get_json(silent=True) or {}


def aid(article_id):
    if not valid_oid(article_id):
        raise ApiError(404, "Article not found.")
    return article_id


# ------------------------------------------------------------------ health
@bp.get("/health")
def health():
    return out({"status": "ok", "time": now()})


# -------------------------------------------------------------------- auth
@bp.post("/auth/register")
@rate_limit()
def register():
    b = body()
    validate_register(b)
    user = U.create(b["name"], b["email"], b["password"])
    login_user(user)
    return out({"token": make_token(user["_id"]), "user": U.public(user)}, 201)


@bp.post("/auth/login")
@rate_limit()
def login():
    b = body()
    validate_login(b)
    user = U.find_by_email(b["email"])
    if not user or not verify_password(b["password"], user.get("password", "")):
        raise ApiError(401, "Incorrect email or password.")
    login_user(user)
    return out({"token": make_token(user["_id"]), "user": U.public(user)})


@bp.post("/auth/logout")
def logout():
    logout_user()
    return out({"loggedOut": True})


@bp.get("/auth/me")
@api_login_required
def me():
    return out({"user": U.public(current_user())})


# ---------------------------------------------------------------- articles
@bp.get("/articles")
def articles_index():
    page, limit, _ = page_params(request.args, 12)
    return out(A.list_articles(request.args.get("category"), request.args.get("source"), request.args.get("sort", "latest"), page, limit))


@bp.get("/articles/latest")
def articles_latest():
    page, limit, _ = page_params(request.args, 12)
    return out(A.latest(page, limit))


@bp.get("/articles/trending")
def articles_trending():
    try:
        limit = min(30, int(request.args.get("limit", 10)))
    except ValueError:
        limit = 10
    return out({"articles": get_trending(limit)})


@bp.get("/articles/breaking")
def articles_breaking():
    return out({"articles": feed.breaking()})


@bp.get("/articles/home")
def articles_home():
    data = feed.home_data()
    if not data:
        raise ApiError(404, "No articles yet.")
    return out(data)


@bp.get("/articles/search")
def articles_search():
    page, limit, _ = page_params(request.args, 10)
    a = request.args
    return out(A.search(a.get("q", ""), a.get("category"), a.get("source"), a.get("sort"), page, limit))


@bp.get("/articles/sources")
def articles_sources():
    return out({"sources": A.distinct_sources()})


@bp.get("/articles/category/<category>")
def articles_by_category(category):
    if category not in CATEGORY_SLUGS:
        raise ApiError(404, "Unknown category.")
    page, limit, _ = page_params(request.args, 12)
    return out(A.by_category(category, request.args.get("sort", "latest"), page, limit))


@bp.get("/articles/<article_id>")
def article_get(article_id):
    art = A.inc_views(aid(article_id))
    if not art:
        raise ApiError(404, "Article not found.")
    return out({"article": art})


@bp.get("/articles/<article_id>/related")
def article_related(article_id):
    try:
        limit = int(request.args.get("limit", 4))
    except ValueError:
        limit = 4
    res = A.related(aid(article_id), limit)
    if res is None:
        raise ApiError(404, "Article not found.")
    return out({"articles": res})


# ------------------------------------------------------------------- likes
@bp.post("/articles/<article_id>/like")
@api_login_required
def like(article_id):
    likes = I.like(current_user()["_id"], aid(article_id))
    return out({"liked": True, "likes": likes}, 201)


@bp.delete("/articles/<article_id>/like")
@api_login_required
def unlike(article_id):
    likes = I.unlike(current_user()["_id"], aid(article_id))
    return out({"liked": False, "likes": likes})


@bp.get("/likes")
@api_login_required
def likes_list():
    page, limit, _ = page_params(request.args, 12)
    return out(I.like_list(current_user()["_id"], page, limit))


# --------------------------------------------------------- recommendations
@bp.get("/recommendations")
def recommendations():
    try:
        limit = min(30, max(1, int(request.args.get("limit", 12))))
    except ValueError:
        limit = 12
    exclude = to_oid(request.args.get("exclude")) if request.args.get("exclude") else None
    user = current_user()
    return out(get_recommendations(user["_id"] if user else None, limit, exclude))


# --------------------------------------------------------------- bookmarks
@bp.get("/bookmarks")
@api_login_required
def bookmarks_list():
    page, limit, _ = page_params(request.args, 12)
    return out(I.bookmark_list(current_user()["_id"], page, limit))


@bp.post("/bookmarks/<article_id>")
@api_login_required
def bookmark_add(article_id):
    I.bookmark_add(current_user()["_id"], aid(article_id))
    return out({"bookmarked": True, "articleId": article_id}, 201)


@bp.delete("/bookmarks/<article_id>")
@api_login_required
def bookmark_remove(article_id):
    I.bookmark_remove(current_user()["_id"], aid(article_id))
    return out({"bookmarked": False, "articleId": article_id})


# ----------------------------------------------------------------- history
@bp.get("/history")
@api_login_required
def history_list():
    page, limit, _ = page_params(request.args, 15)
    return out(I.history_list(current_user()["_id"], page, limit))


@bp.post("/history/<article_id>")
@api_login_required
def history_record(article_id):
    I.history_record(current_user()["_id"], aid(article_id))
    return out({"recorded": True}, 201)


@bp.delete("/history")
@api_login_required
def history_clear():
    I.history_clear(current_user()["_id"])
    return out({"cleared": True})


# ------------------------------------------------------------------- users
@bp.get("/users/profile")
@api_login_required
def profile_get():
    user = current_user()
    return out({"user": U.public(user), "stats": I.user_stats(user["_id"])})


@bp.put("/users/profile")
@api_login_required
def profile_update():
    b = body()
    user = current_user()
    errors, changes = {}, {}
    if b.get("name") is not None:
        if len(str(b["name"]).strip()) < 2:
            errors["name"] = "Name must be at least 2 characters."
        else:
            changes["name"] = str(b["name"]).strip()
    if b.get("email") is not None and str(b["email"]).lower().strip() != user["email"]:
        e = str(b["email"]).lower().strip()
        if not is_email(e):
            errors["email"] = "Please enter a valid email address."
        elif get_db()[USERS].find_one({"email": e, "_id": {"$ne": user["_id"]}}):
            errors["email"] = "That email is already in use."
        else:
            changes["email"] = e
    if b.get("avatar") is not None:
        changes["avatar"] = str(b["avatar"]).strip()[:500]
    if b.get("newPassword"):
        np = str(b["newPassword"])
        if not b.get("currentPassword") or not verify_password(str(b["currentPassword"]), user.get("password", "")):
            errors["currentPassword"] = "Current password is incorrect."
        elif len(np) < 8 or not any(c.isalpha() for c in np) or not any(c.isdigit() for c in np):
            errors["newPassword"] = "New password needs 8+ characters with a letter and a number."
        else:
            changes["password"] = hash_password(np)
    assert_valid(errors)
    updated = U.update(user["_id"], changes) if changes else user
    return out({"user": U.public(updated)})


@bp.put("/users/preferences")
@api_login_required
def preferences_update():
    interests = sanitize_interests(body().get("interests"))
    if not interests:
        raise ApiError(400, "Pick at least one topic you are interested in.")
    updated = U.update(current_user()["_id"], {"interests": interests, "onboarded": True})
    clear_cache("home")
    return out({"user": U.public(updated)})


# -------------------------------------------------------------- newsletter
@bp.post("/newsletter")
def newsletter():
    email = str(body().get("email") or "").lower().strip()
    if not is_email(email):
        raise ApiError(400, "Please enter a valid email address.")
    res = get_db()[SUBSCRIBERS].update_one({"email": email}, {"$setOnInsert": {"email": email, "createdAt": now(), "updatedAt": now()}}, upsert=True)
    return out({"subscribed": True, "alreadySubscribed": res.upserted_id is None}, 201)


# ------------------------------------------------------------------- admin
@bp.get("/admin/stats")
@api_admin_required
def admin_stats():
    return out(admin_stats_data())


def admin_stats_data():
    from datetime import timedelta

    db = get_db()
    week_ago = now() - timedelta(days=7)
    totals = list(db[ARTICLES].aggregate([{"$group": {"_id": None, "views": {"$sum": "$views"}, "likes": {"$sum": "$likes"}}}]))
    return {
        "counts": {
            "users": db[USERS].count_documents({}),
            "articles": db[ARTICLES].count_documents({}),
            "bookmarks": db[BOOKMARKS].count_documents({}),
            "likes": db[LIKES].count_documents({}),
            "reads": db[HISTORY].count_documents({}),
            "subscribers": db[SUBSCRIBERS].count_documents({}),
            "views": totals[0]["views"] if totals else 0,
        },
        "byCategory": list(
            db[ARTICLES].aggregate(
                [{"$group": {"_id": "$category", "articles": {"$sum": 1}, "views": {"$sum": "$views"}}}, {"$sort": {"views": -1}}]
            )
        ),
        "topArticles": list(
            db[ARTICLES].find({}, {"title": 1, "category": 1, "views": 1, "likes": 1, "publishedAt": 1}).sort("views", -1).limit(5)
        ),
        "recentUsers": list(db[USERS].find({}, {"name": 1, "email": 1, "role": 1, "createdAt": 1}).sort("createdAt", -1).limit(5)),
        "activity": list(
            db[HISTORY].aggregate(
                [
                    {"$match": {"readAt": {"$gte": week_ago}}},
                    {"$group": {"_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$readAt"}}, "reads": {"$sum": 1}}},
                    {"$sort": {"_id": 1}},
                ]
            )
        ),
    }


@bp.get("/admin/articles")
@api_admin_required
def admin_articles():
    page, limit, skip = page_params(request.args, 10)
    return out(admin_articles_data(request.args.get("q"), request.args.get("category"), page, limit))


def admin_articles_data(q, category, page, limit):
    flt = {}
    if category in CATEGORY_SLUGS:
        flt["category"] = category
    if q:
        rx = {"$regex": regex_escape(str(q)[:60]), "$options": "i"}
        flt["$or"] = [{"title": rx}, {"source": rx}, {"tags": rx}]
    col = get_db()[ARTICLES]
    items = list(col.find(flt, A.NO_CONTENT).sort("publishedAt", -1).skip((page - 1) * limit).limit(limit))
    total = col.count_documents(flt)
    return {"articles": items, "page": page, "total": total, "pages": max(1, -(-total // limit))}


@bp.get("/admin/articles/<article_id>")
@api_admin_required
def admin_article_get(article_id):
    art = A.get(aid(article_id))
    if not art:
        raise ApiError(404, "Article not found.")
    return out({"article": art})


@bp.post("/admin/articles")
@api_admin_required
def admin_article_create():
    art = A.create(A.build_payload(body()))
    clear_cache()
    return out({"article": art}, 201)


@bp.put("/admin/articles/<article_id>")
@api_admin_required
def admin_article_update(article_id):
    art = A.update(aid(article_id), A.build_payload(body(), partial=True))
    clear_cache()
    return out({"article": art})


@bp.delete("/admin/articles/<article_id>")
@api_admin_required
def admin_article_delete(article_id):
    db = get_db()
    oid = to_oid(aid(article_id))
    if not db[ARTICLES].find_one_and_delete({"_id": oid}):
        raise ApiError(404, "Article not found.")
    db[BOOKMARKS].delete_many({"article": oid})
    db[LIKES].delete_many({"article": oid})
    db[HISTORY].delete_many({"articleId": oid})
    db[USERS].update_many({}, {"$pull": {"bookmarks": oid, "likedArticles": oid}})
    clear_cache()
    return out({"deleted": True})


@bp.post("/admin/import")
@api_admin_required
def admin_import():
    return out(import_external_news())


@bp.get("/admin/users")
@api_admin_required
def admin_users():
    page, limit, _ = page_params(request.args, 10)
    return out(admin_users_data(request.args.get("q"), page, limit))


def admin_users_data(q, page, limit):
    db = get_db()
    flt = {}
    if q:
        rx = {"$regex": regex_escape(str(q)[:60]), "$options": "i"}
        flt["$or"] = [{"name": rx}, {"email": rx}]
    users = list(db[USERS].find(flt).sort("createdAt", -1).skip((page - 1) * limit).limit(limit))
    total = db[USERS].count_documents(flt)
    ids = [u["_id"] for u in users]
    reads = db[HISTORY].aggregate([{"$match": {"userId": {"$in": ids}}}, {"$group": {"_id": "$userId", "count": {"$sum": 1}}}])
    read_map = {r["_id"]: r["count"] for r in reads}
    rows = []
    for u in users:
        u = {k: v for k, v in u.items() if k != "password"}
        u["bookmarkCount"] = len(u.get("bookmarks", []))
        u["likeCount"] = len(u.get("likedArticles", []))
        u["readCount"] = read_map.get(u["_id"], 0)
        rows.append(u)
    return {"users": rows, "page": page, "total": total, "pages": max(1, -(-total // limit))}


@bp.patch("/admin/users/<user_id>/role")
@api_admin_required
def admin_user_role(user_id):
    role = body().get("role")
    if role not in ("user", "admin"):
        raise ApiError(400, 'Role must be "user" or "admin".')
    if str(current_user()["_id"]) == user_id:
        raise ApiError(400, "You cannot change your own role.")
    user = U.find_by_id(user_id)
    if not user:
        raise ApiError(404, "User not found.")
    return out({"user": U.public(U.update(user["_id"], {"role": role}))})


@bp.delete("/admin/users/<user_id>")
@api_admin_required
def admin_user_delete(user_id):
    if not valid_oid(user_id):
        raise ApiError(404, "User not found.")
    if str(current_user()["_id"]) == user_id:
        raise ApiError(400, "You cannot delete your own account.")
    db = get_db()
    oid = to_oid(user_id)
    user = db[USERS].find_one_and_delete({"_id": oid})
    if not user:
        raise ApiError(404, "User not found.")
    if user.get("likedArticles"):
        db[ARTICLES].update_many({"_id": {"$in": user["likedArticles"]}}, {"$inc": {"likes": -1}})
    db[BOOKMARKS].delete_many({"user": oid})
    db[LIKES].delete_many({"user": oid})
    db[HISTORY].delete_many({"userId": oid})
    clear_cache()
    return out({"deleted": True})
