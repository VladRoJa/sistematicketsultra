from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image
from sqlalchemy import BigInteger, Column, Integer, MetaData, String, Table, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.models.purchase_requisition import (
    PurchaseRequisitionAttachmentORM,
    PurchaseRequisitionEventORM,
    PurchaseRequisitionItemORM,
    PurchaseRequisitionORM,
)
from app.services.purchase_requisition_attachment_service import (
    create_purchase_requisition_attachment,
    get_purchase_requisition_attachment_file,
)
from app.services.purchase_requisition_attachment_storage_service import (
    build_purchase_requisition_attachment_storage_key,
    resolve_purchase_requisition_attachment_path,
)
from app.services.purchase_requisition_service import (
    PurchaseRequisitionAuthorizationError,
    create_purchase_requisition,
)
from app.services.purchase_requisition_workflow_service import (
    approve_purchase_requisition,
)


@compiles(BigInteger, "sqlite")
def _compile_bigint_as_integer(_type, compiler, **kw):
    return "INTEGER"


@pytest.fixture()
def engine():
    value = create_engine("sqlite://")
    metadata = MetaData()
    Table(
        "users",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("username", String(100), nullable=False),
        Column("password", String(255), nullable=False),
        Column("rol", String(50), nullable=False),
        Column("sucursal_id", Integer, nullable=False),
        Column("department_id", Integer, nullable=False),
        Column("email", String(255), nullable=True),
    )
    Table(
        "sucursales",
        metadata,
        Column("sucursal_id", Integer, primary_key=True),
    )
    PurchaseRequisitionORM.__table__.to_metadata(metadata)
    PurchaseRequisitionItemORM.__table__.to_metadata(metadata)
    PurchaseRequisitionEventORM.__table__.to_metadata(metadata)
    PurchaseRequisitionAttachmentORM.__table__.to_metadata(metadata)
    with value.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        metadata.create_all(connection)
        connection.exec_driver_sql(
            "INSERT INTO sucursales (sucursal_id) VALUES (10), (20)"
        )
        rows = [
            (1, "requester", "RECEPCIONISTA", 10),
            (2, "sports", "GERENCIA DEPORTIVA", 10),
            (3, "admin", "ADMINISTRADOR", 1000),
            (4, "maint", "MANTENIMIENTO", 1000),
            (5, "reader", "LECTOR_GLOBAL", 1000),
            (6, "other", "RECEPCIONISTA", 20),
            (7, "manager-origin", "GERENTE", 10),
            (8, "manager-other", "GERENTE", 20),
        ]
        for user_id, username, role, branch_id in rows:
            connection.exec_driver_sql(
                "INSERT INTO users "
                "(id, username, password, rol, sucursal_id, department_id, email) "
                "VALUES (?, ?, 'x', ?, ?, 1, ?)",
                (
                    user_id,
                    username,
                    role,
                    branch_id,
                    f"{username}@example.com",
                ),
            )
    try:
        yield value
    finally:
        value.dispose()


@pytest.fixture()
def storage_root(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "PURCHASE_REQUISITION_ATTACHMENT_DIR",
        str(tmp_path),
    )
    return tmp_path


def _user(user_id, role, branch_id):
    return SimpleNamespace(
        id=user_id,
        username=f"user-{user_id}",
        rol=role,
        sucursal_id=branch_id,
        sucursales_ids=[],
    )


def _payload():
    return {
        "sucursal_id": 10,
        "reason": "REPLACEMENT",
        "priority": "NORMAL",
        "justification": "Equipo desgastado.",
        "items": [{
            "item_description": "Caminadora",
            "quantity": 1,
        }],
    }


def _create(session):
    row = create_purchase_requisition(
        _payload(),
        _user(1, "RECEPCIONISTA", 10),
        session=session,
    )
    session.commit()
    return row


def _png_bytes():
    output = BytesIO()
    Image.new("RGB", (4, 4)).save(
        output,
        format="PNG",
    )
    return output.getvalue()


