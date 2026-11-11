"""Controlled QA preparation and immutable claims. No provider HTTP or production DB."""
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

import pytest

from app.services import marketing_campaign_v2_template_probe_service as probe

NOW = datetime(2026, 11, 9, 18, tzinfo=timezone.utc)


def template():
    return NS(id=7, template_name="selected", variables_json={},
              compatible_channel_ids_json=[], metadata_json={})


def group():
    return {"binding_id": 40, "sender_sucursal_id": 4, "sender": "TEC_MXL",
            "origins": ["INDEPENDENCIA", "TEC_MXL"]}


def campaign():
    spec = dict(source_campaign_id=42, template_id=7, certification_scope="TEMPLATE_VERSION_CHANNEL_V2", template_signature=probe._signature(template()),
                channel_id="tec", **group(), phone_mx10="6861000001",
                authorized_by_user_id=47, authorization_reference="Autorización prueba interna")
    return NS(id=80, source="QA_MANUAL", audience_definition_json={"source_metadata": {probe.KEY: spec}})


def child(**kwargs):
    values = dict(id=90, campaign_v2_id=80, template_id=7, provider_channel_id="tec",
                  recipient_count=1, status="READY", submit_started_at=None,
                  submitted_by_user_id=None, provider_campaign_id=None,
                  submitted_at=None, error_code=None, support_ref=None,
                  retry_attempt_count=0, retry_history_json=[], reconciliation_resolution=None,
                  provider_response_json={})
    return NS(**(values | kwargs))


def session(rows=None):
    active = MagicMock()
    active.get_bind.return_value.dialect.name = "postgresql"
    def query(model, *extra):
        q = MagicMock()
        q.filter_by.return_value = q
        q.filter.return_value = q
        q.join.return_value = q
        q.order_by.return_value = q
        q.limit.return_value = q
        if extra:
            q.all.return_value = []
        elif model is probe.Recipient:
            q.all.return_value = [NS(phone_mx10="6861000001")]
        elif model is probe.Child:
            q.all.return_value = rows or []
        elif model is probe.Campaign:
            q.all.return_value = []
        else:
            q.first.return_value = (1,)
        return q
    active.query.side_effect = query
    return active


def context():
    return NS(id=42, purpose="REACTIVATION"), template(), {"tec": group()}


def test_deduplicates_real_sender_but_keeps_all_commercial_origins():
    active = MagicMock()
    active.get.return_value = NS(id=40, sucursal_id=4, sucursal_canon="TEC_MXL",
        provider="IVENTAS", is_active=True, is_default=True, provider_channel_id="tec")
    batches = [NS(channel_binding_id=40, provider_channel_id="tec", sucursal_canon=s)
               for s in ["TEC_MXL", "INDEPENDENCIA"]]
    plan = NS(batches=batches, blocked_missing_branch=(), blocked_invalid_phone=())
    assert probe._groups(plan, active) == {"tec": group()}
    active.get.return_value.provider_channel_id = "changed"
    with pytest.raises(probe.TemplateProbeValidation):
        probe._groups(plan, active)


def prepare_args(active):
    return dict(campaign_id=42, template_id=7, recipient_name="Prueba autorizada",
                phone="6861000001", authorization_reference="Autorización prueba interna",
                confirmed_authorized=True, actor_user_id=47, session=active)


@pytest.mark.parametrize("override", [
    {"confirmed_authorized": False}, {"authorization_reference": ""},
    {"phone": "invalid"}, {"recipient_name": ""}, {"actor_user_id": True},
])
def test_explicit_phone_authorization_required_before_any_write(override):
    active = session()
    with pytest.raises(probe.TemplateProbeValidation):
        probe.prepare_template_probes(**(prepare_args(active) | override))
    active.execute.assert_not_called()
    active.commit.assert_not_called()


def test_prepare_two_commercial_campaigns_reuse_single_cohort_and_never_call_provider():
    active = session()
    saved = {}
    def freeze(**kwargs):
        assert kwargs["commit"] is False
        assert kwargs["recipients"] == [{"name": "Prueba autorizada", "phone": "6861000001"}]
        assert kwargs["sucursal_id"] == 4  # Real TEC sender, not Independencia origin.
        saved["qa"] = NS(id=80, audience_definition_json={"source_metadata": kwargs["source_metadata"]})
    with patch.object(probe, "_context", return_value=context()), \
         patch.object(probe, "_no_commercial_phone"), \
         patch.object(probe, "_existing", side_effect=lambda *args: saved.get("qa")), \
         patch.object(probe, "preview_qa_manual_http", return_value={"preview_fingerprint": "a" * 64}), \
         patch.object(probe, "freeze_campaign_v2_qa_manual", side_effect=freeze) as create, \
         patch.object(probe, "template_probe_matrix", return_value={"rows": []}):
        probe.prepare_template_probes(**prepare_args(active))
        probe.prepare_template_probes(**(prepare_args(active) | {
            "campaign_id": 43, "phone": "6861000002",
        }))
        create.assert_called_once()
    assert active.commit.call_count == 2
    active.rollback.assert_not_called()
    assert "pg_advisory_xact_lock" in str(active.execute.call_args.args[0])


