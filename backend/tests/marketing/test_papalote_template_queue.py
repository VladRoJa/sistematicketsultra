"""Focused checks for Papalote-only audited iVentas queue and source."""
from types import SimpleNamespace as NS

import pytest

from scripts.marketing import queue_papalote_regresa_templates as upload


def test_editorial_source_is_24_papalote_only_and_validates_utf16_fields():
    templates = upload.source_templates()
    assert len(templates) == 24
    assert set(templates) == upload.EXPECTED
    assert all("_449_lb" not in name for name in templates)
    assert all(t["category"] == "MARKETING" and not t["buttons"] for t in templates.values())
    assert all(len(t["message"].encode("utf-16-le")) <= 2048 for t in templates.values())
    assert {name for name, t in templates.items() if not t["fields"]} == upload.SIMPLE_TEMPLATES
    for name, template in templates.items():
        if name in upload.SIMPLE_TEMPLATES:
            continue
        assert len(template["fields"]) == 1
        field = template["fields"][0]
        selected = template["message"].encode("utf-16-le")[field["start"] * 2:field["end"] * 2]
        assert selected.decode("utf-16-le") == "[Nombre]"


def test_offsets_count_emoji_as_two_utf16_units():
    message = "Hola 💪 [Nombre], regresa a Ultra."
    fields = upload.field_offsets(message)
    assert fields == [{"start": 8, "end": 16}]


def test_provider_missing_templates_ready_including_both_simple_variants():
    templates = upload.source_templates()
    rows = upload.plan_queue(
        templates=templates,
        provider_inventory=(NS(template_name="plantilla_ajena", status="accepted"),),
        prior_names=set(),
    )
    assert len(rows) == 24
    assert sum(row.status == "READY" for row in rows) == 24
    assert {row.name for row in rows if row.status != "READY"} == set()


def test_provider_presence_blocks_creation_even_if_not_approved():
    templates = upload.source_templates()
    rows = upload.plan_queue(
        templates=templates,
        provider_inventory=(NS(template_name="1REGRESA_499_N1", status="pending"),),
        prior_names=set(),
    )
    assert next(row for row in rows if row.name == "1regresa_499_n1").status == "PROVIDER_EXISTS"
    assert next(row for row in rows if row.name == "2regresa_499_n1").status == "READY"


def test_previous_queue_blocks_duplicate_even_if_provider_not_observed():
    templates = upload.source_templates()
    rows = upload.plan_queue(
        templates=templates,
        provider_inventory=tuple(),
        prior_names={"3regresa_399_n2"},
    )
    assert next(row for row in rows if row.name == "3regresa_399_n2").status == "PREVIOUS_UPLOAD"
    assert next(row for row in rows if row.name == "4regresa_399_n2").status == "READY"


def test_source_requires_exact_names_and_correct_custom_fields(tmp_path):
    import json

    source = upload.source_templates()
    broken = {
        "templates": [
            {"name": name, "body": row["message"], "placeholder_count": len(row["fields"]),
             "simple_template": name in upload.SIMPLE_TEMPLATES}
            for name, row in source.items()
        ],
    }
    broken["templates"][0]["name"] = "1regresa_449_lb"
    path = tmp_path / "unapproved.json"
    path.write_text(json.dumps(broken), encoding="utf-8")

    with pytest.raises(ValueError, match="24 plantillas"):
        upload.source_templates(path)


def test_two_simple_variants_have_no_positional_variables_and_are_ready():
    templates = upload.source_templates()
    for name in upload.SIMPLE_TEMPLATES:
        assert templates[name]["fields"] == []
        assert "[Nombre]" not in templates[name]["message"]
    plan = upload.plan_queue(templates=templates, provider_inventory=(), prior_names=set())
    assert {row.name for row in plan if row.status == "READY"} == set(templates)
