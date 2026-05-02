"""Crawler orchestrator: cells × buckets → dedup → polygon-clip → classify.

Emits structured progress events through an injected async callback so the
Flask layer can stream them to the browser via SSE.
"""
from __future__ import annotations

import asyncio
import threading
import uuid
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

from . import cache, filters
from .grid import Cell, hex_grid
from .places_client import PlacesClient
from .regions import Region, get_region
from .type_buckets import NEARBY_BUCKETS

ProgressFn = Callable[[dict], Awaitable[None]]


@dataclass
class CrawlConfig:
    region_ids: list[str]
    radius_m: float = 1000.0
    request_budget: int = 5000
    use_cache: bool = True
    include_social_only: bool = True
    use_text_search: bool = True
    max_concurrent: int = 8
    # Test-mode: stop searching a region once it has produced this many leads.
    # When all selected regions hit the cap, the whole run ends early.
    per_region_lead_limit: Optional[int] = None
    # Text-search queries to run per cell. Resolved from query profiles by
    # the caller so the crawler doesn't need to know about profiles.
    text_queries: list[str] = field(default_factory=list)


@dataclass
class CrawlState:
    run_id: str
    cells_total: int = 0
    cells_done: int = 0
    requests_used: int = 0
    places_seen: int = 0
    places_unique: int = 0
    no_website: int = 0
    social_only: int = 0
    aborted_reason: Optional[str] = None
    seen_place_ids: set[str] = field(default_factory=set)
    leads_by_region: dict[str, int] = field(default_factory=dict)


async def _noop(_: dict) -> None:
    pass


class BudgetExceeded(Exception):
    pass


async def crawl(config: CrawlConfig, on_event: ProgressFn = _noop,
                cancel: Optional[threading.Event] = None) -> CrawlState:
    cache.init_db()
    run_id = uuid.uuid4().hex[:12]

    regions: list[Region] = [get_region(r) for r in config.region_ids]

    # Build cells per region (polygon-clipped if polygon available).
    cells_by_region: dict[str, list[Cell]] = {}
    for r in regions:
        poly = r.polygon()
        cells_by_region[r.id] = hex_grid(
            r.bbox,
            config.radius_m,
            polygon=poly,
            center=r.center(),
        )

    cells_total = sum(len(v) for v in cells_by_region.values())
    state = CrawlState(run_id=run_id, cells_total=cells_total)
    cache.create_run(run_id, config.region_ids, cells_total)
    await on_event({"type": "start", "run_id": run_id, "cells_total": cells_total,
                    "regions": [r.id for r in regions]})

    text_queries = list(config.text_queries) if config.use_text_search else []

    async with PlacesClient(max_concurrent=config.max_concurrent) as client:
        for region in regions:
            if cancel is not None and cancel.is_set():
                state.aborted_reason = "user_cancelled"
                break
            poly = region.polygon()
            cells = cells_by_region[region.id]
            state.leads_by_region.setdefault(region.id, 0)
            for cell_idx, cell in enumerate(cells, start=1):
                if cancel is not None and cancel.is_set():
                    state.aborted_reason = "user_cancelled"
                    break
                if (config.per_region_lead_limit is not None
                        and state.leads_by_region[region.id] >= config.per_region_lead_limit):
                    await on_event({
                        "type": "region_done",
                        "run_id": run_id,
                        "region": region.id,
                        "leads": state.leads_by_region[region.id],
                        "reason": "lead_limit_reached",
                    })
                    break
                # Per-cell: fire all buckets in parallel.
                tasks = []
                for bucket_id, types in NEARBY_BUCKETS:
                    if config.use_cache and cache.has_cell_query(cell.cell_id, bucket_id):
                        continue
                    if state.requests_used >= config.request_budget:
                        state.aborted_reason = "budget_exceeded"
                        break
                    state.requests_used += 1
                    tasks.append(_run_nearby(client, cell, bucket_id, types, region))

                for tq in text_queries:
                    bucket_id = f"text:{tq}"
                    if config.use_cache and cache.has_cell_query(cell.cell_id, bucket_id):
                        continue
                    if state.requests_used >= config.request_budget:
                        state.aborted_reason = "budget_exceeded"
                        break
                    # Text search may paginate up to 3 pages; budget for worst case.
                    state.requests_used += 1
                    tasks.append(_run_text(client, cell, tq, region))

                if state.aborted_reason:
                    break

                # Stream results bucket-by-bucket so rows + counters trickle in
                # instead of arriving in one batch when the whole cell finishes.
                await on_event({
                    "type": "cell_start",
                    "run_id": run_id,
                    "region": region.id,
                    "cell_index": cell_idx,
                    "cells_in_region": len(cells),
                    "buckets": len(tasks),
                })
                for fut in asyncio.as_completed(tasks):
                    try:
                        bucket_id, places = await fut
                    except Exception as e:
                        await on_event({"type": "error", "run_id": run_id, "msg": str(e)})
                        continue
                    cache.record_cell_query(cell.cell_id, bucket_id, len(places))
                    for p in places:
                        await _ingest_place(p, region, poly, config, state, on_event)
                    await on_event({
                        "type": "tick",
                        "run_id": run_id,
                        "requests_used": state.requests_used,
                        "places_seen": state.places_seen,
                        "places_unique": state.places_unique,
                        "no_website": state.no_website,
                        "social_only": state.social_only,
                    })

                state.cells_done += 1
                if state.cells_done % 5 == 0 or state.cells_done == cells_total:
                    cache.update_run(
                        run_id,
                        cells_done=state.cells_done,
                        requests_used=state.requests_used,
                        places_seen=state.places_seen,
                        places_unique=state.places_unique,
                        no_website=state.no_website,
                        social_only=state.social_only,
                    )
                await on_event({
                    "type": "progress",
                    "run_id": run_id,
                    "cells_done": state.cells_done,
                    "cells_total": state.cells_total,
                    "requests_used": state.requests_used,
                    "places_seen": state.places_seen,
                    "places_unique": state.places_unique,
                    "no_website": state.no_website,
                    "social_only": state.social_only,
                    "region": region.id,
                    "cell_index": cell_idx,
                    "cells_in_region": len(cells),
                })

            if state.aborted_reason:
                break

    cache.update_run(
        run_id,
        cells_done=state.cells_done,
        requests_used=state.requests_used,
        places_seen=state.places_seen,
        places_unique=state.places_unique,
        no_website=state.no_website,
        social_only=state.social_only,
    )
    cache.finish_run(run_id, status=state.aborted_reason or "done")
    await on_event({
        "type": "done",
        "run_id": run_id,
        "aborted_reason": state.aborted_reason,
        "cells_done": state.cells_done,
        "cells_total": state.cells_total,
        "requests_used": state.requests_used,
        "places_seen": state.places_seen,
        "places_unique": state.places_unique,
        "no_website": state.no_website,
        "social_only": state.social_only,
    })
    return state


