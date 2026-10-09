from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.extensions import db
from app.models import (
    Sucursal,
    SucursalOperationalStatus,
    SystemDailyCheckAnswerORM,
    SystemDailyCheckAnswerValue,
    SystemDailyCheckGeneralStatus,
    SystemDailyCheckIssueAttachmentORM,
    SystemDailyCheckIssueORM,
    SystemDailyCheckORM,
    SystemDailyCheckPromptStateORM,
    SystemDailyCheckRolloutBranchORM,
    UserORM,
)
from app.services.system_daily_check_attachment_storage_service import (
    resolve_system_daily_check_attachment_path,
)
from app.services.system_daily_check_service import (
    QUESTION_BY_KEY,
    SystemDailyCheckAuthorizationError,
    SystemDailyCheckNotFoundError,
    SystemDailyCheckValidationError,
    resolve_business_date,
)
from app.utils.sucursal_audience import TECHNICAL_SUCURSAL_IDS
from app.utils.system_daily_check_access import has_system_daily_check_mvp_access


def _session(session: Session | None):
    return session if session is not None else db.session


def _branch_payload(branch: Sucursal) -> dict:
    return {
        "sucursal_id": int(branch.sucursal_id),
        "sucursal": branch.sucursal,
        "serie": branch.serie,
        "operational_status": branch.operational_status,
        "is_demo": bool(branch.is_demo),
    }


def resolve_system_daily_check_branch_universe(
    *,
    as_of_date: date,
    session: Session | None = None,
) -> dict:
    """Resolve potential vs explicitly expected branches for one business date."""
    if not isinstance(as_of_date, date):
        raise ValueError("as_of_date debe ser datetime.date.")

    target_session = _session(session)
    technical_ids = tuple(sorted(TECHNICAL_SUCURSAL_IDS))

    potential_stmt = (
        select(Sucursal)
        .where(
            Sucursal.is_demo.is_(False),
            Sucursal.operational_status == SucursalOperationalStatus.ACTIVA,
        )
        .order_by(Sucursal.sucursal.asc())
    )
    if technical_ids:
        potential_stmt = potential_stmt.where(
            ~Sucursal.sucursal_id.in_(technical_ids)
        )

    expected_stmt = (
        select(Sucursal, SystemDailyCheckRolloutBranchORM)
        .join(
            SystemDailyCheckRolloutBranchORM,
            SystemDailyCheckRolloutBranchORM.sucursal_id
            == Sucursal.sucursal_id,
        )
        .where(
            Sucursal.is_demo.is_(False),
            SystemDailyCheckRolloutBranchORM.enabled_from <= as_of_date,
            or_(
                SystemDailyCheckRolloutBranchORM.disabled_from.is_(None),
                SystemDailyCheckRolloutBranchORM.disabled_from >= as_of_date,
            ),
        )
        .order_by(Sucursal.sucursal.asc())
    )
    if technical_ids:
        expected_stmt = expected_stmt.where(
            ~Sucursal.sucursal_id.in_(technical_ids)
        )

    potential_branches = list(
        target_session.scalars(potential_stmt).all()
    )
    expected_rows = list(
        target_session.execute(expected_stmt).all()
    )

    expected_branches = []
    for branch, rollout in expected_rows:
        row = _branch_payload(branch)
        row.update(
            {
                "enabled_from": rollout.enabled_from.isoformat(),
                "disabled_from": (
                    rollout.disabled_from.isoformat()
                    if rollout.disabled_from is not None
                    else None
                ),
            }
        )
        expected_branches.append(row)

    return {
        "as_of_date": as_of_date.isoformat(),
        "potential_branches": [
            _branch_payload(branch)
            for branch in potential_branches
        ],
        "expected_branches": expected_branches,
        "potential_count": len(potential_branches),
        "expected_count": len(expected_branches),
    }


def _require_mvp_access(actor) -> None:
    if not has_system_daily_check_mvp_access(actor):
        raise SystemDailyCheckAuthorizationError(
            "El usuario no está habilitado para BI del checklist diario."
        )


def _normalize_branch_ids(branch_ids: object) -> list[int]:
    if not isinstance(branch_ids, list):
        raise SystemDailyCheckValidationError(
            "branch_ids debe ser una lista."
        )

    normalized: list[int] = []
    seen: set[int] = set()
    for raw in branch_ids:
        try:
            branch_id = int(raw)
        except (TypeError, ValueError) as exc:
            raise SystemDailyCheckValidationError(
                "branch_ids contiene un valor inválido."
            ) from exc
        if branch_id <= 0:
            raise SystemDailyCheckValidationError(
                "branch_ids contiene un valor inválido."
            )
        if branch_id in TECHNICAL_SUCURSAL_IDS:
            raise SystemDailyCheckValidationError(
                "branch_ids contiene una sucursal técnica no seleccionable."
            )
        if branch_id not in seen:
            normalized.append(branch_id)
            seen.add(branch_id)
    return normalized


def configure_system_daily_check_rollout_today(
    actor,
    *,
    branch_ids: object,
    now: datetime | None = None,
    session: Session | None = None,
) -> dict:
    """Replace the expected pilot branch set from today's business date forward."""
    _require_mvp_access(actor)
    target_session = _session(session)
    business_date = resolve_business_date(now)
    selected_ids = _normalize_branch_ids(branch_ids)

    selected_branches: list[Sucursal] = []
    if selected_ids:
        selected_branches = list(
            target_session.scalars(
                select(Sucursal).where(
                    Sucursal.sucursal_id.in_(selected_ids)
                )
            ).all()
        )
        found_ids = {
            int(branch.sucursal_id)
            for branch in selected_branches
        }
        missing = sorted(set(selected_ids) - found_ids)
        if missing:
            raise SystemDailyCheckValidationError(
                "No existen las sucursales: "
                + ", ".join(str(value) for value in missing)
                + "."
            )

        invalid = sorted(
            int(branch.sucursal_id)
            for branch in selected_branches
            if (
                bool(branch.is_demo)
                or branch.operational_status
                != SucursalOperationalStatus.ACTIVA
            )
        )
        if invalid:
            raise SystemDailyCheckValidationError(
                "Solo se pueden configurar sucursales activas y no demo: "
                + ", ".join(str(value) for value in invalid)
                + "."
            )

    active_rows = list(
        target_session.scalars(
            select(SystemDailyCheckRolloutBranchORM)
            .where(
                SystemDailyCheckRolloutBranchORM.enabled_from
                <= business_date,
                or_(
                    SystemDailyCheckRolloutBranchORM.disabled_from.is_(None),
                    SystemDailyCheckRolloutBranchORM.disabled_from
                    >= business_date,
                ),
            )
            .order_by(
                SystemDailyCheckRolloutBranchORM.sucursal_id.asc(),
                SystemDailyCheckRolloutBranchORM.enabled_from.asc(),
            )
        ).all()
    )

    active_by_branch: dict[int, SystemDailyCheckRolloutBranchORM] = {}
    for row in active_rows:
        branch_id = int(row.sucursal_id)
        if branch_id in active_by_branch:
            raise SystemDailyCheckValidationError(
                "Existen periodos de rollout traslapados para la sucursal "
                f"{branch_id}."
            )
        active_by_branch[branch_id] = row

    selected_set = set(selected_ids)
    previous_day = business_date - timedelta(days=1)

    for branch_id, row in active_by_branch.items():
        if branch_id in selected_set:
            continue
        if row.enabled_from == business_date:
            target_session.delete(row)
        else:
            row.disabled_from = previous_day
            row.disabled_by_user_id = int(actor.id)

    for branch_id in selected_ids:
        if branch_id in active_by_branch:
            continue
        target_session.add(
            SystemDailyCheckRolloutBranchORM(
                sucursal_id=branch_id,
                enabled_from=business_date,
                disabled_from=None,
                configured_by_user_id=int(actor.id),
            )
        )

    target_session.flush()
    return resolve_system_daily_check_branch_universe(
        as_of_date=business_date,
        session=target_session,
    )


