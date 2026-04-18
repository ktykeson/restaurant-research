"""Geocode a free-text place query via OpenStreetMap Nominatim.

Returns a candidate suitable for turning into a saved Region: bbox,
polygon GeoJSON (when available), ISO country code, and a display name.
Single request per call — Nominatim's usage policy allows 1 req/s.
"""
from __future__ import annotations

from typing import Optional

import httpx

from . import query_profiles
from .regions import slugify, unique_id

NOMINATIM = "https://nominatim.openstreetmap.org/search"
HEADERS = {
    "User-Agent": "restaurant-research/0.2 (local dev tool)",
    "Accept-Language": "en",
}


def geocode(query: str, prefer_polygon: bool = True) -> Optional[dict]:
    """Look up a place and return a region-shaped dict, or None if not found."""
    params = {
        "q": query,
        "format": "jsonv2",
        "polygon_geojson": "1" if prefer_polygon else "0",
        "addressdetails": "1",
        "limit": "5",
    }
    r = httpx.get(NOMINATIM, params=params, headers=HEADERS, timeout=30.0)
    r.raise_for_status()
    items = r.json() or []
    if not items:
        return None

    chosen = _pick_best(items)
    bbox_raw = chosen.get("boundingbox")
    if not bbox_raw or len(bbox_raw) != 4:
        return None
    # Nominatim boundingbox: [min_lat, max_lat, min_lng, max_lng] as strings.
    min_lat, max_lat, min_lng, max_lng = (float(x) for x in bbox_raw)
    bbox = [min_lat, min_lng, max_lat, max_lng]

    address = chosen.get("address") or {}
    country_code = (address.get("country_code") or "").upper() or None

    base_name = chosen.get("name") or chosen.get("display_name", "").split(",")[0].strip() or query
    suggested_profiles = query_profiles.profiles_for_country(country_code)
    language = query_profiles.primary_language(suggested_profiles) or "en"

    return {
        "id": unique_id(slugify(base_name)),
        "name": base_name,
        "display_name": chosen.get("display_name") or base_name,
        "bbox": bbox,
        "polygon_geojson": chosen.get("geojson") if prefer_polygon else None,
        "language_code": language,
        "region_code": country_code or "",
        "text_profiles": suggested_profiles,
    }


def _pick_best(items: list[dict]) -> dict:
    """Prefer an administrative boundary result over a point of interest."""
    for it in items:
        if it.get("class") == "boundary" and it.get("type") == "administrative":
            return it
    for it in items:
        if it.get("geojson"):
            return it
    return items[0]
