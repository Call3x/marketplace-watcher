"""Telegram notification helper.

Requires env vars TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID (see setup
instructions in README.md — created via @BotFather).
"""
import os

import requests


def send(text: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[notify] TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set, skipping send:")
        print(text)
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        r = requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            },
            timeout=15,
        )
        r.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"[notify] failed to send Telegram message: {e}")
        return False


def format_match(reason: str, title: str, price, url: str, old_price=None) -> str:
    price_str = f"€{price:.0f}" if price is not None else "price n/a"
    if reason == "price_drop" and old_price is not None:
        header = f"📉 Price drop: €{old_price:.0f} → {price_str}"
    else:
        header = "🆕 New listing"
    return f"{header}\n<b>{title}</b>\n{price_str}\n{url}"


CATEGORY_ICONS = {
    "watches": "⌚",
    "cars": "🚗",
    "electronics": "🎮",
}

TELEGRAM_MAX_LEN = 4096


def _vs_median_pct(price, median) -> float | None:
    """Negative = cheaper than the historical median for this item, e.g.
    -0.23 means 23% below median. None if there's no median to compare against."""
    if price is None or median in (None, 0):
        return None
    return (price - median) / median


def _verdict_tag(price, median) -> str:
    pct = _vs_median_pct(price, median)
    if pct is None:
        return ""
    if pct <= -0.20:
        return f" 🔥{abs(pct):.0%} below usual"
    if pct <= -0.08:
        return f" 👍{abs(pct):.0%} below usual"
    if pct >= 0.20:
        return f" ⚠️{pct:.0%} above usual"
    return ""


def _value_sort_key(entry):
    """Rank price drops above new listings (a drop is more actionable), and
    within each group rank by best value first: biggest % discount for
    drops (folding in how far below the historical median it is), cheapest
    relative-to-median price for new listings. Missing prices sort last."""
    reason, _title, price, _url, old_price, _item_label, median = entry
    is_drop = reason == "price_drop" and old_price
    group = 0 if is_drop else 1

    vs_median = _vs_median_pct(price, median)
    vs_median = vs_median if vs_median is not None else 0

    if is_drop:
        discount_pct = (old_price - price) / old_price if old_price else 0
        return (group, -discount_pct + vs_median, price if price is not None else float("inf"))
    return (group, vs_median, price if price is not None else float("inf"))


def format_digest(category: str, category_label: str, entries: list) -> list:
    """entries: list of (reason, title, price, url, old_price, item_label, median).
    `median` is the historical median price for that shopping-list item
    (None if not enough data yet) — used to tag standout deals relative to
    what's normally seen, not just relative to today's batch.
    Returns a list of message strings — usually one, split into more only if
    it would exceed Telegram's 4096-char message limit. If entries come from
    more than one distinct shopping-list item, each line is prefixed with
    that item's label so a merged digest doesn't lose which item matched.
    Entries are ranked by value: price drops first (biggest discount % at
    the top), then new listings cheapest-first, both nudged by how the price
    compares to the item's historical median."""
    icon = CATEGORY_ICONS.get(category, "🔎")
    header = f"{icon} <b>{category_label}</b> — {len(entries)} update{'s' if len(entries) != 1 else ''}\n"

    entries = sorted(entries, key=_value_sort_key)
    distinct_items = {item_label for *_rest, item_label, _median in entries}
    show_item_label = len(distinct_items) > 1

    lines = []
    for reason, title, price, url, old_price, item_label, median in entries:
        price_str = f"€{price:.0f}" if price is not None else "price n/a"
        if reason == "price_drop" and old_price is not None:
            tag = f"📉 €{old_price:.0f}→{price_str}"
        else:
            tag = f"🆕 {price_str}"
        tag += _verdict_tag(price, median)
        prefix = f"[{item_label}] " if show_item_label else ""
        lines.append(f"{tag} — {prefix}<a href=\"{url}\">{title}</a>")

    messages = []
    current = header
    for line in lines:
        if len(current) + len(line) + 1 > TELEGRAM_MAX_LEN:
            messages.append(current.rstrip())
            current = f"{icon} <b>{category_label}</b> (cont.)\n"
        current += line + "\n"
    messages.append(current.rstrip())
    return messages
