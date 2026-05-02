import { initSearch } from "./search.js";
import { initLibrary } from "./library.js";
import * as RRMap from "./map.js";
import { initRuns, loadRuns } from "./runs.js";
import { initCost, loadCost } from "./cost.js";
import { initTutorial, startSearchTutorial, shouldAutoStartSearch } from "./tutorial.js";

function showSectionError(viewName, err) {
    const section = document.querySelector(`[data-view="${viewName}"]`);
    if (!section) return;
    let banner = section.querySelector(":scope > .view-error-banner");
    if (!banner) {
        banner = document.createElement("div");
        banner.className = "view-error-banner";
        banner.style.cssText = "margin:12px 0;padding:10px 14px;border-radius:6px;background:#3a1d1d;color:#ffb4b4;font:13px/1.4 system-ui,sans-serif;border:1px solid #5a2a2a";
        section.prepend(banner);
    }
    const msg = (err && (err.stack || err.message)) ? (err.message || String(err)) : String(err);
    banner.innerHTML = `<strong>Couldn't load this view.</strong><br><span style="opacity:.85">${msg.replace(/[<>&]/g, c => ({"<":"&lt;",">":"&gt;","&":"&amp;"}[c]))}</span><br><small style="opacity:.7">Check the debug strip at the bottom for details, then reload.</small>`;
}

function clearSectionError(viewName) {
    const section = document.querySelector(`[data-view="${viewName}"]`);
    if (!section) return;
    const banner = section.querySelector(":scope > .view-error-banner");
    if (banner) banner.remove();
}

function showView(name) {
    document.querySelectorAll("[data-view]").forEach(el => {
        el.hidden = el.dataset.view !== name;
    });
    document.querySelectorAll(".nav-item").forEach(el => {
        el.classList.toggle("active", el.dataset.target === name);
    });
    try {
        if (name === "map") RRMap.activate();
    } catch (err) {
        console.error("RRMap.activate", err);
        showSectionError("map", err);
    }
    // Lazy load data the first time (and refresh on every subsequent open
    // so numbers aren't stale after a crawl). Wrap so a failure here doesn't
    // leave the user staring at an empty page with no clue why.
    if (name === "runs") {
        clearSectionError("runs");
        loadRuns().catch(err => {
            console.error("loadRuns", err);
            showSectionError("runs", err);
        });
    }
    if (name === "cost") {
        clearSectionError("cost");
        loadCost().catch(err => {
            console.error("loadCost", err);
            showSectionError("cost", err);
        });
    }
}

function initSidebar() {
    document.querySelectorAll(".nav-item").forEach(el => {
        el.addEventListener("click", () => showView(el.dataset.target));
    });
    showView("search");
}

function installDebugStrip() {
    const strip = document.createElement("div");
    strip.id = "rr-debug-strip";
    strip.style.cssText = "position:fixed;left:0;right:0;bottom:0;max-height:30vh;overflow:auto;background:#1a0d0d;color:#ffb4b4;font:12px/1.35 ui-monospace,Menlo,monospace;border-top:1px solid #5a2a2a;padding:6px 10px;z-index:9999;display:none";
    strip.innerHTML = `<button id="rr-debug-close" style="float:right;background:none;border:none;color:#ffb4b4;cursor:pointer">×</button><strong>JS errors</strong><div id="rr-debug-list"></div>`;
    document.body.appendChild(strip);
    strip.querySelector("#rr-debug-close").addEventListener("click", () => { strip.style.display = "none"; });
    const list = strip.querySelector("#rr-debug-list");
    function push(msg) {
        const line = document.createElement("div");
        line.textContent = msg;
        list.appendChild(line);
        strip.style.display = "block";
    }
    window.addEventListener("error", (e) => {
        push(`[error] ${e.message} @ ${e.filename}:${e.lineno}:${e.colno}`);
    });
    window.addEventListener("unhandledrejection", (e) => {
        const r = e.reason;
        push(`[promise] ${(r && (r.stack || r.message)) || r}`);
    });
}

async function safeInit(name, fn) {
    try {
        const r = fn();
        if (r && typeof r.then === "function") await r;
    } catch (err) {
        console.error(`init ${name} failed`, err);
    }
}

