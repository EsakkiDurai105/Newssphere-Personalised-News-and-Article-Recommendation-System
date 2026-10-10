"""HTML pages (Jinja2). One route per React Router route of the original app."""
from urllib.parse import urlencode

from flask import Blueprint, abort, jsonify, redirect, render_template, request, url_for

from models import articles as A
from models import interactions as I
from services import feed
from services.recommendation import get_recommendations
from services.trending import get_trending
from utils.auth import admin_page_required, current_user, login_required
from utils.constants import CATEGORIES, CATEGORY_SLUGS, CATEGORY_TINTS
from utils.helpers import page_params, safe_next, to_oid, valid_oid
from utils.jinja import format_date

bp = Blueprint("pages", __name__)

INFO_PAGES = {
    "about": {
        "title": "About NewsSphere", "kicker": "Who we are",
        "body": [
            "NewsSphere is a personalised news reader built around one idea: the front page should be different for everyone, and you should be able to understand why.",
            "Our recommendations are produced by a transparent, rule-based algorithm. It weighs the topics you follow, the categories you read most, the stories you like and save, how popular and how fresh each article is, and whether it is trending — and it demotes stories you have already read. There is no black-box model.",
            "This demo ships with fictional sample stories so it can run entirely offline. Connect a NewsAPI key or RSS feeds on the server to pull in live headlines.",
        ],
    },
    "privacy": {
        "title": "Privacy Policy", "kicker": "Legal",
        "body": [
            "We store the minimum needed to personalise your experience: your name, email, a salted password hash, your chosen interests, and the articles you open, like or save.",
            "Your reading activity is used only to rank stories for you. You can clear your reading history at any time from the History page, and remove saved or liked stories whenever you wish.",
            "We never expose API keys or credentials to the browser, and passwords are never stored in plain text.",
        ],
    },
    "terms": {
        "title": "Terms of Service", "kicker": "Legal",
        "body": [
            "By using NewsSphere you agree to use the service lawfully and not to attempt to disrupt it or access other users’ data.",
            "Articles are provided for information only. Sample content in this demo is fictional and must not be relied upon as real reporting.",
            "We may update these terms from time to time; continued use after changes constitutes acceptance.",
        ],
    },
    "contact": {
        "title": "Contact us", "kicker": "Get in touch",
        "body": [
            "Questions, corrections or partnership ideas? Write to hello@newssphere.example and the newsroom will get back to you within two working days.",
            "Press enquiries: press@newssphere.example. Technical issues: support@newssphere.example.",
        ],
    },
}


def uid():
    u = current_user()
    return u["_id"] if u else None


def fragment(template, **ctx):
    """JSON {html, hasMore, total, shown} used by the 'Load more' buttons."""
    return jsonify(
        html=render_template(template, **ctx),
        hasMore=ctx["data"]["hasMore"],
        total=ctx["data"]["total"],
    )


# --------------------------------------------------------------------- home
@bp.get("/")
def home():
    data = feed.home_data()
    recs = get_recommendations(uid(), 5)
    return render_template("home.html", data=data, recs=recs, title="")


@bp.get("/latest")
def latest():
    page, limit, _ = page_params(request.args, 10)
    data = A.latest(page, limit)
    if request.args.get("partial"):
        return fragment("partials/latest_items.html", data=data, offset=(page - 1) * limit)
    return render_template("latest.html", data=data, title="Latest news")


@bp.get("/trending")
def trending():
    return render_template("trending.html", articles=get_trending(15), title="Trending")


@bp.get("/categories")
def categories():
    return render_template("categories.html", tints=CATEGORY_TINTS, title="All sections")


@bp.get("/category/<slug>")
def category(slug):
    if slug not in CATEGORY_SLUGS:
        abort(404)
    sort = request.args.get("sort", "latest")
    sort = sort if sort in ("latest", "popular") else "latest"
    page, limit, _ = page_params(request.args, 9)
    data = A.by_category(slug, sort, page, limit)
    cat = next(c for c in CATEGORIES if c["slug"] == slug)
    if request.args.get("partial"):
        return fragment("partials/category_items.html", data=data, offset=(page - 1) * limit)
    return render_template("category.html", data=data, cat=cat, sort=sort, title=cat["label"])


@bp.get("/for-you")
def for_you():
    recs = get_recommendations(uid(), 18)
    return render_template("for_you.html", recs=recs, title="For You")


@bp.get("/article/<article_id>")
def article(article_id):
    if not valid_oid(article_id):
        abort(404)
    art = A.inc_views(article_id)  # same as the old API: every page view bumps the counter
    if not art:
        abort(404)
    user = current_user()
    if user:  # reading history – feeds the recommender
        I.history_record(user["_id"], art["_id"])
    related = A.related(article_id, 4) or []
    recs = get_recommendations(uid(), 6, art["_id"])
    return render_template("article.html", article=art, related=related, recs=recs, title=art["title"])


