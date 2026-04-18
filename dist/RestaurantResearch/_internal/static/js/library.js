import { $, escapeHtml, shorten } from "./utils.js";
import { appendLog } from "./search.js";

let libSearchDebounce = null;

function libReviewedFilter() {
    const el = document.querySelector('input[name="lib-reviewed"]:checked');
    return el ? el.value : "unreviewed";
}

export async function loadLibrary() {
    const search = $("#lib-search").value.trim();
    const reviewed = libReviewedFilter();
    const params = new URLSearchParams({ reviewed, limit: "1000" });
    if (search) params.set("search", search);
    const r = await fetch(`/api/leads?${params.toString()}`);
    const j = await r.json();
    const body = $("#lib-body");
    body.innerHTML = "";
    $("#lib-total").textContent = `${j.total}`;
    $("#lib-empty").hidden = j.rows.length > 0;
    for (const row of j.rows) renderLibRow(row, body);
}

function renderLibRow(row, body) {
    const tr = document.createElement("tr");
    tr.dataset.placeId = row.place_id;
    if (row.reviewed) tr.classList.add("is-reviewed");
    const site = row.website_uri
        ? `<a href="${row.website_uri}" target="_blank" rel="noopener">${escapeHtml(shorten(row.website_uri, 40))}</a>`
        : "<span class='muted'>—</span>";
    const maps = row.maps_link
        ? `<a href="${row.maps_link}" target="_blank" rel="noopener">open</a>`
        : "<span class='muted'>—</span>";
    tr.innerHTML = `
        <td><input type="checkbox" class="lib-check" ${row.reviewed ? "checked" : ""}></td>
        <td>${escapeHtml(row.name)}</td>
        <td><span class="tag ${row.reason}">${row.reason.replace("_", " ")}</span></td>
        <td>${escapeHtml(row.primary_type || "")}</td>
        <td>${escapeHtml(row.address || "")}</td>
        <td>${site}</td>
        <td>${maps}</td>
    `;
    tr.querySelector(".lib-check").addEventListener("change", (e) => {
        toggleReviewed(row.place_id, tr, e.target.checked);
    });
    body.appendChild(tr);
}

async function toggleReviewed(placeId, tr, reviewed) {
    try {
        const r = await fetch(`/api/leads/${encodeURIComponent(placeId)}/review`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ reviewed }),
        });
        if (!r.ok) throw new Error(r.status);
        tr.classList.toggle("is-reviewed", reviewed);
        const filter = libReviewedFilter();
        if ((filter === "reviewed" && !reviewed) ||
            (filter === "unreviewed" && reviewed)) {
            tr.remove();
            const remaining = document.querySelectorAll("#lib-body tr").length;
            const totalEl = $("#lib-total");
            const current = parseInt((totalEl.textContent.match(/\d+/) || [0])[0], 10);
            totalEl.textContent = `${Math.max(current - 1, 0)}`;
            $("#lib-empty").hidden = remaining > 0;
        }
    } catch (err) {
        appendLog(`Failed to update review state: ${err}`);
        const cb = tr.querySelector(".lib-check");
        if (cb) cb.checked = !reviewed;
    }
}

export function initLibrary() {
    $("#lib-refresh").addEventListener("click", loadLibrary);
    $("#lib-search").addEventListener("input", () => {
        clearTimeout(libSearchDebounce);
        libSearchDebounce = setTimeout(loadLibrary, 250);
    });
    document.querySelectorAll('input[name="lib-reviewed"]').forEach(el => {
        el.addEventListener("change", loadLibrary);
    });
    loadLibrary();
}
