import { $, $$, escapeHtml, fmtUsd } from "./utils.js";

let currentJobId = null;
let currentSource = null;
let rowCount = 0;

let REGIONS = [];
let PROFILES = [];
let selection = {
    region_ids: [],
    text_profiles: [],
};
let saveSelectionTimer = null;
let profileFilterValue = "";

function setMetric(id, val) { $("#" + id).textContent = val; }

const _pendingMetrics = {};
let _flushScheduled = false;
function queueMetric(id, val) {
    _pendingMetrics[id] = val;
    if (_flushScheduled) return;
    _flushScheduled = true;
    requestAnimationFrame(() => {
        for (const k in _pendingMetrics) setMetric(k, _pendingMetrics[k]);
        for (const k in _pendingMetrics) delete _pendingMetrics[k];
        _flushScheduled = false;
    });
}

function setNow(text) { $("#m_now").textContent = text; }

function applyCounters(ev) {
    queueMetric("m_requests", ev.requests_used);
    queueMetric("m_seen", ev.places_seen);
    queueMetric("m_unique", ev.places_unique);
    queueMetric("m_no_website", ev.no_website);
    queueMetric("m_social", ev.social_only);
    queueMetric("m_cost", fmtUsd(ev.requests_used * ratePer1k() / 1000));
}

function ratePer1k() { return Number($("#rate_per_1k").value) || 32; }

export function appendLog(msg) {
    const el = $("#log");
    if (!el) return;
    const ts = new Date().toLocaleTimeString();
    el.insertAdjacentHTML("beforeend", `<div>[${ts}] ${msg}</div>`);
    el.scrollTop = el.scrollHeight;
}

function appendResult(ev) {
    rowCount += 1;
    setMetric("current-count", rowCount);
    $("#results-empty").hidden = true;
    const tr = document.createElement("tr");
    tr.innerHTML = `
        <td>${rowCount}</td>
        <td>${escapeHtml(ev.name)}</td>
        <td><span class="tag ${ev.reason}">${ev.reason.replace("_", " ")}</span></td>
        <td>${escapeHtml(ev.primary_type || "")}</td>
        <td>${escapeHtml(ev.address || "")}</td>
        <td><a href="${ev.maps_link}" target="_blank" rel="noopener">open</a></td>
    `;
    $("#results-body").appendChild(tr);
}

function resetUi() {
    rowCount = 0;
    setMetric("current-count", 0);
    $("#results-body").innerHTML = "";
    $("#results-empty").hidden = false;
    $("#log").innerHTML = "";
    ["m_cells", "m_cells_total", "m_requests", "m_seen", "m_unique", "m_no_website", "m_social"]
        .forEach(id => setMetric(id, 0));
    setMetric("m_cost", "$0.00");
    setNow("Starting…");
    $("#export").hidden = true;
}

function setRunningUi(running) {
    $("#start").disabled = running;
    $("#stop").hidden = !running;
    $("#status-strip").hidden = false;
    if (!running) {
        $("#export").hidden = rowCount === 0;
    }
}

function updateStartReadiness() {
    const startBtn = $("#start");
    const hint = $("#run-hint");
    const regionCount = selection.region_ids.length;
    const profileCount = selection.text_profiles.length;
    const useText = $("#use_text_search")?.checked;
    const ready = regionCount > 0 && (!useText || profileCount > 0);
    startBtn.disabled = !ready;
    if (regionCount === 0) {
        hint.textContent = "Pick at least one region to enable.";
    } else if (useText && profileCount === 0) {
        hint.textContent = "Tick at least one profile, or turn off Text search.";
    } else {
        hint.textContent = "";
    }
}

// ---------- Regions ----------

async function fetchRegions() {
    const r = await fetch("/api/regions");
    REGIONS = await r.json();
}

