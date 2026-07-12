"""Full-browser E2E tests of the dashboard (Playwright + real server).

Runs the actual FastAPI server against an isolated repo copy and drives
a real Chromium: every view, the graph interactions, the add-exercise
flow (persistence to registry + graph files), the detail panel, the
command palette, and the AI-offline path. Any JS console error fails
the test.

Skipped automatically if playwright isn't installed.
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


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    """Isolated repo (with one ingested workout) + live server."""
    root = tmp_path_factory.mktemp("e2e-repo")
    (root / "data" / "registry").mkdir(parents=True)
    (root / "config").mkdir()
    shutil.copy(REPO / "data/registry/exercises.json", root / "data/registry/exercises.json")
    shutil.copy(REPO / "config/irongraph.yml", root / "config/irongraph.yml")
    env = {**os.environ, "IRONGRAPH_ROOT": str(root)}
    subprocess.run(
        [sys.executable, "-m", "irongraph.ingest", "--issue-number", "1",
         "--issue-body-file", str(REPO / "tests/fixtures/strength_day.md"),
         "--date", "2026-07-12"],
        env=env, check=True, capture_output=True, cwd=REPO)
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "irongraph.server"],
        env={**env, "IRONGRAPH_PORT": str(port)},
        cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                break
        except OSError:
            time.sleep(0.2)
    else:
        proc.kill()
        pytest.fail("server did not start")
    yield {"url": url, "root": root}
    proc.terminate()


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture()
def page(browser, server):
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    pg = ctx.new_page()
    errors: list[str] = []
    # 4xx fetches the app handles (e.g. duplicate → 409 shown in the form)
    # still log a console "Failed to load resource" line — that's expected UX,
    # not a JS failure, so it doesn't fail the test.
    pg.on("console", lambda m: errors.append(m.text)
          if m.type == "error" and "Failed to load resource" not in m.text else None)
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg._js_errors = errors
    yield pg
    assert not errors, f"JS errors on page: {errors}"
    ctx.close()


def test_command_center_renders(page, server):
    page.goto(server["url"])
    expect(page.locator("h1")).to_have_text("Command Center")
    expect(page.locator(".card").first).to_contain_text("LEVEL", ignore_case=True)
    expect(page.locator("#home-prs .pr-item").first).to_be_visible()  # workout ingested → PRs exist


def test_graph_renders_and_node_click_opens_detail(page, server):
    page.goto(server["url"] + "/#graph")
    page.wait_for_selector("#graph-legend .lg-row")
    assert page.locator("#graph-legend .lg-row").count() >= 8
    # search + Enter jumps to and selects the node → detail panel opens
    page.fill("#graph-search", "barbell bench")
    page.press("#graph-search", "Enter")
    expect(page.locator("#detail-panel")).to_be_visible()
    expect(page.locator(".dp-name")).to_have_text("Barbell Bench Press")
    expect(page.locator("#detail-body")).to_contain_text("Personal best")
    href = page.locator(".dp-video").get_attribute("href")
    assert "youtube.com" in href
    # related exercise navigation
    page.locator("[data-ex]").first.click()
    expect(page.locator("#detail-panel")).to_be_visible()
    # esc closes
    page.keyboard.press("Escape")
    expect(page.locator("#detail-panel")).to_be_hidden()


def test_add_exercise_button_opens_modal_and_persists(page, server):
    page.goto(server["url"] + "/#graph")
    page.wait_for_selector("#add-ex-btn")
    page.click("#add-ex-btn")
    expect(page.locator("#add-ex-modal")).to_be_visible()

    page.fill("#add-ex-form [name=name]", "Landmine Press")
    page.select_option("#add-ex-form [name=category]", "shoulders")
    page.select_option("#add-ex-form [name=modality]", "weight_reps")
    page.fill("#add-ex-form [name=equipment]", "barbell")
    page.fill("#add-ex-form [name=movement_pattern]", "vertical push")
    page.fill("#add-ex-form [name=primary_muscles]", "front-delts, core")
    page.fill("#add-ex-form [name=related]", "Overhead Press")
    page.check("#add-ex-form [name=compound]")
    page.click("#add-ex-form button.primary")

    expect(page.locator("#add-ex-modal")).to_be_hidden()
    expect(page.locator("#pr-toast")).to_be_visible()
    expect(page.locator("#pr-toast")).to_contain_text("Landmine Press added")
    # new node is selected → detail panel shows it
    expect(page.locator(".dp-name")).to_have_text("Landmine Press")

    # persisted on disk (Git-tracked files)
    custom = json.loads((server["root"] / "data/registry/custom-exercises.json").read_text())
    assert custom["exercises"][0]["name"] == "Landmine Press"
    graph = json.loads((server["root"] / "data/graph.json").read_text())
    assert any(n["id"] == "landmine-press" for n in graph["nodes"])
    assert any({e["source"], e["target"]} == {"landmine-press", "overhead-press"}
               for e in graph["edges"])

    # duplicate through the UI is rejected with a visible error
    page.click("#add-ex-btn")
    page.fill("#add-ex-form [name=name]", "landmine press")
    page.click("#add-ex-form button.primary")
    expect(page.locator("#aem-error")).to_contain_text("already exists")
    page.click("#aem-cancel")
    expect(page.locator("#add-ex-modal")).to_be_hidden()


def test_deep_link_graph_add(page, server):
    page.goto(server["url"] + "/#graph/add")
    expect(page.locator("#add-ex-modal")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator("#add-ex-modal")).to_be_hidden()


def test_filter_chips_and_zoom(page, server):
    page.goto(server["url"] + "/#graph")
    page.wait_for_selector("#chip-performed")
    page.click("#chip-performed")
    assert "on" in page.locator("#chip-performed").get_attribute("class")
    page.click("#chip-performed")
    assert "on" not in page.locator("#chip-performed").get_attribute("class")
    page.click("#zoom-in")
    page.click("#zoom-out")
    page.click("#zoom-fit")


def test_timeline_vault_achievements_views(page, server):
    page.goto(server["url"] + "/#timeline")
    expect(page.locator(".tl-date").first).to_have_text("2026-07-12")
    page.goto(server["url"] + "/#vault")
    expect(page.locator("table.vault tr").nth(1)).to_contain_text("Barbell Bench Press")
    page.goto(server["url"] + "/#achievements")
    expect(page.locator(".ach.unlocked").first).to_be_visible()


def test_command_palette(page, server):
    page.goto(server["url"])
    page.keyboard.press("Meta+k")
    expect(page.locator("#palette")).to_be_visible()
    page.fill("#palette-input", "deadlift")
    page.press("#palette-input", "Enter")   # jumps to graph + selects node
    expect(page.locator("#detail-panel")).to_be_visible()
    expect(page.locator(".dp-name")).to_contain_text("Deadlift")


def test_ai_coach_offline_path(page, server):
    page.goto(server["url"] + "/#coach")
    page.fill("#coach-input", "How do I improve my bench press?")
    page.click("#coach-form button[type=submit]")
    expect(page.locator("#coach-log .msg.sys").last).to_contain_text("GEMINI_API_KEY")


def test_edit_exercise_from_detail_panel(page, server):
    page.goto(server["url"] + "/#graph")
    page.fill("#graph-search", "lateral raise")
    page.press("#graph-search", "Enter")
    expect(page.locator(".dp-name")).to_have_text("Lateral Raise")
    page.click("#dp-edit")
    expect(page.locator("#add-ex-modal")).to_be_visible()
    # prefilled from the exercise
    assert page.locator("#add-ex-form [name=name]").input_value() == "Lateral Raise"
    assert page.locator("#add-ex-form [name=category]").input_value() == "shoulders"
    # change equipment + add a relation
    page.fill("#add-ex-form [name=equipment]", "cable")
    page.fill("#add-ex-form [name=related]", "Face Pull")
    page.click("#add-ex-form button.primary")
    expect(page.locator("#add-ex-modal")).to_be_hidden()
    expect(page.locator("#pr-toast")).to_contain_text("Lateral Raise updated")
    # detail panel reflects the change
    expect(page.locator(".dp-tags")).to_contain_text("cable")
    # persisted as an override (core file untouched)
    custom = json.loads((server["root"] / "data/registry/custom-exercises.json").read_text())
    assert custom["overrides"]["lateral-raise"]["equipment"] == "cable"


def test_hero_sprite_served_and_on_home(page, server):
    import subprocess as sp
    import sys as _sys
    # regenerate views so the sprite exists (module server was seeded pre-sprite)
    sp.run([_sys.executable, "-m", "irongraph.ingest", "--regen"],
           env={**os.environ, "IRONGRAPH_ROOT": str(server["root"])},
           cwd=REPO, check=True, capture_output=True)
    r = page.request.get(server["url"] + "/generated/hero-sprite.gif")
    assert r.status == 200
    assert r.body()[:6] == b"GIF89a"
    page.goto(server["url"])
    expect(page.locator(".hero-sprite")).to_be_visible()
    expect(page.locator(".hero-name")).to_contain_text("Level")
