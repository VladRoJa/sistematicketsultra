from __future__ import annotations

from datetime import date
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
    UserORM,
)
from app.services.system_daily_check_bi_service import (
    get_system_daily_check_bi_attachment,
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


def _seed(session: Session, storage_key: str):
    session.add(
        SystemDailyCheckORM(
            id=1,
            sucursal_id=10,
            business_date=date(2026, 10, 9),
            performed_by_user_id=1,
            general_status="MINOR_FAILURE",
        )
    )
    session.flush()
    session.add(
        SystemDailyCheckAnswerORM(
            id=1,
            check_id=1,
            question_key="GASCA_WORKING",
            question_label_snapshot="Gasca",
            category_key="CONNECTIVITY_SYSTEMS",
            answer="NO",
        )
    )
    session.flush()
    session.add(
        SystemDailyCheckIssueORM(
            id=1,
            answer_id=1,
            reported_to_support=True,
            description="Gasca no abre.",
        )
    )
    session.flush()
    session.add(
        SystemDailyCheckIssueAttachmentORM(
            id=1,
            issue_id=1,
            original_filename="gasca.png",
            storage_key=storage_key,
            mime_type="image/png",
            file_size_bytes=3,
            sha256="a" * 64,
            uploaded_by_user_id=1,
        )
    )
    session.commit()


def test_attachment_resolver_returns_only_domain_file(
    tmp_path,
    monkeypatch,
):
    engine = _engine()
    storage_key = (
        "system-daily-checks/issues/1/"
        + ("a" * 32)
        + ".png"
    )
    monkeypatch.setenv(
        "SYSTEM_DAILY_CHECK_ATTACHMENT_DIR",
        str(tmp_path),
    )
    path = tmp_path.joinpath(*storage_key.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"png")

    try:
        with Session(engine) as session:
            _seed(session, storage_key)

        with Session(engine) as session:
            result = get_system_daily_check_bi_attachment(
                _actor(),
                attachment_id=1,
                session=session,
            )

        assert result["path"] == path.resolve()
        assert result["original_filename"] == "gasca.png"
        assert result["mime_type"] == "image/png"
        assert result["file_size_bytes"] == 3
        assert result["sha256"] == "a" * 64
    finally:
        engine.dispose()


def test_attachment_resolver_rejects_manager(
    tmp_path,
    monkeypatch,
):
    engine = _engine()
    storage_key = (
        "system-daily-checks/issues/1/"
        + ("b" * 32)
        + ".png"
    )
    monkeypatch.setenv(
        "SYSTEM_DAILY_CHECK_ATTACHMENT_DIR",
        str(tmp_path),
    )
    path = tmp_path.joinpath(*storage_key.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"png")

    try:
        with Session(engine) as session:
            _seed(session, storage_key)

        with Session(engine) as session:
            with pytest.raises(SystemDailyCheckAuthorizationError):
                get_system_daily_check_bi_attachment(
                    _actor(role="GERENTE"),
                    attachment_id=1,
                    session=session,
                )
    finally:
        engine.dispose()