def _normalize_summary_branch_id(
    branch_id: object,
    *,
    session,
) -> int | None:
    if branch_id in (None, ""):
        return None
    try:
        parsed = int(branch_id)
    except (TypeError, ValueError) as exc:
        raise SystemDailyCheckValidationError(
            "branch_id debe ser entero."
        ) from exc
    if parsed <= 0 or parsed in TECHNICAL_SUCURSAL_IDS:
        raise SystemDailyCheckValidationError(
            "branch_id inválido."
        )

    branch = session.get(Sucursal, parsed)
    if branch is None or bool(branch.is_demo):
        raise SystemDailyCheckValidationError(
            "branch_id no corresponde a una sucursal analítica."
        )
    return parsed


def _validate_date_range(
    date_from: date,
    date_to: date,
) -> None:
    if not isinstance(date_from, date) or not isinstance(date_to, date):
        raise SystemDailyCheckValidationError(
            "date_from y date_to deben ser datetime.date."
        )
    if date_from > date_to:
        raise SystemDailyCheckValidationError(
            "date_from no puede ser posterior a date_to."
        )


def _expected_branch_days(
    target_session,
    *,
    date_from: date,
    date_to: date,
    branch_id: int | None,
) -> set[tuple[int, date]]:
    stmt = (
        select(SystemDailyCheckRolloutBranchORM, Sucursal)
        .join(
            Sucursal,
            Sucursal.sucursal_id
            == SystemDailyCheckRolloutBranchORM.sucursal_id,
        )
        .where(
            Sucursal.is_demo.is_(False),
            SystemDailyCheckRolloutBranchORM.enabled_from <= date_to,
            or_(
                SystemDailyCheckRolloutBranchORM.disabled_from.is_(None),
                SystemDailyCheckRolloutBranchORM.disabled_from >= date_from,
            ),
        )
    )
    technical_ids = tuple(sorted(TECHNICAL_SUCURSAL_IDS))
    if technical_ids:
        stmt = stmt.where(
            ~Sucursal.sucursal_id.in_(technical_ids)
        )
    if branch_id is not None:
        stmt = stmt.where(
            Sucursal.sucursal_id == branch_id
        )

    pairs: set[tuple[int, date]] = set()
    for rollout, branch in target_session.execute(stmt).all():
        start = max(date_from, rollout.enabled_from)
        end = min(
            date_to,
            rollout.disabled_from or date_to,
        )
        current = start
        while current <= end:
            pairs.add((int(branch.sucursal_id), current))
            current += timedelta(days=1)
    return pairs


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def build_system_daily_check_bi_summary(
    actor,
    *,
    date_from: date,
    date_to: date,
    branch_id: object = None,
    now: datetime | None = None,
    session: Session | None = None,
) -> dict:
    _require_mvp_access(actor)
    _validate_date_range(date_from, date_to)
    target_session = _session(session)
    resolved_branch_id = _normalize_summary_branch_id(
        branch_id,
        session=target_session,
    )
    expected_pairs = _expected_branch_days(
        target_session,
        date_from=date_from,
        date_to=date_to,
        branch_id=resolved_branch_id,
    )

    check_stmt = select(SystemDailyCheckORM).where(
        SystemDailyCheckORM.business_date >= date_from,
        SystemDailyCheckORM.business_date <= date_to,
    )
    if resolved_branch_id is not None:
        check_stmt = check_stmt.where(
            SystemDailyCheckORM.sucursal_id == resolved_branch_id
        )
    all_checks = list(
        target_session.scalars(check_stmt).all()
    )

    expected_checks = {
        (int(check.sucursal_id), check.business_date): check
        for check in all_checks
        if (
            int(check.sucursal_id),
            check.business_date,
        ) in expected_pairs
    }
    expected_check_ids = [
        int(check.id)
        for check in expected_checks.values()
    ]

    status_counts = {
        SystemDailyCheckGeneralStatus.NORMAL: 0,
        SystemDailyCheckGeneralStatus.MINOR_FAILURE: 0,
        SystemDailyCheckGeneralStatus.OPERATIONAL_IMPACT: 0,
    }
    for check in expected_checks.values():
        status_counts[check.general_status] += 1

    no_answers = 0
    issues: list[SystemDailyCheckIssueORM] = []
    if expected_check_ids:
        no_answers = len(
            list(
                target_session.scalars(
                    select(SystemDailyCheckAnswerORM.id).where(
                        SystemDailyCheckAnswerORM.check_id.in_(
                            expected_check_ids
                        ),
                        SystemDailyCheckAnswerORM.answer
                        == SystemDailyCheckAnswerValue.NO,
                    )
                ).all()
            )
        )
        issues = list(
            target_session.scalars(
                select(SystemDailyCheckIssueORM)
                .join(
                    SystemDailyCheckAnswerORM,
                    SystemDailyCheckIssueORM.answer_id
                    == SystemDailyCheckAnswerORM.id,
                )
                .where(
                    SystemDailyCheckAnswerORM.check_id.in_(
                        expected_check_ids
                    )
                )
            ).all()
        )

    prompt_stmt = select(SystemDailyCheckPromptStateORM).where(
        SystemDailyCheckPromptStateORM.business_date >= date_from,
        SystemDailyCheckPromptStateORM.business_date <= date_to,
    )
    if resolved_branch_id is not None:
        prompt_stmt = prompt_stmt.where(
            SystemDailyCheckPromptStateORM.sucursal_id
            == resolved_branch_id
        )
    prompt_by_pair = {
        (int(row.sucursal_id), row.business_date): row
        for row in target_session.scalars(prompt_stmt).all()
        if (
            int(row.sucursal_id),
            row.business_date,
        ) in expected_pairs
    }

    completed_without_postpone = 0
    completed_after_1 = 0
    completed_after_2 = 0
    reached_mandatory = 0
    now_utc = _as_utc(
        now or datetime.now(timezone.utc)
    )

    for pair in expected_pairs:
        check = expected_checks.get(pair)
        prompt = prompt_by_pair.get(pair)

        if check is not None:
            postpone_count = int(
                getattr(prompt, "postpone_count", 0) or 0
            )
            if postpone_count <= 0:
                completed_without_postpone += 1
            elif postpone_count == 1:
                completed_after_1 += 1
            else:
                completed_after_2 += 1

        if prompt is None or prompt.mandatory_from_at is None:
            continue

        mandatory_at = _as_utc(prompt.mandatory_from_at)
        cutoff = (
            _as_utc(check.submitted_at)
            if check is not None
            else now_utc
        )
        if cutoff >= mandatory_at:
            reached_mandatory += 1

    expected_total = len(expected_pairs)
    completed = len(expected_checks)
    pending = max(0, expected_total - completed)
    issues_total = len(issues)
    reported = sum(
        1
        for issue in issues
        if bool(issue.reported_to_support)
    )
    unreported = issues_total - reported

    return {
        "filters": {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "branch_id": resolved_branch_id,
        },
        "universe": {
            "expected_checklists": expected_total,
            "expected_branches": len(
                {
                    branch_id_value
                    for branch_id_value, _ in expected_pairs
                }
            ),
            "out_of_rollout_submissions": (
                len(all_checks) - completed
            ),
        },
        "summary": {
            "completed": completed,
            "pending": pending,
            "compliance_pct": (
                round((completed / expected_total) * 100, 1)
                if expected_total
                else None
            ),
            "normal": status_counts[
                SystemDailyCheckGeneralStatus.NORMAL
            ],
            "minor_failure": status_counts[
                SystemDailyCheckGeneralStatus.MINOR_FAILURE
            ],
            "operational_impact": status_counts[
                SystemDailyCheckGeneralStatus.OPERATIONAL_IMPACT
            ],
        },
        "failures": {
            "checks_with_failure": (
                status_counts[
                    SystemDailyCheckGeneralStatus.MINOR_FAILURE
                ]
                + status_counts[
                    SystemDailyCheckGeneralStatus.OPERATIONAL_IMPACT
                ]
            ),
            "no_answers": no_answers,
            "issues_total": issues_total,
            "reported": reported,
            "unreported": unreported,
            "reported_pct": (
                round((reported / issues_total) * 100, 1)
                if issues_total
                else None
            ),
        },
        "postponements": {
            "completed_without_postpone": completed_without_postpone,
            "completed_after_1": completed_after_1,
            "completed_after_2": completed_after_2,
            "reached_mandatory": reached_mandatory,
        },
    }


