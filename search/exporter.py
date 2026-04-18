"""CSV exporter for filtered place rows."""
from __future__ import annotations

import csv
from pathlib import Path

EXPORT_COLUMNS = [
    "name",
    "maps_link",
    "reason",
    "website_uri",
    "address",
    "primary_type",
    "place_id",
    "lat",
    "lng",
]


def row_from_place(place: dict, reason: str) -> dict:
    loc = place.get("location") or {}
    return {
        "name": (place.get("displayName") or {}).get("text") or "",
        "maps_link": place.get("googleMapsUri") or "",
        "reason": reason,
        "website_uri": place.get("websiteUri") or "",
        "address": place.get("formattedAddress") or "",
        "primary_type": place.get("primaryType") or "",
        "place_id": place.get("id") or "",
        "lat": loc.get("latitude") or "",
        "lng": loc.get("longitude") or "",
    }


def write_csv(rows: list[dict], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=EXPORT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path
