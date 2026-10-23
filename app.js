/* opencode-foundry Value: client-side role recommendation and sortable table.
 * Loads ./data/latest.json (same origin, no external requests) and applies the
 * role matrix described in the daily prompt of index.html.
 */
"use strict";

const DATA_URL = "data/latest.json";
const NA = "n/a";

// Picks must stay available for at least this long.
const MIN_DAYS_LEFT = 180;
// Reviewer: output price ceiling in USD per 1M tokens.
const REVIEWER_MAX_OUT = 15;

/* ---------- helpers ---------- */

function num(v) {
  return typeof v === "number" && isFinite(v) ? v : null;
}

// Blended price per 1M tokens at 3 input : 1 output, the usual comparison ratio.
function blended(m) {
  const i = num(m.price_in);
  const o = num(m.price_out);
  return i === null || o === null ? null : (3 * i + o) / 4;
}

function daysLeft(m, today) {
  if (!m.deprecation) return Infinity;
  return (Date.parse(m.deprecation) - today) / 86400000;
}

// Only models that can be picked: current release of its line, chat model, Foundry price known, full AA data,
// not about to be retired.
function eligible(models, today) {
  return models.filter(
    (m) =>
      m.chat &&
      m.in_region &&
      !m.superseded_by &&
      blended(m) !== null &&
      num(m.aa_intelligence) !== null &&
      num(m.aa_speed_tps) !== null &&
      num(m.aa_cost_per_task) !== null &&
      !["legacy", "deprecating"].includes(String(m.status).toLowerCase()) &&
      daysLeft(m, today) >= MIN_DAYS_LEFT
  );
}

function sortBy(pool, ...keys) {
  return pool.slice().sort((a, b) => {
    for (const k of keys) {
      const d = k(a) - k(b);
      if (d !== 0 && isFinite(d)) return d;
    }
    return String(a.id).localeCompare(String(b.id));
  });
}

/* ---------- role matrix ---------- */

// orchestrator: many small turns re-read the context, so the cached-input price
// decides. Cheapest cached input among models with AA intel >= 38.
function pickOrchestrator(pool) {
  return sortBy(
    pool.filter((m) => m.aa_intelligence >= 38 && num(m.price_cached) !== null),
    (m) => m.price_cached,
    (m) => -m.aa_intelligence
  )[0] || null;
}

// dev: most calls per task. Highest AA speed per blended dollar at intel >= 34.
function pickDev(pool) {
  return sortBy(
    pool.filter((m) => m.aa_intelligence >= 34),
    (m) => -(m.aa_speed_tps / blended(m)),
    (m) => -m.aa_intelligence
  )[0] || null;
}

// researcher: reads a lot. Lowest blended price at AA intel >= 34.
function pickResearcher(pool) {
  return sortBy(
    pool.filter((m) => m.aa_intelligence >= 34),
    (m) => blended(m),
    (m) => -m.aa_intelligence
  )[0] || null;
}

// reviewer: about one call per task. Highest AA intel (at least 34) with output <= $15/1M, from a
// vendor no other role uses. If every priced vendor is already used, it falls
// back to the best remaining model of a used vendor. Errors may then correlate
// with the other roles, which is accepted and not shown on the page.
function pickReviewer(pool, taken, usedVendors) {
  const open = pool.filter(
    (m) => !taken.has(m.id) && m.aa_intelligence >= 34 && m.price_out <= REVIEWER_MAX_OUT
  );
  const rank = (list) =>
    sortBy(list, (m) => -m.aa_intelligence, (m) => blended(m))[0] || null;
  const other = rank(open.filter((m) => !usedVendors.has(m.vendor)));
  if (other) return { model: other, sameVendor: false };
  const same = rank(open);
  return same ? { model: same, sameVendor: true } : null;
}

function recommend(models, today) {
  const pool = eligible(models, today);
  // Orchestrator, dev and researcher are all cost-driven, so they may end up on
  // the same model when it is clearly the cheapest. Only the reviewer has to differ.
  const orchestrator = pickOrchestrator(pool);
  const dev = pickDev(pool);
  const researcher = pickResearcher(pool);
  const taken = new Set([orchestrator, dev, researcher].filter(Boolean).map((m) => m.id));
  const vendors = new Set([orchestrator, dev, researcher].filter(Boolean).map((m) => m.vendor));
  const rev = pickReviewer(pool, taken, vendors);
  return {
    orchestrator,
    dev,
    researcher,
    reviewer: rev ? rev.model : null,
    reviewerSameVendor: rev ? rev.sameVendor : false,
  };
}

