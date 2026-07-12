"""Test fixtures: every test runs against an isolated copy of the repo
data layout in a tmp dir (IRONGRAPH_ROOT), so tests never touch real data."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture()
def iso_repo(tmp_path, monkeypatch):
    """Isolated repo root with the real registry + config copied in."""
    (tmp_path / "data" / "registry").mkdir(parents=True)
    (tmp_path / "config").mkdir()
    shutil.copy(REPO / "data" / "registry" / "exercises.json",
                tmp_path / "data" / "registry" / "exercises.json")
    shutil.copy(REPO / "config" / "irongraph.yml", tmp_path / "config" / "irongraph.yml")
    monkeypatch.setenv("IRONGRAPH_ROOT", str(tmp_path))
    # config is lru_cached per-process; bust it
    from irongraph import config
    config.load_config.cache_clear()
    yield tmp_path
    config.load_config.cache_clear()


@pytest.fixture()
def iso_git_repo(iso_repo):
    """Isolated repo that is also a git repository (for commit tests)."""
    env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=iso_repo, check=True, env=env)
    subprocess.run(["git", "-c", "user.name=Seed", "-c", "user.email=seed@example.com",
                    "commit", "-q", "--allow-empty", "-m", "init"], cwd=iso_repo, check=True, env=env)
    return iso_repo


FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text()
