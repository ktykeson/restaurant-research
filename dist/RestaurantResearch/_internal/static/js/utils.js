export const $ = (sel) => document.querySelector(sel);
export const $$ = (sel) => Array.from(document.querySelectorAll(sel));

export function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[c]));
}

export function shorten(s, n) {
    return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

export function fmtUsd(n) {
    return "$" + (Number(n) || 0).toFixed(2);
}
