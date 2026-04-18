import { $, escapeHtml } from "./utils.js";

const REASON_COLORS = {
    no_website: "#4cd28a",
    social_only: "#f5c451",
};

const DEFAULT_CENTER = [46.8, 8.2];
const DEFAULT_ZOOM = 8;

let map = null;
let cluster = null;
let allLeads = [];
let currentFilter = "all";

function colorFor(reason) {
    return REASON_COLORS[reason] || "#8a93a3";
}

function popupHtml(lead) {
    const site = lead.website_uri
        ? `<a href="${lead.website_uri}" target="_blank" rel="noopener">${escapeHtml(lead.website_uri)}</a>`
        : `<span class="muted">no website</span>`;
    const maps = lead.maps_link
        ? `<a href="${lead.maps_link}" target="_blank" rel="noopener">open in Google Maps</a>`
        : "";
    return `
        <div class="map-popup">
            <div class="map-popup-title">${escapeHtml(lead.name || "(unnamed)")}</div>
            <div class="map-popup-tag"><span class="tag ${lead.reason}">${lead.reason.replace("_", " ")}</span>
                <span class="muted">${escapeHtml(lead.primary_type || "")}</span></div>
            <div class="map-popup-addr">${escapeHtml(lead.address || "")}</div>
            <div class="map-popup-row">${site}</div>
            <div class="map-popup-row">${maps}</div>
            <div class="map-popup-actions">
                <button type="button" data-place-id="${escapeHtml(lead.place_id)}" class="map-review-btn"
                    ${lead.reviewed ? "disabled" : ""}>
                    ${lead.reviewed ? "✓ Reviewed" : "Mark reviewed"}
                </button>
            </div>
        </div>
    `;
}

function buildMarkers(leads) {
    const markers = [];
    for (const lead of leads) {
        if (typeof lead.lat !== "number" || typeof lead.lng !== "number") continue;
        const color = colorFor(lead.reason);
        const m = L.circleMarker([lead.lat, lead.lng], {
            radius: 6,
            color,
            fillColor: color,
            fillOpacity: 0.85,
            weight: 1.5,
        });
        m.bindPopup(() => popupHtml(lead));
        m.on("popupopen", (e) => {
            const btn = e.popup.getElement().querySelector(".map-review-btn");
            if (btn && !btn.disabled) {
                btn.addEventListener("click", async () => {
                    btn.disabled = true;
                    btn.textContent = "…";
                    try {
                        const r = await fetch(`/api/leads/${encodeURIComponent(lead.place_id)}/review`, {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ reviewed: true }),
                        });
                        if (!r.ok) throw new Error(r.status);
                        lead.reviewed = true;
                        btn.textContent = "✓ Reviewed";
                    } catch (err) {
                        btn.disabled = false;
                        btn.textContent = "Retry";
                    }
                }, { once: true });
            }
        });
        markers.push({ lead, marker: m });
    }
    return markers;
}

function applyFilter() {
    if (!cluster) return;
    cluster.clearLayers();
    const filtered = allLeads.filter(({ lead }) =>
        currentFilter === "all" ? true : lead.reason === currentFilter
    );
    cluster.addLayers(filtered.map(x => x.marker));
    $("#map-count").textContent = `${filtered.length} lead${filtered.length === 1 ? "" : "s"} on map`;
    fitToMarkers(filtered);
}

function fitToMarkers(filtered) {
    if (!map || !filtered.length) return;
    const bounds = L.latLngBounds(filtered.map(x => x.marker.getLatLng()));
    map.fitBounds(bounds, { padding: [40, 40], maxZoom: 14, animate: true });
}

async function loadLeads() {
    $("#map-count").textContent = "loading…";
    const r = await fetch("/api/leads?reviewed=all&limit=10000");
    const j = await r.json();
    allLeads = buildMarkers(j.rows || []);
    applyFilter();
}

function ensureMap() {
    if (map) return;
    map = L.map("leads-map", {
        zoomControl: true,
        preferCanvas: true,
    }).setView(DEFAULT_CENTER, DEFAULT_ZOOM);

    L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", {
        maxZoom: 19,
        subdomains: "abcd",
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
    }).addTo(map);

    cluster = L.markerClusterGroup({
        chunkedLoading: true,
        showCoverageOnHover: false,
        spiderfyOnMaxZoom: true,
    });
    map.addLayer(cluster);
}

function wireFilters() {
    document.querySelectorAll(".map-filter").forEach(btn => {
        btn.addEventListener("click", () => {
            document.querySelectorAll(".map-filter").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            currentFilter = btn.dataset.filter;
            applyFilter();
        });
    });
    $("#map-reload").addEventListener("click", loadLeads);
}

let initialized = false;
let wired = false;

export async function activate() {
    if (!wired) { wireFilters(); wired = true; }
    ensureMap();
    if (!initialized) {
        initialized = true;
        await loadLeads();
    }
    // Leaflet needs this when its container was hidden at init time.
    setTimeout(() => map && map.invalidateSize(), 0);
}
