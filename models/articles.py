"""Article data access (port of models/Article.js + articleController.js queries)."""
import re

from pymongo import ReturnDocument

from extensions import ARTICLES, get_db
from utils.constants import CATEGORY_SLUGS
from utils.helpers import ApiError, assert_valid, now, paged, regex_escape, to_oid

NO_CONTENT = {"content": 0}
SORTS = {
    "latest": [("publishedAt", -1)],
    "popular": [("views", -1), ("popularityScore", -1)],
}


def col():
    return get_db()[ARTICLES]


def reading_time(content):
    words = len(str(content or "").split())
    return max(1, int(words / 200 + 0.5))  # JS Math.round semantics


def get(article_id, with_content=True):
    oid = to_oid(article_id)
    if not oid:
        return None
    return col().find_one({"_id": oid}, None if with_content else NO_CONTENT)


def inc_views(article_id):
    oid = to_oid(article_id)
    if not oid:
        return None
    return col().find_one_and_update({"_id": oid}, {"$inc": {"views": 1}}, return_document=ReturnDocument.AFTER)


def find_many(filter_=None, sort="latest", skip=0, limit=12):
    cur = col().find(filter_ or {}, NO_CONTENT).sort(SORTS.get(sort, SORTS["latest"])).skip(skip).limit(limit)
    return list(cur)


def list_articles(category=None, source=None, sort="latest", page=1, limit=12):
    flt = {}
    if category in CATEGORY_SLUGS:
        flt["category"] = category
    if source:
        flt["source"] = source
    skip = (page - 1) * limit
    return paged(find_many(flt, sort, skip, limit), col().count_documents(flt), page, limit)


def by_category(category, sort="latest", page=1, limit=9):
    flt = {"category": category}
    skip = (page - 1) * limit
    return paged(find_many(flt, sort, skip, limit), col().count_documents(flt), page, limit)


def latest(page=1, limit=10):
    skip = (page - 1) * limit
    return paged(find_many({}, "latest", skip, limit), col().count_documents({}), page, limit)


def most_viewed(limit=5):
    return find_many({}, "popular", 0, limit)


def distinct_sources():
    return sorted(col().distinct("source"))


def search(q="", category=None, source=None, sort=None, page=1, limit=10):
    q = (q or "").strip()[:80]
    flt = {}
    if category in CATEGORY_SLUGS:
        flt["category"] = category
    if source:
        flt["source"] = source
    sort = sort or ("relevance" if q else "latest")
    terms = [t for t in q.split() if t][:5]

    and_clauses = []
    for t in terms:
        rx = {"$regex": regex_escape(t), "$options": "i"}
        and_clauses.append({"$or": [{f: rx} for f in ("title", "description", "source", "category", "tags", "author")]})
    if and_clauses:
        flt["$and"] = and_clauses

    # facets: matches per category, ignoring the category/source filters (same as the Express version)
    facet_pipeline = []
    if and_clauses:
        facet_pipeline.append({"$match": {"$and": and_clauses}})
    facet_pipeline += [{"$group": {"_id": "$category", "count": {"$sum": 1}}}, {"$sort": {"count": -1}}]
    facets = list(col().aggregate(facet_pipeline))

    skip = (page - 1) * limit
    if sort == "relevance" and terms:
        candidates = list(col().find(flt, NO_CONTENT).sort("publishedAt", -1).limit(300))
        lc = [t.lower() for t in terms]
        scored = []
        for a in candidates:
            score = 0
            for t in lc:
                if t in a.get("title", "").lower():
                    score += 10
                if any(t in tag for tag in a.get("tags", [])):
                    score += 6
                if t in a.get("category", ""):
                    score += 4
                if t in a.get("source", "").lower():
                    score += 3
                if t in a.get("description", "").lower():
                    score += 3
            a = dict(a)
            a["relevance"] = score + a.get("popularityScore", 0) / 100
            scored.append(a)
        scored.sort(key=lambda x: x["relevance"], reverse=True)
        result = paged(scored[skip : skip + limit], len(scored), page, limit)
    else:
        result = paged(find_many(flt, sort, skip, limit), col().count_documents(flt), page, limit)
    result["facets"] = facets
    result["query"] = q
    return result


