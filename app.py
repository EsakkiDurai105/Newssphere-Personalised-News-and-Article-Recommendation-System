"""NewsSphere – Flask application factory and entry point.

    python seed.py     # (optional) load sample articles into MongoDB Atlas
    python app.py      # http://localhost:5000
"""
import logging
import os

from flask import Flask, jsonify, render_template, render_template_string, request

from config import Config
from extensions import ARTICLES, get_db, init_db
from utils import jinja as jinja_utils
from utils.auth import current_user
from utils.constants import CATEGORIES
from utils.helpers import ApiError

log = logging.getLogger("newssphere")


def create_app(config_class=Config, mongo_client=None):
    config_class.finalize()
    base_dir = os.path.dirname(os.path.abspath(__file__))
    app = Flask(
        __name__,
        template_folder=os.path.join(base_dir, "templates"),
        static_folder=os.path.join(base_dir, "static"),
    )
    app.config.from_object(config_class)

    init_db(config_class.MONGODB_URI, client=mongo_client)
    jinja_utils.register(app)

    from routes.api import bp as api_bp
    from routes.pages import bp as pages_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp)

    if app.config["SEED_ON_EMPTY"]:
        try:
            if get_db()[ARTICLES].estimated_document_count() == 0:
                from services.seed_service import DEMO_ACCOUNTS, seed_database

                log.warning("Database is empty – seeding sample articles and demo accounts…")
                seed_database()
                log.warning("  admin: %s / %s", DEMO_ACCOUNTS["admin"]["email"], DEMO_ACCOUNTS["admin"]["password"])
                log.warning("  demo : %s / %s", DEMO_ACCOUNTS["demo"]["email"], DEMO_ACCOUNTS["demo"]["password"])
        except Exception as exc:
            log.warning("Could not check/seed database on startup: %s", exc)

    # ------------------------------------------------------------ template context
    @app.context_processor
    def inject_globals():
        user = current_user()
        return {
            "user": user,
            "is_admin": bool(user and user.get("role") == "admin"),
            "bookmark_ids": {str(b) for b in (user or {}).get("bookmarks", [])},
            "liked_ids": {str(b) for b in (user or {}).get("likedArticles", [])},
            "categories": CATEGORIES,
            "path": request.path,
            "now_year": __import__("datetime").datetime.utcnow().year,
            "now_dt": __import__("datetime").datetime.utcnow(),
            "breaking": lambda: __import__("services.feed", fromlist=["breaking"]).breaking(),
        }

    # ------------------------------------------------------------ configuration check
    @app.before_request
    def check_database_config():
        if not config_class.MONGODB_URI and not request.path.startswith("/static/"):
            return render_template_string("""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Setup Required – NewsSphere</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; padding: 2rem; display: flex; justify-content: center; align-items: center; min-height: 85vh; margin: 0; }
    .card { background: #1e293b; border: 1px solid #334155; border-radius: 16px; padding: 2.5rem; max-width: 650px; width: 100%; box-shadow: 0 20px 25px -5px rgba(0,0,0,0.5); }
    h1 { color: #f43f5e; margin-top: 0; font-size: 1.5rem; }
    p { line-height: 1.6; color: #94a3b8; }
    code { background: #0f172a; color: #38bdf8; padding: 0.2rem 0.4rem; border-radius: 4px; font-size: 0.9em; word-break: break-all; }
    ol { color: #cbd5e1; padding-left: 1.2rem; line-height: 1.8; }
    li { margin-bottom: 0.8rem; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Database Connection Needed</h1>
    <p>NewsSphere is deployed on Vercel, but <code>MONGODB_URI</code> is not yet configured in your Vercel Project Settings.</p>
    <h3 style="color: #e2e8f0;">Quick 2-Step Fix:</h3>
    <ol>
      <li>Go to your <strong>Vercel Dashboard &rarr; Settings &rarr; Environment Variables</strong> and add:
        <br><code>MONGODB_URI</code> = <code>mongodb+srv://24104105_db_user:esakki46@esakkiduraim.tiqwods.mongodb.net/newsphere</code>
        <br><code>SECRET_KEY</code> = <code>6fda81ef0c3e33fb70eb9d857c4c51473acc74e527b144759eb1d1e5cf73d2a0</code>
        <br><code>JWT_SECRET</code> = <code>37a54d5e2b479fba1f9cbf867f162839074fa928453239ff09e534b987d09e90</code>
        <br><code>SEED_ON_EMPTY</code> = <code>true</code>
      </li>
      <li>In <strong>MongoDB Atlas &rarr; Network Access</strong>, ensure <code>0.0.0.0/0</code> is whitelisted so Vercel can connect.</li>
    </ol>
    <p>Once saved, click <strong>Redeploy</strong> in Vercel to launch the app!</p>
  </div>
</body>
</html>"""), 503

    # ------------------------------------------------------------ security
    @app.before_request
    def csrf_guard():
        """Cookie-authenticated state-changing API calls must come from our own JS (custom header)."""
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.path.startswith("/api/"):
            if request.headers.get("Authorization", "").startswith("Bearer "):
                return None
            if request.headers.get("X-Requested-With") != "fetch" and not request.is_json:
                return jsonify(message="Forbidden: missing X-Requested-With header."), 403
        return None

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if request.path.startswith("/api/") or request.path.startswith("/admin"):
            resp.headers["Cache-Control"] = "no-store"
        elif resp.mimetype == "text/html":
            resp.headers.setdefault("Cache-Control", "no-cache")
        return resp

    # ------------------------------------------------------------ errors
    @app.errorhandler(ApiError)
    def api_error(err):
        body = {"message": err.message}
        if err.errors:
            body["errors"] = err.errors
        return jsonify(body), err.status

    @app.errorhandler(404)
    def not_found(_err):
        if request.path.startswith("/api/"):
            return jsonify(message=f"Route not found: {request.method} {request.path}"), 404
        return render_template("404.html", title="Page not found"), 404

    @app.errorhandler(413)
    def too_large(_err):
        return jsonify(message="Request too large."), 413

    @app.errorhandler(500)
    def server_error(err):
        log.exception("Unhandled error: %s", err)
        if request.path.startswith("/api/"):
            return jsonify(message="Something went wrong."), 500
        return render_template("404.html", title="Something went wrong", server_error=True), 500

    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    application = create_app()
    application.run(host="0.0.0.0", port=Config.PORT, debug=Config.DEBUG)
