// IronGraph dashboard application.
import { ExerciseGraph, CLUSTER_COLORS } from "./graph.js?v=3";

const $ = (s) => document.querySelector(s);
const api = async (path, opts) => {
  const r = await fetch("/api" + path, opts);
  if (!r.ok) throw new Error(`${r.status} ${path}`);
  return r.json();
};
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtDur = (s) => s >= 3600 ? `${Math.floor(s / 3600)}h ${Math.floor(s % 3600 / 60)}m`
  : s >= 60 ? `${Math.floor(s / 60)}m${s % 60 ? ` ${Math.round(s % 60)}s` : ""}` : `${Math.round(s)}s`;

function setDesc(set) {
  const bits = [];
  if (set.weight != null) bits.push(`${set.added_weight ? "+" : ""}${set.weight} ${set.unit || "lb"}`);
  if (set.reps != null) bits.push(`× ${set.reps}`);
  if (set.duration_s != null) bits.push(fmtDur(set.duration_s));
  if (set.distance != null) bits.push(`${set.distance} ${set.distance_unit || "mi"}`);
  if (set.incline_pct != null) bits.push(`incline ${set.incline_pct}%`);
  if (set.level != null) bits.push(`level ${set.level}`);
  if (set.rpe != null) bits.push(`@${set.rpe} RPE`);
  return bits.join(" ");
}
const REC_LABEL = {
  max_weight: "Max weight", max_e1rm: "Est. 1RM", max_reps: "Max reps",
  max_added: "Added weight", max_volume: "Session volume", max_duration: "Duration",
  max_distance: "Distance", best_pace: "Best pace",
};
const recLabel = (t) => REC_LABEL[t] || (t.startsWith("rep_weight:") ? `Best @ ${t.split(":")[1]} reps` : t);

// ---------------------------------------------------------------- views
const views = ["home", "graph", "timeline", "vault", "achievements", "coach"];
let currentView = "home";
function showView(v) {
  currentView = v;
  document.querySelectorAll(".view").forEach((el) => el.classList.remove("active"));
  document.querySelectorAll(".nav-item").forEach((el) => el.classList.toggle("active", el.dataset.view === v));
  $("#view-" + v).classList.add("active");
  if (v === "graph") initGraph();
  if (v === "home") renderHome();
  if (v === "timeline") renderTimeline();
  if (v === "vault") renderVault();
  if (v === "achievements") renderAchievements();
}
document.querySelectorAll(".nav-item").forEach((el) =>
  el.addEventListener("click", () => showView(el.dataset.view)));

// ---------------------------------------------------------------- home
async function renderHome() {
  const s = await api("/summary");
  const xpInLevel = s.xp - s.xp_cur_floor, xpNeed = s.xp_next - s.xp_cur_floor;
  $("#level-chip").innerHTML =
    `LV ${s.level} · ${esc(s.title)}<br>${s.xp} XP<div class="bar"><i style="width:${Math.min(100, 100 * xpInLevel / Math.max(xpNeed, 1)).toFixed(0)}%"></i></div>`;
  const st = s.streaks;
  const el = $("#view-home");
  const latest = s.latest_workout;
  el.innerHTML = `
    <h1>Command Center</h1>
    <div class="sub">every workout is a commit · every PR is a release</div>
    <div class="grid cols-3">
      <div class="card"><div class="label">Level</div><div class="value accent">${s.level} · ${esc(s.title)}</div>
        <div class="foot">${s.xp} XP — ${s.xp_next - s.xp} to next level</div></div>
      <div class="card"><div class="label">Workouts</div><div class="value">${s.total_workouts}</div>
        <div class="foot">${latest ? "last: " + latest.date + " (" + esc(latest.type) + ")" : "none yet"}</div></div>
      <div class="card"><div class="label">Personal Records</div><div class="value green">${s.total_prs}</div>
        <div class="foot">${s.exercises_tried} exercises tracked</div></div>
      <div class="card"><div class="label">Weekly Consistency</div><div class="value gold">${st.weekly_current}w</div>
        <div class="foot">${st.workouts_this_week}/${st.weekly_target} this week · best ${st.weekly_longest}w</div></div>
      <div class="card"><div class="label">Activity Streak</div><div class="value gold">${st.activity_current}d</div>
        <div class="foot">longest ${st.activity_longest}d</div></div>
      <div class="card"><div class="label">AI Coach</div><div class="value">${s.ai_available ? "online" : "offline"}</div>
        <div class="foot">${s.ai_available ? "Gemini connected" : "set GEMINI_API_KEY to enable"}</div></div>
    </div>
    <div class="grid cols-2" style="margin-top:14px">
      <div class="card">
        <div class="label">Newest records</div>
        <div id="home-prs">${s.newest_prs.length ? s.newest_prs.map((p) =>
          `<div class="pr-item"><b>${esc(p.exercise_id.replace(/-/g, " "))}</b>
             <span class="val">${esc(p.display)}</span><span class="badge pr">${p.date}</span></div>`).join("")
          : '<div class="empty"><span class="big">🏔️</span>No PRs yet — every workout from here is a first ascent.</div>'}</div>
      </div>
      <div class="card">
        <div class="label">Recommended next</div>
        ${s.recommendations.length ? s.recommendations.map((r) =>
          `<div class="rec-item"><div><b>${esc(r.name)}</b><div class="why">${esc(r.reason)}</div></div>
            <span class="badge new">${r.kind}</span></div>`).join("")
          : '<div class="empty">Log a few workouts and IronGraph will start spotting gaps and variations.</div>'}
      </div>
    </div>`;
}