async def _run_nearby(client: PlacesClient, cell: Cell, bucket_id: str,
                      types: list[str], region: Region) -> tuple[str, list[dict]]:
    places = await client.search_nearby(
        cell.lat, cell.lng, cell.radius_m, types,
        language_code=region.language_code,
        region_code=region.region_code,
    )
    return bucket_id, places


async def _run_text(client: PlacesClient, cell: Cell, query: str,
                    region: Region) -> tuple[str, list[dict]]:
    places = await client.search_text(
        query, cell.lat, cell.lng, cell.radius_m,
        language_code=region.language_code,
        region_code=region.region_code,
    )
    return f"text:{query}", places


async def _ingest_place(place: dict, region: Region, polygon, config: CrawlConfig,
                        state: CrawlState, on_event: ProgressFn) -> None:
    state.places_seen += 1
    pid = place.get("id")
    if not pid or pid in state.seen_place_ids:
        return
    state.seen_place_ids.add(pid)

    # Polygon clip — drop places outside the region boundary.
    loc = place.get("location") or {}
    lat = loc.get("latitude")
    lng = loc.get("longitude")
    if lat is None or lng is None:
        return
    if polygon is not None:
        from shapely.geometry import Point
        if not polygon.contains(Point(lng, lat)):
            return

    cache.upsert_place(place)
    state.places_unique += 1

    reason = filters.classify(place)
    if reason == "no_website":
        state.no_website += 1
    elif reason == "social_only":
        state.social_only += 1
        if not config.include_social_only:
            return
    else:
        return  # has_site or skipped

    state.leads_by_region[region.id] = state.leads_by_region.get(region.id, 0) + 1
    await on_event({
        "type": "result",
        "region": region.id,
        "name": (place.get("displayName") or {}).get("text") or "",
        "maps_link": place.get("googleMapsUri") or "",
        "website_uri": place.get("websiteUri") or "",
        "address": place.get("formattedAddress") or "",
        "primary_type": place.get("primaryType") or "",
        "place_id": pid,
        "reason": reason,
        "lat": lat,
        "lng": lng,
        "phone": place.get("nationalPhoneNumber") or "",
        "international_phone": place.get("internationalPhoneNumber") or "",
        "user_rating_count": place.get("userRatingCount"),
        "business_status": place.get("businessStatus") or "",
    })
