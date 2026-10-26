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
from app.services.marketing_campaign_v2_governed_dispatch_service import (
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
    accepted = 0
    if len(child_by_id) == len(child_ids):
        for child_id in child_ids:
            child = child_by_id[child_id]
            if (child.status == "SUBMITTED" and child.provider_campaign_id
                    and child.submitted_at is not None):
                accepted += 1
            else:
                break
    return {
        "job_id": int(job.id),
        "campaign_id": int(job.campaign_v2_id),
        "execution_id": int(job.execution_id),
        "status": str(job.status),
        "total_pending_at_start": int(job.initial_pending_count),
        "accepted_by_provider": accepted,
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
        accepted_count = sum(child.status == "SUBMITTED" for child in ready)
        if [child.status for child in ready] != (
            ["SUBMITTED"] * accepted_count + ["READY"] * (len(ready) - accepted_count)
        ):
            raise BackgroundJobConflict("Prefijo de envíos no conciliado.")
        if accepted_count:
            if (execution.last_child_id != ready[accepted_count - 1].id
                    or any(child.submitted_at is None or not child.provider_campaign_id
                           for child in ready[:accepted_count])):
                raise BackgroundJobConflict("El prefijo aceptado no coincide con la ejecución.")
        elif execution.last_child_id is not None:
            raise BackgroundJobConflict("Estado inicial inconsistente.")
        suffix = [int(child.id) for child in ready[accepted_count:]]
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
