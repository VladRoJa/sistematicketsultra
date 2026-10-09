from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import Session

from app.models import (
    Sucursal,
    SystemDailyCheckAnswerORM,
    SystemDailyCheckIssueAttachmentORM,
    SystemDailyCheckIssueORM,
    SystemDailyCheckORM,
    SystemDailyCheckPromptStateORM,
    UserORM,
)
from app.services.system_daily_check_bi_service import (
    get_system_daily_check_bi_detail,
    list_system_daily_check_bi_history,
)
from app.services.system_daily_check_service import (
    SystemDailyCheckAuthorizationError,
)


def _engine():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Sucursal.__table__.to_metadata(metadata)
    UserORM.__table__.to_metadata(metadata)
    SystemDailyCheckORM.__table__.to_metadata(metadata)
    SystemDailyCheckAnswerORM.__table__.to_metadata(metadata)
    SystemDailyCheckIssueORM.__table__.to_metadata(metadata)
    SystemDailyCheckIssueAttachmentORM.__table__.to_metadata(metadata)
    SystemDailyCheckPromptStateORM.__table__.to_metadata(metadata)

    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        metadata.create_all(connection)
        connection.exec_driver_sql(
            """
            INSERT INTO sucursales (
                sucursal_id, serie, sucursal, estado,
                operational_status, is_demo, municipio, direccion
            )
            VALUES
                (10, 'S10', 'ALFA', 'BC', 'ACTIVA', 0, 'MEXICALI', 'N/A')
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO users (
                id, username, password, rol,
                sucursal_id, department_id, email
            )
            VALUES
                (1, 'SISTEMAS', 'x', 'SISTEMAS', 10, 1, NULL)
            """
        )
    return engine


def _actor(*, role="SISTEMAS"):
    return SimpleNamespace(
        id=1,
        username="SISTEMAS",
        rol=role,
    )


def _seed(session: Session):
    check_old = SystemDailyCheckORM(
        id=1,
        sucursal_id=10,
        business_date=date(2026, 10, 8),
        performed_by_user_id=1,
        general_status="NORMAL",
        submitted_at=datetime(
            2026, 10, 8, 16, 0,
            tzinfo=timezone.utc,
        ),
    )
    check = SystemDailyCheckORM(
        id=2,
        sucursal_id=10,
        business_date=date(2026, 10, 9),
        performed_by_user_id=1,
        general_status="MINOR_FAILURE",
        submitted_at=datetime(
            2026, 10, 9, 17, 0,
            tzinfo=timezone.utc,
        ),
    )
    session.add_all([check_old, check])
    session.flush()

    answers = [
        SystemDailyCheckAnswerORM(
            id=1,
            check_id=1,
            question_key="GASCA_WORKING",
            question_label_snapshot="Gasca",
            category_key="CONNECTIVITY_SYSTEMS",
            answer="YES",
        ),
        SystemDailyCheckAnswerORM(
            id=2,
            check_id=2,
            question_key="GASCA_WORKING",
            question_label_snapshot="Gasca",
            category_key="CONNECTIVITY_SYSTEMS",
            answer="NO",
        ),
        SystemDailyCheckAnswerORM(
            id=3,
            check_id=2,
            question_key="INTERNET_WORKING",
            question_label_snapshot="Internet",
            category_key="CONNECTIVITY_SYSTEMS",
            answer="NO",
        ),
        SystemDailyCheckAnswerORM(
            id=4,
            check_id=2,
            question_key="TV_SCREENS_WORKING",
            question_label_snapshot="TV",
            category_key="AUXILIARY_SYSTEMS",
            answer="NA",
        ),
    ]
    session.add_all(answers)
    session.flush()

    issue_gasca = SystemDailyCheckIssueORM(
        id=1,
        answer_id=2,
        reported_to_support=True,
        description="Gasca no abre.",
    )
    issue_internet = SystemDailyCheckIssueORM(
        id=2,
        answer_id=3,
        affected_scope="MULTIPLE",
        reported_to_support=False,
        description="Sin internet.",
    )
    session.add_all([issue_gasca, issue_internet])
    session.flush()

    session.add(
        SystemDailyCheckIssueAttachmentORM(
            id=1,
            issue_id=1,
            original_filename="gasca.png",
            storage_key=(
                "system-daily-checks/issues/1/gasca.png"
            ),
            mime_type="image/png",
            file_size_bytes=123,
            sha256="a" * 64,
            uploaded_by_user_id=1,
        )
    )
    session.add(
        SystemDailyCheckPromptStateORM(
            sucursal_id=10,
            business_date=date(2026, 10, 9),
            postpone_count=2,
            mandatory_from_at=datetime(
                2026, 10, 9, 16, 30,
                tzinfo=timezone.utc,
            ),
            completed_at=datetime(
                2026, 10, 9, 17, 0,
                tzinfo=timezone.utc,
            ),
        )
    )
    session.commit()