// ---------------------------------------------------------------- timeline
async function renderTimeline() {
  const ws = await api("/workouts");
  const el = $("#view-timeline");
  el.innerHTML = `<h1>Workout Timeline</h1><div class="sub">${ws.length} sessions · newest first</div>` +
    (ws.length ? ws.map((w) => `
      <div class="tl-day">
        <div class="tl-date">${w.date}</div>
        <div class="tl-type">${esc(w.type)} · ${w.entries.length} exercises · ${esc(w.id)}</div>
        ${w.entries.map((e) => `<div class="tl-entry">${esc(e.exercise_name)}
          <span class="m">${e.sets.map(setDesc).map(esc).join(" · ")}</span>
          ${e.notes ? `<span class="m">// ${esc(e.notes)}</span>` : ""}</div>`).join("")}
        ${w.notes ? `<div class="tl-entry m" style="color:var(--muted)">📝 ${esc(w.notes)}</div>` : ""}
      </div>`).join("")
    : '<div class="empty"><span class="big">📜</span>No history yet. Close tonight\'s quest to write the first entry.</div>');
}

// ---------------------------------------------------------------- vault
async function renderVault() {
  const rs = await api("/records");
  const el = $("#view-vault");
  el.innerHTML = `<h1>PR Vault</h1><div class="sub">${rs.length} current records · full history preserved</div>` +
    (rs.length ? `<table class="vault"><tr><th>Exercise</th><th>Record</th><th>Current</th><th>Set</th><th>History</th></tr>` +
      rs.map((r) => `<tr>
        <td><b>${esc(r.exercise_name)}</b></td>
        <td>${esc(recLabel(r.type))}</td>
        <td class="mono"><span class="cur">${esc(r.current.display)}</span></td>
        <td class="mono">${r.current.date}</td>
        <td class="mono">${r.history.length > 1
          ? r.history.slice(0, -1).map((h) => esc(h.display)).join(" → ") + " → <b>now</b>"
          : "first record"}</td></tr>`).join("") + "</table>"
    : '<div class="empty"><span class="big">🏆</span>The vault is empty. It won\'t stay that way.</div>');
}

// ---------------------------------------------------------------- achievements
async function renderAchievements() {
  const a = await api("/achievements");
  $("#view-achievements").innerHTML =
    `<h1>Achievements</h1><div class="sub">${a.unlocked.length} unlocked · ${a.locked.length} remaining</div>
     <div class="ach-grid">
      ${a.unlocked.map((x) => `<div class="ach unlocked"><span class="e">${x.emoji}</span>
        <div><b>${esc(x.name)}</b><div class="d">${esc(x.description)} · ${x.date}</div></div></div>`).join("")}
      ${a.locked.map((x) => `<div class="ach locked"><span class="e">${x.emoji}</span>
        <div><b>${esc(x.name)}</b><div class="d">${esc(x.description)}</div></div></div>`).join("")}
     </div>`;
}

