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
        (
            "/api/purchase-requisitions/"
            "config/finance-approvers"
        ): "GET",
        (
            "/api/purchase-requisitions/"
            "config/finance-approvers"
        ): "POST",
        (
            "/api/purchase-requisitions/"
            "config/finance-approvers/<int:user_id>"
        ): "PUT",
        "/api/purchase-requisitions": "POST",
        "/api/purchase-requisitions": "GET",
        "/api/purchase-requisitions/<int:requisition_id>": "GET",
        (
            "/api/purchase-requisitions/"
            "<int:requisition_id>/quotes"
        ): "POST",
        (
            "/api/purchase-requisitions/"
            "<int:requisition_id>/quotes/"
            "<int:quote_id>/select"
        ): "POST",
        (
            "/api/purchase-requisitions/"
            "<int:requisition_id>/submit-quote-for-finance"
        ): "POST",
        (
            "/api/purchase-requisitions/"
            "<int:requisition_id>/finance/approve-quote"
        ): "POST",
        (
            "/api/purchase-requisitions/"
            "<int:requisition_id>/finance/reject-quote"
        ): "POST",
        (
            "/api/purchase-requisitions/"
            "<int:requisition_id>/advance-logistics"
        ): "POST",
        (
            "/api/purchase-requisitions/"
            "<int:requisition_id>/confirm-receipt"
        ): "POST",
        (
            "/api/purchase-requisitions/"
            "<int:requisition_id>/report-receipt-issue"
        ): "POST",
        (
            "/api/purchase-requisitions/"
            "<int:requisition_id>/resume-logistics"
        ): "POST",
        (
            "/api/purchase-requisitions/"
            "<int:requisition_id>/administrative-correction"
        ): "POST",
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
