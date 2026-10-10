"""NewsSphere – Flask application factory and entry point.

    python seed.py     # (optional) load sample articles into MongoDB Atlas
    python app.py      # http://localhost:5000
"""
import logging
import os

from flask import Flask, jsonify, render_template, request

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

    if app.config["SEED_ON_EMPTY"] and get_db()[ARTICLES].estimated_document_count() == 0:
        from services.seed_service import DEMO_ACCOUNTS, seed_database

        log.warning("Database is empty – seeding sample articles and demo accounts…")
        seed_database()
        log.warning("  admin: %s / %s", DEMO_ACCOUNTS["admin"]["email"], DEMO_ACCOUNTS["admin"]["password"])
        log.warning("  demo : %s / %s", DEMO_ACCOUNTS["demo"]["email"], DEMO_ACCOUNTS["demo"]["password"])

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
