#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import subprocess
import sys
from pathlib import Path


DEFAULT_OUTPUT_DIR = Path.home() / "github-traffic" / "dashboard"
DEFAULT_QUERY_SCRIPT = Path(__file__).resolve().parent / "github_traffic_query.py"


HTML_TEMPLATE = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>GitHub Traffic Intelligence</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root {
  --bg: #0b0f14;
  --panel: #121821;
  --panel2: #18202b;
  --text: #e7edf5;
  --muted: #8ea0b8;
  --line: #2d3a4c;
  --accent: #7dd3fc;
  --accent2: #c084fc;
  --warn: #fbbf24;
  --bad: #fb7185;
  --good: #86efac;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
header {
  padding: 28px;
  border-bottom: 1px solid var(--line);
  background: linear-gradient(135deg, #101724, #090c11);
}

.title-row {
  display: flex;
  align-items: center;
  gap: 18px;
}

.jarri-link {
  display: flex;
  align-items: center;
  text-decoration: none;
}

.jarri-logo {
  width: 64px;
  height: 64px;
  object-fit: contain;
  border-radius: 14px;
  box-shadow: 0 0 18px rgba(125, 211, 252, 0.18);
}

.subtitle {
  margin: 4px 0 0;
  color: var(--muted);
  font-size: 14px;
}

h1 { margin: 0 0 4px; font-size: 28px; }
h2 { margin: 0 0 14px; font-size: 18px; }
h3 { margin: 0 0 8px; font-size: 15px; }
p { color: var(--muted); }
main { padding: 24px; display: grid; gap: 20px; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; }
.card {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 16px;
  padding: 16px;
  box-shadow: 0 10px 30px rgba(0,0,0,0.25);
}
.repo-card {
  cursor: pointer;
  transition: transform 120ms ease, border-color 120ms ease;
}
.repo-card:hover { transform: translateY(-2px); border-color: var(--accent); }
.kpi { font-size: 26px; font-weight: 700; margin: 4px 0; }
.muted { color: var(--muted); font-size: 13px; }
.row { display: flex; justify-content: space-between; gap: 12px; align-items: center; }
.badge {
  display: inline-block;
  padding: 3px 8px;
  border-radius: 999px;
  background: var(--panel2);
  color: var(--muted);
  font-size: 12px;
  border: 1px solid var(--line);
}
.controls { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; }
button, select, input {
  background: var(--panel2);
  color: var(--text);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 8px 10px;
}
input { min-width: 260px; }
button:hover { border-color: var(--accent); cursor: pointer; }
svg { width: 100%; height: 260px; display: block; }
.axis { stroke: var(--line); stroke-width: 1; }
.views { stroke: var(--accent); fill: none; stroke-width: 2.5; }
.clones { stroke: var(--accent2); fill: none; stroke-width: 2.5; }
.event-window { fill: var(--warn); opacity: 0.08; }
.event-line { stroke: var(--warn); stroke-width: 1.5; stroke-dasharray: 4 4; }
.event-dot { fill: var(--warn); }
.point-views { fill: var(--accent); stroke: var(--bg); stroke-width: 1.5; }
.point-clones { fill: var(--accent2); stroke: var(--bg); stroke-width: 1.5; }
.point-views:hover, .point-clones:hover, .event-dot:hover {
  r: 6;
  filter: brightness(1.4);
}
.label { fill: var(--muted); font-size: 11px; }
.legend { display: flex; gap: 14px; flex-wrap: wrap; margin-top: 8px; }
.legend span { font-size: 13px; color: var(--muted); display: inline-flex; align-items: center; gap: 6px; }
.legend-color {
  display: inline-block;
  width: 11px;
  height: 11px;
  border-radius: 999px;
}
.legend-views { background: var(--accent); }
.legend-clones { background: var(--accent2); }
.legend-events { background: var(--warn); }
table { width: 100%; border-collapse: collapse; }
th, td {
  text-align: left;
  padding: 8px;
  border-bottom: 1px solid var(--line);
  vertical-align: top;
}
th { color: var(--muted); font-size: 12px; font-weight: 600; }
td { font-size: 13px; }
a { color: var(--accent); }
pre {
  white-space: pre-wrap;
  background: #07090d;
  border: 1px solid var(--line);
  padding: 12px;
  border-radius: 12px;
  overflow: auto;
}
textarea {
  min-height: 80px;
  background: var(--panel2);
  color: var(--text);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 8px 10px;
}
.modal {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.72);
  display: grid;
  place-items: center;
  z-index: 999;
  padding: 20px;
}
.modal-card {
  width: min(900px, 100%);
  max-height: 90vh;
  overflow: auto;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 18px;
  padding: 18px;
  box-shadow: 0 20px 80px rgba(0,0,0,0.5);
}
.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 12px;
}
.form-grid label {
  display: grid;
  gap: 6px;
  color: var(--muted);
  font-size: 13px;
}
.hidden { display: none !important; }
</style>
</head>
<body>
<header>
  <div class="title-row">
  <a class="jarri-link" href="https://jarri.systems" target="_blank" rel="noopener noreferrer">
    <img class="jarri-logo" src="../docs/images/jarri-logo.png" alt="Jarri">
  </a>
  <div>
    <h1>GitHub Traffic Intelligence</h1>
    <p class="subtitle">Local-first repository traffic intelligence and historical archival</p>
  </div>
