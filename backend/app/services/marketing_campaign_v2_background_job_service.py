"""Issue #1129 M1b: non-sending, durable governed dispatch mandates.

All create/stop operations are server-authorized and PostgreSQL-only.
This service NEVER imports a provider client, sends messages or stores a password.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db
from app.services.marketing_campaign_v2_contact_gate_service import acquire_campaign_v2_contact_gate
from app.models.marketing import (
    MarketingCampaignV2ORM,
    MarketingCampaignV2GovernedExecutionORM,
    MarketingCampaignV2ProviderCampaignORM,
)
from app.models.marketing_campaign_v2_background_job import (
    MarketingCampaignV2BackgroundJobORM as Job,
    MarketingCampaignV2BackgroundJobEventORM as Event,
)
from app.services.marketing_campaign_v2_contact_gate_service import (
    CampaignV2ContactGateConflict,
    acquire_campaign_v2_contact_gate,
)
from app.services.marketing_campaign_v2_confirmed_rejection import confirmed_rejected_child
from app.services.marketing_campaign_v2_governed_dispatch_service import (
    GovernedDispatchConflict, _verified_prefix_and_suffix,
    _check_child_identities, _locked_review, manifest_digest,
)


class BackgroundJobValidation(ValueError):
    pass


class BackgroundJobConflict(RuntimeError):
    pass


class BackgroundJobNotFound(LookupError):
    pass


class BackgroundJobDisabled(RuntimeError):
    pass


BLOCKING_STATES = ("QUEUED", "RUNNING", "STOP_REQUESTED", "REVIEW_REQUIRED")


def _utc(value: datetime | None = None) -> datetime:
    timestamp = datetime.now(timezone.utc) if value is None else value
    if not isinstance(timestamp, datetime) or timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise BackgroundJobValidation("Se requiere tiempo con zona horaria.")
    return timestamp.astimezone(timezone.utc)


def _deadline(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise BackgroundJobConflict("Autorización sin zona horaria.")
    return value.astimezone(timezone.utc)


def _ids(value: Any) -> list[int]:
    if (not isinstance(value, list) or not 1 <= len(value) <= 30
            or any(type(item) is not int or item <= 0 for item in value)
            or len(set(value)) != len(value)):
        raise BackgroundJobValidation("Lotes inválidos o duplicados.")
    return value


def _hex(value: Any, label: str) -> str:
    if (not isinstance(value, str) or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)):
        raise BackgroundJobValidation(f"{label} inválida.")
    return value


def _pg(session: Any) -> None:
    if session.get_bind().dialect.name != "postgresql":
        raise BackgroundJobConflict("Esta operación requiere PostgreSQL.")


def _job(session: Any, campaign_id: int, job_id: int, actor_user_id: int, *,
         locked: bool = False) -> Job:
    query = session.query(Job).filter(
        Job.id == job_id, Job.campaign_v2_id == campaign_id,
        Job.operator_user_id == actor_user_id,
    )
    row = (query.with_for_update() if locked else query).one_or_none()
    if row is None:
        raise BackgroundJobNotFound("Ejecución no encontrada.")
    return row


def _snapshot(session: Any, job: Job) -> dict:
    child_ids = _ids(list(job.pending_child_ids))
    children = session.query(MarketingCampaignV2ProviderCampaignORM).filter(
        MarketingCampaignV2ProviderCampaignORM.id.in_(child_ids),
        MarketingCampaignV2ProviderCampaignORM.campaign_v2_id == job.campaign_v2_id,
    ).all()
    child_by_id = {int(child.id): child for child in children}
    accepted = sum(
        bool(row.status == "SUBMITTED" and row.provider_campaign_id and
             row.submitted_at is not None)
        for row in child_by_id.values()
    ) if len(child_by_id) == len(child_ids) else 0
    failed = sum(confirmed_rejected_child(row) for row in child_by_id.values())
    uncertain = sum(row.status in {"RECONCILIATION_REQUIRED", "SUBMITTING"}
                    for row in child_by_id.values())
    untouched = sum(row.status == "READY" for row in child_by_id.values())
    return {
        "job_id": int(job.id),
        "campaign_id": int(job.campaign_v2_id),
        "execution_id": int(job.execution_id),
        "status": str(job.status),
        "total_pending_at_start": int(job.initial_pending_count),
        "accepted_by_provider": accepted,
        "confirmed_rejected": failed,
        "uncertain_results": uncertain,
        "unattempted": untouched,
        "current_child_id": int(job.current_child_id) if job.current_child_id is not None else None,
        "stop_requested": job.status == "STOP_REQUESTED",
        "reason_code": job.stop_reason_code,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        "delivery_confirmed": False,
        "may_auto_retry": False,
        "may_auto_resume": False,
    }


def enqueue_background_job(
    *, campaign_id: int, approval_id: int, execution_id: int,
    expected_manifest_digest: str, expected_pending_child_ids: Any,
    request_key: str, confirmation: str, confirmed: bool,
    actor_user_id: int, allowed_sucursal_keys: Any,
    session: Any | None = None, now: datetime | None = None,
) -> tuple[dict, bool]:
    """Persist a single exact-scope command; NEVER invoke the provider.

    The caller MUST validate the JWT actor, GLOBAL/config/send capabilities,
    the operator password and all feature switches before entering this code.
    """
    if any(type(value) is not int or value <= 0 for value in (
        campaign_id, approval_id, execution_id, actor_user_id,
    )):
        raise BackgroundJobValidation("Identificadores inválidos.")
    pending_ids = _ids(expected_pending_child_ids)
    _hex(expected_manifest_digest, "Huella de manifiesto")
    _hex(request_key, "Llave de solicitud")
    if confirmed is not True or confirmation != f"ENVIAR PENDIENTES {len(pending_ids)}":
        raise BackgroundJobValidation("Confirmación explícita incorrecta.")
    session = session if session is not None else db.session
    _pg(session)
    at = _utc(now)
    try:
        # Shared lock order with governed dispatch: contact -> campaign ->
        # approval/quota -> execution -> child. Never hold a lock during HTTP.
        acquire_campaign_v2_contact_gate(session)
        campaign = session.query(MarketingCampaignV2ORM).filter(
            MarketingCampaignV2ORM.id == campaign_id,
        ).with_for_update().one_or_none()
        if campaign is None:
            raise BackgroundJobNotFound("Campaña no encontrada.")

        existing = session.query(Job).filter(
            Job.execution_id == execution_id,
        ).with_for_update().one_or_none()
        if existing is not None:
            if not (
                int(existing.campaign_v2_id) == campaign_id
                and int(existing.approval_id) == approval_id
                and int(existing.operator_user_id) == actor_user_id
                and existing.request_key == request_key
                and existing.manifest_digest == expected_manifest_digest
                and list(existing.pending_child_ids) == pending_ids
            ):
                raise BackgroundJobConflict("Ya existe un mandato distinto para esta ejecución.")
            return _snapshot(session, existing), False

        blocking = session.query(Job.id).filter(
            Job.campaign_v2_id == campaign_id,
            Job.status.in_(BLOCKING_STATES),
        ).first()
        if blocking is not None:
            raise BackgroundJobConflict("La campaña ya tiene un envío o revisión pendiente.")

        approval, plan, manifest, children, digest = _locked_review(
            campaign_id=campaign_id, session=session, now=at,
            allowed_sucursal_keys=allowed_sucursal_keys,
            ignore_self=True, allow_started_continuation=True,
        )
        if int(approval.id) != approval_id or digest != expected_manifest_digest:
            raise BackgroundJobConflict("La aprobación no coincide con la vigente.")
        if int(approval.campaign_v2_id) != campaign_id:
            raise BackgroundJobConflict("Aprobación ajena a la campaña.")
        execution = session.query(MarketingCampaignV2GovernedExecutionORM).filter(
            MarketingCampaignV2GovernedExecutionORM.id == execution_id,
            MarketingCampaignV2GovernedExecutionORM.approval_id == approval_id,
        ).with_for_update().one_or_none()
        if execution is None or execution.status != "AUTHORIZED":
            raise BackgroundJobConflict("La ejecución no está autorizada para comenzar.")
        expires_at = min(_deadline(approval.expires_at), _deadline(execution.expires_at))
        if (_utc(None) if now is None else at) >= expires_at:
            raise BackgroundJobConflict("Venció la autorización para iniciar.")
        if execution.manifest_digest != digest or manifest_digest(approval.manifest_json) != digest:
            raise BackgroundJobConflict("Cambió el manifiesto autorizado.")

        _check_child_identities(plan=plan, manifest=manifest, children=children)
        by_branch = {child.sucursal_canon: child for child in children}
        ready = [by_branch[batch.sucursal_canon] for batch in plan.batches
                 if manifest[batch.sucursal_canon]["planned_status"] == "READY"]
        # All previous attempts must be an ordered, immutable prefix. Confirmed
        # template rejections are terminal; uncertain children block enqueue.
        try:
            prior, untouched = _verified_prefix_and_suffix(
                ready=ready, execution=execution,
            )
        except GovernedDispatchConflict as exc:
            raise BackgroundJobConflict(str(exc)) from exc
        suffix = [int(child.id) for child in untouched]
        if not suffix or suffix != pending_ids:
            raise BackgroundJobConflict("Los lotes pendientes cambiaron.")
        if (_utc(None) if now is None else at) >= expires_at:
            raise BackgroundJobConflict("La autorización venció durante la comprobación.")
        if session.query(Job.id).filter(Job.request_key == request_key).first():
            raise BackgroundJobConflict("Llave de solicitud utilizada.")

        job = Job(
            campaign_v2_id=campaign_id, approval_id=approval_id,
            execution_id=execution_id, operator_user_id=actor_user_id,
            request_key=request_key, manifest_digest=digest,
            pending_child_ids=suffix,
            pending_children_digest=hashlib.sha256(
                json.dumps(suffix, separators=(",", ":")).encode("ascii")
            ).hexdigest(),
            initial_pending_count=len(suffix), status="QUEUED",
            created_at=at, updated_at=at, start_deadline_at=expires_at,
        )
        session.add(job)
        session.flush()
        session.add(Event(job_id=job.id, event_no=1, event_kind="ENQUEUED",
                          actor_user_id=actor_user_id, occurred_at=at))
        session.commit()
        return _snapshot(session, job), True
    except CampaignV2ContactGateConflict as exc:
        session.rollback()
        raise BackgroundJobConflict("No fue posible validar la exclusión de contactos.") from exc
    except (IntegrityError, SQLAlchemyError) as exc:
        session.rollback()
        raise BackgroundJobConflict("Conflicto de persistencia al registrar el trabajo.") from exc
    except Exception:
        session.rollback()
        raise



def resolve_unattempted_review(
    *, campaign_id: int, job_id: int, actor_user_id: int,
    confirmation: str, session: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Audit-close a failed job ONLY when no provider claim was ever committed.

    This is not a retry, approval, or send. A new approval/execution must pass
    the existing reauthorization flow before any future dispatch.
    """
    if any(type(value) is not int or value <= 0 for value in
           (campaign_id, job_id, actor_user_id)):
        raise BackgroundJobValidation("Identificadores inválidos.")
    if confirmation != f"CONFIRMAR SIN ENVIO {campaign_id} {job_id}":
        raise BackgroundJobValidation("Confirmación de ausencia de envío incorrecta.")
    active = session if session is not None else db.session
    _pg(active)
    at = _utc(now)
    try:
        # Keep the same global gate/campaign lock order as reauthorization and
        # governed dispatch; this never calls an external provider.
        acquire_campaign_v2_contact_gate(active)
        campaign = active.execute(db.text(
            "SELECT id FROM marketing_campaign_v2_campaigns "
            "WHERE id = :campaign_id FOR UPDATE"
        ), {"campaign_id": campaign_id}).first()
        if campaign is None:
            raise BackgroundJobNotFound("Campaña no encontrada.")
        job = _job(active, campaign_id, job_id, actor_user_id, locked=True)
        if job.status == "STOPPED" and job.stop_reason_code == "NO_ATTEMPT_VERIFIED":
            active.rollback()
            return {"job_id": job_id, "campaign_id": campaign_id,
                    "status": "STOPPED", "already_resolved": True,
                    "requires_reauthorization": True, "provider_calls": 0}
        if (job.status != "REVIEW_REQUIRED" or job.last_accepted_child_id is not None
                or job.finished_at is None or job.worker_lease_until is not None):
            raise BackgroundJobConflict("El trabajo no admite cierre sin intentos.")
        ids = job.pending_child_ids
        if (not isinstance(ids, list) or not 1 <= len(ids) <= 30
                or any(type(value) is not int or value <= 0 for value in ids)
                or len(set(ids)) != len(ids) or len(ids) != job.initial_pending_count
                or job.pending_children_digest != hashlib.sha256(
                    json.dumps(ids, separators=(",", ":")).encode("ascii")
                ).hexdigest()
                or (job.current_child_id is not None and
                    job.current_child_id not in ids)):
            raise BackgroundJobConflict("El mandato original no es íntegro.")

        execution = active.execute(db.text("""
            SELECT approval_id, status, last_child_id, expires_at, manifest_digest
            FROM marketing_campaign_v2_governed_executions
            WHERE id = :execution_id FOR UPDATE
        """), {"execution_id": job.execution_id}).mappings().one_or_none()
        approval = active.execute(db.text("""
            SELECT id, expires_at, manifest_json
            FROM marketing_campaign_v2_dispatch_approvals
            WHERE id = :approval_id AND campaign_v2_id = :campaign_id FOR UPDATE
        """), {"approval_id": job.approval_id,
               "campaign_id": campaign_id}).mappings().one_or_none()
        latest = active.execute(db.text("""
            SELECT id FROM marketing_campaign_v2_dispatch_approvals
            WHERE campaign_v2_id = :campaign_id
            ORDER BY revision_no DESC LIMIT 1
        """), {"campaign_id": campaign_id}).scalar()
        if (execution is None or approval is None
                or latest != job.approval_id
                or execution["approval_id"] != job.approval_id
                or execution["manifest_digest"] != job.manifest_digest
                or manifest_digest(approval["manifest_json"]) != job.manifest_digest
                or execution["status"] != "AUTHORIZED"
                or execution["last_child_id"] is not None
                or _utc(execution["expires_at"]) > at
                or _utc(approval["expires_at"]) > at):
            raise BackgroundJobConflict(
                "La ejecución no está vencida, íntegra o sin intentos.")

        # FOR UPDATE gives a stable view of ALL children, not just the pending
        # manifest; a hidden SUBMITTING/uncertain child must fail closed.
        children = active.execute(db.text("""
            SELECT id, status, submit_started_at, submitted_at,
                   submitted_by_user_id, provider_campaign_id, error_code,
                   support_ref, provider_response_json, retry_history_json,
                   retry_attempt_count, reconciliation_resolution, reconciled_at,
                   provider_deduplicated
            FROM marketing_campaign_v2_provider_campaigns
            WHERE campaign_v2_id = :campaign_id ORDER BY id FOR UPDATE
        """), {"campaign_id": campaign_id}).mappings().all()
        ready = [int(row["id"]) for row in children if row["status"] == "READY"]
        if (not children or set(ready) != set(ids) or len(ready) != len(ids)
                or any(row["status"] not in ("READY", "HELD") or
                    row["submit_started_at"] is not None or
                    row["submitted_at"] is not None or
                    row["submitted_by_user_id"] is not None or
                    row["provider_campaign_id"] is not None or
                    row["error_code"] is not None or
                    row["support_ref"] is not None or
                    bool(row["provider_response_json"]) or
                    bool(row["retry_history_json"]) or
                    int(row["retry_attempt_count"] or 0) != 0 or
                    row["reconciliation_resolution"] is not None or
                    row["reconciled_at"] is not None or
                    row["provider_deduplicated"] is not None
                    for row in children)):
            raise BackgroundJobConflict(
                "Hay evidencia de envío o los lotes cambiaron; concilia antes de continuar.")

        events = (active.query(Event).filter(Event.job_id == job.id)
                  .order_by(Event.event_no).with_for_update().all())
        kinds = [event.event_kind for event in events]
        if (kinds not in (["ENQUEUED", "REVIEW_REQUIRED"],
                          ["ENQUEUED", "STARTED", "REVIEW_REQUIRED"])
                or [event.event_no for event in events] !=
                list(range(1, len(events) + 1))):
            raise BackgroundJobConflict(
                "El historial indica otra actividad o no está íntegro.")

        job.status = "STOPPED"
        job.stop_reason_code = "NO_ATTEMPT_VERIFIED"
        job.current_child_id = None
        job.worker_lease_until = None
        job.finished_at = at
        job.updated_at = at
        active.add(Event(
            job_id=job.id, event_no=len(events) + 1,
            event_kind="STOPPED", actor_user_id=actor_user_id,
            reason_code="NO_ATTEMPT_VERIFIED", occurred_at=at,
        ))
        active.commit()
        return {"job_id": job_id, "campaign_id": campaign_id,
                "status": "STOPPED", "already_resolved": False,
                "requires_reauthorization": True, "provider_calls": 0}
    except Exception:
        active.rollback()
        raise


