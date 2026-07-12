"""README SVG generation — pure Python, zero chart dependencies.

Design system: GitHub-dark cards (#0d1117 bg, #30363d hairlines) with a
single ember accent (#f78166) and a green PR accent (#3fb950). Monospace
metrics, restrained glow on PR markers. Renders correctly in GitHub's
sanitized <img> context (no scripts, no external fonts, no foreignObject).
"""

from __future__ import annotations

import html
from datetime import date, timedelta

from . import paths

BG = "#0d1117"
CARD = "#161b22"
LINE = "#30363d"
FG = "#e6edf3"
MUTED = "#8b949e"
ACCENT = "#f78166"     # ember
GREEN = "#3fb950"
GOLD = "#e3b341"
MONO = "ui-monospace,SFMono-Regular,Menlo,monospace"
SANS = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"

HEAT = ["#161b22", "#1c3a28", "#1f6f3a", "#2ea043", "#56d364"]


def _esc(s: str) -> str:
    return html.escape(str(s), quote=True)


def _svg(w: int, h: int, inner: str, title: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" role="img" aria-label="{_esc(title)}">\n'
        f'<rect width="{w}" height="{h}" rx="10" fill="{BG}" stroke="{LINE}"/>\n'
        f"{inner}\n</svg>\n"
    )


def _header(title: str, sub: str, w: int) -> str:
    return (
        f'<text x="24" y="38" font-family="{SANS}" font-size="17" font-weight="700" fill="{FG}">{_esc(title)}</text>'
        f'<text x="{w - 24}" y="38" text-anchor="end" font-family="{MONO}" font-size="11" fill="{MUTED}">{_esc(sub)}</text>'
        f'<line x1="24" y1="52" x2="{w - 24}" y2="52" stroke="{LINE}"/>'
    )


# ---------------------------------------------------------------- overview
def strength_overview(stats: dict, w: int = 840) -> str:
    tiles = [
        ("WORKOUTS", stats.get("total_workouts", 0), ACCENT),
        ("CURRENT STREAK", f"{stats.get('activity_current', 0)}d", GOLD),
        ("WEEKLY STREAK", f"{stats.get('weekly_current', 0)}w", GOLD),
        ("TOTAL PRs", stats.get("total_prs", 0), GREEN),
        ("EXERCISES", stats.get("exercises_tried", 0), FG),
        ("LEVEL", f"{stats.get('level', 1)} · {stats.get('title', 'Novice')}", ACCENT),
    ]
    h = 150
    tw = (w - 48) / len(tiles)
    parts = [_header("IronGraph — Strength Overview", stats.get("as_of", ""), w)]
    for i, (label, value, color) in enumerate(tiles):
        x = 24 + i * tw
        parts.append(f'<text x="{x + tw / 2:.0f}" y="100" text-anchor="middle" font-family="{MONO}" '
                     f'font-size="{20 if len(str(value)) < 10 else 13}" font-weight="700" fill="{color}">{_esc(value)}</text>')
        parts.append(f'<text x="{x + tw / 2:.0f}" y="124" text-anchor="middle" font-family="{SANS}" '
                     f'font-size="10" letter-spacing="1.2" fill="{MUTED}">{_esc(label)}</text>')
        if i:
            parts.append(f'<line x1="{x:.0f}" y1="72" x2="{x:.0f}" y2="132" stroke="{LINE}"/>')
    return _svg(w, h, "".join(parts), "IronGraph strength overview")


# ---------------------------------------------------------------- heatmap
def workout_heatmap(day_counts: dict[str, int], weeks: int = 26, w: int = 840, end: date | None = None) -> str:
    """GitHub-style heatmap of the last `weeks` weeks. Color = number of
    exercises logged that day (activity, not 'value' — a cardio day is not
    dimmer than a lifting day)."""
    end = end or date.today()
    # align to end of current week (Saturday-start columns like GitHub: Sun rows)
    cell, gap = 13, 3
    top = 74
    left = 52
    start = end - timedelta(days=end.weekday() + 1) - timedelta(weeks=weeks - 1)  # a Sunday
    parts = [_header("Training Activity", f"last {weeks} weeks", w)]
    months_drawn: set[str] = set()
    for wk in range(weeks + 1):
        for dow in range(7):
            d = start + timedelta(weeks=wk, days=dow)
            if d > end:
                continue
            n = day_counts.get(d.isoformat(), 0)
            lvl = 0 if n == 0 else 1 if n <= 2 else 2 if n <= 4 else 3 if n <= 6 else 4
            x = left + wk * (cell + gap)
            y = top + dow * (cell + gap)
            parts.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="3" '
                         f'fill="{HEAT[lvl]}" stroke="{LINE}" stroke-width="0.5">'
                         f'<title>{d.isoformat()}: {n} exercise{"s" if n != 1 else ""}</title></rect>')
            mk = d.strftime("%Y-%m")
            if d.day <= 7 and dow == 0 and mk not in months_drawn:
                months_drawn.add(mk)
                parts.append(f'<text x="{x}" y="{top - 8}" font-family="{MONO}" font-size="10" '
                             f'fill="{MUTED}">{d.strftime("%b")}</text>')
    for i, lbl in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        parts.append(f'<text x="{left - 8}" y="{top + i * (cell + gap) + 10}" text-anchor="end" '
                     f'font-family="{MONO}" font-size="9" fill="{MUTED}">{lbl}</text>')
    ly = top + 7 * (cell + gap) + 16
    parts.append(f'<text x="{left}" y="{ly + 10}" font-family="{MONO}" font-size="9" fill="{MUTED}">less</text>')
    for i, c in enumerate(HEAT):
        parts.append(f'<rect x="{left + 34 + i * 17}" y="{ly}" width="13" height="13" rx="3" fill="{c}" stroke="{LINE}" stroke-width="0.5"/>')
    parts.append(f'<text x="{left + 34 + 5 * 17 + 6}" y="{ly + 10}" font-family="{MONO}" font-size="9" fill="{MUTED}">more</text>')
    h = ly + 34
    return _svg(w, h, "".join(parts), "Training activity heatmap")


