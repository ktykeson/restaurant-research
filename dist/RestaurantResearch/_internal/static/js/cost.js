import { $, escapeHtml, fmtUsd } from "./utils.js";

function fmtNum(n) {
    return (Number(n) || 0).toLocaleString();
}

function renderTiles(j) {
    $("#cost-total-usd").textContent = fmtUsd(j.total_cost_usd);
    $("#cost-total-requests").textContent = fmtNum(j.total_requests);
    $("#cost-total-runs").textContent = fmtNum(j.total_runs);
    $("#cost-total-leads").textContent = fmtNum(j.total_leads);
    $("#cost-total-nw").textContent = fmtNum(j.total_no_website);
    $("#cost-total-so").textContent = fmtNum(j.total_social_only);

    const rate = (Number(j.cache_hit_rate) || 0) * 100;
    $("#cost-cache-rate").textContent = `${rate.toFixed(1)}%`;
    $("#cost-cache-cached").textContent = fmtNum(j.cache_cached_buckets);
    $("#cost-cache-total").textContent = fmtNum(j.cache_total_estimate);

    $("#cost-rate").textContent = fmtUsd(j.rate_per_1k);
}

function renderChart(by_day) {
    const chart = $("#cost-chart");
    chart.innerHTML = "";
    $("#cost-chart-empty").hidden = by_day.length > 0;
    if (!by_day.length) return;

    const max = Math.max(...by_day.map(d => d.requests || 0), 1);
    for (const d of by_day) {
        const pct = Math.max(((d.requests || 0) / max) * 100, 0);
        const row = document.createElement("div");
        row.className = "cost-chart-row";
        row.innerHTML = `
            <div class="cost-chart-label">${escapeHtml(d.date)}</div>
            <div class="cost-chart-bar-wrap">
                <div class="cost-chart-bar" style="width: ${pct.toFixed(1)}%"></div>
            </div>
            <div class="cost-chart-val">
                ${fmtNum(d.requests)} req
                <span class="muted"> · ${fmtUsd(d.cost_usd)}</span>
            </div>
        `;
        chart.appendChild(row);
    }
}

function renderByRegion(rows) {
    const body = $("#cost-region-body");
    body.innerHTML = "";
    $("#cost-region-empty").hidden = rows.length > 0;
    for (const r of rows) {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>${escapeHtml(r.region_name || r.region_id)}</td>
            <td class="num">${fmtNum(r.runs)}</td>
            <td class="num">${fmtNum(Math.round(r.requests))}</td>
            <td class="num">${fmtUsd(r.cost_usd)}</td>
            <td class="num">${fmtNum(Math.round(r.leads))}</td>
        `;
        body.appendChild(tr);
    }
}

export async function loadCost() {
    const r = await fetch("/api/usage/summary?days=30");
    const j = await r.json();
    renderTiles(j);
    renderChart(j.by_day || []);
    renderByRegion(j.by_region || []);
}

export function initCost() {
    // No persistent controls yet — reload each time the view is opened.
}