SYSTEM_DAILY_CHECK_MATRIX_GROUPS = (
    {
        "key": "COMPUTING",
        "label": "Cómputo",
        "question_keys": (
            "COMPUTERS_WORKING",
            "PERIPHERALS_WORKING",
            "PRINTERS_WORKING",
            "BANK_TERMINALS_WORKING",
        ),
    },
    {
        "key": "INTERNET",
        "label": "Internet",
        "question_keys": ("INTERNET_WORKING",),
    },
    {
        "key": "GASCA",
        "label": "Gasca",
        "question_keys": ("GASCA_WORKING",),
    },
    {
        "key": "SUITE_ULTRA",
        "label": "Suite Ultra",
        "question_keys": ("SUITE_ULTRA_WORKING",),
    },
    {
        "key": "ACCESS",
        "label": "Acceso",
        "question_keys": (
            "TURNSTILES_WORKING",
            "ACCESS_READERS_WORKING",
            "TURNSTILE_SCREENS_WORKING",
        ),
    },
    {
        "key": "AUDIO",
        "label": "Audio",
        "question_keys": ("AMBIENT_AUDIO_WORKING",),
    },
    {
        "key": "VIDEO",
        "label": "Video",
        "question_keys": ("TV_SCREENS_WORKING",),
    },
    {
        "key": "CAMERAS",
        "label": "Cámaras",
        "question_keys": ("CAMERAS_WORKING",),
    },
)

MATRIX_STATE_LABELS = {
    "GREEN": "Sin falla",
    "YELLOW": "Falla menor",
    "RED": "Afecta la operación",
    "PENDING": "Pendiente",
    "NA": "No aplica",
    "UNKNOWN": "Dato incompleto",
}


def _matrix_state_payload(state: str) -> dict:
    return {
        "state": state,
        "label": MATRIX_STATE_LABELS[state],
    }


def _matrix_group_state(
    *,
    answers_by_key: dict[str, str],
    question_keys: tuple[str, ...],
    general_status: str,
) -> dict:
    values = [
        answers_by_key.get(question_key)
        for question_key in question_keys
    ]
    present_values = [
        value for value in values if value is not None
    ]

    if SystemDailyCheckAnswerValue.NO in present_values:
        return _matrix_state_payload(
            "RED"
            if general_status
            == SystemDailyCheckGeneralStatus.OPERATIONAL_IMPACT
            else "YELLOW"
        )
    if len(present_values) != len(question_keys):
        return _matrix_state_payload("UNKNOWN")
    if all(
        value == SystemDailyCheckAnswerValue.NA
        for value in present_values
    ):
        return _matrix_state_payload("NA")
    return _matrix_state_payload("GREEN")


def _matrix_general_state(general_status: str) -> dict:
    if general_status == SystemDailyCheckGeneralStatus.NORMAL:
        return _matrix_state_payload("GREEN")
    if general_status == SystemDailyCheckGeneralStatus.MINOR_FAILURE:
        return _matrix_state_payload("YELLOW")
    if general_status == SystemDailyCheckGeneralStatus.OPERATIONAL_IMPACT:
        return _matrix_state_payload("RED")
    return _matrix_state_payload("UNKNOWN")