@bp.get("/search")
def search():
    a = request.args
    page, limit, _ = page_params(a, 10)
    sort = a.get("sort") or ("relevance" if a.get("q") else "latest")
    data = A.search(a.get("q", ""), a.get("category"), a.get("source"), sort, page, limit)
    q = a.get("q", "").strip()[:80]
    base = {"q": q, "category": a.get("category", ""), "source": a.get("source", ""), "sort": a.get("sort", "")}

    def su(**patch):
        """Search URL with `patch` applied; changing any filter resets the page (like the React update())."""
        params = {**base, **patch}
        if "page" not in patch:
            params.pop("page", None)
        return "/search?" + urlencode({k: v for k, v in params.items() if v})

    terms = [t for t in q.split() if t]
    return render_template(
        "search.html", data=data, q=q, category=a.get("category", ""), source=a.get("source", ""), sort=sort, page=page,
        sources=A.distinct_sources(), su=su, terms=terms, title=f"Search: {q}" if q else "Search",
    )


# --------------------------------------------------------------------- auth
@bp.get("/login")
def login():
    nxt = safe_next(request.args.get("next"))
    user = current_user()
    if user:
        return redirect(nxt if user.get("onboarded") else url_for("pages.onboarding"))
    return render_template("login.html", next=nxt, title="Sign in")


@bp.get("/register")
def register():
    nxt = safe_next(request.args.get("next"))
    if current_user():
        return redirect(url_for("pages.home"))
    return render_template("register.html", next=nxt, title="Create account")


@bp.get("/onboarding")
@login_required
def onboarding():
    return render_template("onboarding.html", title="Choose your interests")


# ------------------------------------------------------------------ library
@bp.get("/profile")
@login_required
def profile():
    user = current_user()
    history = I.history_list(user["_id"], 1, 6)
    saved = I.bookmark_list(user["_id"], 1, 6)
    liked = I.like_list(user["_id"], 1, 6)
    return render_template(
        "profile.html", stats=I.user_stats(user["_id"]), history=history, saved=saved, liked=liked, title="Your profile"
    )


@bp.get("/bookmarks")
@login_required
def bookmarks():
    page, limit, _ = page_params(request.args, 12)
    data = I.bookmark_list(current_user()["_id"], page, limit)
    if request.args.get("partial"):
        return fragment("partials/story_items.html", data=data, offset=(page - 1) * limit)
    return render_template("bookmarks.html", data=data, title="Saved articles")


@bp.get("/history")
@login_required
def history():
    page, limit, _ = page_params(request.args, 20)
    data = I.history_list(current_user()["_id"], page, limit)
    groups = {}
    from utils.jinja import _dt
    from datetime import datetime, timedelta, timezone

    today = datetime.now(timezone.utc).replace(tzinfo=None).date()
    for h in data["history"]:
        d = _dt(h["readAt"]).date()
        label = "Today" if d == today else "Yesterday" if d == today - timedelta(days=1) else f"{d.strftime('%A, %B')} {d.day}"
        groups.setdefault(label, []).append(h)
    return render_template("history.html", data=data, groups=groups, page=page, title="Reading history")


@bp.get("/page/<slug>")
def info(slug):
    page = INFO_PAGES.get(slug)
    if not page:
        abort(404)
    return render_template("info.html", page=page, title=page["title"])


# -------------------------------------------------------------------- admin
@bp.get("/admin")
@admin_page_required
def admin_dashboard():
    from routes.api import admin_stats_data

    from datetime import datetime, timedelta

    stats = admin_stats_data()
    reads = {a["_id"]: a.get("reads", 0) for a in stats.get("activity", [])}
    today = datetime.utcnow()
    days = []
    for i in range(7):
        d = today - timedelta(days=6 - i)
        key = d.strftime("%Y-%m-%d")
        days.append({"key": key, "label": d.strftime("%a"), "reads": reads.get(key, 0)})
    return render_template("admin/dashboard.html", stats=stats, days=days, title="Admin overview")


@bp.get("/admin/articles")
@admin_page_required
def admin_articles():
    from routes.api import admin_articles_data

    page, limit, _ = page_params(request.args, 10)
    q, cat = request.args.get("q", ""), request.args.get("category", "")
    data = admin_articles_data(q, cat, page, limit)
    return render_template("admin/articles.html", data=data, q=q, category=cat, page=page, open_new=bool(request.args.get("new")), title="Manage articles")


@bp.get("/admin/users")
@admin_page_required
def admin_users():
    from routes.api import admin_users_data

    page, limit, _ = page_params(request.args, 10)
    q = request.args.get("q", "")
    return render_template("admin/users.html", data=admin_users_data(q, page, limit), q=q, page=page, title="Manage users")