</div>
  <div class="muted" id="subtitle"></div>
  <div class="controls">
    <select id="repoSelect"></select>
    <button data-window="all">All history</button>
    <button data-window="14">14 days</button>
    <button data-window="30">30 days</button>
    <button data-window="90">90 days</button>
  </div>
</header>

<div id="eventModal" class="modal hidden">
  <div class="modal-card">
    <div class="row">
      <h2>Add Promotion / Action Event</h2>
      <button id="closeEventModal">Close</button>
    </div>
    <div class="form-grid">
      <label>Repo <select id="eventRepo"></select></label>
      <label>Event type <input id="eventType" value="reddit_post"></label>
      <label>Platform <input id="eventPlatform" value="reddit"></label>
      <label>Location <input id="eventLocation" placeholder="/r/vibecoding, Facebook group, etc."></label>
      <label>Framework <input id="eventFramework" placeholder="reddit_launch, facebook_group_test, release_push"></label>
      <label>Trail days <input id="eventTrailDays" type="number" min="0" value="3"></label>
      <label>URL <input id="eventUrl" placeholder="optional"></label>
      <label>Title <input id="eventTitle" placeholder="Posted project demo"></label>
      <label>UTC time <input id="eventTime" placeholder="YYYY-MM-DDTHH:MM:SS+00:00"></label>
      <label>Event ID for update <input id="eventUpdateId" placeholder="leave empty for new event"></label>
      <label>Notes <textarea id="eventNotes" placeholder="optional notes"></textarea></label>
    </div>
    <h3>Command</h3>
    <pre id="eventCommand"></pre>
    <div class="controls">
      <button id="copyEventCommand">Copy command</button>
      <button id="runEventLocal" class="hidden">Run locally</button>
      <button id="regenerateLocal" class="hidden">Regenerate dashboard</button>
    </div>
    <div class="muted" id="localApiStatus">Local API not connected. Public/static mode: copy and run the command manually.</div>
  </div>
</div>

<main>
  <section class="grid" id="repoCards"></section>

  <section class="card">
    <div class="row">
      <h2>Repository Inventory</h2>
      <span class="badge" id="repoCountBadge"></span>
    </div>
    <div class="controls">
      <input id="repoSearch" placeholder="Search repositories…" />
      <select id="repoSort">
        <option value="views">Sort by all-time views</option>
        <option value="clones">Sort by all-time clones</option>
        <option value="velocity">Sort by 7-day velocity</option>
        <option value="name">Sort by name</option>
      </select>
    </div>
    <table id="repoTable"></table>
  </section>

  <section class="card">
    <div class="row">
      <div>
        <h2 id="chartTitle">Traffic</h2>
        <div class="muted" id="chartSubtitle"></div>
      </div>
      <span class="badge" id="windowBadge">All history</span>
    </div>
    <svg id="chart" role="img"></svg>
    <div class="legend">
      <span><i class="legend-color legend-views"></i> Views</span>
      <span><i class="legend-color legend-clones"></i> Clones</span>
      <span><i class="legend-color legend-events"></i> Event markers</span>
    </div>
  </section>

  <section class="grid">
    <div class="card">
      <div class="row">
        <h2>Promotion / Action Events</h2>
        <button id="addEventButton">Add event</button>
      </div>
      <table id="eventsTable"></table>
    </div>
    <div class="card">
      <h2>Top Referrers</h2>
      <table id="referrersTable"></table>
    </div>
  </section>

  <section class="card">
    <h2>Top Paths</h2>
    <table id="pathsTable"></table>
  </section>

  <section class="card" id="failuresCard">
    <h2>Recent Collection Failures</h2>
    <table id="failuresTable"></table>
  </section>