/* ---------- formatting ---------- */

function fmtNum(v, digits) {
  const n = num(v);
  if (n === null) return NA;
  return n.toLocaleString("en-US", {
    minimumFractionDigits: digits ?? 0,
    maximumFractionDigits: digits ?? 0,
  });
}

function fmtUsd(v) {
  const n = num(v);
  if (n === null) return NA;
  const digits = n >= 10 ? 0 : n >= 1 ? 2 : n >= 0.1 ? 3 : 4;
  return "$" + parseFloat(n.toFixed(digits)).toLocaleString("en-US", {
    minimumFractionDigits: 2,
  });
}

// Prices taken from global-standard (the EU data-zone card lists none) get an asterisk.
function star(m) {
  return m.price_fallback ? "*" : "";
}

function fmtPair(m) {
  return num(m.price_in) === null
    ? NA
    : fmtUsd(m.price_in) + " / " + fmtUsd(m.price_out) + star(m);
}

/* ---------- role picks ---------- */

function fillRolePick(row, model) {
  const set = (name, text) => {
    const el = row.querySelector('[data-field="' + name + '"]');
    if (el) el.textContent = text;
  };
  if (!model) {
    row.classList.add("pick-empty");
    set("model", "No model meets this role's criteria.");
    return;
  }
  row.classList.remove("pick-empty");
  set("model", model.id);
  set("price", fmtPair(model));
  set("intel", fmtNum(model.aa_intelligence));
  set("speed", fmtNum(model.aa_speed_tps, 0) + " t/s");
}

function renderRoles(reco) {
  for (const row of document.querySelectorAll("#picks .pick[data-role]")) {
    fillRolePick(row, reco[row.dataset.role]);
  }
}

/* ---------- sortable table ---------- */

const COLUMNS = [
  { key: "id", label: "Model", type: "text", cell: (m) => m.id },
  { key: "price_in", label: "in $/1M", type: "num", cell: (m) => m.price_in, fmt: fmtUsd, star: true },
  { key: "price_out", label: "out $/1M", type: "num", cell: (m) => m.price_out, fmt: fmtUsd, star: true },
  { key: "price_cached", label: "cached $/1M", type: "num", cell: (m) => m.price_cached, fmt: fmtUsd, star: true },
  { key: "aa_intelligence", label: "AA intel", type: "num", cell: (m) => m.aa_intelligence, fmt: (v) => fmtNum(v) },
  { key: "aa_speed_tps", label: "AA t/s", type: "num", cell: (m) => m.aa_speed_tps, fmt: (v) => fmtNum(v, 0) },
  { key: "aa_cost_per_task", label: "AA $/task", type: "num", cell: (m) => m.aa_cost_per_task, fmt: fmtUsd },
  { key: "deprecation", label: "retires", type: "text", cls: "retires", cell: (m) => (m.deprecation ? m.deprecation.slice(0, 7) : null) },
];

let sortState = { key: "aa_intelligence", dir: -1 };

function isMuted(m) {
  return blended(m) === null || num(m.aa_intelligence) === null;
}

function sortModels(models) {
  const col = COLUMNS.find((c) => c.key === sortState.key);
  if (!col) return models;
  const dir = sortState.dir;
  return models.slice().sort((a, b) => {
    const ds = (isMuted(a) ? 1 : 0) - (isMuted(b) ? 1 : 0);
    if (ds !== 0) return ds;
    const av = col.cell(a);
    const bv = col.cell(b);
    if (col.type === "text") {
      return String(av ?? "~").localeCompare(String(bv ?? "~")) * dir;
    }
    const an = num(av);
    const bn = num(bv);
    if (an === null && bn === null) return String(a.id).localeCompare(String(b.id));
    if (an === null) return 1;
    if (bn === null) return -1;
    if (an === bn) return String(a.id).localeCompare(String(b.id));
    return (an - bn) * dir;
  });
}

function badge(text, cls, title) {
  const el = document.createElement("span");
  el.className = "tag" + (cls ? " " + cls : "");
  el.textContent = text;
  if (title) el.title = title;
  return el;
}