// ---------------------------------------------------------------- graph
let graph = null, graphLoaded = false;
async function initGraph() {
  if (!graph) {
    graph = new ExerciseGraph($("#graph-canvas"), $("#minimap"), {
      onSelect: (n) => openDetail(n.id),
    });
    bindGraphHud();
  }
  if (!graphLoaded) {
    const g = await api("/graph");
    graph.setData(g);
    graphLoaded = true;
    renderLegend(g);
  }
}
function renderLegend(g) {
  const counts = {};
  for (const n of g.nodes) counts[n.category] = (counts[n.category] || 0) + 1;
  $("#graph-legend").innerHTML = `<div class="lg-title">Clusters</div>` +
    g.clusters.map((c) => `<div class="lg-row" data-c="${c.id}">
      <span class="lg-dot" style="background:${CLUSTER_COLORS[c.id] || "#8b949e"}"></span>
      ${c.id} <span style="margin-left:auto;color:var(--muted)">${counts[c.id] || 0}</span></div>`).join("");
  document.querySelectorAll(".lg-row").forEach((el) =>
    el.addEventListener("click", () => {
      const c = g.clusters.find((x) => x.id === el.dataset.c);
      if (c) graph.flyTo(c.cx, c.cy, 1.7);
    }));
}
function bindGraphHud() {
  const chips = [
    { id: "performed", label: "performed", cls: "", f: () => ({ performed: graph.filters.performed === true ? null : true }) },
    { id: "unexplored", label: "unexplored", cls: "", f: () => ({ performed: graph.filters.performed === false ? null : false }) },
    { id: "prs", label: "recent PRs", cls: "green", f: () => ({ prs: !graph.filters.prs }) },
    { id: "recommended", label: "recommended", cls: "gold", f: () => ({ recommended: !graph.filters.recommended }) },
  ];
  $("#graph-chips").innerHTML = chips.map((c) =>
    `<button class="chip ${c.cls}" id="chip-${c.id}">${c.label}</button>`).join("");
  chips.forEach((c) => $("#chip-" + c.id).addEventListener("click", () => {
    graph.setFilter(c.f());
    $("#chip-performed").classList.toggle("on", graph.filters.performed === true);
    $("#chip-unexplored").classList.toggle("on", graph.filters.performed === false);
    $("#chip-prs").classList.toggle("on", graph.filters.prs);
    $("#chip-recommended").classList.toggle("on", graph.filters.recommended);
  }));
  const search = $("#graph-search");
  search.addEventListener("input", () => graph.setFilter({ q: search.value.trim().toLowerCase() }));
  search.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      const q = search.value.trim().toLowerCase();
      const hit = graph.nodes.find((n) => n.name.toLowerCase().startsWith(q)) ||
                  graph.nodes.find((n) => n.name.toLowerCase().includes(q));
      if (hit) graph.select(hit.id);
    }
    if (e.key === "Escape") { search.value = ""; graph.setFilter({ q: "" }); search.blur(); }
  });
  $("#zoom-in").addEventListener("click", () => graph.zoom(1.35));
  $("#zoom-out").addEventListener("click", () => graph.zoom(1 / 1.35));
  $("#zoom-fit").addEventListener("click", () => graph.fit());
}