</main>

<script id="payload" type="application/json">__DATA__</script>
<script>
const DATA = JSON.parse(document.getElementById("payload").textContent);
let selectedRepo = "ALL";
let selectedWindow = "all";

function fmt(n) { return Number(n || 0).toLocaleString(); }

function parseDay(s) {
  const [y, m, d] = s.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}

function dayKey(date) {
  return date.toISOString().slice(0, 10);
}

function daysBetween(first, last) {
  const out = [];
  let cur = parseDay(first);
  const end = parseDay(last);
  while (cur <= end) {
    out.push(dayKey(cur));
    cur.setUTCDate(cur.getUTCDate() + 1);
  }
  return out;
}

function filteredSeries() {
  let rows = DATA.daily_series || [];
  if (selectedRepo !== "ALL") rows = rows.filter(r => r.repo === selectedRepo);

  if (selectedWindow !== "all") {
    const maxDay = rows.reduce((m, r) => !m || r.day_utc > m ? r.day_utc : m, null);
    if (maxDay) {
      const start = parseDay(maxDay);
      start.setUTCDate(start.getUTCDate() - (Number(selectedWindow) - 1));
      const startKey = dayKey(start);
      rows = rows.filter(r => r.day_utc >= startKey);
    }
  }
  return rows;
}

function aggregateSeries(rows) {
  const map = new Map();
  for (const r of rows) {
    const key = r.day_utc;
    if (!map.has(key)) map.set(key, { day_utc: key, views: 0, clones: 0, unique_viewers: 0, unique_cloners: 0 });
    const item = map.get(key);
    item.views += Number(r.views || 0);
    item.clones += Number(r.clones || 0);
    item.unique_viewers += Number(r.unique_viewers || 0);
    item.unique_cloners += Number(r.unique_cloners || 0);
  }
  return [...map.values()].sort((a, b) => a.day_utc.localeCompare(b.day_utc));
}

function eventsForSelection() {
  let events = DATA.promotion_events || [];
  if (selectedRepo !== "ALL") events = events.filter(e => e.repo === selectedRepo);

  const rows = aggregateSeries(filteredSeries());
  if (!rows.length) return events;

  const first = rows[0].day_utc;
  const last = rows[rows.length - 1].day_utc;
  return events.filter(e => {
    const d = (e.event_time_utc || "").slice(0, 10);
    return d >= first && d <= last;
  });
}

function totals(rows) {
  return rows.reduce((a, r) => {
    a.views += Number(r.views || 0);
    a.clones += Number(r.clones || 0);
    a.unique_viewers += Number(r.unique_viewers || 0);
    a.unique_cloners += Number(r.unique_cloners || 0);
    return a;
  }, { views: 0, clones: 0, unique_viewers: 0, unique_cloners: 0 });
}

function renderHeader() {
  const hb = DATA.history_bounds || {};
  const lr = DATA.latest_run || {};
  document.getElementById("subtitle").textContent =
    `Generated ${DATA.generated_at_utc || ""} · Local history ${hb.first_day || "n/a"} → ${hb.last_day || "n/a"} · Latest run: ${lr.status || "n/a"} ${lr.collected_at_utc || ""}`;
}

function allRepoNames() {
  return [...new Set((DATA.repositories || []).map(r => r.repo))].sort();
}

