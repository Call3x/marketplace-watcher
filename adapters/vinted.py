"""Vinted adapter — uses Vinted's internal catalog search API.

No login required for browsing. Requires an initial homepage GET to pick up
session cookies (anon_id, access_token_web) before the API accepts requests.
"""
import re

import requests

from db import Listing

DOMAINS = {
    "FR": "www.vinted.fr",
    "LU": "www.vinted.fr",   # Vinted has no LU-specific site; FR catalog covers cross-border shipping
    "BE": "www.vinted.be",
}

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def _session_for(domain: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    s.get(f"https://{domain}/", timeout=15)
    s.headers.update({
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
    })
    return s


def _word_matches(word: str, title_l: str) -> bool:
    """True if `word` appears in `title_l` as a whole word, or immediately
    after a digit (so "gb"/"tb" match "500gb"/"512GB" but "consola" doesn't
    match inside "videoconsola", and "game" doesn't match inside a longer
    unrelated word). Short, common require_any_words like storage-size
    abbreviations and translated nouns ("consola", "console", "go") are
    exactly the words prone to this kind of accidental substring match."""
    return re.search(rf"(?:(?<=\d)|\b){re.escape(word)}\b", title_l) is not None


def search(item: dict, countries: list[str]) -> list[Listing]:
    """Search Vinted for a shopping-list item, return matching Listings."""
    results: dict[str, Listing] = {}
    keywords = item.get("keywords", [])
    exclude = [w.lower() for w in item.get("exclude_keywords", [])]
    require_all = [w.lower() for w in item.get("require_all_words", [])]
    require_any = [w.lower() for w in item.get("require_any_words", [])]
    price_max = item.get("price_max")
    price_min = item.get("price_min", 0)

    domains = {DOMAINS[c] for c in countries if c in DOMAINS}

    for domain in domains:
        session = _session_for(domain)
        for kw in keywords:
            params = {
                "search_text": kw,
                "order": "newest_first",
                "per_page": 40,
                "currency": "EUR",
            }
            if price_max:
                params["price_to"] = price_max
            if price_min:
                params["price_from"] = price_min

            try:
                r = session.get(f"https://{domain}/api/v2/catalog/items", params=params, timeout=20)
                r.raise_for_status()
            except requests.RequestException:
                continue

            kw_first_word = kw.lower().split()[0] if kw.strip() else ""

            for raw in r.json().get("items", []):
                title = raw.get("title", "")
                title_l = title.lower()
                # Vinted's own search is fuzzy/related-brand — re-confirm at
                # least the keyword's first word (the core subject, e.g.
                # "pantalon"/"seiko"/"xbox") appears in the title. Requiring
                # the WHOLE keyword verbatim works for single-word brand
                # searches but wrongly rejects real matches for multi-word
                # phrases, since Vinted's search doesn't require exact
                # wording/order either — require_any_words/exclude_keywords
                # below do the actual precision filtering (size, generation,
                # etc.), same pattern as the Xbox console fix.
                if kw_first_word and kw_first_word not in title_l:
                    continue
                if any(x in title_l for x in exclude):
                    continue
                if require_all and not all(_word_matches(w, title_l) for w in require_all):
                    continue
                if require_any and not any(_word_matches(w, title_l) for w in require_any):
                    continue

                price = float(raw["price"]["amount"]) if raw.get("price") else None
                uid = f"vinted:{raw['id']}"
                url = f"https://{domain}{raw['path']}" if raw["path"].startswith("/") else raw["path"]

                results[uid] = Listing(
                    uid=uid,
                    item_id=item["id"],
                    adapter="vinted",
                    title=title,
                    url=url,
                    price=price,
                )

    return list(results.values())
