"""Dashboard API tests (FastAPI TestClient over an isolated repo)."""

import json

from fastapi.testclient import TestClient


def client(iso_repo):
    from irongraph.server.app import S, app
    S.mtime = -1.0  # bust cross-test cache
    return TestClient(app)


def test_add_custom_exercise_persists_and_updates_graph(iso_repo):
    c = client(iso_repo)
    r = c.post("/api/exercises", json={
        "name": "Landmine Press",
        "category": "shoulders",
        "modality": "weight_reps",
        "equipment": "barbell",
        "movement_pattern": "vertical push",
        "primary_muscles": ["front-delts"],
        "secondary_muscles": ["core"],
        "related": ["Overhead Press", "Nonexistent Thing"],
        "compound": True,
    })
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["exercise"]["id"] == "landmine-press"
    assert data["exercise"]["relations"] == {"similar_to": ["overhead-press"]}
    assert data["unresolved_related"] == ["Nonexistent Thing"]

    # persisted to the Git-tracked registry file
    custom = json.loads((iso_repo / "data" / "registry" / "custom-exercises.json").read_text())
    assert custom["exercises"][0]["name"] == "Landmine Press"
    assert custom["exercises"][0]["movement_pattern"] == "vertical-push"

    # graph rebuilt with the new node and its edge
    graph = json.loads((iso_repo / "data" / "graph.json").read_text())
    assert any(n["id"] == "landmine-press" for n in graph["nodes"])
    assert any({e["source"], e["target"]} == {"landmine-press", "overhead-press"}
               for e in graph["edges"])

    # immediately usable by other endpoints
    assert c.get("/api/exercise/landmine-press").status_code == 200


def test_add_duplicate_rejected(iso_repo):
    c = client(iso_repo)
    r = c.post("/api/exercises", json={"name": "bench press"})
    assert r.status_code == 409
    assert "Barbell Bench Press" in r.json()["detail"]


def test_add_invalid_category_rejected(iso_repo):
    c = client(iso_repo)
    r = c.post("/api/exercises", json={"name": "Sled Push", "category": "cardio-ish"})
    assert r.status_code == 422


def test_summary_and_graph_endpoints(iso_repo):
    c = client(iso_repo)
    s = c.get("/api/summary").json()
    assert s["total_workouts"] == 0 and s["level"] == 1
    g = c.get("/api/graph").json()
    assert len(g["nodes"]) >= 56