function renderRepoSelect() {
  const repos = allRepoNames();
  const sel = document.getElementById("repoSelect");
  sel.innerHTML = `<option value="ALL">All repositories</option>` + repos.map(r => `<option value="${escapeHtml(r)}">${escapeHtml(r)}</option>`).join("");
  sel.value = selectedRepo;
  sel.onchange = () => { selectedRepo = sel.value; renderAll(); };
}

function repoStats() {
  const byRepo = new Map();
  for (const r of DATA.daily_series || []) {
    if (!byRepo.has(r.repo)) byRepo.set(r.repo, []);
    byRepo.get(r.repo).push(r);
  }

  return [...byRepo.entries()].map(([repo, repoRows]) => {
    const sortedRows = [...repoRows].sort((a, b) => a.day_utc.localeCompare(b.day_utc));
    const t = totals(sortedRows);
    const lastDay = sortedRows.length ? sortedRows[sortedRows.length - 1].day_utc : null;

    const last7Start = lastDay ? parseDay(lastDay) : null;
    if (last7Start) last7Start.setUTCDate(last7Start.getUTCDate() - 6);

    const prev7Start = lastDay ? parseDay(lastDay) : null;
    const prev7End = lastDay ? parseDay(lastDay) : null;
    if (prev7Start) prev7Start.setUTCDate(prev7Start.getUTCDate() - 13);
    if (prev7End) prev7End.setUTCDate(prev7End.getUTCDate() - 7);

    const last7Key = last7Start ? dayKey(last7Start) : "";
    const prev7StartKey = prev7Start ? dayKey(prev7Start) : "";
    const prev7EndKey = prev7End ? dayKey(prev7End) : "";

    const last7Rows = sortedRows.filter(r => r.day_utc >= last7Key);
    const prev7Rows = sortedRows.filter(r => r.day_utc >= prev7StartKey && r.day_utc <= prev7EndKey);

    const last7 = totals(last7Rows);
    const prev7 = totals(prev7Rows);

    const viewsDelta = last7.views - prev7.views;
    const clonesDelta = last7.clones - prev7.clones;
    const velocityScore = viewsDelta + clonesDelta;
    const trend = velocityScore > 0 ? "rising" : velocityScore < 0 ? "falling" : "flat";

    const lastTraffic = sortedRows
      .filter(r => Number(r.views || 0) > 0 || Number(r.clones || 0) > 0)
      .map(r => r.day_utc)
      .sort()
      .pop() || "";

    const events = (DATA.promotion_events || []).filter(e => e.repo === repo).length;

    return {
      repo,
      days: sortedRows.length,
      lastTraffic,
      events,
      last7Views: last7.views,
      prev7Views: prev7.views,
      viewsDelta,
      last7Clones: last7.clones,
      prev7Clones: prev7.clones,
      clonesDelta,
      velocityScore,
      trend,
      ...t
    };
  });
}

function sortedRepoStats() {
  const search = (document.getElementById("repoSearch")?.value || "").toLowerCase();
  const sort = document.getElementById("repoSort")?.value || "views";

  let rows = repoStats().filter(r => r.repo.toLowerCase().includes(search));

  rows.sort((a, b) => {
    if (sort === "name") return a.repo.localeCompare(b.repo);
    if (sort === "clones") return (b.clones - a.clones) || a.repo.localeCompare(b.repo);
    if (sort === "velocity") return (b.velocityScore - a.velocityScore) || (b.last7Views - a.last7Views) || a.repo.localeCompare(b.repo);
    return (b.views - a.views) || a.repo.localeCompare(b.repo);
  });

  return rows;
}

function rankLabel(index) {
  const sort = document.getElementById("repoSort")?.value || "views";
  if (sort === "name") return "featured";
  if (sort === "clones") return `#${index + 1} by clones`;
  if (sort === "velocity") return `#${index + 1} by velocity`;
  return `#${index + 1} by views`;
}

function trendSymbol(trend) {
  if (trend === "rising") return "↑ rising";
  if (trend === "falling") return "↓ falling";
  return "→ flat";
}

function signed(n) {
  n = Number(n || 0);
  return n > 0 ? `+${fmt(n)}` : fmt(n);
}