// ---------------------------------------------------------------------------
// In-app update banner. The updater downloads new releases silently in the
// background; once a build is staged we show a non-blocking banner with
// "Update now" / "Later" so the user is in control of the restart moment.

const UPDATE_DISMISS_KEY = "rr-update-dismissed-version";

function renderUpdateBanner(version) {
    if (document.getElementById("rr-update-banner")) return;
    const bar = document.createElement("div");
    bar.id = "rr-update-banner";
    bar.setAttribute("role", "status");
    bar.style.cssText = [
        "position:fixed", "top:0", "left:0", "right:0",
        "z-index:10000",
        "padding:10px 16px",
        "background:linear-gradient(90deg,#1d3a6b,#2453a6)",
        "color:#fff",
        "font:13px/1.45 -apple-system,BlinkMacSystemFont,system-ui,sans-serif",
        "display:flex", "align-items:center", "justify-content:center",
        "gap:14px",
        "box-shadow:0 2px 8px rgba(0,0,0,0.35)",
    ].join(";");
    bar.innerHTML = `
        <span><strong>Version ${version}</strong> is ready to install.</span>
        <button id="rr-update-now"
            style="background:#fff;color:#1d3a6b;border:none;padding:5px 14px;border-radius:5px;font-weight:600;cursor:pointer;font-size:12.5px">
            Update now
        </button>
        <button id="rr-update-later"
            style="background:transparent;color:#cfdcef;border:1px solid #6f8bbf;padding:5px 12px;border-radius:5px;cursor:pointer;font-size:12.5px">
            Later
        </button>
    `;
    document.body.appendChild(bar);

    // Push the app shell down so the banner doesn't overlap content.
    document.body.style.paddingTop = `${bar.offsetHeight}px`;

    bar.querySelector("#rr-update-later").addEventListener("click", () => {
        try { sessionStorage.setItem(UPDATE_DISMISS_KEY, version); } catch {}
        bar.remove();
        document.body.style.paddingTop = "";
    });

    bar.querySelector("#rr-update-now").addEventListener("click", async () => {
        const btn = bar.querySelector("#rr-update-now");
        btn.disabled = true;
        btn.textContent = "Restarting…";
        try {
            const r = await fetch("/api/updates/apply", { method: "POST" });
            const data = await r.json().catch(() => ({}));
            if (data.manual_restart_required) {
                btn.textContent = "Quit & reopen to apply";
                btn.disabled = false;
                return;
            }
            // The server is about to kill the webview window. Show feedback
            // until the process actually exits.
            bar.querySelector("#rr-update-later").remove();
        } catch (err) {
            btn.disabled = false;
            btn.textContent = "Update now";
            alert("Couldn't apply the update: " + (err.message || err));
        }
    });
}

async function pollUpdateStatus() {
    try {
        const r = await fetch("/api/updates/status", { cache: "no-store" });
        if (!r.ok) return;
        const data = await r.json();
        if (!data.staged || !data.version) return;
        // Respect a per-session "Later" click for the same version.
        let dismissed = null;
        try { dismissed = sessionStorage.getItem(UPDATE_DISMISS_KEY); } catch {}
        if (dismissed === data.version) return;
        renderUpdateBanner(data.version);
    } catch (_) {
        // Silent — we'll retry on the next poll.
    }
}

function startUpdatePolling() {
    // Initial check after 5s so we don't compete with first paint, then
    // every 90s — the staged file appears at most once per launch.
    setTimeout(pollUpdateStatus, 5000);
    setInterval(pollUpdateStatus, 90000);
}

async function boot() {
    installDebugStrip();
    // Sidebar first — even if a downstream init throws, nav must work.
    safeInit("sidebar", initSidebar);
    safeInit("runs", initRuns);
    safeInit("cost", initCost);
    await Promise.all([
        safeInit("search", initSearch),
        safeInit("library", initLibrary),
    ]);
    safeInit("tutorial", initTutorial);
    safeInit("update-poller", startUpdatePolling);
    if (shouldAutoStartSearch()) {
        requestAnimationFrame(() => {
            try { startSearchTutorial(); } catch (err) { console.error("tutorial", err); }
        });
    }
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
} else {
    boot();
}