def build_system_daily_check_bi_matrix(
    actor,
    *,
    business_date: date,
    branch_id: object = None,
    session: Session | None = None,
) -> dict:
    _require_mvp_access(actor)
    if not isinstance(business_date, date):
        raise SystemDailyCheckValidationError(
            "business_date debe ser datetime.date."
        )

    target_session = _session(session)
    resolved_branch_id = _normalize_summary_branch_id(
        branch_id,
        session=target_session,
    )
    expected_pairs = _expected_branch_days(
        target_session,
        date_from=business_date,
        date_to=business_date,
        branch_id=resolved_branch_id,
    )
    expected_ids = sorted({
        branch_id_value
        for branch_id_value, _ in expected_pairs
    })

    branches_by_id: dict[int, Sucursal] = {}
    if expected_ids:
        branches_by_id = {
            int(branch.sucursal_id): branch
            for branch in target_session.scalars(
                select(Sucursal).where(
                    Sucursal.sucursal_id.in_(expected_ids)
                )
            ).all()
        }

    checks_by_branch: dict[int, SystemDailyCheckORM] = {}
    if expected_ids:
        checks_by_branch = {
            int(check.sucursal_id): check
            for check in target_session.scalars(
                select(SystemDailyCheckORM).where(
                    SystemDailyCheckORM.business_date == business_date,
                    SystemDailyCheckORM.sucursal_id.in_(expected_ids),
                )
            ).all()
        }

    answers_by_check: dict[int, dict[str, str]] = {}
    check_ids = [
        int(check.id)
        for check in checks_by_branch.values()
    ]
    if check_ids:
        for answer in target_session.scalars(
            select(SystemDailyCheckAnswerORM).where(
                SystemDailyCheckAnswerORM.check_id.in_(check_ids)
            )
        ).all():
            answers_by_check.setdefault(
                int(answer.check_id),
                {},
            )[answer.question_key] = answer.answer

    prompts_by_branch: dict[int, SystemDailyCheckPromptStateORM] = {}
    if expected_ids:
        prompts_by_branch = {
            int(prompt.sucursal_id): prompt
            for prompt in target_session.scalars(
                select(SystemDailyCheckPromptStateORM).where(
                    SystemDailyCheckPromptStateORM.business_date
                    == business_date,
                    SystemDailyCheckPromptStateORM.sucursal_id.in_(
                        expected_ids
                    ),
                )
            ).all()
        }

    rows = []
    for branch_id_value in expected_ids:
        branch = branches_by_id[branch_id_value]
        check = checks_by_branch.get(branch_id_value)
        prompt = prompts_by_branch.get(branch_id_value)

        if check is None:
            cells = {
                group["key"]: _matrix_state_payload("PENDING")
                for group in SYSTEM_DAILY_CHECK_MATRIX_GROUPS
            }
            cells["GENERAL"] = _matrix_state_payload("PENDING")
            rows.append({
                "sucursal_id": branch_id_value,
                "sucursal": branch.sucursal,
                "check_id": None,
                "general_status": None,
                "submitted_at": None,
                "postpone_count": int(
                    getattr(prompt, "postpone_count", 0) or 0
                ),
                "cells": cells,
            })
            continue

        answer_values = answers_by_check.get(int(check.id), {})
        cells = {
            group["key"]: _matrix_group_state(
                answers_by_key=answer_values,
                question_keys=group["question_keys"],
                general_status=check.general_status,
            )
            for group in SYSTEM_DAILY_CHECK_MATRIX_GROUPS
        }
        cells["GENERAL"] = _matrix_general_state(
            check.general_status
        )
        rows.append({
            "sucursal_id": branch_id_value,
            "sucursal": branch.sucursal,
            "check_id": int(check.id),
            "general_status": check.general_status,
            "submitted_at": (
                check.submitted_at.isoformat()
                if check.submitted_at is not None
                else None
            ),
            "postpone_count": int(
                getattr(prompt, "postpone_count", 0) or 0
            ),
            "cells": cells,
        })

    return {
        "business_date": business_date.isoformat(),
        "branch_id": resolved_branch_id,
        "groups": [
            {
                "key": group["key"],
                "label": group["label"],
                "question_keys": list(group["question_keys"]),
            }
            for group in SYSTEM_DAILY_CHECK_MATRIX_GROUPS
        ]
        + [
            {
                "key": "GENERAL",
                "label": "Estado general",
                "question_keys": [],
            }
        ],
        "rows": rows,
    }


def _normalize_history_filters(
    *,
    general_status: object,
    question_key: object,
    answer: object,
) -> tuple[str | None, str | None, str | None]:
    normalized_status = (
        str(general_status or "").strip().upper() or None
    )
    if (
        normalized_status is not None
        and normalized_status
        not in SystemDailyCheckGeneralStatus.ALL
    ):
        raise SystemDailyCheckValidationError(
            "general_status inválido."
        )

    normalized_question = (
        str(question_key or "").strip().upper() or None
    )
    if (
        normalized_question is not None
        and normalized_question not in QUESTION_BY_KEY
    ):
        raise SystemDailyCheckValidationError(
            "question_key no reconocido."
        )

    normalized_answer = (
        str(answer or "").strip().upper() or None
    )
    if (
        normalized_answer is not None
        and normalized_answer
        not in SystemDailyCheckAnswerValue.ALL
    ):
        raise SystemDailyCheckValidationError(
            "answer inválido."
        )
    return (
        normalized_status,
        normalized_question,
        normalized_answer,
    )


def _normalize_pagination(
    page: object,
    page_size: object,
) -> tuple[int, int]:
    try:
        parsed_page = int(page or 1)
        parsed_page_size = int(page_size or 50)
    except (TypeError, ValueError) as exc:
        raise SystemDailyCheckValidationError(
            "page y page_size deben ser enteros."
        ) from exc
    if parsed_page <= 0:
        raise SystemDailyCheckValidationError(
            "page debe ser mayor que cero."
        )
    if parsed_page_size <= 0 or parsed_page_size > 100:
        raise SystemDailyCheckValidationError(
            "page_size debe estar entre 1 y 100."
        )
    return parsed_page, parsed_page_size


def _prompt_reached_mandatory(
    prompt,
    *,
    submitted_at: datetime | None,
    now_utc: datetime,
) -> bool:
    if prompt is None or prompt.mandatory_from_at is None:
        return False
    cutoff = (
        _as_utc(submitted_at)
        if submitted_at is not None
        else now_utc
    )
    return cutoff >= _as_utc(prompt.mandatory_from_at)


