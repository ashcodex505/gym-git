"""Daily-quest issue parser.

The quest template asks the user to check exercises and append performance
after a `::` separator:

    - [x] Barbell Bench Press :: 185 lb x 6, 185 x 5
    - [x] Treadmill :: 25 min, 2.3 mi, incline 3
    - [x] Plank :: 2m15s
    - [x] Pull-ups :: bw x 8; +25 lb x 5
    - [x] StairMaster :: 30 min level 8

Grammar is deliberately forgiving (phone keyboards, autocorrect):
* separators `::`, `—`, `|` all work
* `x`, `X`, `×`, `*` all mean "times"
* `185x6x3` = 3 sets of 185×6 ; `3x5 @ 185 lb` = 3 sets of 5 at 185
* set groups split on `;` or `,` for strength; cardio metrics of one
  effort are read from the whole string
* `// text` at the end of a line becomes a per-exercise note

Issue text is untrusted input from a public repository: nothing here is
ever passed to a shell, and all free text is length-clamped before it can
reach commit messages or generated markup.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import Modality, SetRecord, WorkoutEntry
from .registry import Registry

CHECKBOX_RE = re.compile(r"^\s*[-*]\s*\[(?P<mark>[xX ])\]\s*(?P<rest>.+?)\s*$")
META_RE = re.compile(r"\[(?P<meta>[^\]]*?:[^\]]*)\]")           # [muscle: chest; ...]
SEPARATORS = ("::", "—", " | ")
TIMES = r"[x×X*]"
NUM = r"\d+(?:\.\d+)?"

MAX_NOTE_LEN = 280
MAX_NAME_LEN = 80


@dataclass
class ParseProblem:
    line: str
    reason: str


@dataclass
class ParseResult:
    entries: list[WorkoutEntry] = field(default_factory=list)
    problems: list[ParseProblem] = field(default_factory=list)
    session_notes: str | None = None
    new_custom: list[str] = field(default_factory=list)   # exercise ids auto-created

    @property
    def ok(self) -> bool:
        return bool(self.entries) and not self.problems


def _clamp(s: str, n: int) -> str:
    s = s.replace("`", "'").strip()
    return s[:n]


def _split_name_perf(rest: str) -> tuple[str, str]:
    for sep in SEPARATORS:
        if sep in rest:
            name, perf = rest.split(sep, 1)
            return name.strip(), perf.strip()
    # fallback: "Name: 185 lb x 6" — split on first ':' followed by a digit-ish perf
    m = re.match(r"^(?P<name>[^:]{3,}?):\s*(?P<perf>[\dbB+].*)$", rest)
    if m:
        return m.group("name").strip(), m.group("perf").strip()
    return rest.strip(), ""


def _parse_duration_s(text: str) -> float | None:
    text = text.strip().lower()
    m = re.fullmatch(r"(\d+)\s*h(?:ours?)?\s*(\d+)?\s*m?(?:in)?", text)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2) or 0) * 60
    m = re.fullmatch(r"(\d+)\s*m(?:in(?:ute)?s?)?\s*(\d+)?\s*s?(?:ec)?", text)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2) or 0)
    m = re.fullmatch(r"(\d+):(\d{2})", text)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    m = re.fullmatch(r"(\d+)\s*s(?:ec(?:ond)?s?)?", text)
    if m:
        return int(m.group(1))
    return None


DUR_INLINE = re.compile(
    r"(?<![\d.])(?:(?P<h>\d+)\s*h(?:ours?|rs?)?\s*)?(?P<a>\d+)\s*"
    r"(?P<u>min(?:ute)?s?|m(?![i])|s(?:ec(?:ond)?s?)?)\b\s*(?:(?P<b>\d+)\s*s(?:ec)?s?\b)?",
    re.IGNORECASE,
)
DIST_INLINE = re.compile(rf"(?P<v>{NUM})\s*(?P<u>mi(?:les?)?|km|k\b|meters?|m\b)", re.IGNORECASE)
INCLINE_INLINE = re.compile(rf"(?:incline\s*(?:at\s*)?(?P<a>{NUM})\s*%?|(?P<b>{NUM})\s*%\s*incline)", re.IGNORECASE)
SPEED_INLINE = re.compile(rf"(?:speed\s*(?:at\s*)?(?P<a>{NUM})|(?P<b>{NUM})\s*mph)", re.IGNORECASE)
LEVEL_INLINE = re.compile(r"(?:level|lvl|resistance)\s*(?P<v>\d+)", re.IGNORECASE)
CAL_INLINE = re.compile(rf"(?P<v>{NUM})\s*(?:k?cal(?:orie)?s?)\b", re.IGNORECASE)
RPE_INLINE = re.compile(rf"@?\s*rpe\s*(?P<v>{NUM})", re.IGNORECASE)
CLOCK_INLINE = re.compile(r"\b(\d+):(\d{2})\b")
MSS_INLINE = re.compile(r"\b(\d+)\s*m\s*(\d{1,2})\s*s\b", re.IGNORECASE)


def _parse_cardio(perf: str) -> SetRecord | None:
    s = SetRecord()
    txt = perf
    m = MSS_INLINE.search(txt) or None
    if m:
        s.duration_s = int(m.group(1)) * 60 + int(m.group(2))
        txt = txt[: m.start()] + txt[m.end():]
    if s.duration_s is None:
        m = DUR_INLINE.search(txt)
        if m and m.group("u").lower().startswith(("m",)) or (m and m.group("h")):
            h = int(m.group("h") or 0)
            a = int(m.group("a"))
            b = int(m.group("b") or 0)
            unit = m.group("u").lower()
            if unit.startswith("s") and not m.group("h"):
                s.duration_s = a
            else:
                s.duration_s = h * 3600 + a * 60 + b
            txt = txt[: m.start()] + txt[m.end():]
    if s.duration_s is None:
        m = CLOCK_INLINE.search(txt)
        if m:
            s.duration_s = int(m.group(1)) * 60 + int(m.group(2))
            txt = txt[: m.start()] + txt[m.end():]
    # speed BEFORE distance so "3 mph" can never be misread as miles
    m = SPEED_INLINE.search(txt)
    if m:
        s.speed = float(m.group("a") or m.group("b"))
        txt = txt[: m.start()] + txt[m.end():]
    m = DIST_INLINE.search(txt)
    if m:
        s.distance = float(m.group("v"))
        u = m.group("u").lower()
        s.distance_unit = "mi" if u.startswith("mi") else ("km" if u.startswith("k") else "m")
        txt = txt[: m.start()] + txt[m.end():]
    m = INCLINE_INLINE.search(txt)
    if m:
        s.incline_pct = float(m.group("a") or m.group("b"))
        txt = txt[: m.start()] + txt[m.end():]
    m = LEVEL_INLINE.search(txt)
    if m:
        s.level = int(m.group("v"))
        txt = txt[: m.start()] + txt[m.end():]
    m = CAL_INLINE.search(txt)
    if m:
        s.calories = float(m.group("v"))
    if s.duration_s is None and s.distance is None and s.level is None and s.speed is None:
        return None
    # speed × duration with no explicit distance => derive it (settings-style
    # logging: "25 min, incline 12, speed 3" walks 1.25 mi)
    if s.distance is None and s.speed and s.duration_s:
        s.distance = round(s.speed * s.duration_s / 3600.0, 2)
        s.distance_unit = "mi"
        s.distance_derived = True
    return s


SET_RE = re.compile(
    rf"^(?:(?P<bw>bw|bodyweight)|(?P<plus>\+)?(?P<w>{NUM})\s*(?P<u>lbs?|kgs?|kg)?)\s*"
    rf"{TIMES}\s*(?P<r>\d+)(?:\s*{TIMES}\s*(?P<n>\d+)(?:\s*sets?)?)?$",
    re.IGNORECASE,
)
SETS_AT_RE = re.compile(
    rf"^(?P<n>\d+)\s*{TIMES}\s*(?P<r>\d+)\s*@\s*(?P<w>{NUM})\s*(?P<u>lbs?|kgs?|kg)?$",
    re.IGNORECASE,
)
REPS_ONLY_RE = re.compile(rf"^(?P<r>\d+)(?:\s*reps?)?(?:\s*{TIMES}\s*(?P<n>\d+)\s*sets?)?$", re.IGNORECASE)
WEIGHT_ONLY_UNIT_RE = re.compile(rf"^(?P<w>{NUM})\s*(?P<u>lbs?|kgs?|kg)$", re.IGNORECASE)


def _norm_unit(u: str | None, default: str) -> str:
    if not u:
        return default
    return "kg" if u.lower().startswith("kg") else "lb"


def _parse_strength_token(tok: str, default_unit: str) -> list[SetRecord] | None:
    tok = tok.strip().rstrip(".")
    if not tok:
        return []
    m = SETS_AT_RE.match(tok)
    if m:
        n, r = int(m.group("n")), int(m.group("r"))
        w = float(m.group("w"))
        u = _norm_unit(m.group("u"), default_unit)
        return [SetRecord(weight=w, unit=u, reps=r) for _ in range(min(n, 20))]
    m = SET_RE.match(tok)
    if m:
        r = int(m.group("r"))
        n = int(m.group("n") or 1)
        if m.group("bw"):
            base = SetRecord(reps=r)
        else:
            base = SetRecord(
                weight=float(m.group("w")), unit=_norm_unit(m.group("u"), default_unit),
                reps=r, added_weight=bool(m.group("plus")),
            )
        return [SetRecord(**{**base.__dict__}) for _ in range(min(n, 20))]
    m = REPS_ONLY_RE.match(tok)
    if m:
        n = int(m.group("n") or 1)
        return [SetRecord(reps=int(m.group("r"))) for _ in range(min(n, 20))]
    m = WEIGHT_ONLY_UNIT_RE.match(tok)
    if m:
        return [SetRecord(weight=float(m.group("w")), unit=_norm_unit(m.group("u"), default_unit))]
    return None


def _parse_strength(perf: str, default_unit: str) -> tuple[list[SetRecord], str | None]:
    """Returns (sets, error)."""
    rpe = None
    m = RPE_INLINE.search(perf)
    if m:
        rpe = float(m.group("v"))
        perf = perf[: m.start()] + perf[m.end():]
    sets: list[SetRecord] = []
    for tok in re.split(r"[;,]", perf):
        parsed = _parse_strength_token(tok, default_unit)
        if parsed is None:
            return [], f"could not understand `{_clamp(tok, 60)}`"
        sets.extend(parsed)
    if rpe and sets:
        sets[-1].rpe = rpe
    return sets, None


def _parse_time_perf(perf: str) -> tuple[list[SetRecord], str | None]:
    sets = []
    for tok in re.split(r"[;,]", perf):
        tok = tok.strip()
        if not tok:
            continue
        d = _parse_duration_s(tok)
        if d is None:
            card = _parse_cardio(tok)
            if card:
                sets.append(card)
                continue
            return [], f"could not read a duration from `{_clamp(tok, 60)}`"
        sets.append(SetRecord(duration_s=d))
    return sets, None


def _parse_meta(meta: str) -> dict[str, str]:
    out = {}
    for part in re.split(r"[;,]", meta):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip().lower()] = v.strip().lower()
    return out


class QuestParser:
    def __init__(self, registry: Registry, default_unit: str = "lb"):
        self.registry = registry
        self.default_unit = default_unit

    # markdown constructs that can never be a plain exercise line
    _PLAIN_SKIP = ("#", "|", ">", "`", "-", "*", "<", "!", "[", "_", "~")

    def parse(self, body: str) -> ParseResult:
        res = ParseResult()
        body = body.replace("\r\n", "\n")
        res.session_notes = self._extract_session_notes(body)
        in_fence = False
        for line in body.split("\n"):
            # fenced code blocks are documentation (syntax examples), never
            # loggable lines — the 2026-07-12 phantom "Landmine Press" bug
            if line.lstrip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            m = CHECKBOX_RE.match(line)
            if m:
                if m.group("mark") == " ":
                    continue
                self._parse_line(m.group("rest"), res)
                continue
            self._try_plain_line(line, res)
        if not res.entries and not res.problems:
            res.problems.append(ParseProblem("", "no exercises found — check `[x]` boxes (quest issue) or write `Exercise: numbers` lines (log form)"))
        return res

    def _try_plain_line(self, line: str, res: ParseResult) -> None:
        """Issue-form logging: bare `Exercise: numbers` lines (no checkbox).
        Only names already in the registry are accepted, so template prose,
        placeholders and section text can never be misparsed into workouts."""
        line = line.strip()
        if not line or line.startswith(self._PLAIN_SKIP):
            return
        rest = line
        note = None
        if "//" in rest:
            rest, note = rest.split("//", 1)
        name, perf = _split_name_perf(rest.strip())
        if not perf:
            return
        ex = self.registry.resolve(_clamp(name, MAX_NAME_LEN))
        if ex is None:
            return
        self._parse_line(rest.strip() + (f" // {note.strip()}" if note else ""), res)

    def _extract_session_notes(self, body: str) -> str | None:
        m = re.search(r"### .*Session notes.*?```(?:text)?\n(.*?)```", body, re.DOTALL | re.IGNORECASE)
        if m:
            notes = m.group(1).strip()
            if notes and not notes.lower().startswith("(optional"):
                return _clamp(notes, 1000)
        # issue-form style: "### Session notes" followed by plain text
        m = re.search(r"###[^\n]*Session notes[^\n]*\n+(.*?)(?=\n###|\Z)", body, re.DOTALL | re.IGNORECASE)
        if m:
            notes = m.group(1).strip()
            if notes and notes != "_No response_":
                return _clamp(notes, 1000)
        return None

    def _parse_line(self, rest: str, res: ParseResult) -> None:
        note = None
        if "//" in rest:
            rest, note = rest.split("//", 1)
            note = _clamp(note, MAX_NOTE_LEN)
        meta: dict[str, str] = {}
        mm = META_RE.search(rest)
        if mm:
            meta = _parse_meta(mm.group("meta"))
            rest = (rest[: mm.start()] + rest[mm.end():]).strip()
        name, perf = _split_name_perf(rest.strip())
        name = _clamp(name.strip(" -–—*_"), MAX_NAME_LEN)
        if not name:
            res.problems.append(ParseProblem(rest, "missing exercise name"))
            return
        if name.lower().startswith(("<exercise", "exercise name", "your exercise")):
            return  # untouched template placeholder
        ex = self.registry.resolve(name)
        if ex is None:
            modality = self._infer_modality(perf, meta)
            ex = self.registry.register_custom(
                name,
                modality=modality,
                category=meta.get("category", meta.get("muscle", "other")) if meta.get("category", meta.get("muscle", "other")) in
                    ("chest", "back", "shoulders", "biceps", "triceps", "legs", "glutes", "core", "cardio", "calisthenics", "mobility") else "other",
                primary_muscles=[meta["muscle"]] if "muscle" in meta else [],
                equipment=meta.get("equipment", "other"),
                movement_pattern=meta.get("pattern", meta.get("movement", "other")),
            )
            res.new_custom.append(ex.id)

        entry = WorkoutEntry(exercise_id=ex.id, exercise_name=ex.name, modality=ex.modality, notes=note)
        if not perf:
            # A checked box with no numbers is valid only for pure-completion logging.
            res.problems.append(ParseProblem(name, f"**{ex.name}** is checked but has no numbers after `::`"))
            return

        err: str | None
        if ex.modality in ("weight_reps", "reps", "weight_time"):
            entry.sets, err = _parse_strength(perf, self.default_unit)
            if err or not entry.sets:
                # strength-style failed; maybe it's timed ("Plank" logged under core)
                alt, err2 = _parse_time_perf(perf)
                if not err2 and alt:
                    entry.sets, err = alt, None
            if not err and ex.modality == "reps":
                # bodyweight movement logged with plain weight => treat as added weight
                for s in entry.sets:
                    if s.weight is not None:
                        s.added_weight = True
        elif ex.modality == "time":
            entry.sets, err = _parse_time_perf(perf)
            if (err or not entry.sets):
                card = _parse_cardio(perf)
                if card:
                    entry.sets, err = [card], None
        else:  # distance_time / cardio
            card = _parse_cardio(perf)
            if card is None:
                err = f"could not read cardio metrics from `{_clamp(perf, 60)}` — try `25 min, 2.3 mi`"
            else:
                entry.sets, err = [card], None

        if err:
            res.problems.append(ParseProblem(f"{ex.name} :: {perf}", f"**{ex.name}**: {err}"))
            return
        if not entry.sets:
            res.problems.append(ParseProblem(name, f"**{ex.name}**: no readable sets"))
            return
        res.entries.append(entry)

    @staticmethod
    def _infer_modality(perf: str, meta: dict[str, str]) -> Modality:
        if meta.get("modality") in ("weight_reps", "reps", "time", "distance_time", "weight_time"):
            return meta["modality"]  # type: ignore[return-value]
        p = perf.lower()
        if re.search(r"\bmi|km\b|meters", p):
            return "distance_time"
        if re.search(r"\bmin|sec\b|\d+:\d{2}|\d+m\d+s", p) and not re.search(rf"{NUM}\s*(lb|kg)", p):
            return "time"
        if re.search(rf"(lb|kg|{NUM}\s*[x×])", p):
            return "weight_reps"
        return "reps"