function renderRegions() {
    const list = $("#region-list");
    list.innerHTML = "";
    if (!REGIONS.length) {
        list.innerHTML = `<small class="muted">No saved regions yet. Add one above to get started.</small>`;
        updateRegionCount();
        return;
    }
    for (const r of REGIONS) {
        const checked = selection.region_ids.includes(r.id);
        const chip = document.createElement("label");
        chip.className = "region-chip";
        chip.innerHTML = `
            <input type="checkbox" data-region-id="${escapeHtml(r.id)}" ${checked ? "checked" : ""}>
            <span class="region-name">${escapeHtml(r.name)}</span>
            <span class="region-meta">${escapeHtml(r.region_code || "")}</span>
            <button type="button" class="region-del" title="Remove region">×</button>
        `;
        chip.querySelector("input").addEventListener("change", onRegionToggle);
        chip.querySelector(".region-del").addEventListener("click", (e) => {
            e.preventDefault();
            deleteRegion(r.id);
        });
        list.appendChild(chip);
    }
    updateRegionCount();
}

function updateRegionCount() {
    const el = $("#region-count");
    if (!el) return;
    const n = selection.region_ids.length;
    el.textContent = `${n} selected`;
}

function onRegionToggle() {
    const ids = $$("#region-list input[type=checkbox]:checked")
        .map(i => i.dataset.regionId);
    selection.region_ids = ids;
    updateRegionCount();
    updateStartReadiness();
    scheduleSaveSelection();
}

async function addRegion() {
    const q = $("#region-query").value.trim();
    if (!q) return;
    const status = $("#region-add-status");
    const btn = $("#region-add-btn");
    status.hidden = false;
    status.textContent = "Geocoding…";
    btn.disabled = true;
    try {
        const r = await fetch("/api/regions", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query: q }),
        });
        const j = await r.json();
        if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
        $("#region-query").value = "";
        status.textContent = `Added "${j.name}" — profiles: ${(j.text_profiles || []).join(", ") || "en"}`;
        await fetchRegions();
        if (!selection.region_ids.includes(j.id)) {
            selection.region_ids.push(j.id);
        }
        for (const p of (j.text_profiles || [])) {
            if (!selection.text_profiles.includes(p)) {
                selection.text_profiles.push(p);
            }
        }
        renderRegions();
        renderProfiles();
        updateProfilePreview();
        updateStartReadiness();
        scheduleSaveSelection();
        setTimeout(() => { status.hidden = true; }, 4000);
    } catch (err) {
        status.textContent = "Error: " + err.message;
    } finally {
        btn.disabled = false;
    }
}

async function deleteRegion(id) {
    if (!confirm(`Remove "${id}" from saved regions?`)) return;
    const r = await fetch(`/api/regions/${encodeURIComponent(id)}`, { method: "DELETE" });
    if (!r.ok) {
        appendLog(`Failed to remove region ${id}`);
        return;
    }
    selection.region_ids = selection.region_ids.filter(x => x !== id);
    await fetchRegions();
    renderRegions();
    updateStartReadiness();
    scheduleSaveSelection();
}

// ---------- Profiles ----------

async function fetchProfiles() {
    const r = await fetch("/api/query-profiles");
    PROFILES = await r.json();
}

function groupOrder() {
    return [
        "Western European",
        "Eastern European",
        "Middle Eastern",
        "East Asian",
        "South / Southeast Asian",
        "Other",
    ];
}

function renderProfiles() {
    const wrap = $("#profile-list");
    wrap.innerHTML = "";
    const grouped = new Map();
    for (const p of PROFILES) {
        const g = p.group || "Other";
        if (!grouped.has(g)) grouped.set(g, []);
        grouped.get(g).push(p);
    }
    const order = groupOrder();
    const sortedKeys = [
        ...order.filter(g => grouped.has(g)),
        ...[...grouped.keys()].filter(g => !order.includes(g)),
    ];
    for (const g of sortedKeys) {
        const profs = grouped.get(g);
        const groupEl = document.createElement("div");
        groupEl.className = "profile-group";
        groupEl.dataset.group = g;
        const head = document.createElement("div");
        head.className = "profile-group-head";
        head.innerHTML = `
            <span>${escapeHtml(g)}</span>
            <button type="button" class="group-toggle" data-action="select">select all</button>
            <button type="button" class="group-toggle" data-action="clear">clear</button>
        `;
        head.querySelector('[data-action="select"]').addEventListener("click", () => toggleGroup(g, true));
        head.querySelector('[data-action="clear"]').addEventListener("click", () => toggleGroup(g, false));
        const chips = document.createElement("div");
        chips.className = "profile-group-chips";
        for (const p of profs) {
            const checked = selection.text_profiles.includes(p.id);
            const chip = document.createElement("label");
            chip.className = "profile-chip";
            chip.dataset.profileId = p.id;
            chip.dataset.label = p.label.toLowerCase();
            chip.innerHTML = `
                <input type="checkbox" data-profile-id="${escapeHtml(p.id)}" ${checked ? "checked" : ""}>
                <span>${escapeHtml(p.label)}</span>
            `;
            chip.querySelector("input").addEventListener("change", onProfileToggle);
            chips.appendChild(chip);
        }
        groupEl.appendChild(head);
        groupEl.appendChild(chips);
        wrap.appendChild(groupEl);
    }
    applyProfileFilter();
    updateProfileCount();
}

