"""Bookmarks, likes and reading history (ports of Bookmark/Like/ReadingHistory models + controllers)."""
from datetime import timedelta

from pymongo.errors import DuplicateKeyError

from extensions import ARTICLES, BOOKMARKS, HISTORY, LIKES, USERS, get_db
from models import articles as article_model
from utils.helpers import ApiError, now, paged, to_oid

DEDUPE_WINDOW = timedelta(minutes=30)


def _article_or_404(article_id):
    oid = to_oid(article_id)
    art = get_db()[ARTICLES].find_one({"_id": oid}, {"category": 1, "likes": 1}) if oid else None
    if not art:
        raise ApiError(404, "Article not found.")
    return art


def _hydrate(rows, key):
    """Attach the article document (without body) to each row, preserving order and skipping dangling refs."""
    ids = [r[key] for r in rows]
    found = {a["_id"]: a for a in get_db()[ARTICLES].find({"_id": {"$in": ids}}, article_model.NO_CONTENT)}
    return [(r, found[r[key]]) for r in rows if r[key] in found]


# ----------------------------------------------------------------- bookmarks
def bookmark_list(user_id, page=1, limit=12):
    flt = {"user": user_id}
    rows = list(get_db()[BOOKMARKS].find(flt).sort("createdAt", -1).skip((page - 1) * limit).limit(limit))
    total = get_db()[BOOKMARKS].count_documents(flt)
    items = [{**a, "savedAt": r["createdAt"]} for r, a in _hydrate(rows, "article")]
    res = paged(items, total, page, limit)
    return res


def bookmark_add(user_id, article_id):
    art = _article_or_404(article_id)
    try:
        get_db()[BOOKMARKS].update_one(
            {"user": user_id, "article": art["_id"]},
            {"$setOnInsert": {"category": art["category"], "createdAt": now(), "updatedAt": now()}},
            upsert=True,
        )
    except DuplicateKeyError:
        pass
    get_db()[USERS].update_one({"_id": user_id}, {"$addToSet": {"bookmarks": art["_id"]}})


def bookmark_remove(user_id, article_id):
    oid = to_oid(article_id)
    if not oid:
        raise ApiError(404, "Article not found.")
    get_db()[BOOKMARKS].delete_one({"user": user_id, "article": oid})
    get_db()[USERS].update_one({"_id": user_id}, {"$pull": {"bookmarks": oid}})


# --------------------------------------------------------------------- likes
def like(user_id, article_id):
    art = _article_or_404(article_id)
    res = get_db()[LIKES].update_one(
        {"user": user_id, "article": art["_id"]},
        {"$setOnInsert": {"category": art["category"], "createdAt": now(), "updatedAt": now()}},
        upsert=True,
    )
    likes = art.get("likes", 0)
    if res.upserted_id is not None:
        updated = get_db()[ARTICLES].find_one_and_update({"_id": art["_id"]}, {"$inc": {"likes": 1}}, return_document=True)
        likes = updated["likes"]
    get_db()[USERS].update_one({"_id": user_id}, {"$addToSet": {"likedArticles": art["_id"]}})
    return likes


def unlike(user_id, article_id):
    art = _article_or_404(article_id)
    res = get_db()[LIKES].delete_one({"user": user_id, "article": art["_id"]})
    likes = art.get("likes", 0)
    if res.deleted_count:
        updated = get_db()[ARTICLES].find_one_and_update({"_id": art["_id"]}, {"$inc": {"likes": -1}}, return_document=True)
        likes = max(0, updated["likes"])
    get_db()[USERS].update_one({"_id": user_id}, {"$pull": {"likedArticles": art["_id"]}})
    return likes


def like_list(user_id, page=1, limit=12):
    flt = {"user": user_id}
    rows = list(get_db()[LIKES].find(flt).sort("createdAt", -1).skip((page - 1) * limit).limit(limit))
    total = get_db()[LIKES].count_documents(flt)
    items = [{**a, "likedAt": r["createdAt"]} for r, a in _hydrate(rows, "article")]
    return paged(items, total, page, limit)


# ------------------------------------------------------------------- history
def history_record(user_id, article_id):
    """Re-opening the same story within 30 minutes only refreshes the timestamp."""
    art = _article_or_404(article_id)
    col = get_db()[HISTORY]
    recent = col.find_one_and_update(
        {"userId": user_id, "articleId": art["_id"], "readAt": {"$gte": now() - DEDUPE_WINDOW}},
        {"$set": {"readAt": now()}},
    )
    if not recent:
        col.insert_one({"userId": user_id, "articleId": art["_id"], "category": art["category"], "readAt": now()})


def history_list(user_id, page=1, limit=15):
    col = get_db()[HISTORY]
    flt = {"userId": user_id}
    rows = list(col.find(flt).sort("readAt", -1).skip((page - 1) * limit).limit(limit))
    total = col.count_documents(flt)
    history = [
        {"_id": r["_id"], "readAt": r["readAt"], "category": r["category"], "article": a} for r, a in _hydrate(rows, "articleId")
    ]
    by_category = list(
        col.aggregate(
            [
                {"$match": flt},
                {"$group": {"_id": "$category", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": 5},
            ]
        )
    )
    return {
        "history": history,
        "byCategory": by_category,
        "page": page,
        "total": total,
        "pages": max(1, -(-total // limit)),
        "hasMore": page * limit < total,
    }


def history_clear(user_id):
    get_db()[HISTORY].delete_many({"userId": user_id})


def user_stats(user_id):
    db = get_db()
    return {
        "bookmarks": db[BOOKMARKS].count_documents({"user": user_id}),
        "likes": db[LIKES].count_documents({"user": user_id}),
        "reads": db[HISTORY].count_documents({"userId": user_id}),
    }
