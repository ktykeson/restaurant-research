"""SQLite cache: dedup of place rows + cell/bucket query memoization.

Two purposes:
  1. `places` table — one row per unique place_id, full JSON kept for future
     enrichment passes (AI summary, photos, menu, etc.).
  2. `cell_queries` table — remembers which (cell_id, bucket_id) pairs we've
     already hit, so re-runs cost ~$0.
"""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator, Optional

from paths import writable_path

DB_PATH = writable_path("cache.sqlite")


SCHEMA = """
CREATE TABLE IF NOT EXISTS places (
    place_id           TEXT PRIMARY KEY,
    name               TEXT,
    website_uri        TEXT,
    maps_uri           TEXT,
    lat                REAL,
    lng                REAL,
    address            TEXT,
    primary_type       TEXT,
    types_json         TEXT,
    business_status    TEXT,
    phone              TEXT,
    international_phone TEXT,
    user_rating_count  INTEGER,
    call_status        TEXT NOT NULL DEFAULT 'not_called',
    raw_json           TEXT NOT NULL,
    fetched_at         INTEGER NOT NULL,
    reviewed           INTEGER NOT NULL DEFAULT 0,
    reviewed_at        INTEGER,
    notes              TEXT
);

CREATE INDEX IF NOT EXISTS idx_places_website ON places(website_uri);

CREATE TABLE IF NOT EXISTS cell_queries (
    cell_id    TEXT NOT NULL,
    bucket_id  TEXT NOT NULL,
    n_results  INTEGER NOT NULL,
    fetched_at INTEGER NOT NULL,
    PRIMARY KEY (cell_id, bucket_id)
);

CREATE TABLE IF NOT EXISTS runs (
    id            TEXT PRIMARY KEY,
    cantons       TEXT NOT NULL,
    started_at    INTEGER NOT NULL,
    finished_at   INTEGER,
    requests_used INTEGER DEFAULT 0,
    cells_total   INTEGER DEFAULT 0,
    cells_done    INTEGER DEFAULT 0,
    places_seen   INTEGER DEFAULT 0,
    places_unique INTEGER DEFAULT 0,
    no_website    INTEGER DEFAULT 0,
    social_only   INTEGER DEFAULT 0,
    status        TEXT DEFAULT 'running'
);

CREATE TABLE IF NOT EXISTS regions (
    id                TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    display_name      TEXT,
    bbox_json         TEXT NOT NULL,
    polygon_geojson   TEXT,
    language_code     TEXT DEFAULT 'en',
    region_code       TEXT,
    text_queries_json TEXT,
    created_at        INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS ui_state (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, isolation_level=None, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(SCHEMA)
        # Additive migrations for pre-existing DBs.
        existing = {r[1] for r in conn.execute("PRAGMA table_info(places)").fetchall()}
        if "reviewed" not in existing:
            conn.execute("ALTER TABLE places ADD COLUMN reviewed INTEGER NOT NULL DEFAULT 0")
        if "reviewed_at" not in existing:
            conn.execute("ALTER TABLE places ADD COLUMN reviewed_at INTEGER")
        if "notes" not in existing:
            conn.execute("ALTER TABLE places ADD COLUMN notes TEXT")
        if "phone" not in existing:
            conn.execute("ALTER TABLE places ADD COLUMN phone TEXT")
        if "international_phone" not in existing:
            conn.execute("ALTER TABLE places ADD COLUMN international_phone TEXT")
        if "user_rating_count" not in existing:
            conn.execute("ALTER TABLE places ADD COLUMN user_rating_count INTEGER")
        if "call_status" not in existing:
            conn.execute(
                "ALTER TABLE places ADD COLUMN call_status TEXT NOT NULL DEFAULT 'not_called'"
            )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_places_reviewed ON places(reviewed)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_places_call_status ON places(call_status)")


@contextmanager
def cursor() -> Iterator[sqlite3.Cursor]:
    conn = _connect()
    try:
        yield conn.cursor()
    finally:
        conn.close()


def upsert_place(place: dict) -> bool:
    """Insert or update a place. Returns True if it was newly inserted."""
    pid = place.get("id")
    if not pid:
        return False
    name = (place.get("displayName") or {}).get("text") or ""
    loc = place.get("location") or {}
    with cursor() as cur:
        cur.execute("SELECT 1 FROM places WHERE place_id = ?", (pid,))
        existed = cur.fetchone() is not None
        cur.execute(
            """
            INSERT INTO places (place_id, name, website_uri, maps_uri, lat, lng,
                                address, primary_type, types_json, business_status,
                                phone, international_phone, user_rating_count,
                                raw_json, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(place_id) DO UPDATE SET
                name=excluded.name,
                website_uri=excluded.website_uri,
                maps_uri=excluded.maps_uri,
                lat=excluded.lat,
                lng=excluded.lng,
                address=excluded.address,
                primary_type=excluded.primary_type,
                types_json=excluded.types_json,
                business_status=excluded.business_status,
                phone=excluded.phone,
                international_phone=excluded.international_phone,
                user_rating_count=excluded.user_rating_count,
                raw_json=excluded.raw_json,
                fetched_at=excluded.fetched_at
            """,
            (
                pid,
                name,
                place.get("websiteUri"),
                place.get("googleMapsUri"),
                loc.get("latitude"),
                loc.get("longitude"),
                place.get("formattedAddress"),
                place.get("primaryType"),
                json.dumps(place.get("types") or []),
                place.get("businessStatus"),
                place.get("nationalPhoneNumber"),
                place.get("internationalPhoneNumber"),
                place.get("userRatingCount"),
                json.dumps(place),
                int(time.time()),
            ),
        )
    return not existed


def has_cell_query(cell_id: str, bucket_id: str) -> bool:
    with cursor() as cur:
        cur.execute(
            "SELECT 1 FROM cell_queries WHERE cell_id = ? AND bucket_id = ?",
            (cell_id, bucket_id),
        )
        return cur.fetchone() is not None


def record_cell_query(cell_id: str, bucket_id: str, n_results: int) -> None:
    with cursor() as cur:
        cur.execute(
            """
            INSERT INTO cell_queries (cell_id, bucket_id, n_results, fetched_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(cell_id, bucket_id) DO UPDATE SET
                n_results=excluded.n_results, fetched_at=excluded.fetched_at
            """,
            (cell_id, bucket_id, n_results, int(time.time())),
        )


def all_places() -> list[dict]:
    with cursor() as cur:
        cur.execute("SELECT raw_json FROM places")
        return [json.loads(r[0]) for r in cur.fetchall()]


def places_in_bbox(bbox: tuple[float, float, float, float]) -> list[dict]:
    min_lat, min_lng, max_lat, max_lng = bbox
    with cursor() as cur:
        cur.execute(
            """SELECT raw_json FROM places
               WHERE lat BETWEEN ? AND ? AND lng BETWEEN ? AND ?""",
            (min_lat, max_lat, min_lng, max_lng),
        )
        return [json.loads(r[0]) for r in cur.fetchall()]


def list_leads(search: str = "", reviewed: str = "all",
               limit: int = 500, offset: int = 0,
               min_reviews: int = 0,
               call_status: Optional[str] = None) -> tuple[list[dict], int]:
    """Return (rows, total) of lead-eligible places — operational + (no website or social-only).

    - `search` matches name/address/website_uri (case-insensitive, LIKE %term%).
    - `reviewed` is "all", "reviewed", or "unreviewed".
    - Social-only classification happens in Python (regex lives in filters.py).
    """
    from .filters import SOCIAL_REGEX

    clauses = ["(business_status IS NULL OR business_status = 'OPERATIONAL')",
               "(website_uri IS NULL OR website_uri = '' OR "
               "   website_uri LIKE '%facebook.%' OR website_uri LIKE '%fb.me%' OR"
               "   website_uri LIKE '%fb.com%' OR website_uri LIKE '%instagram.%' OR"
               "   website_uri LIKE '%instagr.am%' OR website_uri LIKE '%linktr.ee%' OR"
               "   website_uri LIKE '%linktree.%' OR website_uri LIKE '%beacons.ai%' OR"
               "   website_uri LIKE '%carrd.co%' OR website_uri LIKE '%tiktok.%' OR"
               "   website_uri LIKE '%twitter.%' OR website_uri LIKE '%x.com%' OR"
               "   website_uri LIKE '%threads.net%' OR website_uri LIKE '%wa.me%' OR"
               "   website_uri LIKE '%whatsapp.%' OR website_uri LIKE '%t.me%' OR"
               "   website_uri LIKE '%telegram.%' OR website_uri LIKE '%linkedin.%' OR"
               "   website_uri LIKE '%youtube.%' OR website_uri LIKE '%youtu.be%' OR"
               "   website_uri LIKE '%pinterest.%' OR website_uri LIKE '%bit.ly%' OR"
               "   website_uri LIKE '%goo.gl%' OR website_uri LIKE '%tinyurl.%' OR"
               "   website_uri LIKE '%t.co%' OR website_uri LIKE '%m.me%' OR"
               "   website_uri LIKE '%snapchat.%')"]
    params: list = []

    if reviewed == "reviewed":
        clauses.append("reviewed = 1")
    elif reviewed == "unreviewed":
        clauses.append("reviewed = 0")

    if min_reviews and min_reviews > 0:
        clauses.append("(user_rating_count IS NOT NULL AND user_rating_count >= ?)")
        params.append(int(min_reviews))

    if call_status:
        clauses.append("call_status = ?")
        params.append(call_status)

    if search:
        clauses.append("(name LIKE ? OR address LIKE ? OR website_uri LIKE ? OR phone LIKE ?)")
        term = f"%{search}%"
        params.extend([term, term, term, term])

    where = " AND ".join(clauses)

    with cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM places WHERE {where}", params)
        total = cur.fetchone()[0]

        cur.execute(
            f"""SELECT place_id, name, website_uri, maps_uri, address, primary_type,
                       lat, lng, reviewed, reviewed_at, notes, fetched_at,
                       phone, international_phone, user_rating_count, call_status,
                       business_status
                FROM places WHERE {where}
                ORDER BY reviewed ASC, fetched_at DESC
                LIMIT ? OFFSET ?""",
            (*params, limit, offset),
        )
        rows = []
        for r in cur.fetchall():
            uri = r[2] or ""
            reason = "no_website" if not uri else (
                "social_only" if SOCIAL_REGEX.search(uri) else "has_site")
            rows.append({
                "place_id": r[0],
                "name": r[1] or "",
                "website_uri": uri,
                "maps_link": r[3] or "",
                "address": r[4] or "",
                "primary_type": r[5] or "",
                "lat": r[6],
                "lng": r[7],
                "reviewed": bool(r[8]),
                "reviewed_at": r[9],
                "notes": r[10] or "",
                "fetched_at": r[11],
                "phone": r[12] or "",
                "international_phone": r[13] or "",
                "user_rating_count": r[14],
                "call_status": r[15] or "not_called",
                "business_status": r[16] or "",
                "reason": reason,
            })
        return rows, total


CALL_STATUSES = (
    "not_called",
    "no_answer",
    "not_interested",
    "callback",
    "closed",
    "won",
)


def set_call_status(place_id: str, status: Optional[str] = None,
                    notes: Optional[str] = None) -> bool:
    """Update call_status and/or notes for a lead. Touching either field also
    flips `reviewed=1` so it disappears from the default 'To review' filter."""
    fields: list[str] = []
    params: list = []
    if status is not None:
        if status not in CALL_STATUSES:
            raise ValueError(f"unknown call_status: {status}")
        fields.append("call_status = ?")
        params.append(status)
    if notes is not None:
        fields.append("notes = ?")
        params.append(notes)
    if not fields:
        return False
    fields.append("reviewed = 1")
    fields.append("reviewed_at = ?")
    params.append(int(time.time()))
    params.append(place_id)
    with cursor() as cur:
        cur.execute(
            f"UPDATE places SET {', '.join(fields)} WHERE place_id = ?",
            params,
        )
        return cur.rowcount > 0


def get_place(place_id: str) -> Optional[dict]:
    """Fetch the cached row for a single place (used by the per-run CSV export
    to attach phone/notes/call_status to lead rows)."""
    with cursor() as cur:
        cur.execute(
            """SELECT place_id, name, website_uri, maps_uri, address, primary_type,
                      lat, lng, phone, international_phone, user_rating_count,
                      call_status, notes, business_status, raw_json
               FROM places WHERE place_id = ?""",
            (place_id,),
        )
        r = cur.fetchone()
        if not r:
            return None
        return {
            "place_id": r[0],
            "name": r[1] or "",
            "website_uri": r[2] or "",
            "maps_link": r[3] or "",
            "address": r[4] or "",
            "primary_type": r[5] or "",
            "lat": r[6],
            "lng": r[7],
            "phone": r[8] or "",
            "international_phone": r[9] or "",
            "user_rating_count": r[10],
            "call_status": r[11] or "not_called",
            "notes": r[12] or "",
            "business_status": r[13] or "",
            "raw_json": r[14],
        }


def set_reviewed(place_id: str, reviewed: bool, notes: Optional[str] = None) -> bool:
    with cursor() as cur:
        if notes is None:
            cur.execute(
                "UPDATE places SET reviewed = ?, reviewed_at = ? WHERE place_id = ?",
                (1 if reviewed else 0, int(time.time()) if reviewed else None, place_id),
            )
        else:
            cur.execute(
                "UPDATE places SET reviewed = ?, reviewed_at = ?, notes = ? WHERE place_id = ?",
                (1 if reviewed else 0, int(time.time()) if reviewed else None,
                 notes, place_id),
            )
        return cur.rowcount > 0


def list_regions() -> list[dict]:
    with cursor() as cur:
        cur.execute(
            """SELECT id, name, display_name, bbox_json, polygon_geojson,
                      language_code, region_code, text_queries_json, created_at
               FROM regions ORDER BY created_at ASC"""
        )
        return [_region_row(r) for r in cur.fetchall()]


def get_region(region_id: str) -> Optional[dict]:
    with cursor() as cur:
        cur.execute(
            """SELECT id, name, display_name, bbox_json, polygon_geojson,
                      language_code, region_code, text_queries_json, created_at
               FROM regions WHERE id = ?""",
            (region_id,),
        )
        row = cur.fetchone()
        return _region_row(row) if row else None


def _region_row(r) -> dict:
    return {
        "id": r[0],
        "name": r[1],
        "display_name": r[2] or r[1],
        "bbox": json.loads(r[3]),
        "polygon_geojson": json.loads(r[4]) if r[4] else None,
        "language_code": r[5] or "en",
        "region_code": r[6] or "",
        "text_profiles": json.loads(r[7]) if r[7] else [],
        "created_at": r[8],
    }


def upsert_region(region: dict) -> None:
    with cursor() as cur:
        cur.execute(
            """INSERT INTO regions (id, name, display_name, bbox_json, polygon_geojson,
                                    language_code, region_code, text_queries_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   name=excluded.name,
                   display_name=excluded.display_name,
                   bbox_json=excluded.bbox_json,
                   polygon_geojson=excluded.polygon_geojson,
                   language_code=excluded.language_code,
                   region_code=excluded.region_code,
                   text_queries_json=excluded.text_queries_json""",
            (
                region["id"],
                region["name"],
                region.get("display_name") or region["name"],
                json.dumps(region["bbox"]),
                json.dumps(region["polygon_geojson"]) if region.get("polygon_geojson") else None,
                region.get("language_code") or "en",
                region.get("region_code") or "",
                json.dumps(region.get("text_profiles") or []),
                region.get("created_at") or int(time.time()),
            ),
        )


def delete_region(region_id: str) -> bool:
    with cursor() as cur:
        cur.execute("DELETE FROM regions WHERE id = ?", (region_id,))
        return cur.rowcount > 0


def get_ui_state(key: str) -> Optional[str]:
    with cursor() as cur:
        cur.execute("SELECT value FROM ui_state WHERE key = ?", (key,))
        row = cur.fetchone()
        return row[0] if row else None


def set_ui_state(key: str, value: str) -> None:
    with cursor() as cur:
        cur.execute(
            """INSERT INTO ui_state (key, value) VALUES (?, ?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
            (key, value),
        )


def create_run(run_id: str, cantons: list[str], cells_total: int) -> None:
    with cursor() as cur:
        cur.execute(
            """INSERT INTO runs (id, cantons, started_at, cells_total)
               VALUES (?, ?, ?, ?)""",
            (run_id, ",".join(cantons), int(time.time()), cells_total),
        )


def update_run(run_id: str, **fields) -> None:
    if not fields:
        return
    cols = ", ".join(f"{k} = ?" for k in fields)
    with cursor() as cur:
        cur.execute(f"UPDATE runs SET {cols} WHERE id = ?", (*fields.values(), run_id))


def finish_run(run_id: str, status: str = "done") -> None:
    with cursor() as cur:
        cur.execute(
            "UPDATE runs SET finished_at = ?, status = ? WHERE id = ?",
            (int(time.time()), status, run_id),
        )


RUN_COLS = ("id", "cantons", "started_at", "finished_at", "requests_used",
            "cells_total", "cells_done", "places_seen", "places_unique",
            "no_website", "social_only", "status")


def _region_name_map() -> dict[str, str]:
    with cursor() as cur:
        cur.execute("SELECT id, COALESCE(display_name, name) FROM regions")
        return {r[0]: r[1] for r in cur.fetchall()}


def _row_to_run(row, name_map: dict[str, str]) -> dict:
    d = dict(zip(RUN_COLS, row))
    ids = [s for s in (d["cantons"] or "").split(",") if s]
    d["region_ids"] = ids
    d["region_names"] = [name_map.get(rid, rid) for rid in ids]
    d.pop("cantons", None)
    return d


def list_runs(status: Optional[str] = None, limit: int = 200) -> list[dict]:
    clauses = []
    params: list = []
    if status:
        clauses.append("status = ?")
        params.append(status)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    name_map = _region_name_map()
    with cursor() as cur:
        cur.execute(
            f"SELECT {', '.join(RUN_COLS)} FROM runs {where} "
            f"ORDER BY started_at DESC LIMIT ?",
            (*params, limit),
        )
        return [_row_to_run(r, name_map) for r in cur.fetchall()]


def get_run(run_id: str) -> Optional[dict]:
    name_map = _region_name_map()
    with cursor() as cur:
        cur.execute(
            f"SELECT {', '.join(RUN_COLS)} FROM runs WHERE id = ?", (run_id,)
        )
        row = cur.fetchone()
        return _row_to_run(row, name_map) if row else None


def runs_totals() -> dict:
    """Lifetime totals across all runs."""
    with cursor() as cur:
        cur.execute(
            """SELECT COUNT(*),
                      COALESCE(SUM(requests_used), 0),
                      COALESCE(SUM(no_website), 0),
                      COALESCE(SUM(social_only), 0)
               FROM runs"""
        )
        n, req, nw, so = cur.fetchone()
        return {
            "total_runs": n,
            "total_requests": req,
            "total_leads": nw + so,
            "total_no_website": nw,
            "total_social_only": so,
        }


def runs_by_day(days: int = 30) -> list[dict]:
    since = int(time.time()) - days * 86400
    with cursor() as cur:
        cur.execute(
            """SELECT date(started_at, 'unixepoch') AS d,
                      COALESCE(SUM(requests_used), 0),
                      COALESCE(SUM(no_website + social_only), 0),
                      COUNT(*)
               FROM runs
               WHERE started_at >= ?
               GROUP BY d
               ORDER BY d ASC""",
            (since,),
        )
        return [{"date": r[0], "requests": r[1], "leads": r[2], "runs": r[3]}
                for r in cur.fetchall()]


def runs_by_region() -> list[dict]:
    """Aggregate requests/leads/runs per region ID by splitting runs.cantons."""
    name_map = _region_name_map()
    agg: dict[str, dict] = {}
    with cursor() as cur:
        cur.execute(
            """SELECT cantons, requests_used, no_website, social_only
               FROM runs"""
        )
        for cantons, req, nw, so in cur.fetchall():
            ids = [s for s in (cantons or "").split(",") if s]
            if not ids:
                continue
            # Split attribution equally across regions in a multi-region run —
            # we don't track per-region request counts in the runs table.
            share_req = (req or 0) / len(ids)
            share_nw = (nw or 0) / len(ids)
            share_so = (so or 0) / len(ids)
            for rid in ids:
                bucket = agg.setdefault(rid, {
                    "region_id": rid,
                    "region_name": name_map.get(rid, rid),
                    "requests": 0.0,
                    "no_website": 0.0,
                    "social_only": 0.0,
                    "runs": 0,
                })
                bucket["requests"] += share_req
                bucket["no_website"] += share_nw
                bucket["social_only"] += share_so
                bucket["runs"] += 1
    out = []
    for b in agg.values():
        b["requests"] = round(b["requests"], 1)
        b["leads"] = round(b["no_website"] + b["social_only"], 1)
        out.append(b)
    out.sort(key=lambda x: x["requests"], reverse=True)
    return out


def cache_coverage() -> dict:
    """Cheap re-use stat across all runs.

    `cached_buckets` = distinct (cell, bucket) pairs remembered — every one of
    these is an API call a future `use_cache=True` run won't need to re-make.
    `total_api_requests` = sum of `runs.requests_used`. The ratio expresses
    how many queries across all runs were satisfied from the cache vs. hit
    the network (approximation — multi-run collisions aren't separately
    tracked, but this is a useful lifetime "how much did the cache save us"
    signal and it's O(2 count queries) to compute).
    """
    with cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM cell_queries")
        cached = cur.fetchone()[0] or 0
        cur.execute("SELECT COALESCE(SUM(requests_used), 0) FROM runs")
        requests = cur.fetchone()[0] or 0
    total = cached + requests
    rate = (cached / total) if total else 0.0
    return {
        "cached_buckets": cached,
        "uncached_estimate": requests,
        "total_estimate": total,
        "rate": round(rate, 4),
    }
