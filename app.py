"""Flask server: HTML frontend, job kickoff, SSE progress stream, CSV download."""
from __future__ import annotations

import asyncio
import json
import queue
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, Response, jsonify, redirect, render_template, request

import config
from paths import resource_path, writable_path
from search import cache, exporter, pricing, query_profiles, regions as regions_mod
from search.crawler import CrawlConfig, crawl
from search.geocoder import geocode

# Dev convenience only: pull GOOGLE_MAPS_API_KEY from .env if present.
# In the packaged app (frozen) the key lives in macOS Keychain via `config`.
if not getattr(sys, "frozen", False):
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass

app = Flask(
    __name__,
    template_folder=str(resource_path("templates")),
    static_folder=str(resource_path("static")),
)

RUNS_DIR = writable_path("runs")

# In-memory job registry — fine for a single-user local tool.
JOBS: dict[str, dict] = {}
SENTINEL = object()


def _deliver_csv(src: Path, download_name: str):
    """Copy a CSV to the user's Downloads folder and reveal it in Finder.

    The app runs inside a pywebview/WKWebView shell that has no native
    download manager, so `send_file(as_attachment=True)` opens the CSV in
    Preview/Quick Look instead of saving it. Writing to ~/Downloads and
    revealing in Finder gives the user an unambiguous "downloaded" file.
    """
    downloads = Path.home() / "Downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    dest = downloads / download_name
    stem, suffix = dest.stem, dest.suffix
    i = 1
    while dest.exists():
        dest = downloads / f"{stem} ({i}){suffix}"
        i += 1
    shutil.copyfile(src, dest)
    if sys.platform == "darwin":
        try:
            subprocess.Popen(["open", "-R", str(dest)])
        except Exception:
            pass
    return jsonify({"ok": True, "path": str(dest), "name": dest.name})


def _resolve_text_queries(region_ids: list[str], profile_override: list[str] | None) -> list[str]:
    """Union of text queries for the given profiles.

    If the UI sent an explicit `text_profiles` list we use it directly;
    otherwise we fall back to the union of each region's default profiles.
    """
    if profile_override is not None:
        profiles = profile_override
    else:
        profiles = []
        for rid in region_ids:
            try:
                r = regions_mod.get_region(rid)
            except KeyError:
                continue
            for p in r.text_profiles:
                if p not in profiles:
                    profiles.append(p)
    return query_profiles.queries_for_profiles(profiles)


def _job_thread(job_id: str, config: CrawlConfig) -> None:
    q: queue.Queue = JOBS[job_id]["queue"]
    rows: list[dict] = JOBS[job_id]["rows"]
    cancel: threading.Event = JOBS[job_id]["cancel"]

    async def push(event: dict) -> None:
        if event["type"] == "result":
            rows.append(event)
        q.put(event)

    async def runner():
        try:
            await crawl(config, on_event=push, cancel=cancel)
        except Exception as e:
            q.put({"type": "error", "msg": str(e)})
        finally:
            q.put(SENTINEL)

    asyncio.run(runner())


@app.route("/")
def index():
    if not config.has_api_key():
        return redirect("/setup")
    return render_template("index.html")


@app.route("/setup")
def setup_page():
    return render_template(
        "setup.html",
        mode="setup",
        has_key=config.has_api_key(),
        masked=config.masked_key(),
    )


@app.route("/settings")
def settings_page():
    return render_template(
        "setup.html",
        mode="settings",
        has_key=config.has_api_key(),
        masked=config.masked_key(),
    )


@app.route("/healthz")
def healthz():
    return jsonify({"ok": True})


@app.route("/api/config/status")
def api_config_status():
    return jsonify({"has_key": config.has_api_key(), "masked": config.masked_key()})


@app.route("/api/config/key", methods=["POST"])
def api_set_config_key():
    body = request.get_json(force=True) or {}
    value = (body.get("key") or "").strip()
    if not value:
        return jsonify({"error": "Key is required"}), 400
    config.set_api_key(value)
    return jsonify({"ok": True, "masked": config.masked_key()})


@app.route("/api/config/key", methods=["DELETE"])
def api_clear_config_key():
    config.set_api_key("")
    return jsonify({"ok": True})


@app.route("/api/updates/status")
def api_updates_status():
    """Reports whether a downloaded update is staged and ready to install.

    The frontend polls this and shows a banner when staged=true. The actual
    download happens silently in the background on launch (updater thread).
    """
    import updater
    info = updater.pending_update_info()
    if info is None:
        return jsonify({"staged": False, "version": None,
                        "current": updater.current_version()})
    _, version = info
    return jsonify({
        "staged": True,
        "version": version,
        "current": updater.current_version(),
    })