function renderCards() {
  const container = document.getElementById("repoCards");
  const rows = sortedRepoStats().slice(0, 8);

  container.innerHTML = rows.map((r, index) => `
    <div class="card repo-card" onclick="selectRepo('${escapeJs(r.repo)}')">
      <div class="row"><h3>${escapeHtml(r.repo)}</h3><span class="badge">${escapeHtml(rankLabel(index))}</span></div>
      <div class="grid">
        <div><div class="kpi">${fmt(r.views)}</div><div class="muted">all-time views</div></div>
        <div><div class="kpi">${fmt(r.clones)}</div><div class="muted">all-time clones</div></div>
      </div>
      <div class="muted">7d views: ${fmt(r.last7Views)} (${signed(r.viewsDelta)}) · 7d clones: ${fmt(r.last7Clones)} (${signed(r.clonesDelta)})</div>
      <div class="muted">Velocity: ${escapeHtml(trendSymbol(r.trend))}</div>
    </div>
  `).join("");
}

function renderRepoTable() {
  const rows = sortedRepoStats();
  const badge = document.getElementById("repoCountBadge");
  if (badge) badge.textContent = `${rows.length} repos`;

  document.getElementById("repoTable").innerHTML =
    `<tr><th>Repo</th><th>Views</th><th>Clones</th><th>7d views</th><th>Δ views</th><th>7d clones</th><th>Δ clones</th><th>Trend</th><th>Last traffic</th><th>Events</th></tr>` +
    rows.map(r => `
      <tr onclick="selectRepo('${escapeJs(r.repo)}')" style="cursor:pointer">
        <td>${escapeHtml(r.repo)}</td>
        <td>${fmt(r.views)}</td>
        <td>${fmt(r.clones)}</td>
        <td>${fmt(r.last7Views)}</td>
        <td>${signed(r.viewsDelta)}</td>
        <td>${fmt(r.last7Clones)}</td>
        <td>${signed(r.clonesDelta)}</td>
        <td>${escapeHtml(trendSymbol(r.trend))}</td>
        <td>${escapeHtml(r.lastTraffic || "—")}</td>
        <td>${fmt(r.events)}</td>
      </tr>
    `).join("");
}

window.selectRepo = function(repo) {
  selectedRepo = repo;
  document.getElementById("repoSelect").value = repo;
  renderAll();
}

function renderChart() {
  const svg = document.getElementById("chart");
  const rows = aggregateSeries(filteredSeries());
  const events = eventsForSelection();
  const title = selectedRepo === "ALL" ? "All repositories" : selectedRepo;
  document.getElementById("chartTitle").textContent = `${title} traffic`;
  document.getElementById("chartSubtitle").textContent = rows.length ? `${rows[0].day_utc} → ${rows[rows.length - 1].day_utc}` : "No traffic data";
  document.getElementById("windowBadge").textContent = selectedWindow === "all" ? "All history" : `${selectedWindow} days`;

  const width = 1000, height = 260, pad = 38;
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);

  if (!rows.length) {
    svg.innerHTML = `<text x="40" y="120" class="label">No data</text>`;
    return;
  }

  const maxVal = Math.max(1, ...rows.flatMap(r => [r.views, r.clones]));
  const x = i => pad + (rows.length === 1 ? 0 : i * (width - pad * 2) / (rows.length - 1));
  const y = v => height - pad - (Number(v || 0) * (height - pad * 2) / maxVal);

  const line = key => rows.map((r, i) => `${i === 0 ? "M" : "L"} ${x(i)} ${y(r[key])}`).join(" ");
  const dayIndex = new Map(rows.map((r, i) => [r.day_utc, i]));

  let eventSvg = "";
  for (const ev of events) {
    const trailDays = Number(ev.trail_days ?? 3);
    const d = (ev.event_time_utc || "").slice(0, 10);
    if (!dayIndex.has(d)) continue;

    const startIndex = dayIndex.get(d);
    const endIndex = Math.min(rows.length - 1, startIndex + trailDays);
    const ex = x(startIndex);
    const endX = x(endIndex);
    const windowWidth = Math.max(4, endX - ex);

    eventSvg += `<rect class="event-window" x="${ex}" y="${pad}" width="${windowWidth}" height="${height - pad * 2}">
      <title>${escapeHtml(d + " → +" + trailDays + "d · " + (ev.title || ev.event_type || "event"))}</title>
    </rect>`;

    eventSvg += `<line class="event-line" x1="${ex}" y1="${pad}" x2="${ex}" y2="${height-pad}"></line>`;
    eventSvg += `<circle class="event-dot" cx="${ex}" cy="${pad + 8}" r="4">
      <title>${escapeHtml(d + " · " + (ev.title || ev.event_type || "event") + (ev.location ? " · " + ev.location : ""))}</title>
    </circle>`;
  }

  const pointSvg = rows.map((r, i) => {
    const px = x(i);
    return `
      <circle class="point-views" cx="${px}" cy="${y(r.views)}" r="3.5">
        <title>${escapeHtml(`${r.day_utc} · Views: ${fmt(r.views)} · Unique viewers: ${fmt(r.unique_viewers)}`)}</title>
      </circle>
      <circle class="point-clones" cx="${px}" cy="${y(r.clones)}" r="3.5">
        <title>${escapeHtml(`${r.day_utc} · Clones: ${fmt(r.clones)} · Unique cloners: ${fmt(r.unique_cloners)}`)}</title>
      </circle>
    `;
  }).join("");

  svg.innerHTML = `
    <line class="axis" x1="${pad}" y1="${height-pad}" x2="${width-pad}" y2="${height-pad}"></line>
    <line class="axis" x1="${pad}" y1="${pad}" x2="${pad}" y2="${height-pad}"></line>
    ${eventSvg}
    <path class="views" d="${line("views")}"></path>
    <path class="clones" d="${line("clones")}"></path>
    ${pointSvg}
    <text x="${pad}" y="${height-10}" class="label">${escapeHtml(rows[0].day_utc)}</text>
    <text x="${width-pad-80}" y="${height-10}" class="label">${escapeHtml(rows[rows.length-1].day_utc)}</text>
    <text x="${pad+4}" y="${pad-12}" class="label">max ${fmt(maxVal)}</text>
  `;
}

