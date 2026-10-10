"""Authentication helpers: bcrypt hashing, Flask-session login, optional JWT bearer tokens, decorators."""
import time
from functools import wraps

import bcrypt
import jwt
from flask import current_app, g, redirect, request, session, url_for

from extensions import USERS, get_db
from utils.helpers import ApiError, to_oid


# ---- passwords (bcrypt, 12 rounds – same algorithm as the original bcryptjs, so existing hashes still verify)
def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(12)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, AttributeError):
        return False


# ---- tokens (kept for API clients; the browser UI uses the signed session cookie)
def make_token(user_id) -> str:
    days = current_app.config.get("JWT_EXPIRES_DAYS", 7)
    payload = {"id": str(user_id), "iat": int(time.time()), "exp": int(time.time()) + days * 86400}
    return jwt.encode(payload, current_app.config["JWT_SECRET"], algorithm="HS256")


def _bearer_user_id():
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    try:
        data = jwt.decode(header[7:], current_app.config["JWT_SECRET"], algorithms=["HS256"])
        return data.get("id")
    except jwt.PyJWTError:
        raise ApiError(401, "Your session has expired. Please sign in again.")


def current_user():
    """The signed-in user document (or None). Cached per request."""
    if "_user" in g:
        return g._user
    uid = session.get("uid")
    if not uid:
        try:
            uid = _bearer_user_id()
        except ApiError:
            uid = None
    user = get_db()[USERS].find_one({"_id": to_oid(uid)}) if uid else None
    if uid and not user:
        session.pop("uid", None)
    g._user = user
    return user


def login_user(user):
    session.clear()
    session["uid"] = str(user["_id"])
    session.permanent = True
    g._user = user


def logout_user():
    session.clear()
    g._user = None


def login_required(view):
    """For HTML pages: redirect guests to /login?next=…"""

    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user():
            return redirect(url_for("pages.login", next=request.full_path.rstrip("?")))
        return view(*args, **kwargs)

    return wrapper


def admin_page_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            return redirect(url_for("pages.login", next=request.full_path.rstrip("?")))
        if user.get("role") != "admin":
            return redirect(url_for("pages.home"))
        return view(*args, **kwargs)

    return wrapper


def api_login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user():
            raise ApiError(401, "Please sign in to continue.")
        return view(*args, **kwargs)

    return wrapper


def api_admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            raise ApiError(401, "Please sign in to continue.")
        if user.get("role") != "admin":
            raise ApiError(403, "You do not have permission to do that.")
        return view(*args, **kwargs)

    return wrapper


# ---- minimal in-memory rate limiter for auth endpoints
_hits = {}


def rate_limit(max_hits=30, window=15 * 60):
    def deco(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            ip = request.headers.get("X-Forwarded-For", request.remote_addr or "?").split(",")[0].strip()
            t = time.time()
            count, reset = _hits.get(ip, (0, t + window))
            if reset < t:
                count, reset = 0, t + window
            count += 1
            _hits[ip] = (count, reset)
            if count > max_hits:
                raise ApiError(429, "Too many attempts. Please try again in a few minutes.")
            return view(*args, **kwargs)

        return wrapper

    return deco
