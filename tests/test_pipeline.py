"""End-to-end ingestion pipeline: files, idempotency, commit, attribution."""

import json
import subprocess

from conftest import fixture

from irongraph import gitcommit
from irongraph.ingest import ingest_issue


def test_full_ingest_strength(iso_repo):
    s = ingest_issue(42, fixture("strength_day.md"), date="2026-07-12",
                     issue_url="https://github.com/x/y/issues/42")
    assert s["status"] == "ok"
    assert s["entries"] == 4
    # workout file exists and is auditable
    f = iso_repo / "data" / "workouts" / "2026" / "2026-07-12--issue-42.json"
    data = json.loads(f.read_text())
    assert data["source"]["issue_number"] == 42
    assert data["entries"][0]["raw"] == "" or "exercise_id" in data["entries"][0]
    # derived artifacts regenerated
    assert (iso_repo / "README.md").exists()
    assert (iso_repo / "generated" / "strength-overview.svg").exists()
    assert (iso_repo / "generated" / "workout-heatmap.svg").exists()
    assert (iso_repo / "data" / "graph.json").exists()
    # commit message
    assert s["commit_subject"].startswith("feat(workout):")
    assert len(s["commit_subject"].split("\n")[0]) <= 80
    assert "Barbell Bench Press" in s["commit_body"]
    assert "Ashish Kurse <ashishkurse@gmail.com>" in s["commit_body"]
    # first-workout achievements + PRs fired
    assert any(a["id"] == "first-commit" for a in s["achievements"])
    assert any(p["exercise"] == "Barbell Bench Press" for p in s["prs"])


def test_duplicate_ingestion_is_noop(iso_repo):
    s1 = ingest_issue(42, fixture("strength_day.md"), date="2026-07-12")
    assert s1["status"] == "ok"
    s2 = ingest_issue(42, fixture("strength_day.md"), date="2026-07-12")
    assert s2["status"] == "duplicate"
    files = list((iso_repo / "data" / "workouts").rglob("*.json"))
    assert len(files) == 1
    prof = json.loads((iso_repo / "data" / "profile.json").read_text())
    assert prof["totals"]["workouts"] == 1  # XP not double-awarded


def test_invalid_input_commits_nothing(iso_repo):
    s = ingest_issue(7, fixture("malformed.md"), date="2026-07-16")
    assert s["status"] == "invalid"
    assert len(s["problems"]) == 2
    assert not (iso_repo / "data" / "workouts").exists()
    assert not (iso_repo / "data" / "personal-records.json").exists()


def test_cardio_only_day(iso_repo):
    s = ingest_issue(2, fixture("cardio_day.md"), date="2026-07-13")
    assert s["status"] == "ok"
    assert any(p["exercise"] == "Treadmill" for p in s["prs"])
    assert "cardio" in s["commit_subject"]


def test_custom_exercise_pipeline(iso_repo):
    s = ingest_issue(9, fixture("custom_exercise.md"), date="2026-07-17")
    assert s["status"] == "ok"
    assert s["new_custom_exercises"] == ["landmine-press", "nordic-curl"]
    custom = json.loads((iso_repo / "data" / "registry" / "custom-exercises.json").read_text())
    assert {e["id"] for e in custom["exercises"]} == {"landmine-press", "nordic-curl"}
    # custom exercise present in rebuilt graph
    graph = json.loads((iso_repo / "data" / "graph.json").read_text())
    assert any(n["id"] == "landmine-press" for n in graph["nodes"])


def test_multi_day_progression_and_readme(iso_repo):
    ingest_issue(1, fixture("strength_day.md"), date="2026-07-12")
    ingest_issue(2, fixture("cardio_day.md"), date="2026-07-13")
    ingest_issue(3, fixture("abs_day.md"), date="2026-07-14")
    s = ingest_issue(4, fixture("mixed_day.md"), date="2026-07-15")
    assert s["status"] == "ok"
    readme = (iso_repo / "README.md").read_text()
    assert "IronGraph" in readme and "2026-07-15" in readme
    assert "Recent Activity" in readme
    graph = json.loads((iso_repo / "data" / "graph.json").read_text())
    performed = [n for n in graph["nodes"] if n["performed"]]
    assert len(performed) >= 9
    heat = (iso_repo / "generated" / "workout-heatmap.svg").read_text()
    assert "2026-07-13" in heat  # tooltip title present


def _git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)


def test_commit_author_attribution(iso_git_repo, capsys):
    s = ingest_issue(42, fixture("strength_day.md"), date="2026-07-12")
    assert s["status"] == "ok"
    sha = gitcommit.commit_workout(s["commit_subject"], s["commit_body"])
    assert sha
    meta = _git(iso_git_repo, "log", "-1",
                "--format=Author: %an <%ae>%nCommitter: %cn <%ce>%nSubject: %s").stdout
    assert "Author: Ashish Kurse <ashishkurse@gmail.com>" in meta
    assert "feat(workout):" in meta
    out = capsys.readouterr().out
    assert "Verified workout commit" in out
    # one atomic commit: data + generated + README all inside
    files = _git(iso_git_repo, "show", "--name-only", "--format=", sha).stdout
    assert "data/workouts/2026/2026-07-12--issue-42.json" in files
    assert "README.md" in files
    assert "generated/strength-overview.svg" in files


def test_commit_author_mismatch_fails(iso_git_repo, monkeypatch):
    """If git ends up with the wrong author, the commit must be rolled back."""
    s = ingest_issue(42, fixture("strength_day.md"), date="2026-07-12")
    orig_run = gitcommit.run

    def sabotage(args, **kw):
        if args[:2] == ["git", "commit"]:
            args = [a for a in args if not a.startswith("Ashish") and a != "--author"]
            args.insert(2, "--author")
            args.insert(3, "github-actions[bot] <bot@github.com>")
        return orig_run(args, **kw)

    monkeypatch.setattr(gitcommit, "run", sabotage)
    import pytest
    with pytest.raises(SystemExit) as exc:
        gitcommit.commit_workout(s["commit_subject"], s["commit_body"])
    assert "author mismatch" in str(exc.value)
    # rolled back: HEAD is still the seed commit
    subject = _git(iso_git_repo, "log", "-1", "--format=%s").stdout.strip()
    assert subject == "init"


def test_quest_generation(iso_repo):
    from datetime import date

    from irongraph.quest import build_quest
    title, body = build_quest(date(2026, 7, 12))
    assert "Daily Quest" in title and "July 12, 2026" in title
    assert "irongraph:quest date=2026-07-12" in body
    assert "- [ ] Barbell Bench Press ::" in body
    assert "Treadmill" in body and "Plank" in body
    assert "<details>" in body


def test_quest_shows_pr_hints_after_ingest(iso_repo):
    ingest_issue(1, fixture("strength_day.md"), date="2026-07-12")
    from datetime import date

    from irongraph.quest import build_quest
    _, body = build_quest(date(2026, 7, 13))
    assert "PR 185 lb × 6" in body
