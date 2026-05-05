const TOURS = {
    search: {
        storageKey: "rr.tutorial.search.v1",
        steps: [
            {
                element: '[data-view="search"] .view-header h2',
                popover: {
                    title: "Welcome to Restaurant Research",
                    description: "This is the Search page — where you build a run to find restaurants with no website. Let's walk through it in 30 seconds.",
                    side: "bottom",
                    align: "start",
                },
            },
            {
                element: "#region-query",
                popover: {
                    title: "Step 1 — Pick a region",
                    description: "Type a city, neighborhood, or country and hit <b>Add</b>. You can stack multiple regions per run.",
                    side: "bottom",
                    align: "start",
                },
            },
            {
                element: "#profile-list",
                popover: {
                    title: "Step 2 — Choose cuisine profiles",
                    description: "Each profile expands into localized search queries. Tick the cuisines you expect — e.g. <i>Turkish</i> in Berlin, <i>Izakaya</i> in Tokyo.",
                    side: "bottom",
                    align: "start",
                },
            },
            {
                element: "#test_mode",
                popover: {
                    title: "Step 3 — Keep test mode on (for now)",
                    description: "Test mode caps each region at 5 leads — a cheap sanity check. Turn it off for full sweeps once you've verified your setup.",
                    side: "bottom",
                    align: "start",
                },
            },
            {
                element: ".advanced-drawer",
                popover: {
                    title: "Optional — Tune radius & budget",
                    description: "Expand this for cell radius, hard request budget, and a live cost estimate. Defaults are fine for most runs.",
                    side: "top",
                    align: "start",
                },
            },
            {
                element: "#start",
                popover: {
                    title: "Step 4 — Start the search",
                    description: "Live progress appears below. You can hit <b>Stop</b> any time — partial results are kept.",
                    side: "top",
                    align: "start",
                },
            },
            {
                element: '[data-tab="library"]',
                popover: {
                    title: "Where your leads live",
                    description: "Every lead ever found is saved in the library tab. Searching again won't re-bill the API for places you've already seen.<br><br>Click the <b>?</b> next to any heading to replay a tour.",
                    side: "top",
                    align: "start",
                },
            },
        ],
    },

    library: {
        storageKey: "rr.tutorial.library.v1",
        steps: [
            {
                element: '[data-tab-panel="library"] thead th:first-child',
                popover: {
                    title: "Mark leads as reviewed",
                    description: "Tick the <b>✓</b> checkbox in this column to save a lead as reviewed — useful for tracking which leads you've already contacted or evaluated. Your choice is saved automatically.",
                    side: "bottom",
                    align: "start",
                },
            },
            {
                element: '[data-tab-panel="library"] .segmented',
                popover: {
                    title: "Heads up — reviewed leads are hidden by default",
                    description: "Use this filter to switch between <b>To review</b>, <b>Reviewed</b>, and <b>All</b>. If a lead seems to vanish after you tick it, switch to <b>Reviewed</b> or <b>All</b> to find it again.",
                    side: "bottom",
                    align: "start",
                },
            },
        ],
    },

    map: {
        storageKey: "rr.tutorial.map.v1",
        steps: [
            {
                element: ".map-header h2",
                popover: {
                    title: "Every lead on one map",
                    description: "Pins show every lead in your library. Zoom out and nearby pins group into clusters — click a cluster to expand it.",
                    side: "bottom",
                    align: "start",
                },
            },
            {
                element: ".map-filters",
                popover: {
                    title: "Filter by lead type",
                    description: "Show <b>All</b> leads, just <b>No website</b>, or just <b>Social only</b>. Pins update instantly.",
                    side: "bottom",
                    align: "start",
                },
            },
            {
                element: "#map-reload",
                popover: {
                    title: "Pull in new leads",
                    description: "Hit Reload after a fresh search to pick up any new pins without refreshing the whole page.",
                    side: "bottom",
                    align: "end",
                },
            },
        ],
    },

    runs: {
        storageKey: "rr.tutorial.runs.v1",
        steps: [
            {
                element: '[data-view="runs"] .view-header h2',
                popover: {
                    title: "Your crawl history",
                    description: "Every search you kick off is logged here — cost, cells crawled, requests made, leads found, and whether it finished or was stopped.",
                    side: "bottom",
                    align: "start",
                },
            },
            {
                element: '[data-view="runs"] .segmented',
                popover: {
                    title: "Filter by status",
                    description: "<b>Done</b>, <b>Running</b>, <b>Over budget</b>, <b>Cancelled</b> — narrow the list when you're hunting for a specific run.",
                    side: "bottom",
                    align: "start",
                },
            },
            {
                element: ".runs-table-wrap",
                popover: {
                    title: "Re-export past results",
                    description: "Each row has actions to re-download the CSV or drill into details — no need to re-run a crawl to get the leads again.",
                    side: "top",
                    align: "start",
                },
            },
        ],
    },

    cost: {
        storageKey: "rr.tutorial.cost.v1",
        steps: [
            {
                element: '[data-view="cost"] .view-header h2',
                popover: {
                    title: "Lifetime Places API spend",
                    description: "Track how much the Google Places API has cost you across every run. The rate at the top is the price you're being billed per 1,000 requests.",
                    side: "bottom",
                    align: "start",
                },
            },
            {
                element: ".cost-tiles",
                popover: {
                    title: "Key metrics at a glance",
                    description: "Total spent, runs made, leads found, and <b>cache hit rate</b>. Higher cache rate = more leads per dollar — the crawler skips places it's already seen.",
                    side: "bottom",
                    align: "start",
                },
            },
            {
                element: "#cost-chart",
                popover: {
                    title: "Usage over time",
                    description: "Spot spikes and quiet days. The table below splits cost across regions so you can see where your budget is going.",
                    side: "top",
                    align: "start",
                },
            },
        ],
    },
};

