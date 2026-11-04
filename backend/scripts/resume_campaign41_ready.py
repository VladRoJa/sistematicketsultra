"""One-off governed Campaign #41 continuation, excluding PASEO_2000 #255.

Default is a read-only dry run. --apply makes REAL iVentas requests only for
untouched READY children after the failed child. Neither the original error
nor previously accepted provider identities are modified. Never re-run --apply
after an interrupted or partially successful attempt.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from app import create_app
from app.extensions import db
from app.integrations.iventas.broadcast_provider import IVentasBroadcastProvider
from app.models.marketing import (
    MarketingCampaignV2DispatchApprovalORM,
    MarketingCampaignV2GovernedExecutionORM,
    MarketingCampaignV2ProviderCampaignORM,
)
from app.models.marketing_campaign_v2_background_job import MarketingCampaignV2BackgroundJobORM
from app.models.user_model import UserORM
from app.services.marketing_access import resolve_marketing_access
from app.services.marketing_campaign_v2_contact_gate_service import acquire_campaign_v2_contact_gate
from app.services.marketing_campaign_v2_dispatch_approval_service import (
    _assess_scopes, _database_date,
)
from app.services.marketing_campaign_v2_governed_dispatch_service import manifest_digest
from app.services.marketing_campaign_v2_manifest_service import (
    _assert_manifest, budget_for_existing_approval,
)
from app.services.marketing_campaign_v2_partial_resume_service import (
    PartialResumeReview, continue_ready_children, review_partial_resume,
)
from app.services.marketing_campaign_v2_preflight_service import build_campaign_v2_preflight
from app.services.marketing_campaign_v2_submit_service import _load_campaign_rows

CAMPAIGN_ID = 41
FAILED_CHILD_ID = 255
FAILED_BRANCH = "PASEO_2000"
FAILED_RECIPIENTS = 7994
FAILED_ERROR = "TEMPLATE_NOT_FOUND"
FAILED_SUPPORT_REF = "bc-mw1c1why-phq041"
FAILED_CHANNEL = "6a299740e83fa20008b59c9a"
TEMPLATE_NAME = "promos_noviembre_v"
CONFIRMATION = "CONTINUAR_41_SIN_255"


class RecoveryBlocked(RuntimeError):
    """Do not attempt any provider HTTP after an inconsistent audit."""


@dataclass(frozen=True)
class RecoveryReview:
    plan_review: PartialResumeReview
    approval_id: int
    execution_id: int
    digest: str
    quota_basis: str | None
    submitted: int
    submitted_recipients: int
    held: int


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RecoveryBlocked(message)


def _check_original_order(rows: list, failed_id: int) -> list:
    """Prove one failed boundary: submitted prefix, failed row, READY suffix."""
    ids = [int(row.id) for row in rows]
    _require(len(ids) == len(set(ids)) and failed_id in ids,
             "El lote omitido falta o existen IDs duplicados.")
    pos = ids.index(failed_id)
    _require(pos > 0 and pos < len(rows) - 1,
             "No existe prefijo enviado o sufijo pendiente.")
    _require(all(row.status == "SUBMITTED" and row.provider_campaign_id
                 and row.submitted_at is not None for row in rows[:pos]),
             "El prefijo aceptado cambió.")
    _require(rows[pos].status == "PROVIDER_ERROR",
             "El error original ya no está intacto.")
    _require(all(row.status == "READY" and row.provider_campaign_id is None
                 and row.submit_started_at is None and row.submitted_at is None
                 for row in rows[pos + 1:]),
             "Hay intentos posteriores o cambió un READY. No repetir.")
    return rows[pos + 1:]


def _review() -> RecoveryReview:
    now = datetime.now(timezone.utc)
    approval = (
        db.session.query(MarketingCampaignV2DispatchApprovalORM)
        .filter(MarketingCampaignV2DispatchApprovalORM.campaign_v2_id == CAMPAIGN_ID)
        .order_by(MarketingCampaignV2DispatchApprovalORM.revision_no.desc())
        .first()
    )
    _require(approval is not None, "No existe aprobación gobernada para #41.")
    execution = (
        db.session.query(MarketingCampaignV2GovernedExecutionORM)
        .filter(MarketingCampaignV2GovernedExecutionORM.approval_id == approval.id)
        .one_or_none()
    )
    _require(execution is not None and execution.status == "REVIEW_REQUIRED"
             and execution.last_child_id == FAILED_CHILD_ID,
             "La ejecución no corresponde al error #255 detenido.")
    digest = manifest_digest(approval.manifest_json)
    _require(execution.manifest_digest == digest
             and _database_date(execution.confirmed_at) <
             _database_date(approval.expires_at),
             "Aprobación/digest/ventana originales incompatibles.")

    jobs = (
        db.session.query(MarketingCampaignV2BackgroundJobORM)
        .filter(MarketingCampaignV2BackgroundJobORM.campaign_v2_id == CAMPAIGN_ID)
        .all()
    )
    _require(len(jobs) <= 1, "Existen múltiples trabajos; revisión obligatoria.")
    job = jobs[0] if jobs else None
    if job is not None:
        _require(job.status == "REVIEW_REQUIRED"
                 and job.approval_id == approval.id
                 and job.execution_id == execution.id
                 and job.manifest_digest == digest
                 and job.current_child_id == FAILED_CHILD_ID
                 and job.stop_requested_at is None,
                 "El trabajo background está activo, cambiado o detenido.")
    plan = build_campaign_v2_preflight(
        campaign_id=CAMPAIGN_ID, template_id=int(approval.template_id),
        allowed_sucursal_keys=None, session=db.session, now=now,
    )
    budget = budget_for_existing_approval(
        plan=plan, approval=approval, session=db.session, now=now,
    )
    manifest = _assert_manifest(plan, budget, approval)
    _require(plan.ready and plan.provider == "IVENTAS"
             and plan.mode == "IMMEDIATE"
             and plan.dispatch_fingerprint == approval.dispatch_fingerprint
             and all(batch.template_name == TEMPLATE_NAME for batch in plan.batches),
             "Preflight / plantilla / fingerprint cambiaron.")
    children = _load_campaign_rows(campaign_id=CAMPAIGN_ID, session=db.session)
    by_name = {row.sucursal_canon: row for row in children}
    _require(len(by_name) == len(children) == len(plan.batches),
             "Identidades de sucursales duplicadas o incompletas.")
    failed = by_name.get(FAILED_BRANCH)
    _require(failed is not None and int(failed.id) == FAILED_CHILD_ID
             and int(failed.recipient_count) == FAILED_RECIPIENTS
             and failed.status == "PROVIDER_ERROR"
             and failed.error_code == FAILED_ERROR
             and failed.support_ref == FAILED_SUPPORT_REF
             and failed.template_name == TEMPLATE_NAME
             and failed.provider_channel_id == FAILED_CHANNEL
             and failed.provider_campaign_id is None
             and failed.submitted_at is None
             and failed.submit_started_at is not None
             and not failed.reconciliation_resolution
             and int(failed.retry_attempt_count or 0) == 0
             and not failed.retry_history_json
             and (failed.provider_response_json or {}).get("http_status") == 400,
             "El rechazo iVentas #255 no coincide con la evidencia autorizada.")
    _require(_database_date(failed.submit_started_at) <=
             _database_date(approval.expires_at),
             "El fallo original ocurrió fuera de la autorización.")

    planned_ready = [by_name[batch.sucursal_canon] for batch in plan.batches
                     if manifest[batch.sucursal_canon]["planned_status"] == "READY"]
    pending = _check_original_order(planned_ready, FAILED_CHILD_ID)
    _require(manifest[FAILED_BRANCH]["planned_status"] == "READY"
             and len(pending) > 0,
             "No hay pendientes dentro del manifiesto autorizado.")
    if job is not None:
        job_ids = list(job.pending_child_ids or [])
        ready_ids = [int(row.id) for row in planned_ready]
        _require(bool(job_ids)
                 and len(job_ids) == len(set(job_ids))
                 and job_ids == ready_ids[-len(job_ids):]
                 and FAILED_CHILD_ID in job_ids
                 and job.last_accepted_child_id == planned_ready[
                     ready_ids.index(FAILED_CHILD_ID) - 1].id,
                 "El trabajo background no concuerda con el orden histórico.")

    expected_submitted = {}
    expected_failed = {}
    expected_ready = {}
    expected_held = {}
    for batch in plan.batches:
        row = by_name[batch.sucursal_canon]
        state = manifest[batch.sucursal_canon]["planned_status"]
        if state == "HELD":
            _require(row.status == "HELD", "Un HELD fue modificado.")
            expected_held[row.sucursal_canon] = (
                int(row.recipient_count), "CHANNEL_DAILY_QUOTA",
            )
        elif row.status == "SUBMITTED":
            expected_submitted[row.sucursal_canon] = (
                int(row.recipient_count), str(row.provider_campaign_id),
            )
        elif row.id == FAILED_CHILD_ID:
            expected_failed[row.sucursal_canon] = (
                FAILED_RECIPIENTS, FAILED_ERROR, FAILED_SUPPORT_REF,
            )
        elif row.status == "READY":
            expected_ready[row.sucursal_canon] = int(row.recipient_count)
        else:
            raise RecoveryBlocked("Existe otro estado inesperado en campaña #41.")
    _require(len(expected_failed) == 1 and len(expected_ready) == len(pending),
             "Se detectaron omisiones adicionales o pendientes distintos.")
    complete = review_partial_resume(
        campaign_id=CAMPAIGN_ID,
        template_id=int(approval.template_id),
        expected_fingerprint=approval.dispatch_fingerprint,
        expected_submitted=expected_submitted,
        expected_failed=expected_failed,
        expected_ready=expected_ready,
        expected_held=expected_held,
        session=db.session,
    )
    _require([int(x.child_id) for x in complete.ready_children] ==
             [int(x.id) for x in pending],
             "Orden de READY distinto al autorizado.")
    return RecoveryReview(
        plan_review=complete,
        approval_id=int(approval.id), execution_id=int(execution.id),
        digest=digest, quota_basis=(approval.manifest_json or {}).get("basis"),
        submitted=len(expected_submitted),
        submitted_recipients=sum(x[0] for x in expected_submitted.values()),
        held=len(expected_held),
    )


def _check_current_capacity(review: RecoveryReview, batches: tuple) -> None:
    # The approval may be expired. Never assume its old capacity is still free.
    # Acquire the shared contact gate before the fresh quota assessment.
    acquire_campaign_v2_contact_gate(db.session)
    scoped = replace(review.plan_review.plan, batches=batches)
    _assess_scopes(
        scoped, session=db.session, timestamp=datetime.now(timezone.utc),
        ignore_campaign_id=None, basis_preference=review.quota_basis,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="Envía realmente SOLO los READY posteriores a #255")
    parser.add_argument("--confirm", default="",
                        help="Confirmación literal requerida para --apply")
    args = parser.parse_args()
    app = create_app()
    with app.app_context():
        try:
            actor = UserORM.get_by_username("admicorp")
            _require(actor is not None, "No existe operador admicorp.")
            access = resolve_marketing_access(actor)
            _require(access.is_global and access.can_send_campaigns
                     and access.can_manage_dispatch_config,
                     "El operador no tiene permisos globales de despacho.")
            review = _review()
            pending = review.plan_review.ready_children
            print("CAMPAÑA = 41", flush=True)
            print("MANIFIESTO = " + review.digest, flush=True)
            print("ACEPTADOS_PREVIOS = " + str(review.submitted) +
                  " / " + str(review.submitted_recipients), flush=True)
            print("OMITIDO = PASEO_2000 | #255 | 7994 | PROVIDER_ERROR", flush=True)
            print("HELD = " + str(review.held), flush=True)
            print("PENDIENTES = " + str(len(pending)) + " / " +
                  str(sum(len(x.batch.recipients) for x in pending)), flush=True)
            for child in pending:
                print("READY =", child.child_id, child.batch.sucursal_canon,
                      len(child.batch.recipients), flush=True)

            # Read-only precheck; no provider object is constructed on dry-run.
            try:
                _check_current_capacity(review, tuple(x.batch for x in pending))
            finally:
                db.session.rollback()
            print("CUOTA_ACTUAL = VALIDADA", flush=True)

            if not args.apply:
                print("ENVÍO_REAL = NO EJECUTADO", flush=True)
                return 0
            _require(args.confirm == CONFIRMATION,
                     "Falta confirmación literal para envío real.")
            _require(app.config.get("CAMPAIGN_V2_PROVIDER_SEND_ENABLED") is True
                     and app.config.get("CAMPAIGN_V2_GOVERNED_DISPATCH_ENABLED") is True,
                     "Kill switches de envío no están habilitados en este proceso.")
            key = str(app.config.get("IVENTAS_CAMPAIGN_SEND_API_KEY") or "")
            base_url = str(app.config.get("IVENTAS_CAMPAIGN_SEND_API_BASE_URL") or "").rstrip("/")
            _require(key.startswith("ivk_live_") and base_url == "https://rest.iventas.mx",
                     "Configuración iVentas live inesperada.")
            provider = IVentasBroadcastProvider(api_key=key, base_url=base_url)
            results = []
            for child in pending:
                try:
                    _check_current_capacity(review, (child.batch,))
                    # The helper durably rechecks READY and the contact gate,
                    # commits SUBMITTING before HTTP, and stops on ambiguity.
                    outcome = continue_ready_children(
                        review=replace(review.plan_review, ready_children=(child,)),
                        actor_user_id=int(actor.id), provider=provider,
                        send_enabled=True, session=db.session,
                    )[0]
                except Exception:
                    db.session.rollback()
                    print("DETENIDO = revisión obligatoria; NO REEJECUTAR --apply",
                          flush=True)
                    raise
                results.append(outcome)
                print("RESULTADO =", outcome[0], outcome[1],
                      outcome[2] or "-", flush=True)
                if outcome[1] != "SUBMITTED":
                    print("DETENIDO = resultado no aceptado; NO REEJECUTAR",
                          flush=True)
                    return 2
            print("ACEPTADOS_NUEVOS = " + str(Counter(x[1] for x in results)["SUBMITTED"]),
                  flush=True)
            print("CAMPAÑA_41 = CONTINUACIÓN_CON_PASEO_2000_EXCLUIDO", flush=True)
            print("EJECUCIÓN_ORIGINAL = REVIEW_REQUIRED (sin borrar error)", flush=True)
            return 0
        finally:
            db.session.remove()


if __name__ == "__main__":
    raise SystemExit(main())
