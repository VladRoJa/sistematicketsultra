from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.sucursal_model import Sucursal, SucursalOperationalStatus
from app.models.system_daily_check import (
    SystemDailyCheckAffectedScope,
    SystemDailyCheckAnswerORM,
    SystemDailyCheckAnswerValue,
    SystemDailyCheckGeneralStatus,
    SystemDailyCheckIssueORM,
    SystemDailyCheckORM,
    SystemDailyCheckPromptStateORM,
)
from app.utils.scope_utils import CORPORATE_BRANCH_ID, ROOT_BRANCH_ID
from app.utils.system_daily_check_access import has_system_daily_check_mvp_access


BUSINESS_TZ = ZoneInfo("America/Tijuana")
POSTPONE_INTERVAL = timedelta(minutes=5)

# PILOT TEMPORARY:
# Durante la prueba con SISTEMAS/ADMICORP, el nodo técnico Administrador
# (1000) representa la misma obligación diaria que Corporativo (100).
# Retirar este puente al terminar el piloto; no modifica la política global
# de sucursales técnicas.
SYSTEM_DAILY_CHECK_PILOT_CORPORATE_BRANCH_ID = CORPORATE_BRANCH_ID
SYSTEM_DAILY_CHECK_PILOT_ROOT_BRANCH_ID = ROOT_BRANCH_ID


class SystemDailyCheckAuthorizationError(PermissionError):
    pass


class SystemDailyCheckValidationError(ValueError):
    pass


class SystemDailyCheckConflictError(RuntimeError):
    pass


class SystemDailyCheckNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class SystemDailyCheckQuestion:
    key: str
    label: str
    category_key: str
    requires_affected_scope: bool = False

    def to_dict(self) -> dict:
        return {
            "question_key": self.key,
            "label": self.label,
            "category_key": self.category_key,
            "requires_affected_scope": self.requires_affected_scope,
        }


QUESTIONS: tuple[SystemDailyCheckQuestion, ...] = (
    SystemDailyCheckQuestion(
        key="COMPUTERS_WORKING",
        label="¿Las computadoras de la sucursal funcionan correctamente?",
        category_key="COMPUTING",
        requires_affected_scope=True,
    ),
    SystemDailyCheckQuestion(
        key="PERIPHERALS_WORKING",
        label="¿Los monitores, teclados y mouse funcionan?",
        category_key="COMPUTING",
        requires_affected_scope=True,
    ),
    SystemDailyCheckQuestion(
        key="PRINTERS_WORKING",
        label="¿Las impresoras funcionan correctamente?",
        category_key="COMPUTING",
        requires_affected_scope=True,
    ),
    SystemDailyCheckQuestion(
        key="BANK_TERMINALS_WORKING",
        label="¿Las terminales bancarias permiten realizar cobros?",
        category_key="COMPUTING",
        requires_affected_scope=True,
    ),
    SystemDailyCheckQuestion(
        key="INTERNET_WORKING",
        label="¿Las computadoras tienen conexión a internet?",
        category_key="CONNECTIVITY_SYSTEMS",
        requires_affected_scope=True,
    ),
    SystemDailyCheckQuestion(
        key="GASCA_WORKING",
        label="¿Gasca abre y permite realizar las operaciones necesarias?",
        category_key="CONNECTIVITY_SYSTEMS",
    ),
    SystemDailyCheckQuestion(
        key="SUITE_ULTRA_WORKING",
        label="¿Suite Ultra permite realizar las operaciones necesarias de la sucursal?",
        category_key="CONNECTIVITY_SYSTEMS",
    ),
    SystemDailyCheckQuestion(
        key="BI_REPORTS_WORKING",
        label="¿Los reportes BI que utiliza la sucursal abren y permiten consultar información?",
        category_key="CONNECTIVITY_SYSTEMS",
    ),
    SystemDailyCheckQuestion(
        key="TURNSTILES_WORKING",
        label="¿Los torniquetes permiten la entrada y salida?",
        category_key="ACCESS_CONTROL",
        requires_affected_scope=True,
    ),
    SystemDailyCheckQuestion(
        key="ACCESS_READERS_WORKING",
        label="¿Los lectores de acceso permiten validar correctamente a los usuarios?",
        category_key="ACCESS_CONTROL",
        requires_affected_scope=True,
    ),
    SystemDailyCheckQuestion(
        key="TURNSTILE_SCREENS_WORKING",
        label="¿Las pantallas de los torniquetes funcionan?",
        category_key="ACCESS_CONTROL",
        requires_affected_scope=True,
    ),
    SystemDailyCheckQuestion(
        key="AMBIENT_AUDIO_WORKING",
        label="¿La música ambiental funciona?",
        category_key="AUXILIARY_SYSTEMS",
    ),
    SystemDailyCheckQuestion(
        key="TV_SCREENS_WORKING",
        label="¿Las pantallas/TV funcionan?",
        category_key="AUXILIARY_SYSTEMS",
        requires_affected_scope=True,
    ),
    SystemDailyCheckQuestion(
        key="CAMERAS_WORKING",
        label="¿El sistema de cámaras funciona?",
        category_key="AUXILIARY_SYSTEMS",
        requires_affected_scope=True,
    ),
)