def list_system_daily_check_bi_history(
    actor,
    *,
    date_from: date,
    date_to: date,
    branch_id: object = None,
    general_status: object = None,
    question_key: object = None,
    answer: object = None,
    page: object = 1,
    page_size: object = 50,
    now: datetime | None = None,
    session: Session | None = None,
) -> dict:
    _require_mvp_access(actor)
    _validate_date_range(date_from, date_to)
    target_session = _session(session)
    resolved_branch_id = _normalize_summary_branch_id(
        branch_id,
        session=target_session,
    )
    (
        normalized_status,
        normalized_question,
        normalized_answer,
    ) = _normalize_history_filters(
        general_status=general_status,
        question_key=question_key,
        answer=answer,
    )
    parsed_page, parsed_page_size = _normalize_pagination(
        page,
        page_size,
    )

    stmt = (
        select(
            SystemDailyCheckORM,
            Sucursal.sucursal,
            UserORM.username,
        )
        .join(
            Sucursal,
            Sucursal.sucursal_id
            == SystemDailyCheckORM.sucursal_id,
        )
        .join(
            UserORM,
            UserORM.id
            == SystemDailyCheckORM.performed_by_user_id,
        )
        .where(
            SystemDailyCheckORM.business_date >= date_from,
            SystemDailyCheckORM.business_date <= date_to,
            Sucursal.is_demo.is_(False),
        )
    )
    technical_ids = tuple(sorted(TECHNICAL_SUCURSAL_IDS))
    if technical_ids:
        stmt = stmt.where(
            ~Sucursal.sucursal_id.in_(technical_ids)
        )
    if resolved_branch_id is not None:
        stmt = stmt.where(
            SystemDailyCheckORM.sucursal_id
            == resolved_branch_id
        )
    if normalized_status is not None:
        stmt = stmt.where(
            SystemDailyCheckORM.general_status
            == normalized_status
        )

    if (
        normalized_question is not None
        or normalized_answer is not None
    ):
        answer_filter = select(
            SystemDailyCheckAnswerORM.id
        ).where(
            SystemDailyCheckAnswerORM.check_id
            == SystemDailyCheckORM.id
        )
        if normalized_question is not None:
            answer_filter = answer_filter.where(
                SystemDailyCheckAnswerORM.question_key
                == normalized_question
            )
        if normalized_answer is not None:
            answer_filter = answer_filter.where(
                SystemDailyCheckAnswerORM.answer
                == normalized_answer
            )
        stmt = stmt.where(answer_filter.exists())

    total = int(
        target_session.scalar(
            select(func.count()).select_from(
                stmt.order_by(None).subquery()
            )
        )
        or 0
    )

    stmt = stmt.order_by(
        SystemDailyCheckORM.business_date.desc(),
        SystemDailyCheckORM.submitted_at.desc(),
        SystemDailyCheckORM.id.desc(),
    ).offset(
        (parsed_page - 1) * parsed_page_size
    ).limit(parsed_page_size)

    raw_rows = list(target_session.execute(stmt).all())
    pairs = {
        (
            int(check.sucursal_id),
            check.business_date,
        )
        for check, _, _ in raw_rows
    }
    prompts_by_pair = {}
    if pairs:
        branch_ids = {pair[0] for pair in pairs}
        prompts_by_pair = {
            (int(prompt.sucursal_id), prompt.business_date): prompt
            for prompt in target_session.scalars(
                select(SystemDailyCheckPromptStateORM).where(
                    SystemDailyCheckPromptStateORM.business_date
                    >= date_from,
                    SystemDailyCheckPromptStateORM.business_date
                    <= date_to,
                    SystemDailyCheckPromptStateORM.sucursal_id.in_(
                        branch_ids
                    ),
                )
            ).all()
        }

    now_utc = _as_utc(
        now or datetime.now(timezone.utc)
    )
    items = []
    for check, branch_name, username in raw_rows:
        prompt = prompts_by_pair.get(
            (
                int(check.sucursal_id),
                check.business_date,
            )
        )
        items.append({
            "id": int(check.id),
            "sucursal_id": int(check.sucursal_id),
            "sucursal": branch_name,
            "performed_by_user_id": int(
                check.performed_by_user_id
            ),
            "performed_by_username": username,
            "business_date": check.business_date.isoformat(),
            "general_status": check.general_status,
            "submitted_at": (
                check.submitted_at.isoformat()
                if check.submitted_at is not None
                else None
            ),
            "postpone_count": int(
                getattr(prompt, "postpone_count", 0) or 0
            ),
            "reached_mandatory": _prompt_reached_mandatory(
                prompt,
                submitted_at=check.submitted_at,
                now_utc=now_utc,
            ),
        })

    return {
        "filters": {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "branch_id": resolved_branch_id,
            "general_status": normalized_status,
            "question_key": normalized_question,
            "answer": normalized_answer,
        },
        "page": parsed_page,
        "page_size": parsed_page_size,
        "total": total,
        "items": items,
    }


def get_system_daily_check_bi_detail(
    actor,
    *,
    check_id: object,
    now: datetime | None = None,
    session: Session | None = None,
) -> dict:
    _require_mvp_access(actor)
    try:
        resolved_check_id = int(check_id)
    except (TypeError, ValueError) as exc:
        raise SystemDailyCheckValidationError(
            "check_id debe ser entero."
        ) from exc
    if resolved_check_id <= 0:
        raise SystemDailyCheckValidationError(
            "check_id inválido."
        )

    target_session = _session(session)
    check = target_session.get(
        SystemDailyCheckORM,
        resolved_check_id,
    )
    if check is None:
        raise SystemDailyCheckNotFoundError(
            "Checklist no encontrado."
        )

    branch = target_session.get(
        Sucursal,
        int(check.sucursal_id),
    )
    if (
        branch is None
        or bool(branch.is_demo)
        or int(branch.sucursal_id)
        in TECHNICAL_SUCURSAL_IDS
    ):
        raise SystemDailyCheckNotFoundError(
            "Checklist no encontrado."
        )
    user = target_session.get(
        UserORM,
        int(check.performed_by_user_id),
    )

    answers = list(
        target_session.scalars(
            select(SystemDailyCheckAnswerORM)
            .where(
                SystemDailyCheckAnswerORM.check_id
                == resolved_check_id
            )
            .order_by(SystemDailyCheckAnswerORM.id.asc())
        ).all()
    )
    answer_ids = [int(row.id) for row in answers]
    issues_by_answer = {}
    attachments_by_issue: dict[int, list] = {}
    if answer_ids:
        issues = list(
            target_session.scalars(
                select(SystemDailyCheckIssueORM).where(
                    SystemDailyCheckIssueORM.answer_id.in_(
                        answer_ids
                    )
                )
            ).all()
        )
        issues_by_answer = {
            int(issue.answer_id): issue
            for issue in issues
        }
        issue_ids = [int(issue.id) for issue in issues]
        if issue_ids:
            for attachment in target_session.scalars(
                select(SystemDailyCheckIssueAttachmentORM)
                .where(
                    SystemDailyCheckIssueAttachmentORM.issue_id.in_(
                        issue_ids
                    )
                )
                .order_by(
                    SystemDailyCheckIssueAttachmentORM.id.asc()
                )
            ).all():
                attachments_by_issue.setdefault(
                    int(attachment.issue_id),
                    [],
                ).append(attachment)

    prompt = target_session.scalars(
        select(SystemDailyCheckPromptStateORM).where(
            SystemDailyCheckPromptStateORM.sucursal_id
            == int(check.sucursal_id),
            SystemDailyCheckPromptStateORM.business_date
            == check.business_date,
        )
    ).first()

    serialized_answers = []
    for answer_row in answers:
        issue = issues_by_answer.get(int(answer_row.id))
        issue_payload = None
        if issue is not None:
            issue_payload = {
                "id": int(issue.id),
                "affected_scope": issue.affected_scope,
                "reported_to_support": bool(
                    issue.reported_to_support
                ),
                "description": issue.description,
                "attachments": [
                    {
                        "id": int(attachment.id),
                        "original_filename": (
                            attachment.original_filename
                        ),
                        "mime_type": attachment.mime_type,
                        "file_size_bytes": int(
                            attachment.file_size_bytes
                        ),
                        "sha256": attachment.sha256,
                        "url": (
                            "/api/system-daily-checks/bi/"
                            f"attachments/{int(attachment.id)}"
                        ),
                    }
                    for attachment in attachments_by_issue.get(
                        int(issue.id),
                        [],
                    )
                ],
            }
        serialized_answers.append({
            "id": int(answer_row.id),
            "question_key": answer_row.question_key,
            "question_label": (
                answer_row.question_label_snapshot
            ),
            "category_key": answer_row.category_key,
            "answer": answer_row.answer,
            "issue": issue_payload,
        })

    now_utc = _as_utc(
        now or datetime.now(timezone.utc)
    )
    return {
        "id": int(check.id),
        "sucursal_id": int(check.sucursal_id),
        "sucursal": branch.sucursal,
        "performed_by_user_id": int(
            check.performed_by_user_id
        ),
        "performed_by_username": (
            user.username if user is not None else None
        ),
        "business_date": check.business_date.isoformat(),
        "general_status": check.general_status,
        "created_at": (
            check.created_at.isoformat()
            if check.created_at is not None
            else None
        ),
        "submitted_at": (
            check.submitted_at.isoformat()
            if check.submitted_at is not None
            else None
        ),
        "prompt": {
            "postpone_count": int(
                getattr(prompt, "postpone_count", 0) or 0
            ),
            "last_postponed_at": (
                prompt.last_postponed_at.isoformat()
                if prompt is not None
                and prompt.last_postponed_at is not None
                else None
            ),
            "mandatory_from_at": (
                prompt.mandatory_from_at.isoformat()
                if prompt is not None
                and prompt.mandatory_from_at is not None
                else None
            ),
            "reached_mandatory": _prompt_reached_mandatory(
                prompt,
                submitted_at=check.submitted_at,
                now_utc=now_utc,
            ),
        },
        "answer_count": len(serialized_answers),
        "answers": serialized_answers,
    }


