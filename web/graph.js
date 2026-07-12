// IronGraph — canvas knowledge-graph renderer.
// Interaction model adapted from Multimodal Search's graph mode:
// dirty-flag rAF loop, viewport pan/zoom with clamps, minimap teleport,
// cluster legend fly-tos, pinned node + ←/→ neighbor hopping.

const CLUSTER_COLORS = {
  chest: "#f78166", back: "#58a6ff", shoulders: "#e3b341", biceps: "#bc8cff",
  triceps: "#d2a8ff", legs: "#3fb950", glutes: "#56d364", core: "#f2cc60",
  cardio: "#ff7b72", calisthenics: "#79c0ff", mobility: "#a5d6ff", other: "#8b949e",
};
const EDGE_COLORS = {
  variation_of: "rgba(247,129,102,.5)", similar_to: "rgba(139,148,169,.35)",
  progresses_to: "rgba(63,185,80,.5)", regresses_to: "rgba(88,166,255,.35)",
  complementary_to: "rgba(227,179,65,.4)", alternative_to: "rgba(188,140,255,.4)",
  same_movement_pattern: "rgba(139,148,169,.16)",
};
const SCALE_MIN = 0.18, SCALE_MAX = 14;

export class ExerciseGraph {
  constructor(canvas, minimap, opts = {}) {
    this.canvas = canvas;
    this.minimap = minimap;
    this.ctx = canvas.getContext("2d");
    this.mctx = minimap.getContext("2d");
    this.onSelect = opts.onSelect || (() => {});
    this.nodes = []; this.edges = []; this.clusters = [];
    this.byId = new Map(); this.neighbors = new Map();
    this.vp = { x: 0, y: 0, scale: 1 };       // world coords of viewport center
    this.dirty = true;
    this.hover = null; this.pinned = null;
    this.filters = { performed: null, prs: false, recommended: false, category: null, q: "" };
    this.anim = null;
    this._bind();
    const loop = () => { if (this.dirty) { this.dirty = false; this._draw(); } requestAnimationFrame(loop); };
    requestAnimationFrame(loop);
    new ResizeObserver(() => { this._resize(); }).observe(canvas.parentElement);
    this._resize();
  }

  setData(g) {
    this.nodes = g.nodes; this.edges = g.edges; this.clusters = g.clusters || [];
    this.byId = new Map(g.nodes.map(n => [n.id, n]));
    this.neighbors = new Map(g.nodes.map(n => [n.id, []]));
    for (const e of g.edges) {
      this.neighbors.get(e.source)?.push({ id: e.target, type: e.type });
      this.neighbors.get(e.target)?.push({ id: e.source, type: e.type });
    }
    const maxPerf = Math.max(1, ...g.nodes.map(n => n.times_performed));
    for (const n of g.nodes) {
      n.r = 5 + 11 * Math.sqrt(n.times_performed / maxPerf);   // size = frequency
      n.color = CLUSTER_COLORS[n.category] || CLUSTER_COLORS.other;
    }
    this.fit(); this.dirty = true;
  }

  // ---------- coordinate transforms ----------
  _resize() {
    const dpr = window.devicePixelRatio || 1;
    const { clientWidth: w, clientHeight: h } = this.canvas.parentElement;
    this.canvas.width = w * dpr; this.canvas.height = h * dpr;
    this.W = w; this.H = h; this.dpr = dpr; this.dirty = true;
  }
  toScreen(x, y) {
    return [ (x - this.vp.x) * this.vp.scale + this.W / 2,
             (y - this.vp.y) * this.vp.scale + this.H / 2 ];
  }
  toWorld(sx, sy) {
    return [ (sx - this.W / 2) / this.vp.scale + this.vp.x,
             (sy - this.H / 2) / this.vp.scale + this.vp.y ];
  }

  fit() {
    if (!this.nodes.length) return;
    const xs = this.nodes.map(n => n.x), ys = this.nodes.map(n => n.y);
    const minx = Math.min(...xs), maxx = Math.max(...xs);
    const miny = Math.min(...ys), maxy = Math.max(...ys);
    this.vp.x = (minx + maxx) / 2; this.vp.y = (miny + maxy) / 2;
    this.vp.scale = Math.min(this.W / (maxx - minx + 160), this.H / (maxy - miny + 160));
    this.dirty = true;
  }

