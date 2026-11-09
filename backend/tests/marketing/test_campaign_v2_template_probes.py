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
    def query(model):
        q = MagicMock()
        q.filter_by.return_value = q
        q.filter.return_value = q
        if model is probe.Recipient:
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
