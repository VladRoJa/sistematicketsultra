from app import create_app


def test_purchase_requisition_api_contract_is_registered():
    app = create_app()
    methods_by_rule = {
        rule.rule: set(rule.methods)
        for rule in app.url_map.iter_rules()
        if rule.rule.startswith(
            "/api/purchase-requisitions"
        )
    }

    expected = {
        "/api/purchase-requisitions/access": "GET",
        "/api/purchase-requisitions": "POST",
        "/api/purchase-requisitions": "GET",
        "/api/purchase-requisitions/<int:requisition_id>": "GET",
        (
            "/api/purchase-requisitions/"
            "<int:requisition_id>/requester-edit"
        ): "PUT",
        (
            "/api/purchase-requisitions/"
            "<int:requisition_id>/resubmit"
        ): "POST",
        (
            "/api/purchase-requisitions/"
            "<int:requisition_id>/request-info"
        ): "POST",
        (
            "/api/purchase-requisitions/"
            "<int:requisition_id>/approve"
        ): "POST",
        (
            "/api/purchase-requisitions/"
            "<int:requisition_id>/reject"
        ): "POST",
        (
            "/api/purchase-requisitions/"
            "<int:requisition_id>/attachments"
        ): "POST",
        (
            "/api/purchase-requisitions/"
            "<int:requisition_id>/attachments/"
            "<int:attachment_id>/file"
        ): "GET",
    }

    for rule, method in expected.items():
        assert rule in methods_by_rule
        assert method in methods_by_rule[rule]

    assert all(
        "PATCH" not in methods
        for methods in methods_by_rule.values()
    )