def get_system_daily_check_bi_attachment(
    actor,
    *,
    attachment_id: object,
    session: Session | None = None,
) -> dict:
    _require_mvp_access(actor)
    try:
        resolved_attachment_id = int(attachment_id)
    except (TypeError, ValueError) as exc:
        raise SystemDailyCheckValidationError(
            "attachment_id debe ser entero."
        ) from exc
    if resolved_attachment_id <= 0:
        raise SystemDailyCheckValidationError(
            "attachment_id inválido."
        )

    target_session = _session(session)
    attachment = target_session.get(
        SystemDailyCheckIssueAttachmentORM,
        resolved_attachment_id,
    )
    if attachment is None:
        raise SystemDailyCheckNotFoundError(
            "Evidencia no encontrada."
        )

    issue = target_session.get(
        SystemDailyCheckIssueORM,
        int(attachment.issue_id),
    )
    answer_row = (
        target_session.get(
            SystemDailyCheckAnswerORM,
            int(issue.answer_id),
        )
        if issue is not None
        else None
    )
    check = (
        target_session.get(
            SystemDailyCheckORM,
            int(answer_row.check_id),
        )
        if answer_row is not None
        else None
    )
    branch = (
        target_session.get(
            Sucursal,
            int(check.sucursal_id),
        )
        if check is not None
        else None
    )

    if (
        issue is None
        or answer_row is None
        or check is None
        or branch is None
        or bool(branch.is_demo)
        or int(branch.sucursal_id)
        in TECHNICAL_SUCURSAL_IDS
    ):
        raise SystemDailyCheckNotFoundError(
            "Evidencia no encontrada."
        )

    try:
        path = resolve_system_daily_check_attachment_path(
            attachment.storage_key
        )
    except ValueError as exc:
        raise SystemDailyCheckNotFoundError(
            "Evidencia no encontrada."
        ) from exc

    if not path.is_file():
        raise SystemDailyCheckNotFoundError(
            "El archivo de evidencia no está disponible."
        )

    return {
        "path": path,
        "original_filename": attachment.original_filename,
        "mime_type": attachment.mime_type,
        "file_size_bytes": int(attachment.file_size_bytes),
        "sha256": attachment.sha256,
    }


def _normalize_trend_granularity(value: object) -> str:
    normalized = str(value or "DAY").strip().upper()
    if normalized not in {"DAY", "WEEK", "MONTH"}:
        raise SystemDailyCheckValidationError(
            "granularity debe ser DAY, WEEK o MONTH."
        )
    return normalized


def _trend_bucket_bounds(
    business_date: date,
    granularity: str,
) -> tuple[date, date]:
    if granularity == "DAY":
        return business_date, business_date

    if granularity == "WEEK":
        days_since_sunday = (
            business_date.weekday() + 1
        ) % 7
        start = business_date - timedelta(
            days=days_since_sunday
        )
        return start, start + timedelta(days=6)

    start = business_date.replace(day=1)
    if start.month == 12:
        next_month = start.replace(
            year=start.year + 1,
            month=1,
        )
    else:
        next_month = start.replace(
            month=start.month + 1,
        )
    return start, next_month - timedelta(days=1)


def _new_trend_bucket(
    *,
    period_start: date,
    period_end: date,
) -> dict:
    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "expected": 0,
        "completed": 0,
        "pending": 0,
        "compliance_pct": None,
        "normal": 0,
        "minor_failure": 0,
        "operational_impact": 0,
        "no_answers": 0,
        "issues_total": 0,
        "reported": 0,
        "unreported": 0,
        "reported_pct": None,
        "completed_without_postpone": 0,
        "completed_after_1": 0,
        "completed_after_2": 0,
        "reached_mandatory": 0,
    }


