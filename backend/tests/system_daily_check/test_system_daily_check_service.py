from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, create_engine, select
from sqlalchemy.orm import Session

from app.models import (
    SystemDailyCheckAnswerORM,
    SystemDailyCheckIssueORM,
    SystemDailyCheckORM,
    SystemDailyCheckPromptStateORM,
)
from app.services.system_daily_check_service import (
    QUESTIONS,
    SystemDailyCheckAuthorizationError,
    SystemDailyCheckConflictError,
    SystemDailyCheckValidationError,
    get_today_status,
    list_system_daily_check_questions,
    postpone_today,
    resolve_business_date,
    submit_today,
    validate_submission_payload,
)


def _engine():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table("users", metadata, Column("id", Integer, primary_key=True))
    Table(
        "sucursales",
        metadata,
        Column("sucursal_id", Integer, primary_key=True),
    )
    SystemDailyCheckORM.__table__.to_metadata(metadata)
    SystemDailyCheckAnswerORM.__table__.to_metadata(metadata)
    SystemDailyCheckIssueORM.__table__.to_metadata(metadata)
    SystemDailyCheckPromptStateORM.__table__.to_metadata(metadata)

    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        metadata.create_all(connection)
        connection.exec_driver_sql(
            "INSERT INTO users (id) VALUES (1), (2), (3)"
        )
        connection.exec_driver_sql(
            "INSERT INTO sucursales (sucursal_id) VALUES (10), (11)"
        )
    return engine


def _actor(
    *,
    user_id=1,
    username="sistemas-user",
    role="SISTEMAS",
    branch_id=10,
):
    return SimpleNamespace(
        id=user_id,
        username=username,
        rol=role,
        sucursal_id=branch_id,
        sucursales_ids=[],
    )


def _payload(
    *,
    no_keys=(),
    general_status=None,
    reported_to_support=False,
):
    no_keys = set(no_keys)
    answers = []

    for question in QUESTIONS:
        row = {
            "question_key": question.key,
            "answer": "NO" if question.key in no_keys else "YES",
        }
        if question.key in no_keys:
            issue = {
                "reported_to_support": reported_to_support,
                "description": f"Falla observada en {question.key}.",
            }
            if question.requires_affected_scope:
                issue["affected_scope"] = "ONE"
            row["issue"] = issue
        answers.append(row)

    if general_status is None:
        general_status = (
            "MINOR_FAILURE"
            if no_keys
            else "NORMAL"
        )

    return {
        "answers": answers,
        "general_status": general_status,
    }


def test_question_catalog_matches_contract_and_scope_semantics():
    payload = list_system_daily_check_questions()
    assert len(payload) == 13
    assert [row["question_key"] for row in payload] == [
        "COMPUTERS_WORKING",
        "PERIPHERALS_WORKING",
        "PRINTERS_WORKING",
        "BANK_TERMINALS_WORKING",
        "INTERNET_WORKING",
        "GASCA_WORKING",
        "SUITE_ULTRA_WORKING",
        "TURNSTILES_WORKING",
        "ACCESS_READERS_WORKING",
        "TURNSTILE_SCREENS_WORKING",
        "AMBIENT_AUDIO_WORKING",
        "TV_SCREENS_WORKING",
        "CAMERAS_WORKING",
    ]
    by_key = {row["question_key"]: row for row in payload}
    assert by_key["COMPUTERS_WORKING"]["requires_affected_scope"] is True
    assert by_key["INTERNET_WORKING"]["requires_affected_scope"] is True
    assert by_key["GASCA_WORKING"]["requires_affected_scope"] is False
    assert by_key["SUITE_ULTRA_WORKING"]["requires_affected_scope"] is False
    assert by_key["AMBIENT_AUDIO_WORKING"]["requires_affected_scope"] is False


def test_business_date_uses_america_tijuana_midnight_boundary():
    assert resolve_business_date(
        datetime(2026, 10, 10, 6, 59, tzinfo=timezone.utc)
    ).isoformat() == "2026-10-09"

    assert resolve_business_date(
        datetime(2026, 10, 10, 7, 0, tzinfo=timezone.utc)
    ).isoformat() == "2026-10-10"


def test_submission_requires_all_questions_and_rejects_unknown_or_duplicate():
    missing = _payload()
    missing["answers"] = missing["answers"][:-1]
    with pytest.raises(SystemDailyCheckValidationError, match="Faltan respuestas"):
        validate_submission_payload(missing)

    unknown = _payload()
    unknown["answers"][0]["question_key"] = "UNKNOWN"
    with pytest.raises(SystemDailyCheckValidationError, match="no reconocido"):
        validate_submission_payload(unknown)

    duplicate = _payload()
    duplicate["answers"][-1]["question_key"] = duplicate["answers"][0]["question_key"]
    with pytest.raises(SystemDailyCheckValidationError, match="duplicada"):
        validate_submission_payload(duplicate)


