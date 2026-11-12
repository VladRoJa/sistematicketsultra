"""Opt-in, independently governed daily cobranza per branch.

No HTTP/provider calls here. A separate Campaign V2 job is queued for each
branch so uncertain provider outcomes cannot hold unrelated branches hostage.
Off by default; never changes the fixed one-day Villas del Rey pilot.
"""
from __future__ import annotations

import io
import logging
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any

from flask import current_app
from openpyxl import load_workbook
from sqlalchemy import func

from app.extensions import db
from app.models.marketing import MarketingCampaignV2ORM as Campaign, MarketingCampaignV2RecipientORM as Recipient
from app.models.user_model import UserORM
from app.services.marketing_access import resolve_marketing_access
from app.services.marketing_campaign_v2_cobranza_send_service import enqueue_cobranza_send
from app.services.marketing_campaign_v2_dispatch_branch_service import resolve_dispatch_branch_key
from app.services.marketing_campaign_v2_preflight_service import build_campaign_v2_preflight
from app.utils.warehouse_audit import log_warehouse_audit
from app.warehouse.jobs.cobranza_iventas_auto_pilot import DISPATCH_FLAGS, PILOT_DATE
from app.warehouse.jobs.cobranza_iventas_preparation import (
    CAMPAIGN_PREFIX, JOB_KEY, build_import_bytes, prepare_cobranza_iventas_campaign,
)

LOG = logging.getLogger(__name__)
AUDIT_ACTION = "COBRANZA_BRANCH_AUTO"
MAX_BRANCHES = 30


class MultiBranchBlocked(ValueError):
    """Closed before provider dispatch; requires operator review."""


@dataclass(frozen=True)
class MultiBranchConfig:
    start_date: date
    branch_keys: tuple[str, ...]
    operator_id: int
    max_recipients_per_branch: int
    max_daily_recipients: int


def multi_branch_config(day: date) -> MultiBranchConfig | None:
    """Require an explicit future rollout, branch roster and bounded budget."""
    if os.getenv("COBRANZA_IVENTAS_MULTI_BRANCH_ENABLED", "").strip().lower() != "true":
        return None
    try:
        start = date.fromisoformat(os.environ["COBRANZA_IVENTAS_MULTI_BRANCH_START_DATE"])
        actor = int(os.environ["COBRANZA_IVENTAS_MULTI_BRANCH_OPERATOR_ID"])
        per_branch = int(os.environ["COBRANZA_IVENTAS_MULTI_BRANCH_MAX_RECIPIENTS_PER_BRANCH"])
        total = int(os.environ["COBRANZA_IVENTAS_MULTI_BRANCH_MAX_DAILY_RECIPIENTS"])
        raw_keys = os.environ["COBRANZA_IVENTAS_MULTI_BRANCH_KEYS"].split(",")
    except (ValueError, KeyError) as exc:
        raise MultiBranchBlocked("Configuración multicucursal incompleta.") from exc
    keys = tuple(key.strip() for key in raw_keys)
    if (start <= PILOT_DATE or actor <= 0 or not 1 <= len(keys) <= MAX_BRANCHES
            or len(keys) != len(set(keys))
            or any(not re.fullmatch(r"[A-Z0-9_]{2,100}", key) for key in keys)
            or not 1 <= per_branch <= 10000
            or not 1 <= total <= 100000
            or per_branch > total):
        raise MultiBranchBlocked("Fecha, sucursales o límites multicucursal inválidos.")
    if day < start:
        return None
    return MultiBranchConfig(start, keys, actor, per_branch, total)


def _require_global_authorization(settings: MultiBranchConfig) -> None:
    if not all(current_app.config.get(flag) is True for flag in DISPATCH_FLAGS):
        raise MultiBranchBlocked("Los controles de envío gobernado no están habilitados.")
    actor = db.session.get(UserORM, settings.operator_id)
    try:
        access = resolve_marketing_access(actor)
    except Exception as exc:
        raise MultiBranchBlocked("La identidad técnica no tiene acceso.") from exc
    if not all((
        access.is_global, access.can_manage_campaigns, access.can_preflight_campaigns,
        access.can_manage_dispatch_config, access.can_send_campaigns,
    )):
        raise MultiBranchBlocked("La identidad técnica carece de permisos globales.")


