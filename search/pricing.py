"""Cost estimation for Places API (New) calls.

Default rate matches the Place Details Pro SKU which is what we hit because
the field mask includes `websiteUri`. Override at the call site if Google's
pricing shifts or if you switch SKUs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from . import cache
from .grid import hex_grid
from .regions import get_region
from .type_buckets import NEARBY_BUCKETS

# USD per 1,000 API requests at the Pro tier (websiteUri included).
DEFAULT_RATE_PER_1K = 32.0


@dataclass
class RegionEstimate:
    id: str
    name: str
    cells: int
    buckets_per_cell: int
    total_buckets: int      # cells * buckets_per_cell
    cached_buckets: int     # already done — free on this run
    chargeable: int         # what we actually pay for
    cost_usd: float


@dataclass
class RunEstimate:
    by_region: list[RegionEstimate]
    total_chargeable: int
    total_cost_usd: float
    rate_per_1k: float
    capped_by_budget: bool  # True if request_budget is lower than chargeable


def estimate(
    region_ids: list[str],
    radius_m: float = 1000.0,
    use_text_search: bool = True,
    text_queries: Optional[list[str]] = None,
    use_cache: bool = True,
    request_budget: Optional[int] = None,
    rate_per_1k: float = DEFAULT_RATE_PER_1K,
) -> RunEstimate:
    cache.init_db()
    bucket_ids = [b for b, _ in NEARBY_BUCKETS]
    if use_text_search and text_queries:
        bucket_ids += [f"text:{q}" for q in text_queries]
    buckets_per_cell = len(bucket_ids)

    cells_data: list[RegionEstimate] = []
    total_chargeable = 0
    for rid in region_ids:
        region = get_region(rid)
        cells = hex_grid(
            region.bbox,
            radius_m=radius_m,
            polygon=region.polygon(),
            center=region.center(),
        )
        total_buckets = len(cells) * buckets_per_cell

        cached = 0
        if use_cache and cells:
            cached = _count_cached(cells, bucket_ids)

        chargeable = max(0, total_buckets - cached)
        total_chargeable += chargeable
        cells_data.append(RegionEstimate(
            id=region.id,
            name=region.name,
            cells=len(cells),
            buckets_per_cell=buckets_per_cell,
            total_buckets=total_buckets,
            cached_buckets=cached,
            chargeable=chargeable,
            cost_usd=chargeable * rate_per_1k / 1000.0,
        ))

    capped = False
    if request_budget is not None and total_chargeable > request_budget:
        capped = True

    return RunEstimate(
        by_region=cells_data,
        total_chargeable=total_chargeable,
        total_cost_usd=total_chargeable * rate_per_1k / 1000.0,
        rate_per_1k=rate_per_1k,
        capped_by_budget=capped,
    )


def _count_cached(cells, bucket_ids: list[str]) -> int:
    """Single SQL round-trip — count cell+bucket pairs already in cell_queries."""
    cell_ids = [c.cell_id for c in cells]
    if not cell_ids or not bucket_ids:
        return 0
    placeholders_cells = ",".join("?" * len(cell_ids))
    placeholders_buckets = ",".join("?" * len(bucket_ids))
    sql = (
        f"SELECT COUNT(*) FROM cell_queries "
        f"WHERE cell_id IN ({placeholders_cells}) "
        f"AND bucket_id IN ({placeholders_buckets})"
    )
    with cache.cursor() as cur:
        cur.execute(sql, [*cell_ids, *bucket_ids])
        return cur.fetchone()[0]


def actual_cost(requests_used: int, rate_per_1k: float = DEFAULT_RATE_PER_1K) -> float:
    return requests_used * rate_per_1k / 1000.0