def test_no_requires_issue_description_reported_flag_and_scope_when_applicable():
    payload = _payload(no_keys={"COMPUTERS_WORKING"})
    parsed = validate_submission_payload(payload)
    assert parsed["no_count"] == 1

    missing_issue = _payload(no_keys={"COMPUTERS_WORKING"})
    missing_issue["answers"][0].pop("issue")
    with pytest.raises(SystemDailyCheckValidationError, match="obligatorio"):
        validate_submission_payload(missing_issue)

    missing_scope = _payload(no_keys={"COMPUTERS_WORKING"})
    missing_scope["answers"][0]["issue"].pop("affected_scope")
    with pytest.raises(SystemDailyCheckValidationError, match="affected_scope"):
        validate_submission_payload(missing_scope)

    missing_description = _payload(no_keys={"COMPUTERS_WORKING"})
    missing_description["answers"][0]["issue"]["description"] = "   "
    with pytest.raises(SystemDailyCheckValidationError, match="description"):
        validate_submission_payload(missing_description)

    invalid_reported = _payload(no_keys={"COMPUTERS_WORKING"})
    invalid_reported["answers"][0]["issue"]["reported_to_support"] = "NO"
    with pytest.raises(SystemDailyCheckValidationError, match="booleano"):
        validate_submission_payload(invalid_reported)


def test_non_countable_question_rejects_affected_scope_and_yes_rejects_issue():
    gasca = _payload(no_keys={"GASCA_WORKING"})
    gasca_row = next(
        row
        for row in gasca["answers"]
        if row["question_key"] == "GASCA_WORKING"
    )
    gasca_row["issue"]["affected_scope"] = "ONE"
    with pytest.raises(SystemDailyCheckValidationError, match="no aplica"):
        validate_submission_payload(gasca)

    yes_payload = _payload()
    yes_payload["answers"][0]["issue"] = {
        "affected_scope": "ONE",
        "reported_to_support": False,
        "description": "No debería persistirse.",
    }
    with pytest.raises(SystemDailyCheckValidationError, match="solo aplica"):
        validate_submission_payload(yes_payload)


@pytest.mark.parametrize(
    ("no_keys", "general_status", "valid"),
    [
        (set(), "NORMAL", True),
        (set(), "MINOR_FAILURE", False),
        (set(), "OPERATIONAL_IMPACT", False),
        ({"GASCA_WORKING"}, "NORMAL", False),
        ({"GASCA_WORKING"}, "MINOR_FAILURE", True),
        ({"GASCA_WORKING"}, "OPERATIONAL_IMPACT", True),
    ],
)
def test_general_status_consistency(no_keys, general_status, valid):
    payload = _payload(
        no_keys=no_keys,
        general_status=general_status,
    )
    if valid:
        validate_submission_payload(payload)
    else:
        with pytest.raises(SystemDailyCheckValidationError):
            validate_submission_payload(payload)


def test_initial_status_and_requested_branch_are_backend_validated():
    engine = _engine()
    try:
        with Session(engine) as session:
            status = get_today_status(
                _actor(),
                requested_branch_id=11,
                now=datetime(2026, 10, 9, 16, 0, tzinfo=timezone.utc),
                session=session,
            )
            assert status["eligible"] is True
            assert status["sucursal_id"] == 11
            assert status["completed"] is False
            assert status["postpone_count"] == 0
            assert status["can_postpone"] is True
            assert status["should_prompt"] is True
            assert status["mandatory"] is False

            with pytest.raises(SystemDailyCheckValidationError, match="no existe"):
                get_today_status(
                    _actor(),
                    requested_branch_id=999,
                    now=datetime(2026, 10, 9, 16, 0, tzinfo=timezone.utc),
                    session=session,
                )
    finally:
        engine.dispose()


def test_unauthorized_roles_cannot_activate_daily_flow():
    engine = _engine()
    try:
        with Session(engine) as session:
            with pytest.raises(SystemDailyCheckAuthorizationError):
                get_today_status(
                    _actor(role="GERENTE"),
                    now=datetime(2026, 10, 9, 16, 0, tzinfo=timezone.utc),
                    session=session,
                )

            with pytest.raises(SystemDailyCheckAuthorizationError):
                postpone_today(
                    _actor(role="TECNICO"),
                    now=datetime(2026, 10, 9, 16, 0, tzinfo=timezone.utc),
                    session=session,
                )
    finally:
        engine.dispose()


