"""Aggregated feeds: homepage payload and breaking-news ticker (port of articleController home/breaking)."""
from extensions import ARTICLES, get_db
from models import articles as A
from services.trending import get_trending
from utils.helpers import cached

SECTION_CATEGORIES = ["technology", "business", "sports", "science"]


def breaking(limit=8):
    def produce():
        proj = {"title": 1, "category": 1, "publishedAt": 1}
        col = get_db()[ARTICLES]
        flagged = list(col.find({"isBreaking": True}, proj).sort("publishedAt", -1).limit(limit))
        if len(flagged) >= 4:
            return flagged
        return list(col.find({}, proj).sort("publishedAt", -1).limit(limit))

    return cached("breaking", 60, produce)


def home_data():
    def produce():
        col = get_db()[ARTICLES]
        featured = list(col.find({"isFeatured": True}, A.NO_CONTENT).sort("publishedAt", -1).limit(1))
        latest = list(col.find({}, A.NO_CONTENT).sort("publishedAt", -1).limit(30))
        if not latest:
            return None
        hero = featured[0] if featured else latest[0]
        rest = [a for a in latest if a["_id"] != hero["_id"]]
        sections = [
            {"category": c, "articles": list(col.find({"category": c}, A.NO_CONTENT).sort("publishedAt", -1).limit(4))}
            for c in SECTION_CATEGORIES
        ]
        return {
            "hero": hero,
            "sideStories": rest[:3],
            "topStories": rest[3:7],
            "latest": rest[7:15],
            "trending": get_trending(8),
            "mostRead": A.most_viewed(5),
            "sections": sections,
        }

    return cached("home", 60, produce)
