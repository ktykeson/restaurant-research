import { $, escapeHtml, shorten } from "./utils.js";
import { appendLog } from "./search.js";

let libSearchDebounce = null;

const STATUS_OPTIONS = [
    ["not_called", "Not called"],
    ["no_answer", "No answer"],
    ["callback", "Callback"],
    ["not_interested", "Not interested"],
    ["closed", "Closed / gone"],
    ["won", "Won"],
];

function libReviewedFilter() {
    const el = document.querySelector('input[name="lib-reviewed"]:checked');
    return el ? el.value : "unreviewed";
}

function minReviewsValue() {
    const el = $("#lib-min-reviews");
    if (!el) return 0;
    const n = parseInt(el.value, 10);
    return Number.isFinite(n) && n > 0 ? n : 0;
}

export async function loadLibrary() {
    const search = $("#lib-search").value.trim();
    const reviewed = libReviewedFilter();
    const params = new URLSearchParams({ reviewed, limit: "1000" });
    if (search) params.set("search", search);
    const min = minReviewsValue();
    if (min > 0) params.set("min_reviews", String(min));
    const r = await fetch(`/api/leads?${params.toString()}`);
    const j = await r.json();
    const body = $("#lib-body");
    body.innerHTML = "";
    $("#lib-total").textContent = `${j.total}`;
    $("#lib-empty").hidden = j.rows.length > 0;
    for (const row of j.rows) renderLibRow(row, body);
}

function statusSelectHtml(current) {
    const opts = STATUS_OPTIONS.map(([v, label]) =>
        `<option value="${v}"${v === current ? " selected" : ""}>${escapeHtml(label)}</option>`
    ).join("");
    return `<select class="lib-status">${opts}</select>`;
}

function phoneCellHtml(row) {
    if (!row.phone && !row.international_phone) return "<span class='muted'>—</span>";
    const display = row.phone || row.international_phone;
    const href = row.international_phone || row.phone;
    return `<a href="tel:${encodeURIComponent(href)}">${escapeHtml(display)}</a>`;
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
    const ratings = (row.user_rating_count == null) ? "<span class='muted'>—</span>" : String(row.user_rating_count);
    const status = row.call_status || "not_called";
    const notesVal = (row.notes || "").replace(/"/g, "&quot;");
    tr.innerHTML = `
        <td><input type="checkbox" class="lib-check" ${row.reviewed ? "checked" : ""}></td>
        <td>${escapeHtml(row.name)}</td>
        <td class="lib-phone">${phoneCellHtml(row)}</td>
        <td>${statusSelectHtml(status)}</td>
        <td><input type="text" class="lib-notes" value="${notesVal}" placeholder="notes…"></td>
        <td class="num">${ratings}</td>
        <td><span class="tag ${row.reason}">${row.reason.replace("_", " ")}</span></td>
        <td>${escapeHtml(row.address || "")}</td>
        <td>${site}</td>
        <td>${maps}</td>
    `;
    tr.querySelector(".lib-check").addEventListener("change", (e) => {
        toggleReviewed(row.place_id, tr, e.target.checked);
    });
    tr.querySelector(".lib-status").addEventListener("change", (e) => {
        patchCall(row.place_id, tr, { status: e.target.value });
    });
    const notesInput = tr.querySelector(".lib-notes");
    let notesDirty = false;
    notesInput.addEventListener("input", () => { notesDirty = true; });
    notesInput.addEventListener("blur", () => {
        if (!notesDirty) return;
        notesDirty = false;
        patchCall(row.place_id, tr, { notes: notesInput.value });
    });
    body.appendChild(tr);
}

async function patchCall(placeId, tr, payload) {
    try {
        const r = await fetch(`/api/leads/${encodeURIComponent(placeId)}/call`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        if (!r.ok) throw new Error(r.status);
        // Saving any CRM field also marks the lead reviewed server-side.
        tr.classList.add("is-reviewed");
        const cb = tr.querySelector(".lib-check");
        if (cb) cb.checked = true;
        const filter = libReviewedFilter();
        if (filter === "unreviewed") {
            tr.remove();
            const remaining = document.querySelectorAll("#lib-body tr").length;
            $("#lib-empty").hidden = remaining > 0;
        }
    } catch (err) {
        appendLog(`Failed to save call update: ${err}`);
    }
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
    const minEl = $("#lib-min-reviews");
    if (minEl) {
        minEl.addEventListener("change", loadLibrary);
    }
    document.querySelectorAll('input[name="lib-reviewed"]').forEach(el => {
        el.addEventListener("change", loadLibrary);
    });
    loadLibrary();
}
