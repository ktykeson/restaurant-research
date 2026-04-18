import { initSearch } from "./search.js";
import { initLibrary } from "./library.js";
import * as RRMap from "./map.js";
import { initRuns, loadRuns } from "./runs.js";
import { initCost, loadCost } from "./cost.js";
import { initTutorial, startSearchTutorial, shouldAutoStartSearch } from "./tutorial.js";

function showView(name) {
    document.querySelectorAll("[data-view]").forEach(el => {
        el.hidden = el.dataset.view !== name;
    });
    document.querySelectorAll(".nav-item").forEach(el => {
        el.classList.toggle("active", el.dataset.target === name);
    });
    if (name === "map") RRMap.activate();
    // Lazy load data the first time (and refresh on every subsequent open
    // so numbers aren't stale after a crawl).
    if (name === "runs") loadRuns().catch(err => console.error("loadRuns", err));
    if (name === "cost") loadCost().catch(err => console.error("loadCost", err));
}

function initSidebar() {
    document.querySelectorAll(".nav-item").forEach(el => {
        el.addEventListener("click", () => showView(el.dataset.target));
    });
    showView("search");
}

async function boot() {
    initSidebar();
    initRuns();
    initCost();
    await Promise.all([initSearch(), initLibrary()]);
    initTutorial();
    if (shouldAutoStartSearch()) {
        requestAnimationFrame(() => startSearchTutorial());
    }
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
} else {
    boot();
}