def test_commercial_recipient_is_rejected_even_if_explicitly_confirmed():
    active = session()
    with patch.object(probe, "_context", return_value=context()), \
         patch.object(probe, "freeze_campaign_v2_qa_manual") as freeze:
        with pytest.raises(probe.TemplateProbeValidation, match="campaña comercial"):
            probe.prepare_template_probes(**prepare_args(active))
    freeze.assert_not_called()
    active.commit.assert_not_called()


@pytest.mark.parametrize("mutation", ["template", "media", "channel", "phone", "authorization"])
def test_preflight_blocks_contract_drift(mutation):
    qa = campaign()
    active = session()
    selected = template()
    binding = NS(id=40, sucursal_id=4, sucursal_canon="TEC_MXL",
                 provider="IVENTAS", is_active=True, is_default=True,
                 provider_channel_id="tec")
    requested = 7
    if mutation == "template": requested = 8
    if mutation == "media": selected.metadata_json = {"file_url": "https://example.test/changed.png"}
    if mutation == "channel": binding.id = 41
    if mutation == "phone": probe.probe_spec(qa)["phone_mx10"] = "6861000002"
    if mutation == "authorization": probe.probe_spec(qa)["authorization_reference"] = ""
    active.get.side_effect = lambda model, key: selected if model is probe.Template else binding
    with pytest.raises(probe.TemplateProbeValidation):
        probe.validate_probe_preflight(campaign=qa, template_id=requested, session=active)


def test_governed_claim_once_then_no_retry_after_any_outcome():
    qa = campaign()
    row = child()
    active = session([row])
    active.get.side_effect = lambda model, key: (
        template() if model is probe.Template else
        NS(id=40, sucursal_id=4, sucursal_canon="TEC_MXL",
           provider="IVENTAS", is_active=True, is_default=True, provider_channel_id="tec")
    )
    with patch.object(probe, "_no_commercial_phone"):
        probe.validate_probe_claim(campaign=qa, child=row, session=active)
        for state in ["SUBMITTING", "SUBMITTED", "PROVIDER_ERROR", "RECONCILIATION_REQUIRED", "RETRY_ELIGIBLE"]:
            row.status = state
            row.submit_started_at = NOW
            with pytest.raises(probe.TemplateProbeValidation, match="no admite reenvíos"):
                probe.validate_probe_claim(campaign=qa, child=row, session=active)


@pytest.mark.parametrize("row,expected", [
    (None, "PENDIENTE"), (child(), "PENDIENTE"),
    (child(status="SUBMITTED", provider_campaign_id="iv-1", submitted_at=NOW,
           submit_started_at=NOW), "ACEPTADA POR IVENTAS"),
    (child(status="SUBMITTED", submit_started_at=NOW), "INCIERTA"),
    (child(status="RECONCILIATION_REQUIRED", submit_started_at=NOW), "INCIERTA"),
    (child(status="PROVIDER_ERROR", submit_started_at=NOW, submitted_by_user_id=47,
           error_code="TEMPLATE_NOT_FOUND", support_ref="ref-1",
           provider_response_json={"http_status": 400}), "RECHAZADA"),
    (child(status="PROVIDER_ERROR", submit_started_at=NOW, submitted_by_user_id=47,
           error_code="UNKNOWN", support_ref="ref-2", provider_response_json={"http_status": 400}), "INCIERTA"),
])
def test_acceptance_is_conservative_and_separate_from_delivery(row, expected):
    assert probe._result(row) == expected


def test_matrix_masks_phone_and_marks_stale_acceptance_for_attention():
    qa = campaign()
    probe.probe_spec(qa)["template_signature"] = "old"
    row = child(status="SUBMITTED", provider_campaign_id="iv-1", submitted_at=NOW,
                submit_started_at=NOW, submitted_by_user_id=47)
    with patch.object(probe, "_context", return_value=context()), \
         patch.object(probe, "_existing", return_value=qa):
        matrix = probe.template_probe_matrix(campaign_id=42, template_id=7, session=session([row]))
    result = matrix["rows"][0]
    assert result["result"] == "INVALIDADA" and result["stale"]
    assert result["recorded_acceptance"] == "ACEPTADA POR IVENTAS"
    assert result["delivery_status"] == "NO VERIFICADA"
    assert result["recipient_phone_masked"] == "******0001"
    assert "6861000001" not in str(matrix)
    assert matrix["commercial_dispatch_authorized"] is False


