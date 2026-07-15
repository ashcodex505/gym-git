"""The self-generating log form: registry-complete, and safe untouched."""

import yaml

from irongraph.formgen import build_form, write_form
from irongraph.parser import QuestParser
from irongraph.registry import Registry


def test_form_lists_every_exercise(iso_repo):
    reg = Registry.load()
    form = build_form(reg)
    all_text = "\n".join(b["attributes"].get("value", "")
                         for b in form["body"] if b["type"] == "textarea")
    for ex in reg.by_id.values():
        assert f"{ex.name}:" in all_text, f"{ex.name} missing from form"


def test_written_form_is_valid_yaml(iso_repo, tmp_path):
    out = write_form(out=tmp_path / "log-workout.yml")
    d = yaml.safe_load(out.read_text())
    assert d["labels"] == ["daily-quest", "log-workout"]
    assert [b["id"] for b in d["body"] if b["type"] == "textarea"] == \
        ["strength", "cardio", "core", "notes"]


def test_untouched_form_defaults_parse_to_nothing(iso_repo):
    """Submitting the form without typing numbers = rest day, never phantoms."""
    reg = Registry.load()
    form = build_form(reg)
    # simulate a rendered submission: label headings + untouched defaults
    body = "\n\n".join(
        f"### {b['attributes']['label']}\n\n{b['attributes'].get('value', '')}"
        for b in form["body"] if b["type"] == "textarea")
    res = QuestParser(reg, default_unit="lb").parse(body)
    assert res.entries == []


def test_filled_form_line_parses(iso_repo):
    reg = Registry.load()
    form = build_form(reg)
    val = next(b for b in form["body"] if b.get("id") == "strength")["attributes"]["value"]
    filled = val.replace("Barbell Bench Press:", "Barbell Bench Press: 185 lb x 6, 185 x 5")
    res = QuestParser(reg, default_unit="lb").parse(filled)
    assert len(res.entries) == 1
    assert res.entries[0].exercise_id == "barbell-bench-press"
    assert len(res.entries[0].sets) == 2


def test_form_passes_githubs_official_schema(iso_repo, tmp_path):
    """Validate against GitHub's issue-forms JSON schema (vendored from
    SchemaStore). A schema-invalid form makes GitHub silently fall back
    to a blank issue — this guards the whole logging UX."""
    import json
    from pathlib import Path

    import jsonschema

    schema = json.loads((Path(__file__).parent / "data" / "github-issue-forms.schema.json").read_text())
    out = write_form(out=tmp_path / "log-workout.yml")
    jsonschema.validate(yaml.safe_load(out.read_text()), schema)