def _pdf_bytes():
    return (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog>>endobj\n"
        b"trailer<</Root 1 0 R>>\n"
        b"%%EOF"
    )


def test_storage_key_is_private_namespaced_and_rejects_traversal(
    storage_root,
):
    key = build_purchase_requisition_attachment_storage_key(
        123,
        ".pdf",
    )
    assert key.startswith("purchase-requisitions/123/")
    assert "tickets/" not in key

    path = resolve_purchase_requisition_attachment_path(key)
    assert storage_root.resolve() in path.parents

    with pytest.raises(ValueError):
        resolve_purchase_requisition_attachment_path(
            "purchase-requisitions/123/../evil.pdf"
        )


def test_requester_can_upload_multiple_evidence_files(
    engine,
    storage_root,
):
    actor = _user(1, "RECEPCIONISTA", 10)
    with Session(engine) as session:
        row = _create(session)

        image = create_purchase_requisition_attachment(
            requisition_id=row.id,
            attachment_type="EVIDENCE",
            content=_png_bytes(),
            original_filename="foto.png",
            declared_mime_type="image/png",
            actor=actor,
            session=session,
        )
        pdf = create_purchase_requisition_attachment(
            requisition_id=row.id,
            attachment_type="OTHER",
            content=_pdf_bytes(),
            original_filename="detalle.pdf",
            declared_mime_type="application/pdf",
            actor=actor,
            session=session,
        )

        assert image.id != pdf.id
        assert image.mime_type == "image/png"
        assert pdf.mime_type == "application/pdf"
        assert len(image.sha256) == 64
        assert len(pdf.sha256) == 64
        assert resolve_purchase_requisition_attachment_path(
            image.storage_key
        ).is_file()
        assert resolve_purchase_requisition_attachment_path(
            pdf.storage_key
        ).is_file()

        events = [
            event
            for event in row.events
            if event.event_type == "ATTACHMENT_ADDED"
        ]
        assert len(events) == 2


def test_maintenance_cannot_upload_before_approval(
    engine,
    storage_root,
):
    with Session(engine) as session:
        row = _create(session)
        with pytest.raises(PurchaseRequisitionAuthorizationError):
            create_purchase_requisition_attachment(
                requisition_id=row.id,
                attachment_type="QUOTE",
                content=_pdf_bytes(),
                original_filename="cotizacion.pdf",
                declared_mime_type="application/pdf",
                actor=_user(4, "MANTENIMIENTO", 1000),
                session=session,
            )


def test_maintenance_can_upload_quote_after_approval(
    engine,
    storage_root,
):
    with Session(engine) as session:
        row = _create(session)
        approve_purchase_requisition(
            row.id,
            _user(3, "ADMINISTRADOR", 1000),
            session=session,
        )
        session.commit()

        attachment = create_purchase_requisition_attachment(
            requisition_id=row.id,
            attachment_type="QUOTE",
            content=_pdf_bytes(),
            original_filename="cotizacion.pdf",
            declared_mime_type="application/pdf",
            actor=_user(4, "MANTENIMIENTO", 1000),
            session=session,
        )
        assert attachment.attachment_type == "QUOTE"


def test_lector_global_can_download_but_never_upload(
    engine,
    storage_root,
):
    requester = _user(1, "RECEPCIONISTA", 10)
    lector = _user(5, "LECTOR_GLOBAL", 1000)

    with Session(engine) as session:
        row = _create(session)
        attachment = create_purchase_requisition_attachment(
            requisition_id=row.id,
            attachment_type="EVIDENCE",
            content=_png_bytes(),
            original_filename="foto.png",
            declared_mime_type="image/png",
            actor=requester,
            session=session,
        )

        with pytest.raises(PurchaseRequisitionAuthorizationError):
            create_purchase_requisition_attachment(
                requisition_id=row.id,
                attachment_type="OTHER",
                content=_pdf_bytes(),
                original_filename="otro.pdf",
                declared_mime_type="application/pdf",
                actor=lector,
                session=session,
            )

        loaded, path = get_purchase_requisition_attachment_file(
            requisition_id=row.id,
            attachment_id=attachment.id,
            actor=lector,
            session=session,
        )
        assert loaded.id == attachment.id
        assert path.is_file()