// ---------------------------------------------------------------- detail panel
const detailHistory = [];
let detailSeq = 0;   // guards against a late fetch re-opening a closed panel
async function openDetail(id, push = true) {
  const seq = ++detailSeq;
  const d = await api("/exercise/" + id);
  if (seq !== detailSeq) return;   // closed or superseded while loading
  if (push) detailHistory.push(id);
  const ex = d.exercise, st = d.stats;
  const cur = d.records || {};
  const heroStats = [];
  if (cur.max_weight) heroStats.push(["Personal best", cur.max_weight.display, "green"]);
  if (cur.max_e1rm) heroStats.push(["Est. 1RM (Epley)", `~${Math.round(cur.max_e1rm.value)} lb`, "accent"]);
  if (cur.max_reps) heroStats.push(["Max reps", cur.max_reps.display, "green"]);
  if (cur.max_added) heroStats.push(["Max added weight", cur.max_added.display, "green"]);
  if (cur.max_distance) heroStats.push(["Longest", cur.max_distance.display, "green"]);
  if (cur.best_pace) heroStats.push(["Best pace", cur.best_pace.display, "accent"]);
  if (cur.max_duration) heroStats.push(["Longest effort", cur.max_duration.display, "green"]);
  heroStats.push(["Times performed", st ? st.times_performed : 0, ""]);
  if (st?.last_performed) heroStats.push(["Last performed", st.last_performed, ""]);
  const trendIcon = { improving: "▲", stable: "▶", declining: "▼" }[st?.trend] || "◌";

  $("#detail-body").innerHTML = `
    ${detailHistory.length > 1 ? '<button class="dp-rel" id="dp-back">← back</button>' : ""}
    <div class="dp-name">${esc(ex.name)}</div>
    <div class="dp-tags">
      <span class="dp-tag" style="color:${CLUSTER_COLORS[ex.category]}">${esc(ex.category)}</span>
      <span class="dp-tag">${esc(ex.movement_pattern)}</span>
      <span class="dp-tag">${esc(ex.equipment)}</span>
      <span class="dp-tag">${ex.compound ? "compound" : "isolation"}</span>
      ${ex.custom ? '<span class="dp-tag" style="color:var(--gold)">custom</span>' : ""}
      <span class="dp-tag">${trendIcon} ${esc(st?.trend || "no data")}</span>
    </div>
    <div class="dp-hero">${heroStats.map(([l, v, c]) =>
      `<div class="dp-stat"><div class="l">${esc(l)}</div><div class="v ${c}">${esc(v)}</div></div>`).join("")}</div>
    ${st?.history?.length > 1 ? '<canvas id="dp-spark"></canvas>' : ""}
    <div class="dp-section">Muscles</div>
    <div>${[...ex.primary_muscles.map((m) => `<span class="dp-rel">${esc(m)}</span>`),
            ...ex.secondary_muscles.map((m) => `<span class="dp-rel unperformed">${esc(m)}</span>`)].join("")}</div>
    ${d.recent_performances.length ? `<div class="dp-section">Recent performances</div>` +
      d.recent_performances.map((p) => `<div class="dp-perf"><span>${p.sets.map(setDesc).map(esc).join(" · ")}</span>
        <span class="d">${p.date}</span></div>`).join("") : ""}
    ${Object.keys(d.related).length ? `<div class="dp-section">Related exercises</div>` +
      Object.entries(d.related).map(([t, list]) =>
        `<div style="margin-bottom:6px"><span class="dp-tag">${esc(t.replace(/_/g, " "))}</span><br>` +
        list.map((r) => `<span class="dp-rel ${r.performed ? "" : "unperformed"}" data-ex="${r.id}">${esc(r.name)}${r.performed ? "" : " ○"}</span>`).join("") + "</div>").join("") : ""}
    <a class="dp-video" href="${esc(d.video.url)}" target="_blank" rel="noopener">
      ▶ ${d.video.kind === "search" ? "Find technique video" : "Watch: " + esc(d.video.title)}</a>
    <button class="dp-ask" data-ask="${esc(ex.name)}">✦ Ask IronGraph AI about ${esc(ex.name)}</button>`;

  $("#detail-panel").classList.remove("hidden");
  $("#dp-back")?.addEventListener("click", () => {
    detailHistory.pop();
    const prev = detailHistory[detailHistory.length - 1];
    if (prev) openDetail(prev, false);
  });
  document.querySelectorAll("[data-ex]").forEach((el) =>
    el.addEventListener("click", () => {
      const nid = el.dataset.ex;
      if (graph && graphLoaded && currentView === "graph") graph.select(nid);
      else openDetail(nid);
    }));
  $(".dp-ask").addEventListener("click", (e) => {
    showView("coach");
    $("#coach-input").value = `How do I improve my ${e.target.dataset.ask}?`;
    $("#coach-input").focus();
  });
  if (st?.history?.length > 1) drawSpark(st.history);
}
function drawSpark(hist) {
  const cv = $("#dp-spark");
  if (!cv) return;
  const key = ["weight_lb", "e1rm_lb", "reps", "distance_mi", "duration_s"].find((k) => hist.filter((h) => k in h).length >= 2);
  if (!key) return;
  const pts = hist.filter((h) => key in h).map((h) => h[key]);
  const dpr = devicePixelRatio || 1;
  cv.width = cv.clientWidth * dpr; cv.height = 74 * dpr;
  const g = cv.getContext("2d");
  g.scale(dpr, dpr);
  const W = cv.clientWidth, H = 74, min = Math.min(...pts), max = Math.max(...pts) || 1;
  const X = (i) => 6 + (W - 12) * (i / Math.max(pts.length - 1, 1));
  const Y = (v) => H - 12 - (H - 26) * ((v - min) / Math.max(max - min, 1e-9));
  g.strokeStyle = "#f78166"; g.lineWidth = 2; g.beginPath();
  pts.forEach((v, i) => i ? g.lineTo(X(i), Y(v)) : g.moveTo(X(0), Y(v)));
  g.stroke();
  let run = -Infinity;
  pts.forEach((v, i) => {
    const pr = v > run; run = Math.max(run, v);
    g.beginPath(); g.arc(X(i), Y(v), pr && i ? 3.4 : 2.4, 0, 7);
    g.fillStyle = pr && i ? "#3fb950" : "#f78166"; g.fill();
  });
}
$("#detail-close").addEventListener("click", closeDetail);
function closeDetail() {
  detailSeq++;                     // invalidate any in-flight openDetail
  $("#detail-panel").classList.add("hidden");
  detailHistory.length = 0;
  graph?.clearSelection();
}

