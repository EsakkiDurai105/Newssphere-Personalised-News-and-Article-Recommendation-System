"""Jinja filters/globals – ports of frontend/src/utils/format.js plus the lucide icon renderer."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from markupsafe import Markup, escape

from utils.constants import CATEGORIES

ICON_DIR = Path(__file__).resolve().parent.parent / "static" / "icons"

# lucide-react component names -> lucide-static file names
ICON_ALIASES = {
    "AlertCircle": "circle-alert", "AlertTriangle": "triangle-alert", "CheckCircle2": "circle-check", "Loader2": "loader-circle",
    "Home": "house", "Check": "check", "Bookmark": "bookmark", "Clock": "clock", "Eye": "eye", "Heart": "heart", "Mail": "mail",
    "Menu": "menu", "Moon": "moon", "Sun": "sun", "Search": "search", "SearchX": "search-x", "Sparkles": "sparkles", "Shield": "shield",
    "ShieldCheck": "shield-check", "ShieldOff": "shield-off", "Share2": "share-2", "Link2": "link-2", "Info": "info", "Inbox": "inbox",
    "Flame": "flame", "History": "history", "LogOut": "log-out", "Plus": "plus", "Pencil": "pencil", "Trash2": "trash-2", "User": "user",
    "Users": "users", "X": "x", "Newspaper": "newspaper", "ExternalLink": "external-link", "FileText": "file-text", "Settings2": "settings-2",
    "SlidersHorizontal": "sliders-horizontal", "LayoutDashboard": "layout-dashboard", "CloudDownload": "cloud-download", "BookOpen": "book-open",
    "ArrowRight": "arrow-right", "ArrowUpRight": "arrow-up-right", "ChevronLeft": "chevron-left", "ChevronRight": "chevron-right",
}

_icon_cache = {}


def _load(name):
    name = ICON_ALIASES.get(name, name)
    if name not in _icon_cache:
        raw = (ICON_DIR / f"{name}.svg").read_text(encoding="utf-8")
        inner = re.search(r"<svg[^>]*>(.*)</svg>", raw, re.S).group(1)
        _icon_cache[name] = (name, re.sub(r"\s+", " ", inner).strip())
    return _icon_cache[name]


def icon(name, cls="", fill=None):
    """Inline SVG with the same attributes lucide-react emits (so Tailwind sizing behaves identically)."""
    canonical, inner = _load(name)
    fill_attr = fill if fill else "none"
    return Markup(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="{escape(fill_attr)}" '
        f'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
        f'class="lucide lucide-{canonical} {escape(cls)}" aria-hidden="true">{inner}</svg>'
    )


def icons_json(*names):
    """Inner SVG markup for the few icons the client-side JS needs to render dynamically."""
    return Markup(json.dumps({n: _load(n)[1] for n in names}))


# ---------------------------------------------------------------- formatting
def _dt(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value
    return None


def time_ago(value):
    d = _dt(value)
    if not d:
        return ""
    diff = max(0, (datetime.now(timezone.utc).replace(tzinfo=None) - d).total_seconds())
    m = int(diff // 60)
    if m < 1:
        return "Just now"
    if m < 60:
        return f"{m}m ago"
    h = m // 60
    if h < 24:
        return f"{h}h ago"
    days = h // 24
    if days < 7:
        return f"{days}d ago"
    return f"{d.strftime('%b')} {d.day}"


def format_date(value):
    d = _dt(value)
    return f"{d.strftime('%A, %B')} {d.day}, {d.year}" if d else ""


def format_time(value):
    d = _dt(value)
    if not d:
        return ""
    hour = d.hour % 12 or 12
    return f"{hour}:{d.minute:02d} {'AM' if d.hour < 12 else 'PM'}"


def compact(n):
    """Intl.NumberFormat(notation: 'compact') for English: 999, 1.2K, 12K, 1.2M …"""
    try:
        n = float(n or 0)
    except (TypeError, ValueError):
        return "0"
    for limit, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(n) >= limit:
            v = n / limit
            s = f"{v:.1f}" if v < 10 else f"{v:.0f}"
            return s[:-2] + suffix if s.endswith(".0") else s + suffix
    return str(int(n))


def initials(name):
    parts = [p for p in str(name or "").split() if p][:2]
    return "".join(p[0].upper() for p in parts) or "?"


def cat_label(slug):
    for c in CATEGORIES:
        if c["slug"] == slug:
            return c["label"]
    return (slug[:1].upper() + slug[1:]) if slug else ""


def iso_z(value):
    from utils.helpers import iso

    return iso(value) if value else ""


def highlight_terms(text, terms):
    """Port of Highlight() in ArticleCards.jsx – wraps query terms in <mark>."""
    text = str(text or "")
    terms = [t for t in (terms or []) if t]
    if not terms:
        return escape(text)
    pat = re.compile("(" + "|".join(re.escape(t) for t in terms) + ")", re.I)
    out, last = [], 0
    for m in pat.finditer(text):
        out.append(str(escape(text[last:m.start()])))
        out.append('<mark class="rounded-[2px] bg-accent/15 px-0.5 text-current">' + str(escape(m.group(0))) + "</mark>")
        last = m.end()
    out.append(str(escape(text[last:])))
    return Markup("".join(out))


def register(app):
    app.jinja_env.globals["icon"] = icon
    app.jinja_env.globals["icons_json"] = icons_json
    app.jinja_env.filters.update(
        time_ago=time_ago, format_date=format_date, format_time=format_time, compact=compact,
        initials=initials, cat_label=cat_label, iso_z=iso_z, highlight_terms=highlight_terms,
    )