def test_private_download_respects_requisition_scope(
    engine,
    storage_root,
):
    requester = _user(1, "RECEPCIONISTA", 10)
    foreign = _user(6, "RECEPCIONISTA", 20)

    with Session(engine) as session:
        row = _create(session)
        attachment = create_purchase_requisition_attachment(
            requisition_id=row.id,
            attachment_type="EVIDENCE",
            content=_png_bytes(),
            original_filename="foto.png",
            declared_mime_type="image/png",
            actor=requester,
            session=session,
        )

        with pytest.raises(PurchaseRequisitionAuthorizationError):
            get_purchase_requisition_attachment_file(
                requisition_id=row.id,
                attachment_id=attachment.id,
                actor=foreign,
                session=session,
            )


def test_file_signature_extension_and_mime_are_validated(
    engine,
    storage_root,
):
    actor = _user(1, "RECEPCIONISTA", 10)
    with Session(engine) as session:
        row = _create(session)

        with pytest.raises(Exception):
            create_purchase_requisition_attachment(
                requisition_id=row.id,
                attachment_type="EVIDENCE",
                content=b"not-an-image",
                original_filename="fake.png",
                declared_mime_type="image/png",
                actor=actor,
                session=session,
            )

        with pytest.raises(Exception):
            create_purchase_requisition_attachment(
                requisition_id=row.id,
                attachment_type="OTHER",
                content=_pdf_bytes(),
                original_filename="fake.jpg",
                declared_mime_type="image/jpeg",
                actor=actor,
                session=session,
            )

def test_origin_branch_manager_can_upload_receipt_evidence_only_at_final_destination(
    engine,
    storage_root,
):
    manager = _user(7, "GERENTE", 10)
    other_manager = _user(8, "GERENTE", 20)
    maintenance = _user(4, "MANTENIMIENTO", 1000)

    with Session(engine) as session:
        row = _create(session)
        row.status = "FINAL_DESTINATION_SHIPMENT"
        session.commit()

        receipt = create_purchase_requisition_attachment(
            requisition_id=row.id,
            attachment_type="RECEIPT_EVIDENCE",
            content=_png_bytes(),
            original_filename="recibido.png",
            declared_mime_type="image/png",
            actor=manager,
            session=session,
        )
        issue = create_purchase_requisition_attachment(
            requisition_id=row.id,
            attachment_type="RECEIPT_ISSUE_EVIDENCE",
            content=_pdf_bytes(),
            original_filename="incidencia.pdf",
            declared_mime_type="application/pdf",
            actor=manager,
            session=session,
        )

        assert receipt.attachment_type == "RECEIPT_EVIDENCE"
        assert issue.attachment_type == "RECEIPT_ISSUE_EVIDENCE"

        with pytest.raises(PurchaseRequisitionAuthorizationError):
            create_purchase_requisition_attachment(
                requisition_id=row.id,
                attachment_type="RECEIPT_ISSUE_EVIDENCE",
                content=_png_bytes(),
                original_filename="foranea.png",
                declared_mime_type="image/png",
                actor=other_manager,
                session=session,
            )

        with pytest.raises(PurchaseRequisitionAuthorizationError):
            create_purchase_requisition_attachment(
                requisition_id=row.id,
                attachment_type="RECEIPT_EVIDENCE",
                content=_png_bytes(),
                original_filename="mantenimiento.png",
                declared_mime_type="image/png",
                actor=maintenance,
                session=session,
            )

        row.status = "SHIPPING_IN_PROGRESS"
        session.flush()

        with pytest.raises(PurchaseRequisitionAuthorizationError):
            create_purchase_requisition_attachment(
                requisition_id=row.id,
                attachment_type="RECEIPT_EVIDENCE",
                content=_png_bytes(),
                original_filename="temprano.png",
                declared_mime_type="image/png",
                actor=manager,
                session=session,
            )