# ---------------------------------------------------------------- PR card
def personal_records_card(records: list[dict], w: int = 840) -> str:
    rows = records[:8]
    h = 84 + max(len(rows), 1) * 42 + 16
    parts = [_header("Personal Records", "current bests", w)]
    if not rows:
        parts.append(f'<text x="24" y="100" font-family="{SANS}" font-size="13" fill="{MUTED}">No records yet — the forge is cold, for now.</text>')
    for i, r in enumerate(rows):
        y = 84 + i * 42
        parts.append(f'<rect x="24" y="{y}" width="{w - 48}" height="34" rx="6" fill="{CARD}" stroke="{LINE}"/>')
        parts.append(f'<text x="40" y="{y + 22}" font-family="{SANS}" font-size="13" font-weight="600" fill="{FG}">{_esc(r["name"])}</text>')
        parts.append(f'<text x="{w - 200}" y="{y + 22}" text-anchor="end" font-family="{MONO}" font-size="13" '
                     f'font-weight="700" fill="{GREEN}">{_esc(r["display"])}</text>')
        extra = r.get("e1rm") or ""
        parts.append(f'<text x="{w - 40}" y="{y + 22}" text-anchor="end" font-family="{MONO}" font-size="11" '
                     f'fill="{MUTED}">{_esc(extra)}</text>')
    return _svg(w, h, "".join(parts), "Current personal records")


# ---------------------------------------------------------------- muscles
def muscle_distribution(dist: dict[str, int], w: int = 840) -> str:
    items = list(dist.items())[:10]
    h = 84 + max(len(items), 1) * 30 + 16
    total = sum(dist.values()) or 1
    maxv = max((v for _, v in items), default=1)
    parts = [_header("Muscle Group Distribution", f"{total} logged exercise entries", w)]
    bar_x, bar_w = 170, w - 170 - 110
    for i, (muscle, n) in enumerate(items):
        y = 84 + i * 30
        frac = n / maxv
        parts.append(f'<text x="{bar_x - 12}" y="{y + 13}" text-anchor="end" font-family="{SANS}" '
                     f'font-size="12" fill="{FG}">{_esc(muscle.replace("-", " "))}</text>')
        parts.append(f'<rect x="{bar_x}" y="{y}" width="{bar_w}" height="18" rx="4" fill="{CARD}"/>')
        parts.append(f'<rect x="{bar_x}" y="{y}" width="{max(bar_w * frac, 3):.0f}" height="18" rx="4" fill="{ACCENT}" opacity="{0.45 + 0.55 * frac:.2f}"/>')
        parts.append(f'<text x="{bar_x + bar_w + 12}" y="{y + 13}" font-family="{MONO}" font-size="11" '
                     f'fill="{MUTED}">{n} · {100 * n / total:.0f}%</text>')
    if not items:
        parts.append(f'<text x="24" y="100" font-family="{SANS}" font-size="13" fill="{MUTED}">No training data yet.</text>')
    return _svg(w, h, "".join(parts), "Muscle group distribution")


