"""Seeds the sample articles (data/sample_articles.json – exported unchanged from the original seed/articles.js)
and the two demo accounts. Port of services/seedService.js."""
import json
from datetime import timedelta
from pathlib import Path

from extensions import ARTICLES, BOOKMARKS, HISTORY, LIKES, SUBSCRIBERS, USERS, get_db
from models import articles as A
from models import users as U
from utils.helpers import clear_cache, now

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "sample_articles.json"

DEMO_ACCOUNTS = {
    "admin": {"name": "Site Admin", "email": "admin@newssphere.com", "password": "Admin@12345"},
    "demo": {"name": "Demo Reader", "email": "demo@newssphere.com", "password": "Demo@12345"},
}


def seed_database(reset=False):
    db = get_db()
    if reset:
        for name in (ARTICLES, USERS, BOOKMARKS, LIKES, HISTORY, SUBSCRIBERS):
            db[name].delete_many({})

    raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    t0 = now()
    docs = []
    for i, a in enumerate(raw):
        pop = a["popularityScore"]
        published = t0 - timedelta(hours=a["hoursAgo"])
        docs.append(
            {
                "title": a["title"],
                "subtitle": a.get("subtitle", ""),
                "description": a["description"],
                "content": a["content"],
                "image": a["image"],
                "category": a["category"],
                "source": a["source"],
                "author": a["author"],
                "tags": a["tags"],
                "popularityScore": pop,
                "isFeatured": bool(a.get("isFeatured")),
                "isBreaking": bool(a.get("isBreaking")),
                "publishedAt": published,
                # deterministic, plausible engagement numbers (same formula as the Node seed)
                "views": int(pop * (14 + (i % 7) * 3) + (i * 37) % 400 + 0.5),
                "likes": int(pop / 6 + (i % 5) * 3 + 0.5),  # JS Math.round semantics
                "readingTime": A.reading_time(a["content"]),
                "createdAt": t0,
                "updatedAt": t0,
            }
        )
    if docs:
        res = db[ARTICLES].insert_many(docs)
        for d, oid in zip(docs, res.inserted_ids):
            d["_id"] = oid

    acc = DEMO_ACCOUNTS
    admin = U.find_by_email(acc["admin"]["email"]) or U.create(
        acc["admin"]["name"], acc["admin"]["email"], acc["admin"]["password"],
        role="admin", interests=["technology", "business", "world"], onboarded=True,
    )
    demo = U.find_by_email(acc["demo"]["email"])
    if not demo:
        demo = U.create(
            acc["demo"]["name"], acc["demo"]["email"], acc["demo"]["password"],
            interests=["technology", "science", "gaming"], onboarded=True,
        )
        by_cat = lambda c: [d for d in docs if d["category"] == c]  # noqa: E731
        reads = by_cat("technology")[:3] + by_cat("science")[:2] + by_cat("gaming")[:1]
        if reads:
            db[HISTORY].insert_many(
                [
                    {"userId": demo["_id"], "articleId": a["_id"], "category": a["category"], "readAt": t0 - timedelta(hours=(i + 1) * 5)}
                    for i, a in enumerate(reads)
                ]
            )
            liked, saved = by_cat("technology")[1], by_cat("science")[0]
            db[LIKES].insert_one({"user": demo["_id"], "article": liked["_id"], "category": liked["category"], "createdAt": t0, "updatedAt": t0})
            db[BOOKMARKS].insert_one({"user": demo["_id"], "article": saved["_id"], "category": saved["category"], "createdAt": t0, "updatedAt": t0})
            db[USERS].update_one({"_id": demo["_id"]}, {"$set": {"likedArticles": [liked["_id"]], "bookmarks": [saved["_id"]]}})

    clear_cache()
    return {"articles": len(docs), "users": [admin["email"], demo["email"]]}