@pytest.mark.parametrize("mutation", [None, "timeout", "rejected", "route", "phone", "media"])
def test_only_exact_accepted_qa_is_provider_evidence_without_expiry(mutation):
    qa = campaign()
    selected = template()
    row = child(status="SUBMITTED", provider_campaign_id="iv-1", submitted_at=NOW,
        submit_started_at=NOW, submitted_by_user_id=47)
    row.request_snapshot_json = {"provider": "IVENTAS", "template_name": "selected",
        "provider_channel_id": "tec", "leads": [{"phone": "5216861000001"}]}
    if mutation == "timeout": row.status = "RECONCILIATION_REQUIRED"
    if mutation == "rejected": row.status = "PROVIDER_ERROR"
    if mutation == "route": probe.probe_spec(qa)["binding_id"] = 41
    if mutation == "phone": row.request_snapshot_json["leads"][0]["phone"] = "5216861000002"
    if mutation == "media": selected.metadata_json = {"file_url": "https://example.test/new.png"}
    active = session([row])
    active.get.return_value = NS(id=40, sucursal_id=4, sucursal_canon="TEC_MXL",
        provider="IVENTAS", is_active=True, is_default=True, provider_channel_id="tec")
    outbound = [dict(provider_channel_id="tec", channel_binding_id=40, sucursal_canon=origin)
                for origin in ["TEC_MXL", "INDEPENDENCIA"]]
    with patch.object(probe, "_existing", return_value=qa):
        accepted = probe.accepted_probe_channels(campaign_id=999, template=selected,
            outbound_bindings=outbound, session=active, now=NOW + timedelta(days=120))
    assert accepted == (frozenset({"tec"}) if mutation is None else frozenset())


def test_probe_key_global_and_versioned():
    name = probe._name(7, "a" * 64, "tec")
    assert name == probe._name(7, "a" * 64, "tec")
    assert "42" not in name
    assert name != probe._name(7, "b" * 64, "tec")
    assert name != probe._name(7, "a" * 64, "san_luis")


def test_matrix_reuses_accepted_other_campaign_and_has_no_expiry():
    qa = campaign()
    row = child(status="SUBMITTED", provider_campaign_id="iv-1", submitted_at=NOW,
        submit_started_at=NOW, submitted_by_user_id=47)
    row.request_snapshot_json = {"provider": "IVENTAS", "template_name": "selected",
        "provider_channel_id": "tec", "leads": [{"phone": "5216861000001"}]}
    active = session([row])
    active.get.return_value = NS(id=40, sucursal_id=4, sucursal_canon="TEC_MXL",
        provider="IVENTAS", is_active=True, is_default=True, provider_channel_id="tec")
    with patch.object(probe, "_context", return_value=context()), \
         patch.object(probe, "_existing", return_value=qa), \
         patch.object(probe, "accepted_probe_channels", return_value=frozenset({"tec"})):
        matrix = probe.template_probe_matrix(campaign_id=999, template_id=7, session=active)
    assert matrix["rows"][0]["result"] == "VALIDADA"
    assert matrix["rows"][0]["evidence_expires_at"] is None


def test_catalog_context_deduplicates_routed_origins_without_commercial_campaign():
    from unittest.mock import MagicMock
    active = MagicMock()
    selected = template()
    selected.provider = "IVENTAS"
    selected.is_active = True
    selected.purposes_json = ["REACTIVATION"]
    selected.compatible_channel_ids_json = ["tec"]
    sender = NS(id=40, sucursal_id=4, sucursal_canon="TEC_MXL",
                provider="IVENTAS", provider_channel_id="tec",
                is_active=True, is_default=True, metadata_json={})
    origin = NS(id=41, sucursal_id=5, sucursal_canon="INDEPENDENCIA",
                provider="IVENTAS", provider_channel_id="ind",
                is_active=True, is_default=True,
                metadata_json={"dispatch_via_binding_id": 40})
    active.get.return_value = selected
    active.query.return_value.filter.return_value.all.return_value = [sender, origin]
    source, returned_template, groups = probe._context(None, 7, active)
    assert returned_template is selected
    assert source.purpose == "REACTIVATION"
    assert groups["tec"] == group()
    assert len(groups) == 1


