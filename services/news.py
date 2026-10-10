"""External news ingestion (port of services/newsService.js). Server side only – keys never reach the browser.

Supports NewsAPI (NEWS_API_KEY) and RSS 2.0 feeds listed in RSS_FEEDS as  "category|url,category|url".
With nothing configured the site simply keeps using the articles stored in MongoDB.
"""
import html
import random
import re
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import requests
from flask import current_app

from extensions import ARTICLES, get_db
from models import articles as A
from utils.constants import CATEGORY_SLUGS
from utils.helpers import clear_cache, now

NEWSAPI_MAP = {
    "world": ("top-headlines", {"category": "general"}),
    "politics": ("everything", {"q": "politics OR parliament OR election", "sortBy": "publishedAt", "language": "en"}),
    "technology": ("top-headlines", {"category": "technology"}),
    "business": ("top-headlines", {"category": "business"}),
    "science": ("top-headlines", {"category": "science"}),
    "health": ("top-headlines", {"category": "health"}),
    "sports": ("top-headlines", {"category": "sports"}),
    "entertainment": ("top-headlines", {"category": "entertainment"}),
    "gaming": ("everything", {"q": "video games OR gaming OR esports", "sortBy": "publishedAt", "language": "en"}),
    "lifestyle": ("everything", {"q": "lifestyle OR wellness OR home design", "sortBy": "publishedAt", "language": "en"}),
    "travel": ("everything", {"q": "travel OR tourism OR airlines", "sortBy": "publishedAt", "language": "en"}),
}
STOP = set("the a an and or of to in on for with from by at is are was were be as it its this that new says say after over into more about how why what who will can could".split())


def _tags_from(title, category):
    words = [w for w in re.sub(r"[^a-z0-9\s]", " ", (title or "").lower()).split() if len(w) > 3 and w not in STOP]
    out = []
    for t in [category] + words:
        if t not in out:
            out.append(t)
    return out[:5]


def _strip_html(s=""):
    s = re.sub(r"<!\[CDATA\[([\s\S]*?)\]\]>", r"\1", s or "")
    s = re.sub(r"<[^>]*>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def _doc(title, description, content, image, category, source, author, published_at, url):
    desc = (description or "")[:480]
    body = content if content and len(content) > len(desc) else f"{desc}\n\nRead the full report at {source}: {url}"
    return {
        "title": title[:220],
        "description": desc or title,
        "content": body,
        "image": image or "",
        "category": category,
        "source": source or "External",
        "author": author or source or "Staff Reporter",
        "publishedAt": published_at or now(),
        "tags": _tags_from(title, category),
        "popularityScore": 35 + random.randint(0, 39),
        "sourceUrl": url,
    }


def _parse_dt(value):
    from datetime import datetime
    from email.utils import parsedate_to_datetime

    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(value).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def _from_newsapi(category, page_size, key):
    endpoint, params = NEWSAPI_MAP[category]
    qs = {**params, "pageSize": page_size, "apiKey": key}
    if endpoint == "top-headlines":
        qs["country"] = "us"
    res = requests.get(f"https://newsapi.org/v2/{endpoint}", params=qs, timeout=15)
    if not res.ok:
        raise RuntimeError(f"NewsAPI {res.status_code}: {res.text[:120]}")
    out = []
    for a in res.json().get("articles", []):
        if not a.get("title") or not a.get("url") or a["title"] == "[Removed]":
            continue
        out.append(
            _doc(
                re.sub(r"\s+-\s+[^-]+$", "", a["title"]),
                a.get("description"),
                re.sub(r"\s*\[\+\d+ chars\]$", "", a.get("content") or ""),
                a.get("urlToImage"),
                category,
                (a.get("source") or {}).get("name"),
                a.get("author"),
                _parse_dt(a.get("publishedAt")),
                a["url"],
            )
        )
    return out


def _from_rss(category, url, limit):
    res = requests.get(url, headers={"user-agent": "NewsSphere/1.0"}, timeout=15)
    if not res.ok:
        raise RuntimeError(f"RSS {res.status_code} for {url}")
    root = ET.fromstring(res.content)
    ns = {"media": "http://search.yahoo.com/mrss/", "dc": "http://purl.org/dc/elements/1.1/", "content": "http://purl.org/rss/1.0/modules/content/"}
    channel = root.find("channel")
    channel_title = _strip_html(channel.findtext("title", "")) if channel is not None else ""
    channel_title = channel_title or urlparse(url).hostname or "RSS"
    out = []
    for item in (channel.findall("item") if channel is not None else [])[:limit]:
        title = _strip_html(item.findtext("title", ""))
        link = _strip_html(item.findtext("link", ""))
        if not title or not link:
            continue
        img = ""
        for tag in ("media:content", "media:thumbnail"):
            el = item.find(tag, ns)
            if el is not None and el.get("url"):
                img = el.get("url")
                break
        if not img:
            enc = item.find("enclosure")
            if enc is not None and (enc.get("type") or "").startswith("image") and enc.get("url"):
                img = enc.get("url")
        out.append(
            _doc(
                title,
                _strip_html(item.findtext("description", "")),
                _strip_html(item.findtext("content:encoded", "", ns)),
                img,
                category,
                channel_title,
                _strip_html(item.findtext("dc:creator", "", ns)) or channel_title,
                _parse_dt(item.findtext("pubDate")),
                link,
            )
        )
    return out


def import_external_news(per_category=8):
    cfg = current_app.config
    summary = {"inserted": 0, "skipped": 0, "errors": [], "providers": []}
    docs = []
    if cfg.get("NEWS_API_KEY"):
        summary["providers"].append("newsapi")
        for cat in CATEGORY_SLUGS:
            try:
                docs += _from_newsapi(cat, per_category, cfg["NEWS_API_KEY"])
            except Exception as exc:  # noqa: BLE001 - report and continue
                summary["errors"].append(f"newsapi/{cat}: {exc}")
    feeds = [f.strip() for f in (cfg.get("RSS_FEEDS") or "").split(",") if f.strip()]
    if feeds:
        summary["providers"].append("rss")
    for entry in feeds:
        cat, _, url = entry.partition("|")
        if cat not in CATEGORY_SLUGS or not url:
            summary["errors"].append(f'rss: invalid entry "{entry}"')
            continue
        try:
            docs += _from_rss(cat, url, per_category)
        except Exception as exc:  # noqa: BLE001
            summary["errors"].append(f"rss/{cat}: {exc}")

    col = get_db()[ARTICLES]
    for d in docs:
        if col.find_one({"sourceUrl": d["sourceUrl"]}, {"_id": 1}):
            summary["skipped"] += 1
            continue
        try:
            A.create(d)
            summary["inserted"] += 1
        except Exception as exc:  # noqa: BLE001
            summary["errors"].append(f"{d['title'][:40]}: {exc}")
    if summary["inserted"]:
        clear_cache()
    if not summary["providers"]:
        summary["errors"].append("No provider configured. Set NEWS_API_KEY and/or RSS_FEEDS in .env.")
    return summary
