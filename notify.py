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