def get_background_job(*, campaign_id: int, job_id: int, actor_user_id: int,
                       session: Any | None = None) -> dict:
    if any(type(value) is not int or value <= 0 for value in (
        campaign_id, job_id, actor_user_id,
    )):
        raise BackgroundJobValidation("Identificadores inválidos.")
    session = session if session is not None else db.session
    return _snapshot(session, _job(session, campaign_id, job_id, actor_user_id))


def list_background_jobs(*, operator_user_id: int, session: Any | None = None,
                         limit: int = 20) -> list[dict]:
    if (type(operator_user_id) is not int or operator_user_id <= 0
            or type(limit) is not int or not 1 <= limit <= 20):
        raise BackgroundJobValidation("Consulta inválida.")
    session = session if session is not None else db.session
    # Live or unresolved jobs cannot vanish behind newer completed work.
    important = session.query(Job).filter(
        Job.operator_user_id == operator_user_id,
        Job.status.in_(BLOCKING_STATES),
    ).order_by(Job.updated_at.desc()).limit(limit).all()
    count = limit - len(important)
    history = (session.query(Job).filter(
        Job.operator_user_id == operator_user_id,
        Job.status.in_(("STOPPED", "COMPLETED")),
    ).order_by(Job.updated_at.desc()).limit(count).all()) if count else []
    return [_snapshot(session, job) for job in important + history]