function toggleGroup(group, on) {
    const ids = PROFILES.filter(p => (p.group || "Other") === group).map(p => p.id);
    if (on) {
        for (const id of ids) {
            if (!selection.text_profiles.includes(id)) selection.text_profiles.push(id);
        }
    } else {
        selection.text_profiles = selection.text_profiles.filter(id => !ids.includes(id));
    }
    syncProfileChipsToSelection();
    updateProfilePreview();
    updateProfileCount();
    updateStartReadiness();
    scheduleSaveSelection();
}

function syncProfileChipsToSelection() {
    for (const input of $$("#profile-list input[type=checkbox]")) {
        input.checked = selection.text_profiles.includes(input.dataset.profileId);
    }
}

function applyProfileFilter() {
    const q = profileFilterValue.trim().toLowerCase();
    for (const chip of $$("#profile-list .profile-chip")) {
        const matches = !q || chip.dataset.label.includes(q);
        chip.classList.toggle("is-hidden", !matches);
    }
    for (const group of $$("#profile-list .profile-group")) {
        const anyVisible = group.querySelector(".profile-chip:not(.is-hidden)");
        group.classList.toggle("is-empty", !anyVisible);
    }
}

function onProfileFilterInput(e) {
    profileFilterValue = e.target.value || "";
    applyProfileFilter();
}

function clearAllProfiles() {
    selection.text_profiles = [];
    syncProfileChipsToSelection();
    updateProfilePreview();
    updateProfileCount();
    updateStartReadiness();
    scheduleSaveSelection();
}

function onProfileToggle() {
    selection.text_profiles = $$("#profile-list input[type=checkbox]:checked")
        .map(i => i.dataset.profileId);
    updateProfilePreview();
    updateProfileCount();
    updateStartReadiness();
    scheduleSaveSelection();
}

function updateProfileCount() {
    const el = $("#profile-count");
    if (!el) return;
    const picked = selection.text_profiles;
    const seen = new Set();
    for (const pid of picked) {
        const p = PROFILES.find(x => x.id === pid);
        if (!p) continue;
        for (const q of p.queries) seen.add(q);
    }
    el.textContent = `${picked.length} profile${picked.length === 1 ? "" : "s"} · ${seen.size} ${seen.size === 1 ? "query" : "queries"}`;
}

function updateProfilePreview() {
    const out = $("#profile-preview");
    const picked = selection.text_profiles;
    if (!picked.length) {
        out.textContent = "No profiles ticked — text-search will be skipped.";
        return;
    }
    const seen = new Set();
    const queries = [];
    for (const pid of picked) {
        const p = PROFILES.find(x => x.id === pid);
        if (!p) continue;
        for (const q of p.queries) {
            if (!seen.has(q)) { seen.add(q); queries.push(q); }
        }
    }
    out.textContent = `${queries.length} queries: ${queries.join(", ")}`;
}

// ---------- Persisted selection ----------

async function fetchSelection() {
    try {
        const r = await fetch("/api/ui-state");
        const j = await r.json();
        if (Array.isArray(j.region_ids)) selection.region_ids = j.region_ids;
        if (Array.isArray(j.text_profiles)) selection.text_profiles = j.text_profiles;
    } catch (err) {
        // Fresh install — nothing persisted yet.
    }
}

function scheduleSaveSelection() {
    clearTimeout(saveSelectionTimer);
    saveSelectionTimer = setTimeout(saveSelection, 300);
}