@app.route("/api/updates/apply", methods=["POST"])
def api_updates_apply():
    """User clicked 'Update now'. Schedule a relaunch — the next launch will
    apply the staged update via the launcher's pending-update applier."""
    import updater
    if updater.pending_update_info() is None:
        return jsonify({"error": "no update staged"}), 409
    if not updater.schedule_relaunch():
        return jsonify({
            "error": "Update is downloaded. Quit and reopen the app to apply it.",
            "manual_restart_required": True,
        }), 200
    return jsonify({"ok": True, "relaunching": True})


@app.route("/api/regions", methods=["GET"])
def api_list_regions():
    return jsonify([r.to_api_dict() for r in regions_mod.list_regions()])


@app.route("/api/regions", methods=["POST"])
def api_create_region():
    body = request.get_json(force=True) or {}
    query = (body.get("query") or "").strip()
    if not query:
        return jsonify({"error": "Provide a 'query' to geocode (e.g. 'Barcelona, Spain')"}), 400
    try:
        found = geocode(query)
    except Exception as e:
        return jsonify({"error": f"Geocoding failed: {e}"}), 502
    if not found:
        return jsonify({"error": f"No results for '{query}'"}), 404

    # User can override the auto-picked profiles on creation.
    if isinstance(body.get("text_profiles"), list):
        found["text_profiles"] = [str(p) for p in body["text_profiles"]]
    if body.get("language_code"):
        found["language_code"] = str(body["language_code"])
    if body.get("region_code") is not None:
        found["region_code"] = str(body["region_code"])

    cache.upsert_region(found)
    r = regions_mod.get_region(found["id"])
    return jsonify(r.to_api_dict())


@app.route("/api/regions/<region_id>", methods=["PATCH"])
def api_update_region(region_id: str):
    body = request.get_json(force=True) or {}
    existing = cache.get_region(region_id)
    if existing is None:
        return jsonify({"error": "unknown region"}), 404
    for key in ("name", "display_name", "language_code", "region_code"):
        if key in body:
            existing[key] = str(body[key])
    if isinstance(body.get("text_profiles"), list):
        existing["text_profiles"] = [str(p) for p in body["text_profiles"]]
    cache.upsert_region(existing)
    return jsonify(regions_mod.get_region(region_id).to_api_dict())


@app.route("/api/regions/<region_id>", methods=["DELETE"])
def api_delete_region(region_id: str):
    ok = cache.delete_region(region_id)
    if not ok:
        return jsonify({"error": "unknown region"}), 404
    return jsonify({"ok": True})


@app.route("/api/query-profiles")
def api_query_profiles():
    return jsonify([
        {"id": p["id"], "label": p["label"],
         "group": p.get("group", "Other"),
         "suggested_language_code": p.get("suggested_language_code"),
         "queries": p["queries"]}
        for p in query_profiles.PROFILES
    ])


@app.route("/api/ui-state", methods=["GET"])
def api_get_ui_state():
    raw = cache.get_ui_state("selection")
    try:
        data = json.loads(raw) if raw else {}
    except Exception:
        data = {}
    return jsonify(data)


@app.route("/api/ui-state", methods=["PUT"])
def api_put_ui_state():
    body = request.get_json(force=True) or {}
    cache.set_ui_state("selection", json.dumps(body))
    return jsonify({"ok": True})


@app.route("/api/search", methods=["POST"])
def api_search():
    body = request.get_json(force=True) or {}
    region_ids = body.get("region_ids") or body.get("regions") or []
    if not region_ids:
        return jsonify({"error": "Pick at least one region"}), 400

    per_region_lead_limit = body.get("per_region_lead_limit")
    if per_region_lead_limit is None:
        # Back-compat for any stale client fields.
        per_region_lead_limit = body.get("per_canton_lead_limit")
    if per_region_lead_limit is not None:
        per_region_lead_limit = int(per_region_lead_limit)
        if per_region_lead_limit <= 0:
            per_region_lead_limit = None

    profile_override = body.get("text_profiles") if isinstance(body.get("text_profiles"), list) else None
    text_queries = _resolve_text_queries(region_ids, profile_override)

    config = CrawlConfig(
        region_ids=region_ids,
        radius_m=float(body.get("radius_m", 1000.0)),
        request_budget=int(body.get("request_budget", 5000)),
        use_cache=bool(body.get("use_cache", True)),
        include_social_only=bool(body.get("include_social_only", True)),
        use_text_search=bool(body.get("use_text_search", True)),
        per_region_lead_limit=per_region_lead_limit,
        text_queries=text_queries,
    )

    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = {
        "queue": queue.Queue(maxsize=10000),
        "rows": [],
        "config": config,
        "started_at": time.time(),
        "cancel": threading.Event(),
    }
    t = threading.Thread(target=_job_thread, args=(job_id, config), daemon=True)
    t.start()
    return jsonify({"job_id": job_id})