def test_catalog_context_rejects_duplicate_real_channel():
    active = MagicMock()
    selected = template()
    selected.provider = "IVENTAS"
    selected.is_active = True
    selected.purposes_json = []
    selected.compatible_channel_ids_json = []
    active.get.return_value = selected
    left = NS(id=40, sucursal_id=4, sucursal_canon="TEC_MXL",
              provider_channel_id="tec", metadata_json={})
    right = NS(id=42, sucursal_id=6, sucursal_canon="OTHER",
               provider_channel_id="tec", metadata_json={})
    active.query.return_value.filter.return_value.all.return_value = [left, right]
    with pytest.raises(probe.TemplateProbeValidation, match="ambiguos"):
        probe._catalog_context(7, active)


def test_new_channel_does_not_invalidate_existing_template_version():
    selected = template()
    signature = probe._signature(selected)
    selected.compatible_channel_ids_json = ["tec", "san_luis"]
    assert probe._signature(selected) == signature
    selected.template_name = "renamed"
    assert probe._signature(selected) != signature


def test_catalog_reuses_existing_qa_without_commercial_source():
    active = session()
    existing_qa = campaign()
    existing_qa.audience_definition_json["source_metadata"][probe.KEY][
        "source_campaign_id"] = None
    with patch.object(probe, "_catalog_context", return_value=(
        NS(purpose="REACTIVATION"), template(), {"tec": group()})), \
         patch.object(probe, "_existing", return_value=existing_qa), \
         patch.object(probe, "freeze_campaign_v2_qa_manual") as create, \
         patch.object(probe, "template_probe_matrix", return_value={"rows": []}):
        probe.prepare_template_probes(
            **(prepare_args(active) | {"campaign_id": None}))
    create.assert_not_called()
    active.commit.assert_called_once()


@pytest.mark.parametrize('selected', [
    [], ['tec','tec'], ['unknown'], ['tec','unknown'], 'tec', [123], [None],
])
def test_selected_channels_reject_invalid_or_unknown_before_freeze(selected):
    active = session()
    with patch.object(probe, '_context', return_value=context()), \
         patch.object(probe, 'freeze_campaign_v2_qa_manual') as freeze, \
         patch.object(probe, 'commercial_certifications', return_value={}):
        with pytest.raises(probe.TemplateProbeValidation):
            probe.prepare_template_probes(**prepare_args(active),
                                          selected_channel_ids=selected)
    freeze.assert_not_called()
    active.commit.assert_not_called()


def test_selection_prepares_only_requested_channel_and_never_another():
    active = session()
    groups = {
        'villa': dict(group(), sender='VILLA_VERDE', origins=['VILLA_VERDE']),
        'cul': dict(group(), sender='SEND_CUL', origins=['SEND_CUL']),
        'tec': group(),
    }
    chosen = ['villa', 'cul']
    with patch.object(probe, '_context', return_value=(context()[0], template(), groups)), \
         patch.object(probe, 'commercial_certifications', return_value={}) as delivered, \
         patch.object(probe, '_no_commercial_phone'), \
         patch.object(probe, '_existing', return_value=None), \
         patch.object(probe, 'preview_qa_manual_http', return_value={'preview_fingerprint': 'a'*64}), \
         patch.object(probe, 'freeze_campaign_v2_qa_manual') as freeze, \
         patch.object(probe, 'template_probe_matrix', return_value={'rows': []}):
        probe.prepare_template_probes(**prepare_args(active),
                                      selected_channel_ids=chosen)
    assert freeze.call_count == 2
    assert {call.kwargs['source_metadata'][probe.KEY]['channel_id'] for call in freeze.call_args_list} == set(chosen)
    assert 'tec' not in str([call.kwargs['source_metadata'] for call in freeze.call_args_list])
    assert set(delivered.call_args.kwargs['groups']) == set(chosen)


def test_commercial_rejection_audit_never_claims_a_qa_attempt():
    rejection = NS(id=290, campaign_v2_id=43, error_code="TEMPLATE_NOT_FOUND",
                   submit_started_at=NOW, submitted_by_user_id=47)
    active = session()
    with patch.object(probe, "_context", return_value=context()), \
         patch.object(probe, "_existing", return_value=None), \
         patch.object(probe, "_previous_version", return_value=None), \
         patch.object(probe, "commercial_certifications", return_value={}), \
         patch.object(probe, "accepted_probe_channels", return_value=frozenset()), \
         patch.object(probe, "last_confirmed_template_rejection", return_value=rejection):
        row = probe.template_probe_matrix(
            campaign_id=42, template_id=7, session=active)["rows"][0]
    assert row["result"] == "RECHAZADA"
    assert row["rejection_source"] == "COMMERCIAL_REJECTION"
    assert row["rejection_campaign_id"] == 43
    assert row["qa_campaign_id"] is None
    assert row["child_id"] == 290
    assert row["actor_user_id"] == 47
    assert row["attempted_at"] == NOW.isoformat()