function renderEvents() {
  const rows = eventsForSelection();
  const table = document.getElementById("eventsTable");
  table.innerHTML = `<tr><th>Date</th><th>Repo</th><th>Event</th><th>Location</th><th>Trail</th><th>Edit</th></tr>` +
    rows.map(e => `
      <tr>
        <td>${escapeHtml((e.event_time_utc || "").slice(0, 10))}</td>
        <td>${escapeHtml(e.repo || "")}</td>
        <td>${escapeHtml(e.title || e.event_type || "")}<div class="muted">${escapeHtml(e.platform || "")} · ${escapeHtml(e.event_type || "")}</div></td>
        <td>${e.url ? `<a href="${escapeAttr(e.url)}">${escapeHtml(e.location || e.url)}</a>` : escapeHtml(e.location || "")}</td>
        <td>+${fmt(e.trail_days ?? 3)}d</td>
        <td><button onclick="editEvent(${Number(e.id)})">Edit</button></td>
      </tr>
    `).join("");
}

function renderTables() {
  const repoFilter = r => selectedRepo === "ALL" || r.repo === selectedRepo;

  const refs = (DATA.latest_popular_referrers || []).filter(repoFilter).slice(0, 20);
  document.getElementById("referrersTable").innerHTML =
    `<tr><th>Repo</th><th>Referrer</th><th>Count</th><th>Uniques</th></tr>` +
    refs.map(r => `<tr><td>${escapeHtml(r.repo)}</td><td>${escapeHtml(r.referrer)}</td><td>${fmt(r.count)}</td><td>${fmt(r.uniques)}</td></tr>`).join("");

  const paths = (DATA.latest_popular_paths || []).filter(repoFilter).slice(0, 40);
  document.getElementById("pathsTable").innerHTML =
    `<tr><th>Repo</th><th>Path</th><th>Count</th><th>Uniques</th></tr>` +
    paths.map(r => `<tr><td>${escapeHtml(r.repo)}</td><td>${escapeHtml(r.path)}</td><td>${fmt(r.count)}</td><td>${fmt(r.uniques)}</td></tr>`).join("");

  const failures = DATA.recent_failures || [];
  document.getElementById("failuresCard").classList.toggle("hidden", failures.length === 0);
  document.getElementById("failuresTable").innerHTML =
    `<tr><th>Run</th><th>Repo</th><th>Endpoint</th><th>Status</th><th>Error</th></tr>` +
    failures.map(f => `<tr><td>${f.run_id}</td><td>${escapeHtml(f.repo)}</td><td>${escapeHtml(f.endpoint)}</td><td>${escapeHtml(String(f.status_code || ""))}</td><td>${escapeHtml(f.error || "")}</td></tr>`).join("");
}

