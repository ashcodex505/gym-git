"""Repository path layout, resolved relative to the repo root."""

from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    env = os.environ.get("IRONGRAPH_ROOT")
    if env:
        return Path(env).resolve()
    here = Path(__file__).resolve().parent.parent
    return here


def data_dir() -> Path:
    return repo_root() / "data"


def registry_path() -> Path:
    return data_dir() / "registry" / "exercises.json"


def custom_registry_path() -> Path:
    return data_dir() / "registry" / "custom-exercises.json"


def workouts_dir() -> Path:
    return data_dir() / "workouts"


def records_path() -> Path:
    return data_dir() / "personal-records.json"


def achievements_path() -> Path:
    return data_dir() / "achievements.json"


def profile_path() -> Path:
    return data_dir() / "profile.json"


def ingested_path() -> Path:
    return data_dir() / "ingested.json"


def graph_path() -> Path:
    return data_dir() / "graph.json"


def generated_dir() -> Path:
    return repo_root() / "generated"


def config_path() -> Path:
    return repo_root() / "config" / "irongraph.yml"


def videos_path() -> Path:
    return data_dir() / "registry" / "videos.json"