// ---------------------------------------------------------------- coach
$("#coach-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const q = $("#coach-input").value.trim();
  if (!q) return;
  const log = $("#coach-log");
  log.insertAdjacentHTML("beforeend", `<div class="msg user">${esc(q)}</div>`);
  $("#coach-input").value = "";
  log.insertAdjacentHTML("beforeend", `<div class="msg sys" id="thinking">forging answer…</div>`);
  log.scrollTop = log.scrollHeight;
  try {
    const r = await api("/ai/ask", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: q, grounding: $("#coach-ground").checked }),
    });
    $("#thinking").remove();
    if (!r.available) {
      log.insertAdjacentHTML("beforeend", `<div class="msg sys">⚠️ ${esc(r.error)}</div>`);
    } else {
      log.insertAdjacentHTML("beforeend", `<div class="msg ai">${esc(r.text)}${
        r.grounding_urls.map((u) => `<a class="src" href="${esc(u)}" target="_blank" rel="noopener">${esc(u)}</a>`).join("")}</div>`);
    }
  } catch (err) {
    $("#thinking")?.remove();
    log.insertAdjacentHTML("beforeend", `<div class="msg sys">⚠️ ${esc(err.message)}</div>`);
  }
  log.scrollTop = log.scrollHeight;
});

// ---------------------------------------------------------------- palette
let palItems = [], palSel = 0;
async function openPalette() {
  $("#palette").classList.remove("hidden");
  const inp = $("#palette-input");
  inp.value = ""; inp.focus();
  if (!palItems.length) {
    const exs = await api("/exercises");
    palItems = [
      ...views.map((v) => ({ label: v === "home" ? "Command Center" : v[0].toUpperCase() + v.slice(1), kind: "view", act: () => showView(v) })),
      ...exs.map((x) => ({ label: x.name, kind: x.category, act: () => { showView("graph"); setTimeout(() => graph?.select(x.id), 150); } })),
    ];
  }
  renderPalette("");
}
function renderPalette(q) {
  const ql = q.toLowerCase();
  const hits = palItems.filter((i) => i.label.toLowerCase().includes(ql)).slice(0, 12);
  palSel = Math.min(palSel, Math.max(hits.length - 1, 0));
  $("#palette-results").innerHTML = hits.map((h, i) =>
    `<div class="pal-item ${i === palSel ? "sel" : ""}" data-i="${i}">${esc(h.label)}<span class="k">${esc(h.kind)}</span></div>`).join("");
  document.querySelectorAll(".pal-item").forEach((el) =>
    el.addEventListener("click", () => { hits[+el.dataset.i].act(); closePalette(); }));
  return hits;
}
function closePalette() { $("#palette").classList.add("hidden"); palSel = 0; }
$("#palette-input").addEventListener("input", (e) => { palSel = 0; renderPalette(e.target.value); });
$("#palette-input").addEventListener("keydown", (e) => {
  const hits = renderPalette(e.target.value);
  if (e.key === "ArrowDown") { palSel = Math.min(palSel + 1, hits.length - 1); renderPalette(e.target.value); e.preventDefault(); }
  if (e.key === "ArrowUp") { palSel = Math.max(palSel - 1, 0); renderPalette(e.target.value); e.preventDefault(); }
  if (e.key === "Enter" && hits[palSel]) { hits[palSel].act(); closePalette(); }
  if (e.key === "Escape") closePalette();
});