def test_existing_qa_revision_prefers_latest_and_keeps_original_immutable():
    signature = probe._signature(template())
    base = probe._name(7, signature, "tec")
    rows = [
        NS(id=80, name=base),
        NS(id=81, name=base + "-R2"),
        NS(id=82, name=base + "-R3"),
        NS(id=100, name=base + "-unknown"),
    ]
    active = session()
    active.query.return_value.filter.return_value.all.return_value = rows
    assert probe._existing(7, signature, "tec", active).id == 82
    assert probe._retry_name(7, signature, "tec", rows[0]) == base + "-R2"
    assert probe._retry_name(7, signature, "tec", rows[2]) == base + "-R4"


def test_after_confirmed_template_not_found_new_qa_preserves_failed_history():
    active = session([child(
        status="PROVIDER_ERROR", submit_started_at=NOW,
        submitted_by_user_id=47, error_code="TEMPLATE_NOT_FOUND",
        support_ref="provider-ref-73", provider_response_json={"http_status": 400},
    )])
    previous = campaign()
    previous.name = probe._name(7, probe._signature(template()), "tec")
    captured = {}
    def freeze(**kwargs):
        captured.update(kwargs)
    with patch.object(probe, "_context", return_value=context()), \
         patch.object(probe, "_existing", return_value=previous), \
         patch.object(probe, "_no_commercial_phone"), \
         patch.object(probe, "preview_qa_manual_http", return_value={"preview_fingerprint": "a" * 64}), \
         patch.object(probe, "freeze_campaign_v2_qa_manual", side_effect=freeze) as prepare, \
         patch.object(probe, "template_probe_matrix", return_value={"rows": []}):
        probe.prepare_template_probes(**prepare_args(active), selected_channel_ids=["tec"])
    prepare.assert_called_once()
    assert captured["name"] == previous.name + "-R2"
    assert captured["source_metadata"][probe.KEY]["retry_of_qa_campaign_id"] == previous.id
    assert captured["source_metadata"][probe.KEY]["retry_reason"] == "CONFIRMED_TEMPLATE_NOT_FOUND"
    assert captured["commit"] is False
    active.commit.assert_called_once()


@pytest.mark.parametrize("bad_child", [
    child(status="RECONCILIATION_REQUIRED", submit_started_at=NOW,
          error_code="TEMPLATE_NOT_FOUND", support_ref="unknown",
          submitted_by_user_id=47, provider_response_json={"http_status": 400}),
    child(status="PROVIDER_ERROR", submit_started_at=NOW,
          error_code="UNKNOWN", support_ref="provider-ref",
          submitted_by_user_id=47, provider_response_json={"http_status": 400}),
    child(status="SUBMITTED", submit_started_at=NOW, submitted_at=NOW,
          submitted_by_user_id=47, provider_campaign_id="accepted-iv"),
])
def test_uncertain_or_accepted_qa_cannot_create_another_attempt(bad_child):
    active = session([bad_child])
    previous = campaign()
    previous.name = probe._name(7, probe._signature(template()), "tec")
    with patch.object(probe, "_context", return_value=context()), \
         patch.object(probe, "_existing", return_value=previous), \
         patch.object(probe, "freeze_campaign_v2_qa_manual") as freeze, \
         patch.object(probe, "template_probe_matrix", return_value={"rows": []}):
        probe.prepare_template_probes(**prepare_args(active), selected_channel_ids=["tec"])
    freeze.assert_not_called()


def test_retry_qa_cohort_preparation_is_idempotent_before_send():
    active = session()
    previous = campaign()
    previous.name = probe._name(7, probe._signature(template()), "tec") + "-R2"
    with patch.object(probe, "_context", return_value=context()), \
         patch.object(probe, "_existing", return_value=previous), \
         patch.object(probe, "freeze_campaign_v2_qa_manual") as freeze, \
         patch.object(probe, "template_probe_matrix", return_value={"rows": []}):
        # There is a saved retry cohort without a submitted provider child.
        probe.prepare_template_probes(**prepare_args(active), selected_channel_ids=["tec"])
    freeze.assert_not_called()
