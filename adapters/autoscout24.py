"""AutoScout24 adapter for car searches.

No anti-bot wall encountered (unlike Leboncoin/La Centrale, both behind
DataDome). Listings are read from the __NEXT_DATA__ JSON blob embedded in
the search results page rather than parsed from HTML.
"""
import json
import re

import requests

from db import Listing

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S
)

# AutoScout24 has no dedicated Luxembourg domain; FR/BE/DE listings are the
# practical cross-border equivalent for someone shopping from LU.
COUNTRY_MAP = {"FR": "FR", "BE": "BE", "LU": "DE"}


def _find_listings(data: dict):
    def walk(d, depth=0):
        if depth > 6:
            return None
        if isinstance(d, dict):
            if "listings" in d and isinstance(d["listings"], list):
                return d["listings"]
            for v in d.values():
                res = walk(v, depth + 1)
                if res is not None:
                    return res
        elif isinstance(d, list):
            for v in d:
                res = walk(v, depth + 1)
                if res is not None:
                    return res
        return None

    return walk(data) or []


def _parse_year(vehicle_details: list) -> int | None:
    for entry in vehicle_details:
        if entry.get("iconName") == "calendar":
            m = re.search(r"(\d{4})", entry.get("data", ""))
            if m:
                return int(m.group(1))
    return None


def _parse_mileage(vehicle_details: list) -> int | None:
    for entry in vehicle_details:
        if entry.get("iconName") == "mileage_odometer":
            digits = re.sub(r"[^\d]", "", entry.get("data", ""))
            if digits:
                return int(digits)
    return None


def search(item: dict, countries: list[str]) -> list[Listing]:
    make = item["make"]
    model = item["model"].lower().replace(" ", "")
    year_min = item.get("year_min")
    year_max = item.get("year_max")
    price_min = item.get("price_min", 0)
    price_max = item.get("price_max")
    mileage_max = item.get("mileage_max_km")
    exclude = [w.lower() for w in item.get("exclude_keywords", [])]
    wanted_countries = {COUNTRY_MAP[c] for c in countries if c in COUNTRY_MAP}

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    params = {"sort": "price", "desc": "0", "size": "60"}
    if year_min:
        params["fregfrom"] = year_min
    if year_max:
        params["fregto"] = year_max
    if price_min:
        params["pricefrom"] = price_min
    if price_max:
        params["priceto"] = price_max
    if mileage_max:
        params["kmto"] = mileage_max

    url = f"https://www.autoscout24.fr/lst/{make}/3-series"

    listings = []
    for page in range(1, 4):  # up to 180 results, cheapest first
        page_params = dict(params, page=page)
        try:
            r = session.get(url, params=page_params, timeout=20)
            r.raise_for_status()
        except requests.RequestException:
            break

        m = NEXT_DATA_RE.search(r.text)
        if not m:
            break
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            break

        page_listings = _find_listings(data)
        if not page_listings:
            break
        listings.extend(page_listings)
        if len(page_listings) < 60:
            break  # last page

    results = []

    for l in listings:
        vehicle = l.get("vehicle", {})
        motor = (vehicle.get("motorTypeName") or "").lower().replace(" ", "")
        if model not in motor:
            continue

        country = l.get("location", {}).get("countryCode")
        if wanted_countries and country not in wanted_countries:
            continue

        year = _parse_year(l.get("vehicleDetails", []))
        if year_min and year and year < year_min:
            continue
        if year_max and year and year > year_max:
            continue

        mileage = _parse_mileage(l.get("vehicleDetails", []))
        if mileage_max and mileage and mileage > mileage_max:
            continue

        subtitle = (vehicle.get("subtitle") or "").lower()
        title = f"BMW {vehicle.get('motorTypeName', '')} {vehicle.get('variant', '')}".strip()
        if any(x in (title + " " + subtitle).lower() for x in exclude):
            continue

        price = l.get("price", {}).get("priceRaw")
        listing_url = l.get("url", "")
        if listing_url and not listing_url.startswith("http"):
            listing_url = f"https://www.autoscout24.fr{listing_url}"

        uid = f"autoscout24:{l.get('id')}"
        results.append(
            Listing(
                uid=uid,
                item_id=item["id"],
                adapter="autoscout24",
                title=f"{title} — {mileage or '?'} km — {year or '?'} — {country}",
                url=listing_url,
                price=float(price) if price else None,
            )
        )

    return results
