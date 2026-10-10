"""Trending = engagement weighted by recency (port of services/trendingService.js).

    engagement = popularityScore + 8 * ln(1 + views) + 3 * likes
    recency    = 0.4 + 0.6 * e^(-ageHours / 96)
Computed over the most recent 200 stories of the last 30 days and cached for a minute.
"""
import math
from datetime import timedelta

from extensions import ARTICLES, get_db
from models.articles import NO_CONTENT
from utils.helpers import cached, hours_since, now


def _compute():
    since = now() - timedelta(days=30)
    pool = list(get_db()[ARTICLES].find({"publishedAt": {"$gte": since}}, NO_CONTENT).sort("publishedAt", -1).limit(200))
    out = []
    for a in pool:
        age_h = hours_since(a["publishedAt"])
        engagement = a.get("popularityScore", 0) + 8 * math.log1p(a.get("views", 0)) + 3 * a.get("likes", 0)
        item = dict(a)
        item["trendingScore"] = engagement * (0.4 + 0.6 * math.exp(-age_h / 96))
        out.append(item)
    out.sort(key=lambda x: x["trendingScore"], reverse=True)
    return out


def get_trending(limit=10):
    return cached("trending:all", 60, _compute)[:limit]