function getDriverFactory() {
    const factory = window.driver && window.driver.js && window.driver.js.driver;
    if (typeof factory !== "function") {
        console.warn("[tutorial] Driver.js not loaded — tutorial disabled");
        return null;
    }
    return factory;
}

function ensureViewVisible(viewName) {
    if (!viewName) return;
    const nav = document.querySelector(`.nav-item[data-target="${viewName}"]`);
    if (!nav) return;
    if (nav.classList.contains("active")) return;
    nav.click();
}

let activeTour = null;

const NAV_FOR_TOUR = {
    search: "search",
    map: "map",
    runs: "runs",
    cost: "cost",
};

function runTour(name) {
    const tour = TOURS[name];
    if (!tour) return;
    if (activeTour) return;
    const driver = getDriverFactory();
    if (!driver) return;

    ensureViewVisible(NAV_FOR_TOUR[name]);

    const instance = driver({
        showProgress: true,
        allowClose: true,
        overlayOpacity: 0.55,
        stagePadding: 6,
        stageRadius: 8,
        popoverClass: "rr-tutorial-popover",
        nextBtnText: "Next →",
        prevBtnText: "← Back",
        doneBtnText: "Got it",
        steps: tour.steps,
        onDestroyed: () => {
            activeTour = null;
            try { localStorage.setItem(tour.storageKey, "1"); } catch (_) {}
        },
    });

    activeTour = instance;
    requestAnimationFrame(() => instance.drive());
}

function hasSeen(tourName) {
    const tour = TOURS[tourName];
    if (!tour) return true;
    try { return !!localStorage.getItem(tour.storageKey); } catch (_) { return false; }
}

export function startSearchTutorial() { runTour("search"); }
export function startLibraryTutorial() { runTour("library"); }
export function startMapTutorial() { runTour("map"); }
export function startRunsTutorial() { runTour("runs"); }
export function startCostTutorial() { runTour("cost"); }

export function shouldAutoStartSearch() {
    return !hasSeen("search");
}

export function initTutorial() {
    document.querySelectorAll("[data-tutorial-replay]").forEach(el => {
        const name = el.dataset.tutorialReplay;
        if (!TOURS[name]) return;
        el.addEventListener("click", (e) => {
            e.stopPropagation();
            runTour(name);
        });
    });

    const libTab = document.querySelector('[data-tab="library"]');
    if (libTab) {
        libTab.addEventListener("click", () => {
            if (hasSeen("library")) return;
            setTimeout(() => runTour("library"), 80);
        });
    }

    ["map", "runs", "cost"].forEach(viewName => {
        const nav = document.querySelector(`.nav-item[data-target="${viewName}"]`);
        if (!nav) return;
        nav.addEventListener("click", () => {
            if (hasSeen(viewName)) return;
            setTimeout(() => runTour(viewName), 150);
        });
    });

    window.__rrReplayTutorial = (name = "search") => runTour(name);
}
