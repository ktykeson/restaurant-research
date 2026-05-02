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