@app.route("/api/jobs/<job_id>/cancel", methods=["POST"])
def api_cancel(job_id: str):
    job = JOBS.get(job_id)
    if job is None:
        return jsonify({"error": "unknown job"}), 404
    job["cancel"].set()
    return jsonify({"ok": True})


@app.route("/api/jobs/<job_id>/stream")
def api_stream(job_id: str):
    if job_id not in JOBS:
        return jsonify({"error": "unknown job"}), 404
    q: queue.Queue = JOBS[job_id]["queue"]

    def gen():
        # Initial hello so the connection opens immediately.
        yield "event: open\ndata: {}\n\n"
        while True:
            try:
                ev = q.get(timeout=15)
            except queue.Empty:
                # SSE keep-alive comment.
                yield ": keepalive\n\n"
                continue
            if ev is SENTINEL:
                yield "event: end\ndata: {}\n\n"
                break
            yield f"data: {json.dumps(ev)}\n\n"

    return Response(gen(), mimetype="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


@app.route("/api/jobs/<job_id>/export")
def api_export(job_id: str):
    if job_id not in JOBS:
        return jsonify({"error": "unknown job"}), 404
    rows = JOBS[job_id]["rows"]
    out_rows = [exporter.row_from_place({
        "id": r["place_id"],
        "displayName": {"text": r["name"]},
        "googleMapsUri": r["maps_link"],
        "websiteUri": r["website_uri"],
        "formattedAddress": r["address"],
        "primaryType": r["primary_type"],
        "location": {"latitude": r["lat"], "longitude": r["lng"]},
        "nationalPhoneNumber": r.get("phone") or "",
        "internationalPhoneNumber": r.get("international_phone") or "",
        "userRatingCount": r.get("user_rating_count"),
        "businessStatus": r.get("business_status") or "",
    }, r["reason"]) for r in rows]
    path = RUNS_DIR / f"run-{job_id}.csv"
    exporter.write_csv(out_rows, path)
    return _deliver_csv(path, path.name)


@app.route("/api/estimate", methods=["POST"])
def api_estimate():
    body = request.get_json(force=True) or {}
    region_ids = body.get("region_ids") or body.get("regions") or []
    if not region_ids:
        return jsonify({"error": "Pick at least one region"}), 400
    profile_override = body.get("text_profiles") if isinstance(body.get("text_profiles"), list) else None
    text_queries = _resolve_text_queries(region_ids, profile_override)
    est = pricing.estimate(
        region_ids=region_ids,
        radius_m=float(body.get("radius_m", 1000.0)),
        use_text_search=bool(body.get("use_text_search", True)),
        text_queries=text_queries,
        use_cache=bool(body.get("use_cache", True)),
        request_budget=int(body["request_budget"]) if body.get("request_budget") else None,
        rate_per_1k=float(body.get("rate_per_1k", pricing.DEFAULT_RATE_PER_1K)),
    )
    return jsonify({
        "by_region": [r.__dict__ for r in est.by_region],
        "total_chargeable": est.total_chargeable,
        "total_cost_usd": round(est.total_cost_usd, 2),
        "rate_per_1k": est.rate_per_1k,
        "capped_by_budget": est.capped_by_budget,
        "text_queries": text_queries,
    })


@app.route("/api/leads")
def api_leads():
    search = (request.args.get("search") or "").strip()
    reviewed = request.args.get("reviewed") or "all"
    if reviewed not in ("all", "reviewed", "unreviewed"):
        reviewed = "all"
    try:
        limit = min(max(int(request.args.get("limit", 500)), 1), 10000)
        offset = max(int(request.args.get("offset", 0)), 0)
    except ValueError:
        limit, offset = 500, 0
    try:
        min_reviews = max(int(request.args.get("min_reviews", 0)), 0)
    except ValueError:
        min_reviews = 0
    call_status = request.args.get("call_status") or None
    if call_status and call_status not in cache.CALL_STATUSES:
        call_status = None
    rows, total = cache.list_leads(search=search, reviewed=reviewed,
                                    limit=limit, offset=offset,
                                    min_reviews=min_reviews,
                                    call_status=call_status)
    return jsonify({"rows": rows, "total": total, "limit": limit, "offset": offset})


@app.route("/api/leads/<place_id>/review", methods=["POST"])
def api_set_reviewed(place_id: str):
    body = request.get_json(silent=True) or {}
    reviewed = bool(body.get("reviewed", True))
    notes = body.get("notes")
    ok = cache.set_reviewed(place_id, reviewed, notes=notes)
    if not ok:
        return jsonify({"error": "place not found"}), 404
    return jsonify({"ok": True, "place_id": place_id, "reviewed": reviewed})


@app.route("/api/leads/<place_id>/call", methods=["PATCH", "POST"])
def api_set_call(place_id: str):
    """Inline CRM update: set call_status and/or notes for a lead."""
    body = request.get_json(silent=True) or {}
    status = body.get("status")
    notes = body.get("notes")
    if status is None and notes is None:
        return jsonify({"error": "Provide 'status' and/or 'notes'"}), 400
    try:
        ok = cache.set_call_status(place_id, status=status, notes=notes)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if not ok:
        return jsonify({"error": "place not found"}), 404
    return jsonify({"ok": True, "place_id": place_id,
                    "status": status, "notes": notes})


@app.route("/api/call-statuses")
def api_call_statuses():
    return jsonify({"statuses": list(cache.CALL_STATUSES)})


def _enrich_run(run: dict) -> dict:
    run = dict(run)
    run["cost_usd"] = round(pricing.actual_cost(run.get("requests_used") or 0), 2)
    started = run.get("started_at") or 0
    finished = run.get("finished_at")
    run["duration_s"] = (finished - started) if (finished and started) else None
    return run


@app.route("/api/runs")
def api_list_runs():
    status = request.args.get("status") or None
    if status and status not in ("running", "done", "cancelled",
                                  "user_cancelled", "budget_exceeded", "error"):
        status = None
    try:
        limit = min(max(int(request.args.get("limit", 200)), 1), 1000)
    except ValueError:
        limit = 200
    rows = [_enrich_run(r) for r in cache.list_runs(status=status, limit=limit)]
    return jsonify({"rows": rows, "total": len(rows)})


@app.route("/api/runs/<run_id>")
def api_get_run(run_id: str):
    row = cache.get_run(run_id)
    if row is None:
        return jsonify({"error": "unknown run"}), 404
    return jsonify(_enrich_run(row))


@app.route("/api/runs/<run_id>/export")
def api_export_run(run_id: str):
    from search import filters, regions as regions_mod

    row = cache.get_run(run_id)
    if row is None:
        return jsonify({"error": "unknown run"}), 404

    out_rows: list[dict] = []
    seen: set[str] = set()
    for rid in row["region_ids"]:
        try:
            region = regions_mod.get_region(rid)
        except KeyError:
            continue
        poly = region.polygon()
        for place in cache.places_in_bbox(region.bbox):
            pid = place.get("id")
            if not pid or pid in seen:
                continue
            loc = place.get("location") or {}
            lat, lng = loc.get("latitude"), loc.get("longitude")
            if poly is not None and lat is not None and lng is not None:
                if not region.contains(lat, lng):
                    continue
            reason = filters.classify(place)
            if reason not in ("no_website", "social_only"):
                continue
            seen.add(pid)
            # Pull the cached lead row so the CSV carries phone/notes/call_status
            # (the raw API JSON in `place` lacks the CRM fields the user typed).
            lead = cache.get_place(pid)
            if lead is not None:
                out_rows.append(exporter.row_from_db(lead, reason))
            else:
                out_rows.append(exporter.row_from_place(place, reason))

    path = RUNS_DIR / f"run-{run_id}.csv"
    exporter.write_csv(out_rows, path)
    return _deliver_csv(path, path.name)


@app.route("/api/usage/summary")
def api_usage_summary():
    try:
        days = min(max(int(request.args.get("days", 30)), 1), 365)
    except ValueError:
        days = 30

    totals = cache.runs_totals()
    by_day_rows = cache.runs_by_day(days=days)
    by_region_rows = cache.runs_by_region()
    coverage = cache.cache_coverage()

    for d in by_day_rows:
        d["cost_usd"] = round(pricing.actual_cost(d["requests"]), 2)
    for r in by_region_rows:
        r["cost_usd"] = round(pricing.actual_cost(r["requests"]), 2)

    return jsonify({
        "total_runs": totals["total_runs"],
        "total_requests": totals["total_requests"],
        "total_leads": totals["total_leads"],
        "total_no_website": totals["total_no_website"],
        "total_social_only": totals["total_social_only"],
        "total_cost_usd": round(pricing.actual_cost(totals["total_requests"]), 2),
        "rate_per_1k": pricing.DEFAULT_RATE_PER_1K,
        "cache_hit_rate": coverage["rate"],
        "cache_cached_buckets": coverage["cached_buckets"],
        "cache_total_estimate": coverage["total_estimate"],
        "by_day": by_day_rows,
        "by_region": by_region_rows,
    })


if __name__ == "__main__":
    # Dev convenience: `python app.py` still works and uses Flask's dev server.
    # The packaged app always starts via `launcher.py` + waitress.
    cache.init_db()
    regions_mod.seed_swiss_cantons()
    app.run(host="127.0.0.1", port=5000, debug=True, threaded=True)