# ------------------------------------------------------------- progression
def exercise_progression(name: str, history: list[dict], w: int = 840) -> str | None:
    """Line chart of best set weight (or reps/duration/distance) over time,
    with PR moments marked. Returns None when < 2 usable points."""
    for key, unit, fmt in (("weight_lb", "lb", "{:g}"), ("e1rm_lb", "lb e1RM", "{:g}"),
                           ("reps", "reps", "{:g}"), ("distance_mi", "mi", "{:.1f}"),
                           ("duration_s", "min", None)):
        pts = [(h["date"], h[key]) for h in history if key in h]
        if len(pts) >= 2:
            break
    else:
        return None
    if key == "duration_s":
        pts = [(d, v / 60.0) for d, v in pts]
        fmt = "{:.0f}"
    h_img = 300
    px0, px1, py0, py1 = 64, w - 32, 84, h_img - 48
    xs = list(range(len(pts)))
    vals = [v for _, v in pts]
    vmin, vmax = min(vals), max(vals)
    if vmax == vmin:
        vmax += 1
    pad = (vmax - vmin) * 0.15
    vmin, vmax = vmin - pad, vmax + pad

    def X(i: int) -> float:
        return px0 + (px1 - px0) * (i / max(len(pts) - 1, 1))

    def Y(v: float) -> float:
        return py1 - (py1 - py0) * ((v - vmin) / (vmax - vmin))

    parts = [_header(name, f"best {unit} per session · {len(pts)} sessions", w)]
    grid_fmt = "{:.0f}" if (vmax - vmin) >= 8 else "{:.1f}"
    for gy in range(4):
        v = vmin + (vmax - vmin) * gy / 3
        y = Y(v)
        parts.append(f'<line x1="{px0}" y1="{y:.1f}" x2="{px1}" y2="{y:.1f}" stroke="{LINE}" stroke-dasharray="2,4"/>')
        parts.append(f'<text x="{px0 - 8}" y="{y + 4:.1f}" text-anchor="end" font-family="{MONO}" font-size="10" fill="{MUTED}">{grid_fmt.format(v)}</text>')
    # area + line
    line_pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in zip(xs, vals))
    parts.append(f'<polyline points="{line_pts}" fill="none" stroke="{ACCENT}" stroke-width="2.2" stroke-linejoin="round"/>')
    area = f"{px0},{py1} " + line_pts + f" {X(len(pts) - 1):.1f},{py1}"
    parts.append(f'<polygon points="{area}" fill="{ACCENT}" opacity="0.08"/>')
    running_max = -1e18
    for i, (d, v) in enumerate(pts):
        is_pr = v > running_max
        running_max = max(running_max, v)
        cx, cy = X(i), Y(v)
        if is_pr and i > 0:
            parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="7" fill="{GREEN}" opacity="0.25"/>')
            parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="3.4" fill="{GREEN}"><title>{d}: {(fmt or "{:g}").format(v)} {unit} (PR)</title></circle>')
        else:
            parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="2.8" fill="{ACCENT}"><title>{d}: {(fmt or "{:g}").format(v)} {unit}</title></circle>')
    # first/last date labels
    parts.append(f'<text x="{px0}" y="{h_img - 20}" font-family="{MONO}" font-size="10" fill="{MUTED}">{pts[0][0]}</text>')
    parts.append(f'<text x="{px1}" y="{h_img - 20}" text-anchor="end" font-family="{MONO}" font-size="10" fill="{MUTED}">{pts[-1][0]}</text>')
    parts.append(f'<circle cx="{px1 - 150}" cy="{h_img - 24}" r="3.4" fill="{GREEN}"/>')
    parts.append(f'<text x="{px1 - 140}" y="{h_img - 20}" font-family="{MONO}" font-size="10" fill="{MUTED}">= PR session</text>')
    return _svg(w, h_img, "".join(parts), f"{name} progression")


# -------------------------------------------------------------- achievements
def achievements_card(unlocked: list[dict], total: int, w: int = 840) -> str:
    per_row = 2
    rows = (len(unlocked) + per_row - 1) // per_row if unlocked else 1
    h = 84 + rows * 52 + 16
    parts = [_header("Achievements", f"{len(unlocked)} / {total} unlocked", w)]
    if not unlocked:
        parts.append(f'<text x="24" y="104" font-family="{SANS}" font-size="13" fill="{MUTED}">None yet — the first workout unlocks the first badge.</text>')
    cw = (w - 48 - 12) / per_row
    for i, a in enumerate(unlocked):
        x = 24 + (i % per_row) * (cw + 12)
        y = 84 + (i // per_row) * 52
        parts.append(f'<rect x="{x:.0f}" y="{y}" width="{cw:.0f}" height="44" rx="6" fill="{CARD}" stroke="{LINE}"/>')
        parts.append(f'<text x="{x + 14:.0f}" y="{y + 28}" font-size="18">{a["emoji"]}</text>')
        parts.append(f'<text x="{x + 44:.0f}" y="{y + 19}" font-family="{SANS}" font-size="12" font-weight="700" fill="{GOLD}">{_esc(a["name"])}</text>')
        parts.append(f'<text x="{x + 44:.0f}" y="{y + 34}" font-family="{SANS}" font-size="10" fill="{MUTED}">{_esc(a["description"][:70])} · {a["date"]}</text>')
    return _svg(w, h, "".join(parts), "Achievements")


def write(name: str, svg: str | None, subdir: str = "") -> None:
    if svg is None:
        return
    d = paths.generated_dir() / subdir if subdir else paths.generated_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(svg)
