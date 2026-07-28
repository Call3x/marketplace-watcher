#!/usr/bin/env python3
"""Marketplace watcher — runs the full shopping list against all configured
adapters, diffs against price history in SQLite, and notifies on new
listings or price drops via Telegram.

Usage: python3 run.py [--dry-run]
"""
import sys
import time
from pathlib import Path

import yaml

import db
import notify
from adapters import autoscout24, vinted

ADAPTERS = {
    "vinted": vinted.search,
    "autoscout24": autoscout24.search,
}

CONFIG_PATH = Path(__file__).parent / "config.yaml"


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def run(dry_run: bool = False):
    config = load_config()
    countries = config["settings"]["countries"]
    budget_seconds = config["settings"].get("run_budget_minutes", 15) * 60
    start = time.monotonic()

    events = []  # (reason, listing, old_price, category, item_label)

    with db.connect() as conn:
        for item in config["items"]:
            if item.get("enabled", True) is False:
                print(f"[run] {item['id']} is disabled, skipping")
                continue
            for adapter_name in item.get("adapters", []):
                if adapter_name not in ADAPTERS:
                    continue
                if time.monotonic() - start > budget_seconds:
                    print(f"[run] time budget exceeded, stopping ({adapter_name}/{item['id']} skipped)")
                    break

                print(f"[run] searching {adapter_name} for {item['id']}...")
                try:
                    listings = ADAPTERS[adapter_name](item, countries)
                except Exception as e:
                    print(f"[run] {adapter_name}/{item['id']} failed: {e}")
                    continue

                print(f"[run]   {len(listings)} candidate(s)")
                seen_uids = set()
                for listing in listings:
                    seen_uids.add(listing.uid)
                    cur = conn.execute(
                        "SELECT last_price FROM listings WHERE uid = ?", (listing.uid,)
                    )
                    row = cur.fetchone()
                    old_price = row[0] if row else None

                    reason = db.upsert_listing(conn, listing)
                    if reason in ("new", "price_drop"):
                        events.append((reason, listing, old_price, item.get("category", "other"), item.get("label", item["id"])))

                db.mark_inactive_not_seen_since(conn, adapter_name, item["id"], seen_uids)

        # Group events by category so Telegram gets one digest message per
        # category instead of one message per listing (which becomes
        # unusable at 100+ matches for a broad category like watches).
        by_category: dict[str, list] = {}
        for reason, listing, old_price, category, item_label in events:
            by_category.setdefault(category, []).append(
                (reason, listing.title, listing.price, listing.url, old_price, item_label)
            )

        if not dry_run:
            for category, entries in by_category.items():
                for msg in notify.format_digest(category, category.capitalize(), entries):
                    notify.send(msg)
            for reason, listing, old_price, _category, _label in events:
                db.log_notification(conn, listing.uid, reason)
        else:
            print(f"\n[dry-run] {len(events)} event(s) across {len(by_category)} categorie(s):")
            for category, entries in by_category.items():
                for msg in notify.format_digest(category, category.capitalize(), entries):
                    print(f"--- message ({len(msg)} chars) ---")
                    print(msg)

    print(f"[run] done in {time.monotonic() - start:.1f}s, {len(events)} notification(s)")


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
