"""RULE-BASED RECOMMENDER (no AI / LLM) – direct port of services/recommendationService.js.

    score = interestMatch       * 5
          + readingHistoryMatch * 4
          + likedCategoryMatch  * 5
          + bookmarkCategoryMatch * 5
          + popularityScore     * 2
          + freshnessScore      * 3
          + trendingBonus       * 2
          + tagAffinity         * 2
          - alreadyReadPenalty (8)

Every signal is normalised to 0..1 first so the weights stay meaningful.
"""
import math
from datetime import timedelta

from extensions import ARTICLES, BOOKMARKS, HISTORY, LIKES, USERS, get_db
from models.articles import NO_CONTENT
from services.trending import get_trending
from utils.helpers import hours_since, now

WEIGHTS = {"interest": 5, "history": 4, "liked": 5, "bookmark": 5, "popularity": 2, "freshness": 3, "trending": 2, "tags": 2}
ALREADY_READ_PENALTY = 8


def _label(c):
    return c[:1].upper() + c[1:]


def _normalise(m):
    mx = max([0] + list(m.values()))
    if not mx:
        return {}
    return {k: v / mx for k, v in m.items()}


def build_profile(user_id):
    """Behaviour profile from interests, history, likes and bookmarks."""
    if not user_id:
        return None
    db = get_db()
    user = db[USERS].find_one({"_id": user_id}, {"interests": 1})
    if not user:
        return None
    history = list(db[HISTORY].find({"userId": user_id}).sort("readAt", -1).limit(300))
    likes = list(db[LIKES].find({"user": user_id}).sort("createdAt", -1).limit(200))
    bookmarks = list(db[BOOKMARKS].find({"user": user_id}).sort("createdAt", -1).limit(200))

    hist_cat = {}
    for h in history:
        age_days = hours_since(h["readAt"]) / 24.0
        # recent reads count more
        hist_cat[h["category"]] = hist_cat.get(h["category"], 0) + math.exp(-age_days / 14)
    liked_cat, bookmark_cat = {}, {}
    for l in likes:
        liked_cat[l["category"]] = liked_cat.get(l["category"], 0) + 1
    for b in bookmarks:
        bookmark_cat[b["category"]] = bookmark_cat.get(b["category"], 0) + 1

    read_ids = {h["articleId"] for h in history}

    # Tag affinity: tags of liked / saved / recently read articles
    signal_ids = [l["article"] for l in likes] + [b["article"] for b in bookmarks] + [h["articleId"] for h in history[:50]]
    tag_counts = {}
    if signal_ids:
        for a in db[ARTICLES].find({"_id": {"$in": signal_ids}}, {"tags": 1}):
            for t in a.get("tags", []):
                tag_counts[t] = tag_counts.get(t, 0) + 1

    interests = set(user.get("interests", []))
    return {
        "interests": interests,
        "hist_cat": _normalise(hist_cat),
        "liked_cat": _normalise(liked_cat),
        "bookmark_cat": _normalise(bookmark_cat),
        "tag_affinity": _normalise(tag_counts),
        "read_ids": read_ids,
        "has_signals": bool(interests or history or likes or bookmarks),
    }


def _explain(parts, article):
    reasons = []
    if parts["interest"]:
        reasons.append(f"Because you follow {_label(article['category'])}")
    if parts["liked"] > 0.3:
        reasons.append("Similar to stories you liked")
    if parts["bookmark"] > 0.3:
        reasons.append("Matches your saved stories")
    if parts["history"] > 0.3:
        reasons.append(f"You read a lot of {_label(article['category'])}")
    if parts["tags"] > 0.3:
        reasons.append("Covers topics you engage with")
    if parts["trending"]:
        reasons.append("Trending right now")
    if not reasons:
        reasons.append("Popular and recent")
    return reasons[:2]


def get_recommendations(user_id=None, limit=12, exclude_id=None):
    """user_id=None → generic popularity/freshness/trending ranking (anonymous visitors)."""
    db = get_db()
    profile = build_profile(user_id)
    trending_ids = {t["_id"] for t in get_trending(10)}

    flt = {"publishedAt": {"$gte": now() - timedelta(days=45)}}
    if exclude_id:
        flt["_id"] = {"$ne": exclude_id}
    candidates = list(db[ARTICLES].find(flt, NO_CONTENT).sort("publishedAt", -1).limit(400))
    if len(candidates) < limit:
        older = {"_id": {"$ne": exclude_id}} if exclude_id else {}
        candidates = list(db[ARTICLES].find(older, NO_CONTENT).sort("publishedAt", -1).limit(400))

    max_views = max([1] + [c.get("views", 0) for c in candidates])
    scored = []
    for a in candidates:
        age_h = hours_since(a["publishedAt"])
        parts = {
            "interest": 1 if profile and a["category"] in profile["interests"] else 0,
            "history": profile["hist_cat"].get(a["category"], 0) if profile else 0,
            "liked": profile["liked_cat"].get(a["category"], 0) if profile else 0,
            "bookmark": profile["bookmark_cat"].get(a["category"], 0) if profile else 0,
            "popularity": (a.get("popularityScore", 0) / 100) * 0.6
            + (math.log1p(a.get("views", 0)) / math.log1p(max_views)) * 0.4,
            "freshness": math.exp(-age_h / 72),
            "trending": 1 if a["_id"] in trending_ids else 0,
            "tags": 0,
        }
        if profile and a.get("tags"):
            hits = [profile["tag_affinity"].get(t, 0) for t in a["tags"]]
            hits = [h for h in hits if h]
            parts["tags"] = min(1, sum(hits) / 2) if hits else 0
        already_read = bool(profile and a["_id"] in profile["read_ids"])

        score = (
            parts["interest"] * WEIGHTS["interest"]
            + parts["history"] * WEIGHTS["history"]
            + parts["liked"] * WEIGHTS["liked"]
            + parts["bookmark"] * WEIGHTS["bookmark"]
            + parts["popularity"] * WEIGHTS["popularity"]
            + parts["freshness"] * WEIGHTS["freshness"]
            + parts["trending"] * WEIGHTS["trending"]
            + parts["tags"] * WEIGHTS["tags"]
            - (ALREADY_READ_PENALTY if already_read else 0)
        )
        item = dict(a)
        item["recommendationScore"] = round(score * 100) / 100
        item["reasons"] = _explain(parts, a)
        item["alreadyRead"] = already_read
        scored.append(item)

    scored.sort(key=lambda x: x["recommendationScore"], reverse=True)

    # Diversify: no single category may take more than ~half the feed, then backfill.
    per_cat, picked, overflow = {}, [], []
    max_per = max(3, math.ceil(limit * 0.5))
    for a in scored:
        per_cat[a["category"]] = per_cat.get(a["category"], 0) + 1
        (picked if per_cat[a["category"]] <= max_per else overflow).append(a)
    feed = (picked + overflow)[:limit]
    return {"personalized": bool(profile and profile["has_signals"]), "articles": feed}