function renderAll() {
  renderHeader();
  renderRepoSelect();
  renderCards();
  renderRepoTable();
  renderChart();
  renderEvents();
  renderTables();
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function escapeAttr(s) { return escapeHtml(s); }
function escapeJs(s) { return String(s ?? "").replace(/\\/g, "\\\\").replace(/'/g, "\\'"); }

function shellQuote(value) {
  value = String(value ?? "");
  return "'" + value.replace(/'/g, "'\\''") + "'";
}

function eventPayloadFromForm() {
  const payload = {
    id: document.getElementById("eventUpdateId").value || null,
    repo: document.getElementById("eventRepo").value,
    event_type: document.getElementById("eventType").value,
    platform: document.getElementById("eventPlatform").value,
    location: document.getElementById("eventLocation").value || null,
    framework: document.getElementById("eventFramework").value || null,
    trail_days: Number(document.getElementById("eventTrailDays").value || 3),
    url: document.getElementById("eventUrl").value || null,
    title: document.getElementById("eventTitle").value || "Untitled event",
    event_time_utc: document.getElementById("eventTime").value,
    notes: document.getElementById("eventNotes").value || null
  };

  if (!payload.id) delete payload.id;
  return payload;
}

async function localApi(path, payload) {
  const res = await fetch("http://127.0.0.1:8765" + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {})
  });
  return await res.json();
}

async function checkLocalApi() {
  try {
    const res = await fetch("http://127.0.0.1:8765/health");
    const data = await res.json();
    if (!data.ok) throw new Error("health check failed");

    document.getElementById("runEventLocal")?.classList.remove("hidden");
    document.getElementById("regenerateLocal")?.classList.remove("hidden");
    const status = document.getElementById("localApiStatus");
    if (status) status.textContent = "Local API connected. Run locally is available.";
  } catch {
    const status = document.getElementById("localApiStatus");
    if (status) status.textContent = "Local API not connected. Public/static mode: copy and run the command manually.";
  }
}

function initEventModal() {
  const modal = document.getElementById("eventModal");
  const open = document.getElementById("addEventButton");
  const close = document.getElementById("closeEventModal");
  const repo = document.getElementById("eventRepo");
  const command = document.getElementById("eventCommand");

  repo.innerHTML = allRepoNames().map(r => `<option value="${escapeHtml(r)}">${escapeHtml(r)}</option>`).join("");
  if (selectedRepo !== "ALL") repo.value = selectedRepo;

  const now = new Date().toISOString().replace(".000Z", "+00:00");
  document.getElementById("eventTime").value = now;

  function updateCommand() {
    const parts = [
      "python3 github_traffic_event.py",
      "--repo " + shellQuote(document.getElementById("eventRepo").value),
      "--event-type " + shellQuote(document.getElementById("eventType").value),
      "--platform " + shellQuote(document.getElementById("eventPlatform").value),
      "--title " + shellQuote(document.getElementById("eventTitle").value || "Untitled event"),
      "--event-time-utc " + shellQuote(document.getElementById("eventTime").value),
      "--trail-days " + shellQuote(document.getElementById("eventTrailDays").value || "3")
    ];

    const updateId = document.getElementById("eventUpdateId").value;
    if (updateId) parts.splice(1, 0, "--update-id " + shellQuote(updateId));

    const location = document.getElementById("eventLocation").value;
    const url = document.getElementById("eventUrl").value;
    const notes = document.getElementById("eventNotes").value;
    const framework = document.getElementById("eventFramework").value;

    if (location) parts.push("--location " + shellQuote(location));
    if (framework) parts.push("--framework " + shellQuote(framework));
    if (url) parts.push("--url " + shellQuote(url));
    if (notes) parts.push("--notes " + shellQuote(notes));

    command.textContent = parts.join(" \\\n  ");
  }

  open.onclick = () => {
    if (selectedRepo !== "ALL") repo.value = selectedRepo;
    modal.classList.remove("hidden");
    updateCommand();
  };

  close.onclick = () => modal.classList.add("hidden");

  modal.addEventListener("input", updateCommand);
  modal.addEventListener("change", updateCommand);

  document.getElementById("copyEventCommand").onclick = async () => {
    await navigator.clipboard.writeText(command.textContent);
  };

  document.getElementById("runEventLocal").onclick = async () => {
    const status = document.getElementById("localApiStatus");
    status.textContent = "Running local event action...";
    const result = await localApi("/events/upsert", eventPayloadFromForm());
    status.textContent = result.ok
      ? `Event ${result.action || "saved"} with id ${result.id}. Dashboard regenerated. Refreshing...`
      : `Local action failed: ${result.error || "unknown error"}`;
    if (result.ok) setTimeout(() => location.reload(), 800);
  };

  document.getElementById("regenerateLocal").onclick = async () => {
    const status = document.getElementById("localApiStatus");
    status.textContent = "Regenerating dashboard...";
    const result = await localApi("/dashboard/regenerate", {});
    status.textContent = result.ok ? "Dashboard regenerated. Refreshing..." : `Regeneration failed: ${result.error || result.stderr || "unknown error"}`;
    if (result.ok) setTimeout(() => location.reload(), 800);
  };
}

window.editEvent = function(id) {
  const ev = (DATA.promotion_events || []).find(e => Number(e.id) === Number(id));
  if (!ev) return;

  document.getElementById("eventUpdateId").value = ev.id || "";
  document.getElementById("eventRepo").value = ev.repo || "";
  document.getElementById("eventType").value = ev.event_type || "";
  document.getElementById("eventPlatform").value = ev.platform || "";
  document.getElementById("eventLocation").value = ev.location || "";
  document.getElementById("eventFramework").value = ev.framework || "";
  document.getElementById("eventTrailDays").value = ev.trail_days ?? 3;
  document.getElementById("eventUrl").value = ev.url || "";
  document.getElementById("eventTitle").value = ev.title || "";
  document.getElementById("eventTime").value = ev.event_time_utc || "";
  document.getElementById("eventNotes").value = ev.notes || "";
  document.getElementById("eventModal").classList.remove("hidden");
  document.getElementById("eventModal").dispatchEvent(new Event("input"));
}

document.querySelectorAll("button[data-window]").forEach(btn => {
  btn.onclick = () => {
    selectedWindow = btn.dataset.window;
    renderAll();
  };
});

initEventModal();
checkLocalApi();

document.addEventListener("input", ev => {
  if (ev.target && ev.target.id === "repoSearch") renderAll();
});
document.addEventListener("change", ev => {
  if (ev.target && ev.target.id === "repoSort") renderAll();
});

renderAll();
</script>
</body>
</html>
'''


def run_query(query_script: Path, db: Path, limit: int) -> dict:
    cmd = [
        sys.executable,
        str(query_script),
        "--db",
        str(db),
        "--summary-json",
        "--limit",
        str(limit),
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def write_dashboard(payload: dict, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    data_path = output_dir / "dashboard-data.json"
    html_path = output_dir / "dashboard.html"

    data_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
    data_path.write_text(data_json + "\n", encoding="utf-8")

    escaped_json = html.escape(data_json, quote=False)
    html_text = HTML_TEMPLATE.replace("__DATA__", escaped_json)
    html_path.write_text(html_text, encoding="utf-8")

    return data_path, html_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a static GitHub traffic intelligence dashboard.")
    parser.add_argument("--db", default=str(Path.home() / "github-traffic" / "github-traffic.sqlite3"))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--query-script", default=str(DEFAULT_QUERY_SCRIPT))
    parser.add_argument("--limit", type=int, default=100)
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    db = Path(args.db).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    query_script = Path(args.query_script).expanduser().resolve()

    payload = run_query(query_script, db, args.limit)
    data_path, html_path = write_dashboard(payload, output_dir)

    print(f"Wrote {data_path}")
    print(f"Wrote {html_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
