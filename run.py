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

    events = []  # (reason, listing, old_price)

    with db.connect() as conn:
        for item in config["items"]:
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
                        events.append((reason, listing, old_price))

                db.mark_inactive_not_seen_since(conn, adapter_name, item["id"], seen_uids)

        if not dry_run:
            for reason, listing, old_price in events:
                text = notify.format_match(reason, listing.title, listing.price, listing.url, old_price)
                if notify.send(text):
                    db.log_notification(conn, listing.uid, reason)
        else:
            print(f"\n[dry-run] {len(events)} event(s) would be sent:")
            for reason, listing, old_price in events:
                print(" -", notify.format_match(reason, listing.title, listing.price, listing.url, old_price))

    print(f"[run] done in {time.monotonic() - start:.1f}s, {len(events)} notification(s)")


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
