"""User data access (port of models/User.js)."""
from extensions import USERS, get_db
from utils.auth import hash_password
from utils.helpers import ApiError, jsonable, now, to_oid


def col():
    return get_db()[USERS]


def find_by_email(email):
    return col().find_one({"email": str(email or "").lower().strip()})


def find_by_id(user_id):
    oid = to_oid(user_id)
    return col().find_one({"_id": oid}) if oid else None


def create(name, email, password, role="user", interests=None, onboarded=False):
    email = str(email).lower().strip()
    if find_by_email(email):
        raise ApiError(409, "An account with this email already exists.")
    doc = {
        "name": str(name).strip(),
        "email": email,
        "password": hash_password(password),
        "role": role,
        "avatar": "",
        "interests": interests or [],
        "onboarded": onboarded,
        "bookmarks": [],
        "likedArticles": [],
        "createdAt": now(),
        "updatedAt": now(),
    }
    res = col().insert_one(doc)
    doc["_id"] = res.inserted_id
    return doc


def update(user_id, changes):
    changes = dict(changes)
    changes["updatedAt"] = now()
    col().update_one({"_id": to_oid(user_id)}, {"$set": changes})
    return find_by_id(user_id)


def public(user):
    """JSON-safe user (no password hash) – same shape the Express API returned."""
    if not user:
        return None
    out = {k: v for k, v in user.items() if k not in ("password", "__v")}
    return jsonable(out)