def test_history_answer_filter_uses_check_semantics_not_answer_rows():
    engine = _engine()
    try:
        with Session(engine) as session:
            _seed(session)

        with Session(engine) as session:
            result = list_system_daily_check_bi_history(
                _actor(),
                date_from=date(2026, 10, 8),
                date_to=date(2026, 10, 9),
                answer="NO",
                session=session,
            )

        assert result["total"] == 1
        assert len(result["items"]) == 1
        item = result["items"][0]
        assert item["id"] == 2
        assert item["sucursal"] == "ALFA"
        assert item["performed_by_username"] == "SISTEMAS"
        assert item["postpone_count"] == 2
        assert item["reached_mandatory"] is True
    finally:
        engine.dispose()


def test_history_question_and_answer_filter_match_same_answer():
    engine = _engine()
    try:
        with Session(engine) as session:
            _seed(session)

        with Session(engine) as session:
            result = list_system_daily_check_bi_history(
                _actor(),
                date_from=date(2026, 10, 8),
                date_to=date(2026, 10, 9),
                question_key="GASCA_WORKING",
                answer="YES",
                session=session,
            )

        assert result["total"] == 1
        assert result["items"][0]["id"] == 1
    finally:
        engine.dispose()


def test_detail_reconstructs_issue_attachment_and_prompt():
    engine = _engine()
    try:
        with Session(engine) as session:
            _seed(session)

        with Session(engine) as session:
            detail = get_system_daily_check_bi_detail(
                _actor(),
                check_id=2,
                session=session,
            )

        assert detail["sucursal"] == "ALFA"
        assert detail["performed_by_username"] == "SISTEMAS"
        assert detail["general_status"] == "MINOR_FAILURE"
        assert detail["answer_count"] == 3
        assert detail["prompt"]["postpone_count"] == 2
        assert detail["prompt"]["reached_mandatory"] is True

        by_key = {
            row["question_key"]: row
            for row in detail["answers"]
        }
        gasca = by_key["GASCA_WORKING"]
        assert gasca["answer"] == "NO"
        assert gasca["issue"]["reported_to_support"] is True
        assert gasca["issue"]["description"] == "Gasca no abre."
        assert gasca["issue"]["attachments"][0] == {
            "id": 1,
            "original_filename": "gasca.png",
            "mime_type": "image/png",
            "file_size_bytes": 123,
            "sha256": "a" * 64,
            "url": "/api/system-daily-checks/bi/attachments/1",
        }
        assert by_key["TV_SCREENS_WORKING"]["answer"] == "NA"
        assert by_key["TV_SCREENS_WORKING"]["issue"] is None
    finally:
        engine.dispose()


def test_history_rejects_non_mvp_actor():
    engine = _engine()
    try:
        with Session(engine) as session:
            with pytest.raises(SystemDailyCheckAuthorizationError):
                list_system_daily_check_bi_history(
                    _actor(role="GERENTE"),
                    date_from=date(2026, 10, 9),
                    date_to=date(2026, 10, 9),
                    session=session,
                )
    finally:
        engine.dispose()
