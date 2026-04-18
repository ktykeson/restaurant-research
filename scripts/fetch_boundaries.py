"""Refresh the bundled Swiss canton GeoJSONs from OSM/Nominatim.

These are only used to seed the original ZG/ZH/AG/LU regions on first run.
All new regions are geocoded live via `POST /api/regions`, so you don't
need this script for anything else.

Usage:  python scripts/fetch_boundaries.py
Saves:  data/boundaries/<CODE>.geojson
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "boundaries"
OUT_DIR.mkdir(parents=True, exist_ok=True)

NOMINATIM = "https://nominatim.openstreetmap.org/search"
HEADERS = {
    "User-Agent": "restaurant-research/0.2 (local dev tool)",
    "Accept-Language": "de,en",
}

QUERIES = {
    "ZG": "Kanton Zug, Schweiz",
    "ZH": "Kanton Zürich, Schweiz",
    "AG": "Kanton Aargau, Schweiz",
    "LU": "Kanton Luzern, Schweiz",
}


def fetch(code: str, query: str) -> None:
    out = OUT_DIR / f"{code}.geojson"
    if out.exists() and out.stat().st_size > 1000:
        print(f"[skip] {code} already present at {out}")
        return
    params = {
        "q": query, "format": "json",
        "polygon_geojson": "1", "limit": "5",
    }
    print(f"[fetch] {code}: {query}")
    r = httpx.get(NOMINATIM, params=params, headers=HEADERS, timeout=30.0)
    r.raise_for_status()
    items = r.json()
    chosen = None
    for it in items:
        if it.get("class") == "boundary" and it.get("type") == "administrative":
            chosen = it
            break
    if chosen is None and items:
        chosen = items[0]
    if not chosen or "geojson" not in chosen:
        raise RuntimeError(f"No GeoJSON polygon found for {code} ({query})")
    feature = {
        "type": "Feature",
        "properties": {"code": code, "display_name": chosen.get("display_name")},
        "geometry": chosen["geojson"],
    }
    out.write_text(json.dumps(feature, ensure_ascii=False))
    print(f"[ok]   {code} -> {out} ({out.stat().st_size:,} bytes)")
    time.sleep(1.2)  # Nominatim policy: max 1 req/s.


def main() -> None:
    for code, query in QUERIES.items():
        try:
            fetch(code, query)
        except Exception as e:
            print(f"[error] {code}: {e}")


if __name__ == "__main__":
    main()