  zoom(f, sx, sy) {
    const [wx, wy] = this.toWorld(sx ?? this.W / 2, sy ?? this.H / 2);
    const s = Math.min(SCALE_MAX, Math.max(SCALE_MIN, this.vp.scale * f));
    const k = s / this.vp.scale;
    this.vp.x = wx - (wx - this.vp.x) / k;
    this.vp.y = wy - (wy - this.vp.y) / k;
    this.vp.scale = s; this.dirty = true;
  }

  flyTo(x, y, scale = 2.4) {
    if (this.anim) cancelAnimationFrame(this.anim);
    const from = { ...this.vp }, t0 = performance.now(), dur = 480;
    const step = (t) => {
      const p = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - p, 3);
      this.vp.x = from.x + (x - from.x) * e;
      this.vp.y = from.y + (y - from.y) * e;
      this.vp.scale = from.scale + (scale - from.scale) * e;
      this.dirty = true;
      if (p < 1) this.anim = requestAnimationFrame(step);
    };
    this.anim = requestAnimationFrame(step);
  }

  // ---------- filtering ----------
  matches(n) {
    const f = this.filters;
    if (f.performed === true && !n.performed) return false;
    if (f.performed === false && n.performed) return false;
    if (f.prs && !n.recent_pr) return false;
    if (f.recommended && !n.recommended) return false;
    if (f.category && n.category !== f.category) return false;
    if (f.q && !n.name.toLowerCase().includes(f.q)) return false;
    return true;
  }
  hasFilter() {
    const f = this.filters;
    return f.performed !== null || f.prs || f.recommended || f.category || f.q;
  }
  setFilter(patch) { Object.assign(this.filters, patch); this.dirty = true; }

  select(id, fly = true) {
    const n = this.byId.get(id);
    if (!n) return;
    this.pinned = n;
    if (fly) this.flyTo(n.x, n.y, Math.max(this.vp.scale, 2.2));
    this.dirty = true;
    this.onSelect(n);
  }
  clearSelection() { this.pinned = null; this.dirty = true; }

  hopNeighbor(dir) {
    if (!this.pinned) return;
    const ns = (this.neighbors.get(this.pinned.id) || []).map(x => this.byId.get(x.id)).filter(Boolean);
    if (!ns.length) return;
    if (this._hopIdx === undefined || this._hopList !== this.pinned.id) { this._hopIdx = -1; this._hopList = this.pinned.id; }
    // hop simply cycles neighbors; remember origin id so index resets on new pin
    this._hopIdx = (this._hopIdx + dir + ns.length) % ns.length;
    this.select(ns[this._hopIdx].id);
    this._hopList = ns[this._hopIdx].id === this.pinned.id ? this._hopList : this.pinned.id;
  }

  nodeAt(sx, sy) {
    const [wx, wy] = this.toWorld(sx, sy);
    let best = null, bestD = Infinity;
    for (const n of this.nodes) {
      const d = Math.hypot(n.x - wx, n.y - wy);
      const hitR = (n.r + 6) / Math.min(this.vp.scale, 1) * (this.vp.scale < 1 ? 1 : 1 / 1) + n.r;
      if (d < Math.max(n.r + 4, 10 / this.vp.scale) && d < bestD) { best = n; bestD = d; }
    }
    return best;
  }

  // ---------- drawing ----------
  _draw() {
    const ctx = this.ctx, dpr = this.dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, this.W, this.H);
    const filterOn = this.hasFilter();
    const focus = this.pinned || this.hover;
    const focusSet = focus ? new Set([focus.id, ...(this.neighbors.get(focus.id) || []).map(x => x.id)]) : null;

    // edges
    for (const e of this.edges) {
      const a = this.byId.get(e.source), b = this.byId.get(e.target);
      if (!a || !b) continue;
      const [ax, ay] = this.toScreen(a.x, a.y), [bx, by] = this.toScreen(b.x, b.y);
      if (Math.max(ax, bx) < -50 || Math.min(ax, bx) > this.W + 50 ||
          Math.max(ay, by) < -50 || Math.min(ay, by) > this.H + 50) continue;
      let stroke = EDGE_COLORS[e.type] || "rgba(139,148,169,.2)";
      let lw = 1;
      if (focusSet) {
        if (e.source === focus.id || e.target === focus.id) { stroke = "rgba(227,179,65,.85)"; lw = 1.6; }
        else stroke = "rgba(139,148,169,.07)";
      } else if (filterOn && (!this.matches(a) || !this.matches(b))) {
        stroke = "rgba(139,148,169,.05)";
      }
      ctx.strokeStyle = stroke; ctx.lineWidth = lw;
      ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke();
    }

    // cluster labels (only when zoomed out-ish)
    if (this.vp.scale < 1.8) {
      ctx.font = `700 ${Math.max(11, 13 * Math.min(this.vp.scale, 1))}px ui-monospace, monospace`;
      ctx.textAlign = "center";
      for (const c of this.clusters) {
        const [sx, sy] = this.toScreen(c.cx, c.cy);
        ctx.fillStyle = "rgba(139,148,169,.5)";
        ctx.fillText(c.id.toUpperCase(), sx, sy - 60 * this.vp.scale - 8);
      }
    }

    // nodes
    const t = performance.now() / 1000;
    let needsPulse = false;
    for (const n of this.nodes) {
      const [sx, sy] = this.toScreen(n.x, n.y);
      if (sx < -40 || sx > this.W + 40 || sy < -40 || sy > this.H + 40) continue;
      const dim = (focusSet && !focusSet.has(n.id)) || (filterOn && !this.matches(n));
      const r = Math.max(2.5, n.r * Math.min(Math.sqrt(this.vp.scale), 1.6));
      ctx.globalAlpha = dim ? 0.13 : 1;

      // PR glow — subtle breathing halo
      if (n.recent_pr && !dim) {
        needsPulse = true;
        const pulse = 0.5 + 0.5 * Math.sin(t * 2.2);
        ctx.beginPath(); ctx.arc(sx, sy, r + 5 + pulse * 3, 0, 7);
        ctx.fillStyle = "rgba(63,185,80," + (0.10 + 0.10 * pulse) + ")"; ctx.fill();
        ctx.beginPath(); ctx.arc(sx, sy, r + 2.5, 0, 7);
        ctx.strokeStyle = "rgba(63,185,80,.8)"; ctx.lineWidth = 1.4; ctx.stroke();
      }
      if (n.recommended && !dim) {
        ctx.beginPath(); ctx.arc(sx, sy, r + 3, 0, 7);
        ctx.setLineDash([3, 3]); ctx.strokeStyle = "rgba(227,179,65,.8)";
        ctx.lineWidth = 1.2; ctx.stroke(); ctx.setLineDash([]);
      }
      ctx.beginPath(); ctx.arc(sx, sy, r, 0, 7);
      if (n.performed) { ctx.fillStyle = n.color; ctx.fill(); }
      else { // never performed: hollow outline — undiscovered territory
        ctx.fillStyle = "rgba(13,17,24,.9)"; ctx.fill();
        ctx.strokeStyle = n.color; ctx.lineWidth = 1.3; ctx.globalAlpha = dim ? 0.13 : 0.65; ctx.stroke();
        ctx.globalAlpha = dim ? 0.13 : 1;
      }
      if (n.compound && n.performed && !dim) {   // inner core dot marks compounds
        ctx.beginPath(); ctx.arc(sx, sy, Math.max(1.2, r * 0.32), 0, 7);
        ctx.fillStyle = "rgba(10,13,18,.85)"; ctx.fill();
      }
      if (this.pinned === n) {
        ctx.beginPath(); ctx.arc(sx, sy, r + 4.5, 0, 7);
        ctx.strokeStyle = "#f78166"; ctx.lineWidth = 2; ctx.stroke();
      }
      // labels
      const showLabel = this.vp.scale > 1.15 || n === this.hover || n === this.pinned ||
        (focusSet && focusSet.has(n.id)) || (this.vp.scale > 0.8 && n.times_performed > 0);
      if (showLabel && !dim) {
        ctx.font = (n === this.pinned || n === this.hover ? "700 " : "") + "11px -apple-system, sans-serif";
        ctx.textAlign = "center";
        ctx.fillStyle = n === this.pinned ? "#ffb199" : "rgba(230,237,243,.85)";
        ctx.fillText(n.name, sx, sy + r + 13);
      }
      ctx.globalAlpha = 1;
    }
    this._drawMinimap();
    if (needsPulse) this.dirty = true;  // keep animating while a PR halo is visible
  }

  _drawMinimap() {
    const m = this.mctx, W = this.minimap.width, H = this.minimap.height;
    m.clearRect(0, 0, W, H);
    if (!this.nodes.length) return;
    const xs = this.nodes.map(n => n.x), ys = this.nodes.map(n => n.y);
    const minx = Math.min(...xs) - 60, maxx = Math.max(...xs) + 60;
    const miny = Math.min(...ys) - 60, maxy = Math.max(...ys) + 60;
    const s = Math.min(W / (maxx - minx), H / (maxy - miny));
    this._mm = { minx, miny, s, ox: (W - (maxx - minx) * s) / 2, oy: (H - (maxy - miny) * s) / 2 };
    for (const n of this.nodes) {
      m.beginPath();
      m.arc(this._mm.ox + (n.x - minx) * s, this._mm.oy + (n.y - miny) * s, Math.max(1, n.r * s * 0.5), 0, 7);
      m.fillStyle = n.performed ? n.color : "rgba(139,148,169,.4)";
      m.fill();
    }
    // viewport rectangle
    const [wx0, wy0] = this.toWorld(0, 0), [wx1, wy1] = this.toWorld(this.W, this.H);
    m.strokeStyle = "rgba(247,129,102,.9)"; m.lineWidth = 1;
    m.strokeRect(this._mm.ox + (wx0 - minx) * s, this._mm.oy + (wy0 - miny) * s,
                 (wx1 - wx0) * s, (wy1 - wy0) * s);
  }

  minimapJump(mx, my) {
    if (!this._mm) return;
    this.vp.x = this._mm.minx + (mx - this._mm.ox) / this._mm.s;
    this.vp.y = this._mm.miny + (my - this._mm.oy) / this._mm.s;
    this.dirty = true;
  }

  // ---------- events ----------
  _bind() {
    const c = this.canvas;
    let drag = null, moved = false;
    c.addEventListener("pointerdown", (e) => {
      drag = { x: e.clientX, y: e.clientY, vx: this.vp.x, vy: this.vp.y };
      moved = false; c.classList.add("dragging"); c.setPointerCapture(e.pointerId);
    });
    c.addEventListener("pointermove", (e) => {
      const rect = c.getBoundingClientRect();
      if (drag) {
        const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
        if (Math.abs(dx) + Math.abs(dy) > 3) moved = true;
        this.vp.x = drag.vx - dx / this.vp.scale;
        this.vp.y = drag.vy - dy / this.vp.scale;
        this.dirty = true;
      } else {
        const n = this.nodeAt(e.clientX - rect.left, e.clientY - rect.top);
        if (n !== this.hover) { this.hover = n; c.style.cursor = n ? "pointer" : "grab"; this.dirty = true; }
      }
    });
    c.addEventListener("pointerup", (e) => {
      c.classList.remove("dragging");
      const rect = c.getBoundingClientRect();
      if (!moved) {
        const n = this.nodeAt(e.clientX - rect.left, e.clientY - rect.top);
        if (n) this.select(n.id, false);
        else this.clearSelection();
      }
      drag = null;
    });
    c.addEventListener("wheel", (e) => {
      e.preventDefault();
      const rect = c.getBoundingClientRect();
      if (e.ctrlKey || e.metaKey || Math.abs(e.deltaY) > Math.abs(e.deltaX)) {
        this.zoom(Math.exp(-e.deltaY * 0.0016), e.clientX - rect.left, e.clientY - rect.top);
      } else {
        this.vp.x += e.deltaX / this.vp.scale; this.dirty = true;
      }
    }, { passive: false });

    const mm = this.minimap;
    let mmDrag = false;
    const mmPos = (e) => { const r = mm.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
    mm.addEventListener("pointerdown", (e) => { mmDrag = true; this.minimapJump(...mmPos(e)); mm.setPointerCapture(e.pointerId); });
    mm.addEventListener("pointermove", (e) => { if (mmDrag) this.minimapJump(...mmPos(e)); });
    mm.addEventListener("pointerup", () => { mmDrag = false; });
  }
}

export { CLUSTER_COLORS };