async function saveSelection() {
    try {
        await fetch("/api/ui-state", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                region_ids: selection.region_ids,
                text_profiles: selection.text_profiles,
            }),
        });
    } catch (_) { /* best-effort */ }
}

// ---------- Estimate / Search ----------

function baseRequestBody() {
    return {
        region_ids: selection.region_ids,
        text_profiles: selection.text_profiles,
        radius_m: Number($("#radius_m").value),
        request_budget: Number($("#request_budget").value),
        use_cache: $("#use_cache").checked,
        use_text_search: $("#use_text_search").checked,
        include_social_only: $("#include_social_only").checked,
        rate_per_1k: ratePer1k(),
    };
}

async function refreshEstimate() {
    const out = $("#estimate-out");
    if (!selection.region_ids.length) { out.textContent = "Pick at least one region."; return; }
    out.textContent = "Estimating…";
    const r = await fetch("/api/estimate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(baseRequestBody()),
    });
    const j = await r.json();
    if (!r.ok) { out.textContent = "Error: " + (j.error || r.status); return; }
    let html = `<table>
        <tr><th>Region</th><th>Cells</th><th>Buckets/cell</th><th>Total</th><th>Cached (free)</th><th>Chargeable</th><th>Cost</th></tr>`;
    for (const c of j.by_region) {
        html += `<tr>
            <td>${escapeHtml(c.id)} — ${escapeHtml(c.name)}</td>
            <td>${c.cells}</td>
            <td>${c.buckets_per_cell}</td>
            <td>${c.total_buckets.toLocaleString()}</td>
            <td>${c.cached_buckets.toLocaleString()}</td>
            <td>${c.chargeable.toLocaleString()}</td>
            <td>${fmtUsd(c.cost_usd)}</td>
        </tr>`;
    }
    html += `<tr class="total">
        <td>TOTAL</td><td></td><td></td><td></td><td></td>
        <td>${j.total_chargeable.toLocaleString()} req</td>
        <td>${fmtUsd(j.total_cost_usd)}</td>
    </tr></table>`;
    if (j.capped_by_budget) {
        html += `<div class="warn">⚠ Estimate exceeds request budget — the run will abort partway. Raise the budget or test-mode it.</div>`;
    }
    html += `<div class="muted" style="margin-top:6px">@ $${j.rate_per_1k}/1k requests · ${j.text_queries.length} text-search queries across ${selection.text_profiles.length} profiles.</div>`;
    out.innerHTML = html;
}

