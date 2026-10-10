"""Populate MongoDB Atlas with the sample articles and demo accounts.

    python seed.py           # seeds only if the articles collection is empty
    python seed.py --reset   # wipe articles/users/bookmarks/likes/history first, then seed
"""
import sys

from config import Config
from extensions import ARTICLES, get_db, init_db
from services.seed_service import DEMO_ACCOUNTS, seed_database


def main():
    reset = "--reset" in sys.argv
    init_db(Config.MONGODB_URI)
    if not reset and get_db()[ARTICLES].count_documents({}) > 0:
        print("Articles already exist – nothing to do. Use `python seed.py --reset` to wipe and reseed.")
        return
    result = seed_database(reset=reset)
    print(f"Seeded {result['articles']} articles.")
    print("Admin  :", DEMO_ACCOUNTS["admin"]["email"], "/", DEMO_ACCOUNTS["admin"]["password"])
    print("Reader :", DEMO_ACCOUNTS["demo"]["email"], "/", DEMO_ACCOUNTS["demo"]["password"])


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"Seeding failed: {exc}", file=sys.stderr)
        sys.exit(1)
