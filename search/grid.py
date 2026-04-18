"""Hex-grid generator using a per-region azimuthal equidistant projection.

The projection is re-centered on each region's centroid so distances are
metric-accurate near the region, regardless of latitude. This replaces the
Swiss-LV95-only implementation used in the original version of the tool.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Optional

from pyproj import Transformer
from shapely.geometry.base import BaseGeometry
from shapely.geometry import Point


@dataclass(frozen=True)
class Cell:
    lat: float
    lng: float
    radius_m: float

    @property
    def cell_id(self) -> str:
        # Stable id at ~10m precision — used as cache key.
        return f"{self.lat:.5f},{self.lng:.5f},{int(self.radius_m)}"


def _aeqd_transformers(center_lat: float, center_lng: float):
    """Azimuthal equidistant projection centered at (lat, lng). Units: metres."""
    proj = (f"+proj=aeqd +lat_0={center_lat} +lon_0={center_lng} "
            f"+x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs")
    to_m = Transformer.from_crs("EPSG:4326", proj, always_xy=True)
    to_wgs = Transformer.from_crs(proj, "EPSG:4326", always_xy=True)
    return to_m, to_wgs


def hex_grid(
    bbox: tuple[float, float, float, float],
    radius_m: float = 1000.0,
    polygon: Optional[BaseGeometry] = None,
    center: Optional[tuple[float, float]] = None,
) -> list[Cell]:
    """Generate a hex grid of circular cells covering the bbox.

    bbox: (min_lat, min_lng, max_lat, max_lng) in WGS84.
    radius_m: per-cell circle radius; sets the pitch so circles fully tile the area.
    polygon: optional WGS84 shapely polygon — cells whose center is >radius_m outside
             the polygon are dropped.
    center: (lat, lng) to center the local AEQD projection on. Defaults to bbox center.
    """
    min_lat, min_lng, max_lat, max_lng = bbox
    if center is None:
        center = ((min_lat + max_lat) / 2.0, (min_lng + max_lng) / 2.0)
    c_lat, c_lng = center
    to_m, to_wgs = _aeqd_transformers(c_lat, c_lng)

    # Project bbox corners to local metric space and order them.
    corners = [
        to_m.transform(min_lng, min_lat),
        to_m.transform(min_lng, max_lat),
        to_m.transform(max_lng, min_lat),
        to_m.transform(max_lng, max_lat),
    ]
    xs = [c[0] for c in corners]
    ys = [c[1] for c in corners]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)

    step_x = radius_m * math.sqrt(3)
    step_y = radius_m * 1.5

    cells: list[Cell] = []
    row = 0
    y = y_min
    while y <= y_max + step_y:
        x_offset = (step_x / 2.0) if (row % 2 == 1) else 0.0
        x = x_min + x_offset
        while x <= x_max + step_x:
            lng, lat = to_wgs.transform(x, y)
            if polygon is not None:
                # Drop cells whose center is comfortably outside the polygon.
                # Buffer by radius_m (converted to degrees at this latitude)
                # so edge places aren't missed.
                if not polygon.buffer(_meters_to_deg(radius_m, lat)).contains(Point(lng, lat)):
                    x += step_x
                    continue
            cells.append(Cell(lat=lat, lng=lng, radius_m=radius_m))
            x += step_x
        row += 1
        y += step_y
    return cells


def _meters_to_deg(meters: float, at_lat: float) -> float:
    """Rough conversion: meters -> degrees latitude. Good enough for buffering."""
    return meters / 111_320.0


def points_in_polygon(places: Iterable[tuple[float, float]], polygon: BaseGeometry) -> list[bool]:
    return [polygon.contains(Point(lng, lat)) for lat, lng in places]