// ---------------------------------------------------------------- global keys
document.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); openPalette(); return; }
  if (e.target.matches("input, textarea")) return;
  if (e.key === "Escape") {
    if (!$("#add-ex-modal").classList.contains("hidden")) return $("#add-ex-modal").classList.add("hidden");
    if (!$("#palette").classList.contains("hidden")) return closePalette();
    if (!$("#detail-panel").classList.contains("hidden")) return closeDetail();
  }
  if (currentView === "graph" && graph) {
    if (e.key === "ArrowLeft") graph.hopNeighbor(-1);
    if (e.key === "ArrowRight") graph.hopNeighbor(1);
    if (e.key === "/") { e.preventDefault(); $("#graph-search").focus(); }
    if (e.key === "f") graph.fit();
    if (e.key === "+" || e.key === "=") graph.zoom(1.3);
    if (e.key === "-") graph.zoom(1 / 1.3);
  }
  const num = parseInt(e.key);
  if (num >= 1 && num <= views.length && !e.metaKey && !e.ctrlKey) showView(views[num - 1]);
});

// ---------------------------------------------------------------- add exercise
const APP_VERSION = 3;
console.info(`IronGraph dashboard app.js v${APP_VERSION}`);

function openAddModal() {
  $("#add-ex-modal").classList.remove("hidden");
  $("#aem-error").textContent = "";
  $("#add-ex-form").reset();
  $("#add-ex-form [name=name]").focus();
}
// Delegated: survives any DOM timing/rerender, works from any view.
document.addEventListener("click", (e) => {
  if (e.target.closest("#add-ex-btn")) openAddModal();
});
$("#aem-cancel").addEventListener("click", () => $("#add-ex-modal").classList.add("hidden"));
$("#add-ex-modal").addEventListener("click", (e) => {
  if (e.target.id === "add-ex-modal") $("#add-ex-modal").classList.add("hidden");
});
// Escape must work even while typing in a modal input (the global handler
// ignores keys from inputs)
$("#add-ex-modal").addEventListener("keydown", (e) => {
  if (e.key === "Escape") { e.stopPropagation(); $("#add-ex-modal").classList.add("hidden"); }
});
$("#add-ex-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  const csv = (k) => (f.get(k) || "").split(",").map((s) => s.trim()).filter(Boolean);
  const body = {
    name: (f.get("name") || "").trim(),
    category: f.get("category"),
    modality: f.get("modality"),
    equipment: (f.get("equipment") || "").trim() || "other",
    movement_pattern: (f.get("movement_pattern") || "").trim() || "other",
    primary_muscles: csv("primary_muscles"),
    secondary_muscles: csv("secondary_muscles"),
    related: csv("related"),
    compound: f.get("compound") === "on",
  };
  try {
    const r = await fetch("/api/exercises", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await r.json();
    if (!r.ok) { $("#aem-error").textContent = data.detail || `Error ${r.status}`; return; }
    $("#add-ex-modal").classList.add("hidden");
    // reload graph data and fly to the new node
    const g = await api("/graph");
    graph.setData(g);
    renderLegend(g);
    palItems = [];                       // palette picks up the new exercise
    graph.select(data.exercise.id);
    const warn = data.unresolved_related.length
      ? `  (couldn't match: ${data.unresolved_related.join(", ")})` : "";
    toast(`＋ ${data.exercise.name} added to the registry${warn}<br>
      <span style="color:var(--muted);font-size:11px">changed: ${data.files_changed.join(" · ")} — commit &amp; push to persist</span>`);
  } catch (err) {
    $("#aem-error").textContent = err.message;
  }
});
function toast(html) {
  const t = $("#pr-toast");
  t.innerHTML = html;
  t.classList.remove("hidden");
  clearTimeout(t._h);
  t._h = setTimeout(() => t.classList.add("hidden"), 6000);
}

// boot — support #graph, #vault, … deep links
window.addEventListener("hashchange", () => {
  const v = location.hash.slice(1);
  if (views.includes(v)) showView(v);
});
const boot = location.hash.slice(1);
if (boot === "graph/add") {           // deep link straight into the add-exercise form
  showView("graph");
  setTimeout(() => $("#add-ex-btn").click(), 400);
} else {
  showView(views.includes(boot) ? boot : "home");
}
