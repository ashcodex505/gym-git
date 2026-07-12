"""Technique-video resolution — with a hard no-hallucination guarantee.

Three tiers, best available wins:
1. Curated registry (data/registry/videos.json) — hand-verified URLs you
   add yourself. Ships empty on purpose: shipping model-remembered video
   IDs would risk exactly the hallucinated-URL failure this design bans.
2. YouTube Data API search (YOUTUBE_API_KEY set) — real results from the
   official API, cached to local/video-cache.json (local-only, gitignored).
3. Guaranteed-real fallback: a youtube.com/results deep link for
   "<exercise> technique form" — always valid, never fabricated.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

from . import paths
from .models import SCHEMA_VERSION
from .registry import Registry

CACHE_PATH = paths.repo_root() / "local" / "video-cache.json"


def _load_curated() -> dict[str, Any]:
    p = paths.videos_path()
    if p.exists():
        return json.loads(p.read_text()).get("videos", {})
    return {}


def _search_link(name: str) -> dict[str, Any]:
    q = urllib.parse.quote_plus(f"{name} technique form tutorial")
    return {"kind": "search", "title": f"Search YouTube: {name} technique",
            "url": f"https://www.youtube.com/results?search_query={q}", "verified": True}


def _yt_api_search(name: str, api_key: str) -> dict[str, Any] | None:
    cache: dict[str, Any] = {}
    if CACHE_PATH.exists():
        cache = json.loads(CACHE_PATH.read_text())
    if name in cache:
        return cache[name]
    params = urllib.parse.urlencode({
        "part": "snippet", "type": "video", "maxResults": 3,
        "q": f"{name} technique form", "videoEmbeddable": "true",
        "safeSearch": "strict", "key": api_key,
    })
    try:
        with urllib.request.urlopen(
                f"https://www.googleapis.com/youtube/v3/search?{params}", timeout=8) as r:
            data = json.loads(r.read())
        items = data.get("items", [])
        if not items:
            return None
        it = items[0]
        video = {"kind": "youtube-api",
                 "title": it["snippet"]["title"],
                 "channel": it["snippet"]["channelTitle"],
                 "url": f"https://www.youtube.com/watch?v={it['id']['videoId']}",
                 "verified": True}
        cache[name] = video
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(cache, indent=2))
        return video
    except Exception:
        return None


def resolve_video(exercise_id: str, registry: Registry, youtube_api_key: str = "") -> dict[str, Any]:
    ex = registry.by_id.get(exercise_id)
    if not ex:
        return _search_link(exercise_id.replace("-", " "))
    curated = _load_curated()
    if exercise_id in curated:
        v = dict(curated[exercise_id])
        v.setdefault("kind", "curated")
        v.setdefault("verified", True)
        return v
    if youtube_api_key:
        found = _yt_api_search(ex.name, youtube_api_key)
        if found:
            return found
    return _search_link(ex.name)


def init_curated_file() -> None:
    p = paths.videos_path()
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({
            "schema_version": SCHEMA_VERSION,
            "comment": "Hand-verified technique videos. Add entries like: "
                       "\"barbell-bench-press\": {\"title\": \"...\", \"channel\": \"...\", "
                       "\"url\": \"https://www.youtube.com/watch?v=...\"}. "
                       "Only add URLs you have actually opened and watched.",
            "videos": {},
        }, indent=2) + "\n")