function renderTable(models, reco) {
  const table = document.getElementById("models-table");
  if (!table) return;
  const recommended = new Map();
  for (const role of ["orchestrator", "dev", "reviewer", "researcher"]) {
    const m = reco[role];
    if (!m) continue;
    if (!recommended.has(m.id)) recommended.set(m.id, []);
    recommended.get(m.id).push(role);
  }

  const thead = document.createElement("thead");
  const htr = document.createElement("tr");
  for (const col of COLUMNS) {
    const th = document.createElement("th");
    th.textContent = col.label;
    th.className = "sortable";
    if (col.type === "num") th.classList.add("num");
    if (col.cls) th.classList.add(col.cls);
    if (sortState.key === col.key) {
      th.classList.add(sortState.dir === 1 ? "sort-asc" : "sort-desc");
      th.setAttribute("aria-sort", sortState.dir === 1 ? "ascending" : "descending");
    }
    th.addEventListener("click", () => {
      sortState =
        sortState.key === col.key
          ? { key: col.key, dir: -sortState.dir }
          : { key: col.key, dir: col.type === "text" ? 1 : -1 };
      renderTable(models, reco);
    });
    htr.append(th);
  }
  thead.append(htr);
  table.textContent = "";
  table.append(thead);

  const tbody = document.createElement("tbody");
  for (const m of sortModels(models)) {
    const tr = document.createElement("tr");
    if (isMuted(m)) tr.classList.add("muted");
    if (recommended.has(m.id)) tr.classList.add("recommended-row");
    COLUMNS.forEach((col, idx) => {
      const td = document.createElement("td");
      const raw = col.cell(m);
      td.textContent =
        col.type === "text"
          ? raw === null || raw === undefined ? NA : String(raw)
          : col.fmt(raw) + (col.star && num(raw) !== null ? star(m) : "");
      td.dataset.label = col.label;
      if (col.type === "num") td.classList.add("num");
      if (col.cls) td.classList.add(col.cls);
      if (idx === 0) {
        for (const role of recommended.get(m.id) || []) td.append(" ", badge(role));
        if (blended(m) === null)
          td.append(" ", badge("no price", "tag-free", "modelavailability.com lists no data-zone-standard (EU) price for this model."));
        else if (num(m.aa_intelligence) === null)
          td.append(" ", badge("no AA data", "tag-free", "No Artificial Analysis Intelligence Index v4 value."));
        const st = String(m.status).toLowerCase();
        if (st === "legacy" || st === "deprecating" || st === "preview")
          td.append(" ", badge(st, "tag-free"));
      }
      tr.append(td);
    });
    tbody.append(tr);
  }
  table.append(tbody);
}

/* ---------- chrome ---------- */

function renderMeta(meta) {
  const set = (id, text) => {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  };
  set("stand-date", meta.as_of || NA);
  set("scope-name", (meta.region || NA) + ", " + (meta.deployment || NA));
  const full = meta.aa_index_version || NA;
  const v = /v[\d.]+\s*$/.exec(full);
  set("aa-version", v ? v[0].trim() : full);
}

function wireCopy() {
  const btn = document.getElementById("copy-prompt");
  const src = document.getElementById("daily-prompt");
  if (!btn || !src) return;
  const label = btn.textContent;
  btn.addEventListener("click", async () => {
    const text = src.textContent.trim();
    try {
      await navigator.clipboard.writeText(text);
      btn.textContent = "Copied ✓";
    } catch (err) {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.append(ta);
      ta.select();
      try {
        document.execCommand("copy");
        btn.textContent = "Copied ✓";
      } catch (e2) {
        btn.textContent = "Copy failed";
      }
      ta.remove();
    }
    setTimeout(() => (btn.textContent = label), 2000);
  });
}

function showLoadError(message) {
  for (const row of document.querySelectorAll("#picks .pick[data-role]")) {
    row.classList.add("pick-empty");
    const line = row.querySelector('[data-field="model"]');
    if (line) line.textContent = message;
  }
}

async function init() {
  wireCopy();
  let payload;
  try {
    const res = await fetch(DATA_URL, { cache: "no-store" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    payload = await res.json();
  } catch (err) {
    showLoadError("Data could not be loaded: " + err.message);
    return;
  }
  const meta = payload.meta || {};
  // Chat models of the current release in their line; older ones are hidden.
  const chat = (Array.isArray(payload.models) ? payload.models : []).filter((m) => m.chat);
  const models = chat.filter((m) => !m.superseded_by);
  const hidden = document.getElementById("hidden-count");
  if (hidden) hidden.textContent = String(chat.length - models.length);
  const starNote = document.getElementById("star-note");
  if (starNote && !models.some((m) => m.price_fallback)) starNote.hidden = true;
  renderMeta(meta);
  const reco = recommend(models, Date.now());
  renderRoles(reco);
  renderTable(models, reco);
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
} else if (typeof module !== "undefined") {
  module.exports = { recommend, eligible, blended };
}
