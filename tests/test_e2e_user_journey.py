"""User-journey E2E: replicates the owner's exact environment.

Differences from test_e2e_dashboard.py (which uses seeded data and hash
deep links): this suite runs against EMPTY data (a fresh repo, exactly
like the real one before any workout), navigates by clicking the sidebar
like a human, and runs in BOTH Chromium and WebKit (Safari engine).
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect, sync_playwright  # noqa: E402

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    """Empty-state repo (registry + config only, zero workouts) + live server."""
    root = tmp_path_factory.mktemp("journey-repo")
    (root / "data" / "registry").mkdir(parents=True)
    (root / "config").mkdir()
    shutil.copy(REPO / "data/registry/exercises.json", root / "data/registry/exercises.json")
    shutil.copy(REPO / "config/irongraph.yml", root / "config/irongraph.yml")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen(
        [sys.executable, "-m", "irongraph.server"],
        env={**os.environ, "IRONGRAPH_ROOT": str(root), "IRONGRAPH_PORT": str(port)},
        cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                break
        except OSError:
            time.sleep(0.2)
    else:
        proc.kill()
        pytest.fail("server did not start")
    yield {"url": f"http://127.0.0.1:{port}", "root": root}
    proc.terminate()


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_full_add_exercise_journey(server, engine):
    with sync_playwright() as p:
        browser = getattr(p, engine).launch()
        page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        # 1. land on home (empty state must render, not crash)
        page.goto(server["url"])
        expect(page.locator("h1")).to_have_text("Command Center")
        expect(page.locator("#view-home")).to_contain_text("No PRs yet")

        # 2. click "Exercise Graph" in the sidebar (human path, no deep link)
        page.click(".nav-item[data-view=graph]")
        page.wait_for_selector("#add-ex-btn", state="visible")

        # 3. the version beacon proves the fresh script is running
        ver = page.evaluate("() => document.querySelector('script[src^=\"app.js\"]').src")
        assert "v=3" in ver

        # 4. click ＋ add exercise → modal MUST appear
        page.click("#add-ex-btn")
        expect(page.locator("#add-ex-modal")).to_be_visible()
        expect(page.locator("#add-ex-form [name=name]")).to_be_focused()

        # 5. fill + submit (unique name per engine — the server is shared)
        ex_name = f"Sled Push {engine}"
        page.fill("#add-ex-form [name=name]", ex_name)
        page.select_option("#add-ex-form [name=category]", "legs")
        page.select_option("#add-ex-form [name=modality]", "weight_time")
        page.fill("#add-ex-form [name=equipment]", "sled")
        page.fill("#add-ex-form [name=primary_muscles]", "quads, glutes")
        page.fill("#add-ex-form [name=related]", "Leg Press")
        page.click("#add-ex-form button.primary")
        expect(page.locator("#add-ex-modal")).to_be_hidden()
        expect(page.locator("#pr-toast")).to_contain_text(f"{ex_name} added")
        expect(page.locator(".dp-name")).to_have_text(ex_name)

        # 6. persisted where git can see it
        custom = json.loads((server["root"] / "data/registry/custom-exercises.json").read_text())
        assert any(e["name"] == ex_name for e in custom["exercises"])
        graph = json.loads((server["root"] / "data/graph.json").read_text())
        assert any(n["id"].startswith("sled-push") for n in graph["nodes"])

        # 7. server responses forbid caching (the original failure mode)
        resp = page.request.get(server["url"] + "/app.js?v=3")
        assert "no-cache" in resp.headers.get("cache-control", "")

        assert not errors, f"JS errors ({engine}): {errors}"
        browser.close()


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_empty_state_all_views_no_js_errors(server, engine):
    with sync_playwright() as p:
        browser = getattr(p, engine).launch()
        page = browser.new_context().new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(server["url"])
        for view in ["graph", "timeline", "vault", "achievements", "coach", "home"]:
            page.click(f".nav-item[data-view={view}]")
            page.wait_for_timeout(250)
        assert not errors, f"JS errors ({engine}): {errors}"
        browser.close()
