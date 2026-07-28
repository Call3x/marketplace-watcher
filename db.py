"""SQLite storage for listings and price history."""
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "watcher.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    uid TEXT PRIMARY KEY,          -- adapter:site_listing_id
    item_id TEXT NOT NULL,         -- shopping list item id from config
    adapter TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    last_price REAL,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT NOT NULL REFERENCES listings(uid),
    price REAL NOT NULL,
    seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT NOT NULL,
    reason TEXT NOT NULL,          -- 'new' | 'price_drop'
    sent_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_price_history_uid ON price_history(uid);
"""


@dataclass
class Listing:
    uid: str
    item_id: str
    adapter: str
    title: str
    url: str
    price: float


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert_listing(conn, listing: Listing) -> str:
    """Insert or update a listing, record price history, return 'new' | 'price_drop' | 'unchanged'."""
    cur = conn.execute("SELECT last_price FROM listings WHERE uid = ?", (listing.uid,))
    row = cur.fetchone()
    ts = now_iso()

    if row is None:
        conn.execute(
            "INSERT INTO listings (uid, item_id, adapter, title, url, first_seen, last_seen, last_price, is_active) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)",
            (listing.uid, listing.item_id, listing.adapter, listing.title, listing.url, ts, ts, listing.price),
        )
        conn.execute(
            "INSERT INTO price_history (uid, price, seen_at) VALUES (?, ?, ?)",
            (listing.uid, listing.price, ts),
        )
        return "new"

    old_price = row[0]
    conn.execute(
        "UPDATE listings SET last_seen = ?, last_price = ?, title = ?, is_active = 1 WHERE uid = ?",
        (ts, listing.price, listing.title, listing.uid),
    )
    if old_price is not None and listing.price is not None and listing.price < old_price:
        conn.execute(
            "INSERT INTO price_history (uid, price, seen_at) VALUES (?, ?, ?)",
            (listing.uid, listing.price, ts),
        )
        return "price_drop"
    return "unchanged"


def mark_inactive_not_seen_since(conn, adapter: str, item_id: str, seen_uids: set[str]):
    """Mark listings absent from this run's results as inactive (delisted/sold)."""
    cur = conn.execute(
        "SELECT uid FROM listings WHERE adapter = ? AND item_id = ? AND is_active = 1",
        (adapter, item_id),
    )
    for (uid,) in cur.fetchall():
        if uid not in seen_uids:
            conn.execute("UPDATE listings SET is_active = 0 WHERE uid = ?", (uid,))


def log_notification(conn, uid: str, reason: str):
    conn.execute(
        "INSERT INTO notifications (uid, reason, sent_at) VALUES (?, ?, ?)",
        (uid, reason, now_iso()),
    )


def clear_history_for_item(conn, item_id: str) -> int:
    """Delete all tracked listings (and their price_history/notifications rows)
    for a shopping-list item, so the next run treats every currently-live
    match as brand new again. Useful after materially changing an item's
    filters/keywords when you want a fresh baseline instead of only seeing
    what's genuinely new since the old filter was last run. Returns the
    number of listings deleted."""
    cur = conn.execute("SELECT uid FROM listings WHERE item_id = ?", (item_id,))
    uids = [row[0] for row in cur.fetchall()]
    for uid in uids:
        conn.execute("DELETE FROM price_history WHERE uid = ?", (uid,))
        conn.execute("DELETE FROM notifications WHERE uid = ?", (uid,))
    conn.execute("DELETE FROM listings WHERE item_id = ?", (item_id,))
    return len(uids)


def median_price_for_item(conn, item_id: str, exclude_uid: str, min_samples: int = 5) -> float | None:
    """Median of the first-seen price of every other listing ever recorded for
    this shopping-list item — used to judge whether a new match is cheap
    relative to what's historically shown up, not just relative to today's
    batch. Requires at least min_samples data points, otherwise the median
    is too noisy to be a meaningful signal and this returns None."""
    cur = conn.execute(
        """
        SELECT MIN(ph.price) FROM price_history ph
        JOIN listings l ON l.uid = ph.uid
        WHERE l.item_id = ? AND l.uid != ?
        GROUP BY ph.uid
        """,
        (item_id, exclude_uid),
    )
    prices = sorted(row[0] for row in cur.fetchall() if row[0] is not None)
    if len(prices) < min_samples:
        return None

    mid = len(prices) // 2
    if len(prices) % 2 == 0:
        return (prices[mid - 1] + prices[mid]) / 2
    return prices[mid]
