import { $, escapeHtml, fmtUsd } from "./utils.js";

const STATUS_LABEL = {
    done: "done",
    running: "running",
    budget_exceeded: "over budget",
    user_cancelled: "cancelled",
    cancelled: "cancelled",
    error: "error",
};

function currentStatus() {
    const el = document.querySelector('input[name="runs-status"]:checked');
    const v = el ? el.value : "all";
    return v === "all" ? null : v;
}

function fmtDate(unix) {
    if (!unix) return "—";
    const d = new Date(unix * 1000);
    return d.toLocaleString(undefined, {
        year: "numeric", month: "short", day: "2-digit",
        hour: "2-digit", minute: "2-digit",
    });
}

function fmtDuration(s) {
    if (s == null) return "—";
    if (s < 60) return `${s}s`;
    const m = Math.floor(s / 60);
    const sec = s % 60;
    if (m < 60) return `${m}m ${sec}s`;
    const h = Math.floor(m / 60);
    return `${h}h ${m % 60}m`;
}

function statusChip(s) {
    const label = STATUS_LABEL[s] || s || "—";
    return `<span class="tag status-${escapeHtml(s || "unknown")}">${escapeHtml(label)}</span>`;
}

function renderRun(row, tbody) {
    const tr = document.createElement("tr");
    tr.dataset.runId = row.id;

    const regions = (row.region_names || []).map(escapeHtml).join(", ") || "<span class='muted'>—</span>";
    const leads = (row.no_website || 0) + (row.social_only || 0);

    tr.innerHTML = `
        <td>
            <div>${fmtDate(row.started_at)}</div>
            <small class="muted">${fmtDuration(row.duration_s)}</small>
        </td>
        <td class="cell-regions">${regions}</td>
        <td>${statusChip(row.status)}</td>
        <td class="num">${row.cells_done || 0} / ${row.cells_total || 0}</td>
        <td class="num">${row.requests_used || 0}</td>
        <td class="num">${fmtUsd(row.cost_usd)}</td>
        <td class="num">
            ${leads}
            <br><small class="muted">${row.no_website || 0} / ${row.social_only || 0}</small>
        </td>
        <td>
            <a class="btn-link run-export" href="/api/runs/${encodeURIComponent(row.id)}/export"
               download>CSV</a>
        </td>
    `;
    tbody.appendChild(tr);
}

export async function loadRuns() {
    const status = currentStatus();
    const params = new URLSearchParams({ limit: "200" });
    if (status) params.set("status", status);
    const r = await fetch(`/api/runs?${params.toString()}`);
    const j = await r.json();
    const tbody = $("#runs-body");
    tbody.innerHTML = "";
    $("#runs-total").textContent = j.total;
    $("#runs-empty").hidden = j.rows.length > 0;
    for (const row of j.rows) renderRun(row, tbody);
}

export function initRuns() {
    $("#runs-refresh").addEventListener("click", loadRuns);
    document.querySelectorAll('input[name="runs-status"]').forEach(el => {
        el.addEventListener("change", loadRuns);
    });
}