def build_system_daily_check_bi_trends(
    actor,
    *,
    date_from: date,
    date_to: date,
    granularity: object = "DAY",
    branch_id: object = None,
    now: datetime | None = None,
    session: Session | None = None,
) -> dict:
    _require_mvp_access(actor)
    _validate_date_range(date_from, date_to)
    normalized_granularity = _normalize_trend_granularity(
        granularity
    )
    target_session = _session(session)
    resolved_branch_id = _normalize_summary_branch_id(
        branch_id,
        session=target_session,
    )
    expected_pairs = _expected_branch_days(
        target_session,
        date_from=date_from,
        date_to=date_to,
        branch_id=resolved_branch_id,
    )
    expected_branch_ids = sorted({
        branch_id_value
        for branch_id_value, _ in expected_pairs
    })
    branches_by_id = {}
    if expected_branch_ids:
        branches_by_id = {
            int(branch.sucursal_id): branch
            for branch in target_session.scalars(
                select(Sucursal).where(
                    Sucursal.sucursal_id.in_(
                        expected_branch_ids
                    )
                )
            ).all()
        }

    check_stmt = select(SystemDailyCheckORM).where(
        SystemDailyCheckORM.business_date >= date_from,
        SystemDailyCheckORM.business_date <= date_to,
    )
    if resolved_branch_id is not None:
        check_stmt = check_stmt.where(
            SystemDailyCheckORM.sucursal_id
            == resolved_branch_id
        )
    expected_checks = {
        (int(check.sucursal_id), check.business_date): check
        for check in target_session.scalars(check_stmt).all()
        if (
            int(check.sucursal_id),
            check.business_date,
        ) in expected_pairs
    }
    expected_check_ids = [
        int(check.id)
        for check in expected_checks.values()
    ]

    answers = []
    if expected_check_ids:
        answers = list(
            target_session.scalars(
                select(SystemDailyCheckAnswerORM).where(
                    SystemDailyCheckAnswerORM.check_id.in_(
                        expected_check_ids
                    )
                )
            ).all()
        )
    check_by_id = {
        int(check.id): check
        for check in expected_checks.values()
    }

    answer_ids = [int(answer_row.id) for answer_row in answers]
    issues_by_answer = {}
    if answer_ids:
        issues_by_answer = {
            int(issue.answer_id): issue
            for issue in target_session.scalars(
                select(SystemDailyCheckIssueORM).where(
                    SystemDailyCheckIssueORM.answer_id.in_(
                        answer_ids
                    )
                )
            ).all()
        }

    prompts_by_pair = {}
    if expected_pairs:
        prompt_stmt = select(
            SystemDailyCheckPromptStateORM
        ).where(
            SystemDailyCheckPromptStateORM.business_date
            >= date_from,
            SystemDailyCheckPromptStateORM.business_date
            <= date_to,
        )
        if expected_branch_ids:
            prompt_stmt = prompt_stmt.where(
                SystemDailyCheckPromptStateORM.sucursal_id.in_(
                    expected_branch_ids
                )
            )
        prompts_by_pair = {
            (int(prompt.sucursal_id), prompt.business_date):
                prompt
            for prompt in target_session.scalars(
                prompt_stmt
            ).all()
            if (
                int(prompt.sucursal_id),
                prompt.business_date,
            ) in expected_pairs
        }

    buckets: dict[date, dict] = {}
    daily_bucket_key: dict[date, date] = {}
    dates_in_range = sorted({
        business_date_value
        for _, business_date_value in expected_pairs
    })
    for business_date_value in dates_in_range:
        period_start, period_end = _trend_bucket_bounds(
            business_date_value,
            normalized_granularity,
        )
        daily_bucket_key[business_date_value] = (
            period_start
        )
        buckets.setdefault(
            period_start,
            _new_trend_bucket(
                period_start=period_start,
                period_end=period_end,
            ),
        )

    question_stats: dict[str, dict] = {}
    branch_stats: dict[int, dict] = {
        branch_id_value: {
            "sucursal_id": branch_id_value,
            "sucursal": (
                branches_by_id[branch_id_value].sucursal
                if branch_id_value in branches_by_id
                else None
            ),
            "expected": 0,
            "completed": 0,
            "checks_with_failure": 0,
            "no_answers": 0,
            "issues_total": 0,
            "reported": 0,
        }
        for branch_id_value in expected_branch_ids
    }
    recurrence_dates: dict[
        tuple[int, str], set[date]
    ] = {}

    now_utc = _as_utc(
        now or datetime.now(timezone.utc)
    )

    for pair in expected_pairs:
        branch_id_value, business_date_value = pair
        bucket = buckets[
            daily_bucket_key[business_date_value]
        ]
        bucket["expected"] += 1
        branch_stats[branch_id_value]["expected"] += 1

        check = expected_checks.get(pair)
        prompt = prompts_by_pair.get(pair)

        if check is None:
            if _prompt_reached_mandatory(
                prompt,
                submitted_at=None,
                now_utc=now_utc,
            ):
                bucket["reached_mandatory"] += 1
            continue

        bucket["completed"] += 1
        branch_stats[branch_id_value]["completed"] += 1

        if check.general_status == SystemDailyCheckGeneralStatus.NORMAL:
            bucket["normal"] += 1
        elif (
            check.general_status
            == SystemDailyCheckGeneralStatus.MINOR_FAILURE
        ):
            bucket["minor_failure"] += 1
            branch_stats[branch_id_value][
                "checks_with_failure"
            ] += 1
        elif (
            check.general_status
            == SystemDailyCheckGeneralStatus.OPERATIONAL_IMPACT
        ):
            bucket["operational_impact"] += 1
            branch_stats[branch_id_value][
                "checks_with_failure"
            ] += 1

        postpone_count = int(
            getattr(prompt, "postpone_count", 0) or 0
        )
        if postpone_count <= 0:
            bucket["completed_without_postpone"] += 1
        elif postpone_count == 1:
            bucket["completed_after_1"] += 1
        else:
            bucket["completed_after_2"] += 1

        if _prompt_reached_mandatory(
            prompt,
            submitted_at=check.submitted_at,
            now_utc=now_utc,
        ):
            bucket["reached_mandatory"] += 1

    for answer_row in answers:
        if (
            answer_row.answer
            != SystemDailyCheckAnswerValue.NO
        ):
            continue
        check = check_by_id.get(int(answer_row.check_id))
        if check is None:
            continue
        pair = (
            int(check.sucursal_id),
            check.business_date,
        )
        bucket = buckets[
            daily_bucket_key[check.business_date]
        ]
        bucket["no_answers"] += 1

        branch_row = branch_stats[int(check.sucursal_id)]
        branch_row["no_answers"] += 1

        stat = question_stats.setdefault(
            answer_row.question_key,
            {
                "question_key": answer_row.question_key,
                "question_label": (
                    answer_row.question_label_snapshot
                ),
                "no_answers": 0,
                "issues_total": 0,
                "reported": 0,
                "affected_branches": set(),
                "business_dates": set(),
            },
        )
        stat["no_answers"] += 1
        stat["affected_branches"].add(
            int(check.sucursal_id)
        )
        stat["business_dates"].add(check.business_date)
        recurrence_dates.setdefault(
            (
                int(check.sucursal_id),
                answer_row.question_key,
            ),
            set(),
        ).add(check.business_date)

        issue = issues_by_answer.get(int(answer_row.id))
        if issue is None:
            continue

        bucket["issues_total"] += 1
        branch_row["issues_total"] += 1
        stat["issues_total"] += 1
        if bool(issue.reported_to_support):
            bucket["reported"] += 1
            branch_row["reported"] += 1
            stat["reported"] += 1

    trend = []
    for period_start in sorted(buckets):
        bucket = buckets[period_start]
        bucket["pending"] = max(
            0,
            bucket["expected"] - bucket["completed"],
        )
        bucket["compliance_pct"] = (
            round(
                (
                    bucket["completed"]
                    / bucket["expected"]
                )
                * 100,
                1,
            )
            if bucket["expected"]
            else None
        )
        bucket["unreported"] = (
            bucket["issues_total"] - bucket["reported"]
        )
        bucket["reported_pct"] = (
            round(
                (
                    bucket["reported"]
                    / bucket["issues_total"]
                )
                * 100,
                1,
            )
            if bucket["issues_total"]
            else None
        )
        trend.append(bucket)

    question_ranking = []
    for stat in question_stats.values():
        issues_total = int(stat["issues_total"])
        reported = int(stat["reported"])
        question_ranking.append({
            "question_key": stat["question_key"],
            "question_label": stat["question_label"],
            "no_answers": int(stat["no_answers"]),
            "issues_total": issues_total,
            "reported": reported,
            "reported_pct": (
                round(
                    (reported / issues_total) * 100,
                    1,
                )
                if issues_total
                else None
            ),
            "affected_branches": len(
                stat["affected_branches"]
            ),
            "distinct_days": len(
                stat["business_dates"]
            ),
        })
    question_ranking.sort(
        key=lambda row: (
            -row["no_answers"],
            row["question_key"],
        )
    )

    branch_ranking = []
    for row in branch_stats.values():
        issues_total = int(row["issues_total"])
        reported = int(row["reported"])
        branch_ranking.append({
            **row,
            "pending": max(
                0,
                int(row["expected"])
                - int(row["completed"]),
            ),
            "reported_pct": (
                round(
                    (reported / issues_total) * 100,
                    1,
                )
                if issues_total
                else None
            ),
        })
    branch_ranking.sort(
        key=lambda row: (
            -row["no_answers"],
            -row["checks_with_failure"],
            str(row["sucursal"] or ""),
        )
    )

    recurrence = []
    for (
        branch_id_value,
        question_key,
    ), business_dates in recurrence_dates.items():
        distinct_days = len(business_dates)
        if distinct_days < 2:
            continue
        question_stat = question_stats[question_key]
        recurrence.append({
            "sucursal_id": branch_id_value,
            "sucursal": (
                branches_by_id[branch_id_value].sucursal
                if branch_id_value in branches_by_id
                else None
            ),
            "question_key": question_key,
            "question_label": (
                question_stat["question_label"]
            ),
            "distinct_days": distinct_days,
            "first_business_date": min(
                business_dates
            ).isoformat(),
            "last_business_date": max(
                business_dates
            ).isoformat(),
        })
    recurrence.sort(
        key=lambda row: (
            -row["distinct_days"],
            str(row["sucursal"] or ""),
            row["question_key"],
        )
    )

    return {
        "filters": {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "branch_id": resolved_branch_id,
            "granularity": normalized_granularity,
            "week_convention": (
                "SUNDAY_TO_SATURDAY"
                if normalized_granularity == "WEEK"
                else None
            ),
        },
        "trend": trend,
        "question_ranking": question_ranking,
        "branch_ranking": branch_ranking,
        "recurrence": recurrence,
    }