def related(article_id, limit=4):
    base = get(article_id, with_content=False)
    if not base:
        return None
    flt = {"_id": {"$ne": base["_id"]}, "$or": [{"category": base["category"]}, {"tags": {"$in": base.get("tags", [])}}]}
    candidates = list(col().find(flt, NO_CONTENT).sort("publishedAt", -1).limit(40))
    base_tags = set(base.get("tags", []))

    def rel(a):
        return (2 if a["category"] == base["category"] else 0) + len([t for t in a.get("tags", []) if t in base_tags]) * 3

    candidates.sort(key=lambda a: (rel(a), a["publishedAt"]), reverse=True)
    return candidates[:limit]


# ------------------------------------------------------------------ admin CRUD
def _to_tags(tags):
    items = tags if isinstance(tags, list) else str(tags or "").split(",")
    return [str(t).strip().lower() for t in items if str(t).strip()][:10]


def build_payload(body, partial=False):
    errors, out = {}, {}
    for k in ("title", "subtitle", "description", "content", "image", "source", "author"):
        if body.get(k) is not None:
            out[k] = str(body[k]).strip()[: 100000 if k == "content" else 600]
    if body.get("category") is not None:
        out["category"] = str(body["category"]).lower()
    if body.get("tags") is not None:
        out["tags"] = _to_tags(body["tags"])
    if body.get("publishedAt"):
        from datetime import datetime

        try:
            out["publishedAt"] = datetime.fromisoformat(str(body["publishedAt"]).replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            errors["publishedAt"] = "Invalid date."
    if body.get("popularityScore") is not None:
        try:
            out["popularityScore"] = min(100, max(0, float(body["popularityScore"])))
            if out["popularityScore"].is_integer():
                out["popularityScore"] = int(out["popularityScore"])
        except (TypeError, ValueError):
            out["popularityScore"] = 0
    for flag in ("isBreaking", "isFeatured"):
        if body.get(flag) is not None:
            out[flag] = bool(body[flag])

    def req(field, msg):
        if (not partial or field in out) and not out.get(field):
            errors[field] = msg

    req("title", "Title is required.")
    req("description", "Description is required.")
    req("content", "Article content is required.")
    req("source", "Source is required.")
    if (not partial or "category" in out) and out.get("category") not in CATEGORY_SLUGS:
        errors["category"] = "Choose a valid category."
    if out.get("image") and not re.match(r"^https?://", out["image"], re.I):
        errors["image"] = "Image must be an http(s) URL."
    assert_valid(errors)
    return out


def create(payload):
    doc = {
        "title": payload["title"],
        "subtitle": payload.get("subtitle", ""),
        "description": payload["description"],
        "content": payload["content"],
        "image": payload.get("image", ""),
        "category": payload["category"],
        "source": payload["source"],
        "author": payload.get("author") or "Staff Reporter",
        "publishedAt": payload.get("publishedAt") or now(),
        "tags": payload.get("tags", []),
        "popularityScore": payload.get("popularityScore", 50),
        "views": 0,
        "likes": 0,
        "readingTime": reading_time(payload["content"]),
        "isBreaking": payload.get("isBreaking", False),
        "isFeatured": payload.get("isFeatured", False),
        "createdAt": now(),
        "updatedAt": now(),
    }
    if payload.get("sourceUrl"):
        doc["sourceUrl"] = payload["sourceUrl"]
    res = col().insert_one(doc)
    doc["_id"] = res.inserted_id
    return doc


def update(article_id, payload):
    oid = to_oid(article_id)
    if not oid or not col().find_one({"_id": oid}, {"_id": 1}):
        raise ApiError(404, "Article not found.")
    changes = dict(payload)
    if "content" in changes:
        changes["readingTime"] = reading_time(changes["content"])
    changes["updatedAt"] = now()
    return col().find_one_and_update({"_id": oid}, {"$set": changes}, return_document=ReturnDocument.AFTER)
