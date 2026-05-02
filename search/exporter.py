"""CSV exporter for filtered place rows."""
from __future__ import annotations

import csv
from pathlib import Path

EXPORT_COLUMNS = [
    "name",
    "phone",
    "international_phone",
    "call_status",
    "notes",
    "user_rating_count",
    "business_status",
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
    """Build an export row from a raw Places API payload (no CRM fields)."""
    loc = place.get("location") or {}
    return {
        "name": (place.get("displayName") or {}).get("text") or "",
        "phone": place.get("nationalPhoneNumber") or "",
        "international_phone": place.get("internationalPhoneNumber") or "",
        "call_status": "not_called",
        "notes": "",
        "user_rating_count": place.get("userRatingCount") or "",
        "business_status": place.get("businessStatus") or "",
        "maps_link": place.get("googleMapsUri") or "",
        "reason": reason,
        "website_uri": place.get("websiteUri") or "",
        "address": place.get("formattedAddress") or "",
        "primary_type": place.get("primaryType") or "",
        "place_id": place.get("id") or "",
        "lat": loc.get("latitude") or "",
        "lng": loc.get("longitude") or "",
    }


def row_from_db(lead: dict, reason: str) -> dict:
    """Build an export row from the cached lead dict (carries notes/status)."""
    return {
        "name": lead.get("name") or "",
        "phone": lead.get("phone") or "",
        "international_phone": lead.get("international_phone") or "",
        "call_status": lead.get("call_status") or "not_called",
        "notes": lead.get("notes") or "",
        "user_rating_count": lead.get("user_rating_count") or "",
        "business_status": lead.get("business_status") or "",
        "maps_link": lead.get("maps_link") or "",
        "reason": reason,
        "website_uri": lead.get("website_uri") or "",
        "address": lead.get("address") or "",
        "primary_type": lead.get("primary_type") or "",
        "place_id": lead.get("place_id") or "",
        "lat": lead.get("lat") if lead.get("lat") is not None else "",
        "lng": lead.get("lng") if lead.get("lng") is not None else "",
    }


def write_csv(rows: list[dict], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=EXPORT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path
