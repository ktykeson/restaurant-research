"""Saved regions: generic WGS84 bbox + optional polygon, persisted in SQLite.

Replaces the old hardcoded Swiss-canton list. A region is anything the user
added via geocoding (city, county, country, …). The four original cantons
are seeded on first run from bundled GeoJSONs so existing cached runs and
exports still line up.

Each region stores a default list of text-search profile ids
(see query_profiles.py). Users can override the set per run.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from shapely.geometry import shape, Point
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from paths import resource_path
from . import cache

BOUNDARIES_DIR = resource_path("data/boundaries")

_SEED_CANTONS = [
    {"id": "ZG", "name": "Zug",    "bbox": [47.0780, 8.3970, 47.2480, 8.6900]},
    {"id": "ZH", "name": "Zürich", "bbox": [47.1600, 8.3580, 47.6950, 8.9850]},
    {"id": "AG", "name": "Aargau", "bbox": [47.1370, 7.7140, 47.6230, 8.4570]},
    {"id": "LU", "name": "Luzern", "bbox": [46.7740, 7.7960, 47.3030, 8.5170]},
]


@dataclass
class Region:
    id: str
    name: str
    display_name: str
    bbox: tuple[float, float, float, float]
    polygon_geojson: Optional[dict]
    language_code: str
    region_code: str
    text_profiles: list[str]

    @classmethod
    def from_dict(cls, d: dict) -> "Region":
        bbox = tuple(d["bbox"])
        # Back-compat: the older schema stored text_queries. We now store
        # text_profiles (list of profile ids); fall back to ["en"] if absent.
        profiles = d.get("text_profiles")
        if profiles is None:
            profiles = d.get("text_queries") or ["en"]
            if profiles and not isinstance(profiles[0], str):
                profiles = ["en"]
        return cls(
            id=d["id"],
            name=d["name"],
            display_name=d.get("display_name") or d["name"],
            bbox=bbox,  # type: ignore[arg-type]
            polygon_geojson=d.get("polygon_geojson"),
            language_code=d.get("language_code") or "en",
            region_code=d.get("region_code") or "",
            text_profiles=list(profiles),
        )

    def to_api_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "display_name": self.display_name,
            "bbox": list(self.bbox),
            "has_polygon": self.polygon_geojson is not None,
            "language_code": self.language_code,
            "region_code": self.region_code,
            "text_profiles": list(self.text_profiles),
        }

    def polygon(self) -> Optional[BaseGeometry]:
        gj = self.polygon_geojson
        if not gj:
            return None
        if gj.get("type") == "FeatureCollection":
            geoms = [shape(f["geometry"]) for f in gj["features"]]
        elif gj.get("type") == "Feature":
            geoms = [shape(gj["geometry"])]
        else:
            geoms = [shape(gj)]
        return unary_union(geoms)

    def center(self) -> tuple[float, float]:
        min_lat, min_lng, max_lat, max_lng = self.bbox
        poly = self.polygon()
        if poly is not None:
            c = poly.centroid
            return (c.y, c.x)
        return ((min_lat + max_lat) / 2.0, (min_lng + max_lng) / 2.0)

    def contains(self, lat: float, lng: float) -> bool:
        poly = self.polygon()
        if poly is None:
            min_lat, min_lng, max_lat, max_lng = self.bbox
            return min_lat <= lat <= max_lat and min_lng <= lng <= max_lng
        return poly.contains(Point(lng, lat))


def slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s-]+", "-", s)
    return s.strip("-") or "region"


def unique_id(base: str) -> str:
    existing = {r["id"] for r in cache.list_regions()}
    if base not in existing:
        return base
    i = 2
    while f"{base}-{i}" in existing:
        i += 1
    return f"{base}-{i}"


def seed_swiss_cantons() -> None:
    """Seed the four original cantons into the regions table if missing."""
    existing = {r["id"] for r in cache.list_regions()}
    for seed in _SEED_CANTONS:
        if seed["id"] in existing:
            continue
        gj_path = BOUNDARIES_DIR / f"{seed['id']}.geojson"
        polygon_geojson = None
        if gj_path.exists():
            try:
                polygon_geojson = json.loads(gj_path.read_text())
            except Exception:
                polygon_geojson = None
        cache.upsert_region({
            "id": seed["id"],
            "name": seed["name"],
            "display_name": f"Kanton {seed['name']}, Schweiz",
            "bbox": seed["bbox"],
            "polygon_geojson": polygon_geojson,
            "language_code": "de",
            "region_code": "CH",
            "text_profiles": ["de_swiss"],
        })


def list_regions() -> list[Region]:
    return [Region.from_dict(r) for r in cache.list_regions()]


def get_region(region_id: str) -> Region:
    r = cache.get_region(region_id)
    if r is None:
        raise KeyError(f"Unknown region: {region_id}")
    return Region.from_dict(r)