def list_system_daily_check_bi_pending(
    actor,
    *,
    date_from: date,
    date_to: date,
    branch_id: object = None,
    page: object = 1,
    page_size: object = 50,
    now: datetime | None = None,
    session: Session | None = None,
) -> dict:
    _require_mvp_access(actor)
    _validate_date_range(date_from, date_to)
    target_session = _session(session)
    resolved_branch_id = _normalize_summary_branch_id(
        branch_id,
        session=target_session,
    )
    parsed_page, parsed_page_size = _normalize_pagination(
        page,
        page_size,
    )

    expected_pairs = _expected_branch_days(
        target_session,
        date_from=date_from,
        date_to=date_to,
        branch_id=resolved_branch_id,
    )
    expected_branch_ids = sorted({
        branch_id_value
        for branch_id_value, _ in expected_pairs
    })

    completed_pairs = set()
    if expected_branch_ids:
        completed_pairs = {
            (int(check.sucursal_id), check.business_date)
            for check in target_session.scalars(
                select(SystemDailyCheckORM).where(
                    SystemDailyCheckORM.business_date >= date_from,
                    SystemDailyCheckORM.business_date <= date_to,
                    SystemDailyCheckORM.sucursal_id.in_(
                        expected_branch_ids
                    ),
                )
            ).all()
            if (
                int(check.sucursal_id),
                check.business_date,
            ) in expected_pairs
        }

    pending_pairs = sorted(
        expected_pairs - completed_pairs,
        key=lambda pair: (
            pair[1],
            pair[0],
        ),
        reverse=True,
    )
    total = len(pending_pairs)
    start = (parsed_page - 1) * parsed_page_size
    page_pairs = pending_pairs[
        start:start + parsed_page_size
    ]

    page_branch_ids = sorted({
        branch_id_value
        for branch_id_value, _ in page_pairs
    })
    branches_by_id = {}
    if page_branch_ids:
        branches_by_id = {
            int(branch.sucursal_id): branch
            for branch in target_session.scalars(
                select(Sucursal).where(
                    Sucursal.sucursal_id.in_(
                        page_branch_ids
                    )
                )
            ).all()
        }

    prompt_by_pair = {}
    if page_pairs:
        page_dates = [pair[1] for pair in page_pairs]
        prompt_by_pair = {
            (int(prompt.sucursal_id), prompt.business_date): prompt
            for prompt in target_session.scalars(
                select(SystemDailyCheckPromptStateORM).where(
                    SystemDailyCheckPromptStateORM.sucursal_id.in_(
                        page_branch_ids
                    ),
                    SystemDailyCheckPromptStateORM.business_date
                    >= min(page_dates),
                    SystemDailyCheckPromptStateORM.business_date
                    <= max(page_dates),
                )
            ).all()
            if (
                int(prompt.sucursal_id),
                prompt.business_date,
            ) in set(page_pairs)
        }

    now_utc = _as_utc(
        now or datetime.now(timezone.utc)
    )
    items = []
    for pair in page_pairs:
        branch_id_value, business_date_value = pair
        branch = branches_by_id.get(branch_id_value)
        prompt = prompt_by_pair.get(pair)
        items.append({
            "sucursal_id": branch_id_value,
            "sucursal": (
                branch.sucursal
                if branch is not None
                else None
            ),
            "business_date": business_date_value.isoformat(),
            "postpone_count": int(
                getattr(prompt, "postpone_count", 0) or 0
            ),
            "mandatory": _prompt_reached_mandatory(
                prompt,
                submitted_at=None,
                now_utc=now_utc,
            ),
            "next_prompt_at": (
                _as_utc(prompt.next_prompt_at).isoformat()
                if prompt is not None
                and prompt.next_prompt_at is not None
                else None
            ),
            "mandatory_from_at": (
                _as_utc(prompt.mandatory_from_at).isoformat()
                if prompt is not None
                and prompt.mandatory_from_at is not None
                else None
            ),
        })

    return {
        "filters": {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "branch_id": resolved_branch_id,
        },
        "page": parsed_page,
        "page_size": parsed_page_size,
        "total": total,
        "items": items,
    }
