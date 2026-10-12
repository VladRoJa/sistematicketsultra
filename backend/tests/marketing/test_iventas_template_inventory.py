import pytest

from app.integrations.iventas.template_inventory import (
    TemplateInventoryValidationError,
    evaluate_template_coverage,
    parse_template_inventory,
)


def _row(name, channel_id, status="accepted", channel_name="Ultra Gym"):
    return {
        "id": "template-instance-id",
        "name": name,
        "status": status,
        "channelId": channel_id,
        "channel": {"id": channel_id, "name": channel_name},
        "components": [{"format": "TEXT", "text": "Hola {{1}}"}],
    }


def test_observed_iventas_inventory_maps_three_templates_to_one_channel():
    names = [
        "bcn_low_ticket_octubre",
        "winback_general_octubre",
        "adeudo_menor_a_3000",
    ]
    inventory = parse_template_inventory([_row(name, "metepec") for name in names])
    matrix = evaluate_template_coverage(
        inventory=inventory, expected_channel_ids=["metepec"], template_names=names
    )
    assert len(inventory) == 3
    assert all(matrix[name]["metepec"] == "accepted" for name in names)


def test_missing_is_not_observed_not_inferred_available():
    inventory = parse_template_inventory([_row("bcn_low_ticket_octubre", "metepec")])
    matrix = evaluate_template_coverage(
        inventory=inventory,
        expected_channel_ids=["metepec", "papalote"],
        template_names=["bcn_low_ticket_octubre"],
    )
    assert matrix["bcn_low_ticket_octubre"]["papalote"] == "not_observed"


@pytest.mark.parametrize(
    "bad_payload",
    [
        {"rows": []},
        [None],
        [_row("a", "x") | {"channelId": "y"}],
        [_row("a", "x") | {"status": None}],
        [_row("a", "x") | {"channel": {}}],
    ],
)
def test_invalid_inventory_fails_closed(bad_payload):
    with pytest.raises(TemplateInventoryValidationError):
        parse_template_inventory(bad_payload)


def test_denied_does_not_count_as_accepted():
    inventory = parse_template_inventory([_row("bcn", "x", "denied")])
    matrix = evaluate_template_coverage(
        inventory=inventory, expected_channel_ids=["x"], template_names=["bcn"]
    )
    assert matrix["bcn"]["x"] == "denied"


def test_duplicate_conflicting_statuses_fail_closed_at_evaluation():
    inventory = parse_template_inventory(
        [_row("bcn", "x", "accepted"), _row("bcn", "x", "denied")]
    )
    assert evaluate_template_coverage(
        inventory=inventory, expected_channel_ids=["x"], template_names=["bcn"]
    )["bcn"]["x"] == "conflict"