def _extract_phones(artifact: dict[str, Any]) -> set[str]:
    """Reuse the existing Excel normalizer; never guess missing columns."""
    payload, _ = build_import_bytes([artifact])
    workbook = load_workbook(io.BytesIO(payload), read_only=True, data_only=True)
    try:
        return {str(row[1]) for row in list(workbook.active.values)[1:] if row[1]}
    finally:
        workbook.close()


def _index_daily_artifacts(
    artifacts: list[dict[str, Any]], branches: tuple[str, ...],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, frozenset[str]], dict[str, str], int]:
    """Index all branches, including unselected ones, to exclude cross-branch overlaps."""
    files: dict[str, list[dict[str, Any]]] = defaultdict(list)
    observed: dict[str, set[str]] = defaultdict(set)
    invalid: dict[str, str] = {}
    owners: dict[str, set[str]] = defaultdict(set)
    for artifact in artifacts:
        raw = str(artifact.get("sucursal_raw") or "").strip()
        try:
            resolved = resolve_dispatch_branch_key(raw, session=db.session)
            canonical = str(resolved.sucursal_canon) if resolved else ""
        except Exception:
            canonical = ""
            db.session.rollback()
        # Unknown branches are still included in the overlap check if parseable.
        ownership = canonical or "UNKNOWN:" + raw
        try:
            phones = _extract_phones(artifact)
            for phone in phones:
                owners[phone].add(ownership)
        except Exception:
            if canonical in branches:
                invalid[canonical] = "INVALID_BRANCH_FILE"
            LOG.warning("Cobranza archivo inválido, sucursal=%s", raw)
            db.session.rollback()
            continue
        if canonical in branches:
            files[canonical].append(artifact)
            observed[canonical].update(phones)
        elif not canonical:
            LOG.warning("Cobranza sucursal sin mapeo, archivo=%s", raw)
    shared = {phone for phone, branches_seen in owners.items() if len(branches_seen) > 1}
    safe = {
        key: frozenset(observed[key] - shared)
        for key in branches
    }
    return files, safe, invalid, len(shared)


def _audit(settings: MultiBranchConfig, *, day: date, branch: str,
           status: str, campaign_id: int | None = None, job_id: int | None = None,
           recipients: int = 0, reason: str | None = None) -> None:
    log_warehouse_audit(
        action=AUDIT_ACTION,
        performed_by_user_id=settings.operator_id,
        details={
            "source": "reports_scheduler",
            "job_key": JOB_KEY,
            "business_date": day.isoformat(),
            "branch": branch,
            "status": status,
            "campaign_id": campaign_id,
            "dispatch_job_id": job_id,
            "recipients": recipients,
            "reason": reason,
        },
    )
    db.session.commit()


def _persist_blocked(campaign_id: int, day: date, branch: str) -> None:
    campaign = db.session.get(Campaign, campaign_id)
    if campaign is None:
        return
    doc = dict(campaign.audience_definition_json or {})
    meta = dict(doc.get("source_metadata") or {})
    if (meta.get("auto_multibranch_date") != day.isoformat()
            or meta.get("isolated_branch_key") != branch):
        return
    meta["auto_multibranch_blocked"] = True
    doc["source_metadata"] = meta
    campaign.audience_definition_json = doc
    db.session.commit()


def _queue_branch(day: date, branch: str, campaign_id: int,
                  settings: MultiBranchConfig) -> dict[str, Any]:
    campaign = db.session.get(Campaign, campaign_id)
    meta = ((campaign.audience_definition_json or {}).get("source_metadata") or {}) if campaign else {}
    if (campaign is None or campaign.name !=
            f"{CAMPAIGN_PREFIX} - {day.isoformat()} - {branch}"
            or meta.get("automation_job") != JOB_KEY
            or meta.get("business_date") != day.isoformat()
            or meta.get("isolated_branch_key") != branch
            or meta.get("auto_multibranch_date") != day.isoformat()):
        raise MultiBranchBlocked("Identidad de campaña aislada inválida.")
    recipients = int(db.session.query(func.count(Recipient.id))
                     .filter(Recipient.campaign_id == campaign_id).scalar() or 0)
    if not 1 <= recipients <= settings.max_recipients_per_branch:
        raise MultiBranchBlocked("Límite de destinatarios por sucursal.")
    template_id = meta.get("template_id_at_freeze")
    if type(template_id) is not int:
        raise MultiBranchBlocked("Plantilla congelada inválida.")
    plan = build_campaign_v2_preflight(
        campaign_id=campaign_id, template_id=template_id,
        allowed_sucursal_keys=None, session=db.session,
    )
    if (len(plan.batches) != 1 or plan.batches[0].sucursal_canon != branch
            or not plan.ready):
        raise MultiBranchBlocked("El preflight no corresponde a la sucursal autorizada.")
    return enqueue_cobranza_send(
        campaign_id=campaign_id, actor_user_id=settings.operator_id,
        allowed_sucursal_keys=None, session=db.session,
    )