async function startSearch() {
    if (!selection.region_ids.length) { alert("Pick at least one region"); return; }
    const body = {
        ...baseRequestBody(),
        per_region_lead_limit: $("#test_mode").checked ? Number($("#per_region_lead_limit").value) : null,
    };

    showResultsTab("current");
    resetUi();
    if (currentSource) currentSource.close();

    appendLog(`Starting search: ${selection.region_ids.join(", ")} (budget ${body.request_budget})`);
    const r = await fetch("/api/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    const j = await r.json();
    if (!r.ok) { appendLog("ERROR: " + (j.error || r.status)); return; }
    currentJobId = j.job_id;
    setRunningUi(true);
    appendLog(`Job ${currentJobId} started — opening event stream…`);

    currentSource = new EventSource(`/api/jobs/${currentJobId}/stream`);
    currentSource.addEventListener("open", () => appendLog("Stream connected."));
    currentSource.addEventListener("end", () => {
        appendLog("Stream ended.");
        currentSource.close();
        setRunningUi(false);
    });
    currentSource.onmessage = (e) => {
        let ev;
        try { ev = JSON.parse(e.data); } catch { return; }
        switch (ev.type) {
            case "start":
                setMetric("m_cells_total", ev.cells_total);
                setNow(`Searching ${ev.regions.join(", ")} — ${ev.cells_total} cells.`);
                appendLog(`Run ${ev.run_id}: ${ev.cells_total} cells across ${ev.regions.join(", ")}.`);
                break;
            case "cell_start":
                setNow(`Now: ${ev.region} cell ${ev.cell_index}/${ev.cells_in_region} (${ev.buckets} bucket queries)`);
                break;
            case "progress":
                queueMetric("m_cells", ev.cells_done);
                queueMetric("m_cells_total", ev.cells_total);
                applyCounters(ev);
                if (ev.cell_index && ev.cells_in_region) {
                    setNow(`Now: ${ev.region} cell ${ev.cell_index}/${ev.cells_in_region} done`);
                }
                break;
            case "tick":
                applyCounters(ev);
                break;
            case "result":
                appendResult(ev);
                break;
            case "region_done":
                appendLog(`Region ${ev.region} reached limit (${ev.leads} leads) — moving on.`);
                break;
            case "error":
                appendLog("ERROR: " + ev.msg);
                break;
            case "done":
                setMetric("m_cost", fmtUsd(ev.requests_used * ratePer1k() / 1000));
                setMetric("m_requests", ev.requests_used);
                setMetric("m_seen", ev.places_seen);
                setMetric("m_unique", ev.places_unique);
                setMetric("m_no_website", ev.no_website);
                setMetric("m_social", ev.social_only);
                setMetric("m_cells", ev.cells_done);
                setNow(ev.aborted_reason ? `Stopped (${ev.aborted_reason}).` : "Done.");
                appendLog(`Done. ${ev.no_website} no-website + ${ev.social_only} social-only out of ${ev.places_unique} unique places. Requests: ${ev.requests_used} (${fmtUsd(ev.requests_used * ratePer1k() / 1000)})${ev.aborted_reason ? " — " + ev.aborted_reason : ""}.`);
                $("#export").hidden = rowCount === 0;
                setRunningUi(false);
                break;
        }
    };
    currentSource.onerror = () => appendLog("Stream error (will reconnect or end).");
}

async function stopSearch() {
    if (!currentJobId) return;
    $("#stop").disabled = true;
    setNow("Stopping… finishing current cell.");
    appendLog("Stop requested — finishing current cell, then ending.");
    try {
        await fetch(`/api/jobs/${currentJobId}/cancel`, { method: "POST" });
    } catch (err) {
        appendLog("Stop failed: " + err);
        $("#stop").disabled = false;
    }
}

async function downloadCsv() {
    if (!currentJobId) return;
    const btn = $("#export");
    const original = btn.textContent;
    btn.disabled = true;
    btn.textContent = "Saving…";
    try {
        const r = await fetch(`/api/jobs/${currentJobId}/export`);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const data = await r.json();
        btn.textContent = "Saved to Downloads";
        appendLog(`CSV saved: ${data.path}`);
    } catch (err) {
        btn.textContent = original;
        alert("Couldn't save CSV: " + (err.message || err));
        return;
    }
    setTimeout(() => { btn.textContent = original; btn.disabled = false; }, 2500);
}

// ---------- Results / Library tabs ----------

function showResultsTab(name) {
    for (const tab of $$(".results-tab")) {
        tab.classList.toggle("is-active", tab.dataset.tab === name);
    }
    for (const panel of $$(".tab-panel")) {
        panel.hidden = panel.dataset.tabPanel !== name;
    }
}

function initResultsTabs() {
    for (const tab of $$(".results-tab")) {
        tab.addEventListener("click", () => showResultsTab(tab.dataset.tab));
    }
}

// ---------- Init ----------

export async function initSearch() {
    $("#start").addEventListener("click", startSearch);
    $("#stop").addEventListener("click", stopSearch);
    $("#export").addEventListener("click", downloadCsv);
    $("#estimate").addEventListener("click", refreshEstimate);
    $("#region-add-btn").addEventListener("click", addRegion);
    $("#region-query").addEventListener("keydown", (e) => {
        if (e.key === "Enter") { e.preventDefault(); addRegion(); }
    });
    $("#profile-filter").addEventListener("input", onProfileFilterInput);
    $("#profile-clear").addEventListener("click", clearAllProfiles);
    $("#use_text_search").addEventListener("change", updateStartReadiness);

    initResultsTabs();

    await Promise.all([fetchRegions(), fetchProfiles(), fetchSelection()]);
    const validIds = new Set(REGIONS.map(r => r.id));
    selection.region_ids = selection.region_ids.filter(id => validIds.has(id));
    const validProfiles = new Set(PROFILES.map(p => p.id));
    selection.text_profiles = selection.text_profiles.filter(p => validProfiles.has(p));
    renderRegions();
    renderProfiles();
    updateProfilePreview();
    updateStartReadiness();
}