def stop_background_job(*, campaign_id: int, job_id: int, actor_user_id: int,
                        session: Any | None = None, now: datetime | None = None) -> dict:
    if any(type(value) is not int or value <= 0 for value in (
        campaign_id, job_id, actor_user_id,
    )):
        raise BackgroundJobValidation("Identificadores inválidos.")
    session = session if session is not None else db.session
    _pg(session)
    at = _utc(now)
    try:
        job = _job(session, campaign_id, job_id, actor_user_id, locked=True)
        if job.status == "QUEUED":
            job.status = "STOPPED"
            job.stop_requested_at = at
            job.finished_at = at
            job.updated_at = at
            job.stop_reason_code = "OPERATOR_STOP"
            session.add(Event(job_id=job.id, event_no=2, event_kind="STOP_REQUESTED",
                              actor_user_id=actor_user_id, occurred_at=at))
            session.add(Event(job_id=job.id, event_no=3, event_kind="STOPPED",
                              actor_user_id=actor_user_id, occurred_at=at))
            session.commit()
        elif job.status == "RUNNING":
            job.status = "STOP_REQUESTED"
            job.stop_requested_at = at
            job.updated_at = at
            next_event = (session.query(Event.event_no)
                          .filter(Event.job_id == job.id)
                          .order_by(Event.event_no.desc()).limit(1).scalar() or 0) + 1
            session.add(Event(job_id=job.id, event_no=next_event,
                              event_kind="STOP_REQUESTED", actor_user_id=actor_user_id,
                              occurred_at=at))
            session.commit()
        # Idempotent terminal or already STOP_REQUESTED; no replay.
        return _snapshot(session, job)
    except (IntegrityError, SQLAlchemyError) as exc:
        session.rollback()
        raise BackgroundJobConflict("Conflicto al detener el trabajo.") from exc
    except Exception:
        session.rollback()
        raise