QUESTION_BY_KEY = {question.key: question for question in QUESTIONS}


def _session(session: Session | None):
    return session if session is not None else db.session


def _utc_now(now: datetime | None = None) -> datetime:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise SystemDailyCheckValidationError(
            "now debe incluir timezone."
        )
    return value.astimezone(timezone.utc)


def _db_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def resolve_business_date(now: datetime | None = None) -> date:
    return _utc_now(now).astimezone(BUSINESS_TZ).date()


def list_system_daily_check_questions() -> list[dict]:
    return [question.to_dict() for question in QUESTIONS]


def _require_mvp_access(actor) -> None:
    if not has_system_daily_check_mvp_access(actor):
        raise SystemDailyCheckAuthorizationError(
            "El usuario no está habilitado para el piloto del checklist diario."
        )


def _positive_int(value: object, field: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise SystemDailyCheckValidationError(
            f"{field} debe ser entero."
        ) from exc
    if parsed <= 0:
        raise SystemDailyCheckValidationError(
            f"{field} debe ser mayor que cero."
        )
    return parsed


def canonicalize_system_daily_check_branch_id(
    value: object,
) -> int:
    branch_id = _positive_int(value, "sucursal_id")
    if branch_id == SYSTEM_DAILY_CHECK_PILOT_ROOT_BRANCH_ID:
        return SYSTEM_DAILY_CHECK_PILOT_CORPORATE_BRANCH_ID
    return branch_id


def list_system_daily_check_branches(
    actor,
    *,
    session: Session | None = None,
) -> dict:
    """Checklist-only branch catalog for the temporary corporate pilot bridge."""
    _require_mvp_access(actor)
    target_session = _session(session)

    branches = list(
        target_session.scalars(
            select(Sucursal)
            .where(
                Sucursal.is_demo.is_(False),
                Sucursal.operational_status
                == SucursalOperationalStatus.ACTIVA,
                Sucursal.sucursal_id
                != SYSTEM_DAILY_CHECK_PILOT_ROOT_BRANCH_ID,
            )
            .order_by(Sucursal.sucursal.asc())
        ).all()
    )

    branch_ids = {
        int(branch.sucursal_id)
        for branch in branches
    }

    preferred_branch_id = None
    raw_primary = getattr(actor, "sucursal_id", None)
    if raw_primary not in (None, ""):
        candidate = canonicalize_system_daily_check_branch_id(
            raw_primary
        )
        if candidate in branch_ids:
            preferred_branch_id = candidate

    if preferred_branch_id is None and len(branches) == 1:
        preferred_branch_id = int(branches[0].sucursal_id)

    return {
        "branches": [
            {
                "sucursal_id": int(branch.sucursal_id),
                "sucursal": branch.sucursal,
                "serie": branch.serie,
                "operational_status": branch.operational_status,
                "is_demo": bool(branch.is_demo),
            }
            for branch in branches
        ],
        "preferred_branch_id": preferred_branch_id,
    }


def resolve_branch_id(
    actor,
    requested_branch_id: object = None,
) -> int:
    _require_mvp_access(actor)

    raw_value = requested_branch_id
    if raw_value in (None, ""):
        raw_value = getattr(actor, "sucursal_id", None)

    if raw_value in (None, ""):
        raise SystemDailyCheckValidationError(
            "No fue posible resolver la sucursal del checklist."
        )

    return canonicalize_system_daily_check_branch_id(raw_value)


def _assert_branch_exists(
    target_session,
    branch_id: int,
    *,
    lock: bool = False,
) -> None:
    stmt = select(Sucursal.sucursal_id).where(
        Sucursal.sucursal_id == int(branch_id)
    )
    if lock:
        stmt = stmt.with_for_update()

    found = target_session.execute(stmt).scalar_one_or_none()
    if found is None:
        raise SystemDailyCheckValidationError(
            "La sucursal seleccionada no existe."
        )


def _get_check(
    target_session,
    branch_id: int,
    business_date: date,
):
    return target_session.execute(
        select(SystemDailyCheckORM).where(
            SystemDailyCheckORM.sucursal_id == branch_id,
            SystemDailyCheckORM.business_date == business_date,
        )
    ).scalar_one_or_none()


def _get_prompt_state(
    target_session,
    branch_id: int,
    business_date: date,
):
    return target_session.execute(
        select(SystemDailyCheckPromptStateORM).where(
            SystemDailyCheckPromptStateORM.sucursal_id == branch_id,
            SystemDailyCheckPromptStateORM.business_date == business_date,
        )
    ).scalar_one_or_none()


def _get_or_create_prompt_state(
    target_session,
    branch_id: int,
    business_date: date,
):
    row = _get_prompt_state(
        target_session,
        branch_id,
        business_date,
    )
    if row is None:
        row = SystemDailyCheckPromptStateORM(
            sucursal_id=branch_id,
            business_date=business_date,
            postpone_count=0,
        )
        target_session.add(row)
        target_session.flush()
    return row


def _status_payload(
    *,
    branch_id: int,
    business_date: date,
    now_utc: datetime,
    check,
    prompt_state,
) -> dict:
    completed = check is not None
    postpone_count = (
        int(prompt_state.postpone_count)
        if prompt_state is not None
        else 0
    )
    next_prompt_at = (
        prompt_state.next_prompt_at
        if prompt_state is not None
        else None
    )
    mandatory_from_at = (
        prompt_state.mandatory_from_at
        if prompt_state is not None
        else None
    )

    eligible_now = (
        not completed
        and (
            next_prompt_at is None
            or now_utc >= _db_utc(next_prompt_at)
        )
    )
    mandatory = (
        not completed
        and mandatory_from_at is not None
        and now_utc >= _db_utc(mandatory_from_at)
    )
    can_postpone = (
        eligible_now
        and not mandatory
        and postpone_count < 2
    )

    return {
        "eligible": True,
        "sucursal_id": branch_id,
        "business_date": business_date.isoformat(),
        "completed": completed,
        "check_id": getattr(check, "id", None),
        "postpone_count": postpone_count,
        "can_postpone": can_postpone,
        "should_prompt": eligible_now,
        "mandatory": mandatory,
        "next_prompt_at": (
            next_prompt_at.isoformat()
            if next_prompt_at is not None
            else None
        ),
        "mandatory_from_at": (
            mandatory_from_at.isoformat()
            if mandatory_from_at is not None
            else None
        ),
        "completed_at": (
            prompt_state.completed_at.isoformat()
            if prompt_state is not None
            and prompt_state.completed_at is not None
            else (
                check.submitted_at.isoformat()
                if completed and check.submitted_at is not None
                else None
            )
        ),
    }


def get_today_status(
    actor,
    *,
    requested_branch_id: object = None,
    now: datetime | None = None,
    session: Session | None = None,
) -> dict:
    target_session = _session(session)
    now_utc = _utc_now(now)
    business_date = resolve_business_date(now_utc)
    branch_id = resolve_branch_id(actor, requested_branch_id)

    _assert_branch_exists(target_session, branch_id)
    check = _get_check(target_session, branch_id, business_date)
    prompt_state = _get_prompt_state(
        target_session,
        branch_id,
        business_date,
    )
    return _status_payload(
        branch_id=branch_id,
        business_date=business_date,
        now_utc=now_utc,
        check=check,
        prompt_state=prompt_state,
    )


def postpone_today(
    actor,
    *,
    requested_branch_id: object = None,
    now: datetime | None = None,
    session: Session | None = None,
) -> dict:
    target_session = _session(session)
    now_utc = _utc_now(now)
    business_date = resolve_business_date(now_utc)
    branch_id = resolve_branch_id(actor, requested_branch_id)

    _assert_branch_exists(
        target_session,
        branch_id,
        lock=True,
    )

    check = _get_check(target_session, branch_id, business_date)
    if check is not None:
        raise SystemDailyCheckConflictError(
            "El checklist de la sucursal ya fue enviado hoy."
        )

    prompt_state = _get_or_create_prompt_state(
        target_session,
        branch_id,
        business_date,
    )

    if (
        prompt_state.next_prompt_at is not None
        and now_utc < _db_utc(prompt_state.next_prompt_at)
    ):
        raise SystemDailyCheckConflictError(
            "El checklist todavía está dentro del periodo de aplazamiento."
        )

    postpone_count = int(prompt_state.postpone_count or 0)
    if postpone_count >= 2:
        raise SystemDailyCheckConflictError(
            "Ya se utilizaron los dos aplazamientos permitidos."
        )

    postpone_count += 1
    next_prompt_at = now_utc + POSTPONE_INTERVAL

    prompt_state.postpone_count = postpone_count
    prompt_state.last_postponed_at = now_utc
    prompt_state.next_prompt_at = next_prompt_at
    if postpone_count == 2:
        prompt_state.mandatory_from_at = next_prompt_at

    target_session.flush()

    return _status_payload(
        branch_id=branch_id,
        business_date=business_date,
        now_utc=now_utc,
        check=None,
        prompt_state=prompt_state,
    )


def _required_text(value: object, field: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise SystemDailyCheckValidationError(
            f"{field} es obligatorio."
        )
    return normalized


def _validate_choice(
    value: object,
    field: str,
    allowed: tuple[str, ...],
) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in allowed:
        raise SystemDailyCheckValidationError(
            f"{field} inválido."
        )
    return normalized


def _validate_issue(
    question: SystemDailyCheckQuestion,
    raw_issue: object,
    *,
    field_prefix: str,
) -> dict:
    if not isinstance(raw_issue, dict):
        raise SystemDailyCheckValidationError(
            f"{field_prefix} es obligatorio para una respuesta NO."
        )

    reported = raw_issue.get("reported_to_support")
    if not isinstance(reported, bool):
        raise SystemDailyCheckValidationError(
            f"{field_prefix}.reported_to_support debe ser booleano."
        )

    affected_scope_raw = raw_issue.get("affected_scope")
    affected_scope = None

    if question.requires_affected_scope:
        affected_scope = _validate_choice(
            affected_scope_raw,
            f"{field_prefix}.affected_scope",
            SystemDailyCheckAffectedScope.ALL,
        )
    elif affected_scope_raw not in (None, ""):
        raise SystemDailyCheckValidationError(
            f"{field_prefix}.affected_scope no aplica para esta pregunta."
        )

    return {
        "affected_scope": affected_scope,
        "reported_to_support": reported,
        "description": _required_text(
            raw_issue.get("description"),
            f"{field_prefix}.description",
        ),
    }


def validate_submission_payload(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise SystemDailyCheckValidationError(
            "Payload inválido."
        )

    raw_answers = payload.get("answers")
    if not isinstance(raw_answers, list):
        raise SystemDailyCheckValidationError(
            "answers debe ser una lista."
        )

    parsed_answers: dict[str, dict] = {}

    for index, raw_answer in enumerate(raw_answers):
        field_prefix = f"answers[{index}]"
        if not isinstance(raw_answer, dict):
            raise SystemDailyCheckValidationError(
                f"{field_prefix} es inválido."
            )

        question_key = _required_text(
            raw_answer.get("question_key"),
            f"{field_prefix}.question_key",
        ).upper()

        question = QUESTION_BY_KEY.get(question_key)
        if question is None:
            raise SystemDailyCheckValidationError(
                f"{field_prefix}.question_key no reconocido."
            )

        if question_key in parsed_answers:
            raise SystemDailyCheckValidationError(
                f"La pregunta {question_key} está duplicada."
            )

        answer_value = _validate_choice(
            raw_answer.get("answer"),
            f"{field_prefix}.answer",
            SystemDailyCheckAnswerValue.ALL,
        )

        issue = None
        if answer_value == SystemDailyCheckAnswerValue.NO:
            issue = _validate_issue(
                question,
                raw_answer.get("issue"),
                field_prefix=f"{field_prefix}.issue",
            )
        elif raw_answer.get("issue") not in (None, {}):
            raise SystemDailyCheckValidationError(
                f"{field_prefix}.issue solo aplica a respuestas NO."
            )

        parsed_answers[question_key] = {
            "question": question,
            "answer": answer_value,
            "issue": issue,
        }

    missing = [
        question.key
        for question in QUESTIONS
        if question.key not in parsed_answers
    ]
    if missing:
        raise SystemDailyCheckValidationError(
            "Faltan respuestas obligatorias: "
            + ", ".join(missing)
            + "."
        )

    general_status = _validate_choice(
        payload.get("general_status"),
        "general_status",
        SystemDailyCheckGeneralStatus.ALL,
    )

    no_count = sum(
        1
        for parsed in parsed_answers.values()
        if parsed["answer"] == SystemDailyCheckAnswerValue.NO
    )

    if (
        no_count == 0
        and general_status != SystemDailyCheckGeneralStatus.NORMAL
    ):
        raise SystemDailyCheckValidationError(
            "Sin respuestas NO, el estado general debe ser NORMAL."
        )

    if (
        no_count > 0
        and general_status == SystemDailyCheckGeneralStatus.NORMAL
    ):
        raise SystemDailyCheckValidationError(
            "Con respuestas NO, el estado general no puede ser NORMAL."
        )

    return {
        "answers": parsed_answers,
        "general_status": general_status,
        "no_count": no_count,
    }


def submit_today(
    actor,
    payload: object,
    *,
    requested_branch_id: object = None,
    now: datetime | None = None,
    session: Session | None = None,
) -> SystemDailyCheckORM:
    parsed = validate_submission_payload(payload)
    target_session = _session(session)
    now_utc = _utc_now(now)
    business_date = resolve_business_date(now_utc)
    branch_id = resolve_branch_id(actor, requested_branch_id)

    _assert_branch_exists(
        target_session,
        branch_id,
        lock=True,
    )

    existing = _get_check(
        target_session,
        branch_id,
        business_date,
    )
    if existing is not None:
        raise SystemDailyCheckConflictError(
            "El checklist de la sucursal ya fue enviado hoy."
        )

    check = SystemDailyCheckORM(
        sucursal_id=branch_id,
        business_date=business_date,
        performed_by_user_id=int(actor.id),
        general_status=parsed["general_status"],
        created_at=now_utc,
        submitted_at=now_utc,
    )
    target_session.add(check)
    target_session.flush()

    for question in QUESTIONS:
        parsed_answer = parsed["answers"][question.key]
        answer_row = SystemDailyCheckAnswerORM(
            check_id=check.id,
            question_key=question.key,
            question_label_snapshot=question.label,
            category_key=question.category_key,
            answer=parsed_answer["answer"],
            created_at=now_utc,
        )
        check.answers.append(answer_row)
        target_session.flush()

        issue = parsed_answer["issue"]
        if issue is not None:
            answer_row.issue = SystemDailyCheckIssueORM(
                answer_id=answer_row.id,
                affected_scope=issue["affected_scope"],
                reported_to_support=issue["reported_to_support"],
                description=issue["description"],
                created_at=now_utc,
            )
            target_session.flush()

    prompt_state = _get_or_create_prompt_state(
        target_session,
        branch_id,
        business_date,
    )
    prompt_state.completed_at = now_utc
    target_session.flush()
    return check