def test_two_postpones_five_minutes_and_mandatory_transition():
    engine = _engine()
    t0 = datetime(2026, 10, 9, 16, 0, tzinfo=timezone.utc)
    try:
        with Session(engine) as session:
            first = postpone_today(
                _actor(),
                now=t0,
                session=session,
            )
            session.commit()
            assert first["postpone_count"] == 1
            assert first["can_postpone"] is False
            assert first["should_prompt"] is False
            assert first["mandatory"] is False

        with Session(engine) as session:
            before_five = get_today_status(
                _actor(),
                now=t0 + timedelta(minutes=4, seconds=59),
                session=session,
            )
            assert before_five["should_prompt"] is False
            assert before_five["can_postpone"] is False

        with Session(engine) as session:
            after_five = get_today_status(
                _actor(),
                now=t0 + timedelta(minutes=5),
                session=session,
            )
            assert after_five["should_prompt"] is True
            assert after_five["can_postpone"] is True

            second = postpone_today(
                _actor(),
                now=t0 + timedelta(minutes=5),
                session=session,
            )
            session.commit()
            assert second["postpone_count"] == 2
            assert second["can_postpone"] is False
            assert second["mandatory"] is False

        with Session(engine) as session:
            before_mandatory = get_today_status(
                _actor(),
                now=t0 + timedelta(minutes=9, seconds=59),
                session=session,
            )
            assert before_mandatory["mandatory"] is False
            assert before_mandatory["should_prompt"] is False

            mandatory = get_today_status(
                _actor(),
                now=t0 + timedelta(minutes=10),
                session=session,
            )
            assert mandatory["mandatory"] is True
            assert mandatory["should_prompt"] is True
            assert mandatory["can_postpone"] is False

            with pytest.raises(SystemDailyCheckConflictError, match="dos aplazamientos"):
                postpone_today(
                    _actor(),
                    now=t0 + timedelta(minutes=10),
                    session=session,
                )
    finally:
        engine.dispose()


def test_double_click_cannot_consume_second_postpone_during_wait():
    engine = _engine()
    t0 = datetime(2026, 10, 9, 16, 0, tzinfo=timezone.utc)
    try:
        with Session(engine) as session:
            postpone_today(
                _actor(),
                now=t0,
                session=session,
            )
            session.commit()

        with Session(engine) as session:
            with pytest.raises(SystemDailyCheckConflictError, match="periodo"):
                postpone_today(
                    _actor(),
                    now=t0 + timedelta(seconds=1),
                    session=session,
                )

            state = session.execute(
                select(SystemDailyCheckPromptStateORM)
            ).scalar_one()
            assert state.postpone_count == 1
    finally:
        engine.dispose()


def test_submit_persists_answers_independent_issues_and_marks_completed():
    engine = _engine()
    now = datetime(2026, 10, 9, 16, 0, tzinfo=timezone.utc)
    payload = _payload(
        no_keys={
            "COMPUTERS_WORKING",
            "GASCA_WORKING",
        },
        reported_to_support=True,
    )
    try:
        with Session(engine) as session:
            postpone_today(
                _actor(),
                now=now - timedelta(minutes=10),
                session=session,
            )
            session.commit()

        with Session(engine) as session:
            check = submit_today(
                _actor(),
                payload,
                now=now,
                session=session,
            )
            session.commit()
            check_id = check.id

        with Session(engine) as session:
            check = session.get(SystemDailyCheckORM, check_id)
            answers = list(
                session.scalars(
                    select(SystemDailyCheckAnswerORM).where(
                        SystemDailyCheckAnswerORM.check_id == check_id
                    )
                ).all()
            )
            issues = list(
                session.scalars(
                    select(SystemDailyCheckIssueORM)
                ).all()
            )
            prompt = session.execute(
                select(SystemDailyCheckPromptStateORM)
            ).scalar_one()

            assert check.sucursal_id == 10
            assert check.performed_by_user_id == 1
            assert check.general_status == "MINOR_FAILURE"
            assert len(answers) == 13
            assert len(issues) == 2
            assert {
                answer.question_key
                for answer in answers
                if answer.answer == "NO"
            } == {
                "COMPUTERS_WORKING",
                "GASCA_WORKING",
            }
            assert prompt.postpone_count == 1
            assert prompt.completed_at is not None

            status = get_today_status(
                _actor(),
                now=now,
                session=session,
            )
            assert status["completed"] is True
            assert status["check_id"] == check_id
            assert status["can_postpone"] is False
            assert status["should_prompt"] is False
            assert status["mandatory"] is False
    finally:
        engine.dispose()


def test_repeated_submit_is_explicit_conflict_not_duplicate():
    engine = _engine()
    now = datetime(2026, 10, 9, 16, 0, tzinfo=timezone.utc)
    try:
        with Session(engine) as session:
            submit_today(
                _actor(),
                _payload(),
                now=now,
                session=session,
            )
            session.commit()

        with Session(engine) as session:
            with pytest.raises(SystemDailyCheckConflictError, match="ya fue enviado"):
                submit_today(
                    _actor(user_id=2),
                    _payload(),
                    now=now,
                    session=session,
                )

            assert session.scalar(
                select(SystemDailyCheckORM)
                .with_only_columns(
                    SystemDailyCheckORM.id
                )
                .limit(2)
            ) is not None
            assert len(
                list(session.scalars(select(SystemDailyCheckORM)).all())
            ) == 1
    finally:
        engine.dispose()