def process_multi_branch(*, day: date, artifacts: list[dict[str, Any]],
                         settings: MultiBranchConfig) -> dict[str, Any]:
    """Try all independent branches once; no retries or provider calls here."""
    if not isinstance(settings, MultiBranchConfig) or day < settings.start_date:
        raise MultiBranchBlocked("Fecha de operación inválida.")
    _require_global_authorization(settings)
    # Do not mix the older whole-day campaign (manual or pilot) and per-branch jobs.
    existing_day = db.session.query(Campaign.id).filter(
        Campaign.name == f"{CAMPAIGN_PREFIX} - {day.isoformat()}",
    ).first()
    if existing_day:
        raise MultiBranchBlocked("Existe campaña general/piloto para este corte.")

    files, safe, invalid, ambiguous_count = _index_daily_artifacts(
        artifacts, settings.branch_keys,
    )
    daily_total = sum(len(safe[key]) for key in settings.branch_keys if key not in invalid)
    if daily_total > settings.max_daily_recipients:
        raise MultiBranchBlocked("Se superó el límite diario multicucursal.")
    result: list[dict[str, Any]] = []
    for branch in settings.branch_keys:
        campaign_id = None
        entry: dict[str, Any] = {"branch": branch, "campaign_id": None, "job_id": None}
        try:
            if branch in invalid:
                entry.update(status="SKIPPED", reason=invalid[branch])
            elif not files[branch]:
                entry.update(status="SKIPPED", reason="NOT_IN_REPORT")
            elif not safe[branch]:
                entry.update(status="SKIPPED", reason="NO_UNAMBIGUOUS_PHONES")
            elif len(safe[branch]) > settings.max_recipients_per_branch:
                entry.update(status="SKIPPED", reason="RECIPIENT_LIMIT")
            else:
                # Every branch gets its own append-only audit before approving costs.
                _audit(settings, day=day, branch=branch, status="STARTED",
                       recipients=len(safe[branch]))
                prepared = prepare_cobranza_iventas_campaign(
                    business_date=day, artifacts=files[branch],
                    isolated_branch_key=branch, allowed_phones=safe[branch],
                )
                if prepared.get("status") not in {"PREPARED", "ALREADY_PREPARED"}:
                    entry.update(status="SKIPPED", reason=str(prepared.get("status", "NOT_PREPARED")))
                else:
                    campaign_id = int(prepared["campaign_id"])
                    entry["campaign_id"] = campaign_id
                    queued = _queue_branch(day, branch, campaign_id, settings)
                    entry.update(
                        status=str(queued["status"]),
                        job_id=int(queued["job_id"]),
                        recipients=int(queued["recipient_count"]),
                    )
        except Exception as exc:
            db.session.rollback()
            LOG.exception("Cobranza aislada bloqueada. branch=%s reason=%s",
                          branch, type(exc).__name__)
            entry.update(status="SKIPPED", reason="PREPARATION_OR_DISPATCH_BLOCKED")
            if campaign_id is not None:
                try:
                    _persist_blocked(campaign_id, day, branch)
                except Exception:
                    db.session.rollback()
                    LOG.exception("No se pudo marcar bloqueo. branch=%s", branch)
        finally:
            try:
                _audit(
                    settings, day=day, branch=branch,
                    status=str(entry.get("status", "SKIPPED")),
                    campaign_id=entry.get("campaign_id"), job_id=entry.get("job_id"),
                    recipients=int(entry.get("recipients") or 0),
                    reason=entry.get("reason"),
                )
            except Exception:
                db.session.rollback()
                LOG.exception("No se pudo auditar cobranza. branch=%s", branch)
        result.append(entry)
    queued_count = sum(1 for item in result if item.get("job_id") is not None)
    skipped_count = len(result) - queued_count
    summary = {
        "status": "QUEUED_PARTIAL" if skipped_count else "QUEUED_ALL",
        "business_date": day.isoformat(),
        "queued_branches": queued_count,
        "skipped_branches": skipped_count,
        "ambiguous_phones_excluded": ambiguous_count,
        "branches": result,
    }
    LOG.info("Cobranza multibranch summary: %s", summary)
    return summary
