"""Validate and queue per-account template uploads. The web process has no browser credentials."""

from datetime import datetime, timezone
import os
import re

from sqlalchemy.orm import defer

from app.extensions import db
from app.models.iventas_template_upload import IventasTemplateUploadORM as Upload
from app.services.marketing_campaign_v2_dispatch_config_service import list_channel_bindings


MAX_IMAGE_BYTES = 5 * 1024 * 1024
CATEGORIES = {"MARKETING", "UTILITY"}
QUEUED, RUNNING, FINISHED = "QUEUED", "RUNNING", "FINISHED"
TERMINAL_BRANCH_STATES = {"SUBMITTED", "EXISTS", "ERROR", "VERIFY"}


class TemplateUploadError(ValueError):
    pass


def template_upload_enabled() -> bool:
    return os.getenv("IVENTAS_TEMPLATE_UPLOAD_ENABLED", "").lower() in {"1", "true"}


def upload_targets(*, session=None) -> list[dict]:
    by_branch: dict[int, list[dict]] = {}
    for binding in list_channel_bindings(active_only=True, session=session):
        if binding["is_default"]:
            by_branch.setdefault(binding["sucursal_id"], []).append(binding)
    return [
        {key: rows[0][key] for key in ("sucursal_id", "sucursal_canon", "provider_channel_id")}
        for rows in by_branch.values()
        if len(rows) == 1
    ]


def validate_template(data: dict) -> dict:
    name = data.get("name")
    message = data.get("message")
    category = data.get("category")
    if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9_]{1,255}", name):
        raise TemplateUploadError("Usa minúsculas, números y guiones bajos para el nombre.")
    if not isinstance(message, str) or not message.strip() or len(message.encode("utf-16-le", "surrogatepass")) > 2048:
        raise TemplateUploadError("Escribe un mensaje de hasta 1,024 caracteres.")
    if not isinstance(category, str) or category not in CATEGORIES:
        raise TemplateUploadError("Selecciona Marketing o Utilidad.")

    fields = data.get("fields", [])
    if not isinstance(fields, list):
        raise TemplateUploadError("Los campos personalizados deben ser una lista.")
    # The browser selection API uses UTF-16 offsets, the same as Angular's textarea.
    encoded_message = message.encode("utf-16-le", "surrogatepass")
    positions = set()
    for field in fields:
        if not isinstance(field, dict):
            raise TemplateUploadError("Campo personalizado inválido.")
        start, end = field.get("start"), field.get("end")
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(encoded_message) // 2:
            raise TemplateUploadError("La selección de un campo quedó fuera del mensaje.")
        if (start, end) in positions:
            raise TemplateUploadError("La selección de un campo está repetida.")
        positions.add((start, end))

    checked_fields = []
    previous_end = 0
    for start, end in sorted(positions):
        try:
            selected = encoded_message[start * 2:end * 2].decode("utf-16-le")
        except UnicodeError:
            raise TemplateUploadError("Selecciona el texto completo del campo.") from None
        if start < previous_end or not re.search(r"\w", selected):
            raise TemplateUploadError("Los campos deben tener texto y sus selecciones no pueden superponerse.")
        checked_fields.append({"start": start, "end": end, "example": selected})
        previous_end = end
    if checked_fields and not re.search(r"[^\W_]", encoded_message[previous_end * 2:].decode("utf-16-le", "surrogatepass")):
        raise TemplateUploadError("Escribe una palabra después del último campo.")

    buttons = data.get("buttons", [])
    if not isinstance(buttons, list) or len(buttons) > 3 or any(
        not isinstance(label, str) or not label.strip() or len(label.encode("utf-16-le", "surrogatepass")) > 50
        for label in buttons
    ):
        raise TemplateUploadError("Agrega hasta 3 botones de hasta 25 caracteres.")
    return {"name": name, "message": message, "category": category, "fields": checked_fields,
            "buttons": [label.strip() for label in buttons]}


def create_upload(data: dict, image_file, *, actor_id: int, session=None) -> Upload:
    active = session if session is not None else db.session
    template = validate_template(data)
    selected = data.get("branch_ids")
    if not isinstance(selected, list) or not selected or any(type(value) is not int or value <= 0 for value in selected):
        raise TemplateUploadError("Selecciona al menos una sucursal.")
    targets = {row["sucursal_id"]: row for row in upload_targets(session=active)}
    if not set(selected).issubset(targets):
        raise TemplateUploadError("Una sucursal ya no tiene un canal de iVentas predeterminado y activo.")

    image, image_type = None, None
    if image_file is not None:
        image = image_file.read(MAX_IMAGE_BYTES + 1)
        if len(image) > MAX_IMAGE_BYTES:
            raise TemplateUploadError("La imagen excede 5 MB.")
        if image.startswith(b"\x89PNG\r\n\x1a\n"):
            image_type = "image/png"
        elif image.startswith(b"\xff\xd8\xff"):
            image_type = "image/jpeg"
        else:
            raise TemplateUploadError("Adjunta una imagen PNG o JPEG.")

    branches = [{**targets[branch_id], "status": QUEUED} for branch_id in dict.fromkeys(selected)]
    row = Upload(requested_by_user_id=actor_id, status=QUEUED, template=template, branches=branches,
                 image=image, image_type=image_type)
    active.add(row)
    active.commit()
    return row


def upload_history(*, session=None) -> list[dict]:
    active = session if session is not None else db.session
    rows = active.query(Upload).options(defer(Upload.image)).order_by(Upload.id.desc()).limit(30).all()
    return [serialize_upload(row) for row in rows]


def serialize_upload(row: Upload) -> dict:
    return {
        "id": row.id,
        "requested_by_user_id": row.requested_by_user_id,
        "created_at": row.created_at.isoformat(),
        "status": row.status,
        "name": row.template["name"],
        "category": row.template["category"],
        "branches": row.branches,
    }


def claim_next_branch(session) -> tuple | None:
    row = session.query(Upload).filter_by(status=QUEUED).order_by(Upload.id).with_for_update(skip_locked=True).first()
    if row is None:
        session.rollback()
        return None
    branch = next(target for target in row.branches if target["status"] == QUEUED)
    row.branches = [
        {**target, "status": RUNNING} if target is branch else target
        for target in row.branches
    ]
    row.status = RUNNING
    row.updated_at = datetime.now(timezone.utc)
    snapshot = (row.id, dict(branch), row.template, row.image, row.image_type)
    session.commit()
    return snapshot


def finish_branch(session, upload_id: int, branch_id: int, status: str, detail: str = "") -> None:
    if status not in TERMINAL_BRANCH_STATES:
        raise ValueError("Estado de carga inválido.")
    row = session.query(Upload).filter_by(id=upload_id, status=RUNNING).with_for_update().one()
    branch = next(target for target in row.branches if target["status"] == RUNNING)
    if branch["sucursal_id"] != branch_id:
        raise ValueError("La sucursal no coincide con la carga en proceso.")
    row.branches = [
        {**target, "status": status, "detail": detail}
        if target is branch else target
        for target in row.branches
    ]
    _update_batch_state(row)
    session.commit()


def recover_interrupted_uploads(session) -> None:
    for row in session.query(Upload).filter_by(status=RUNNING).with_for_update():
        row.branches = [
            {**target, "status": "VERIFY", "detail": "Se interrumpió la carga. Consulta la plantilla en iVentas."}
            if target["status"] == RUNNING else target
            for target in row.branches
        ]
        _update_batch_state(row)
    session.commit()


def _update_batch_state(row: Upload) -> None:
    row.updated_at = datetime.now(timezone.utc)
    row.status = QUEUED if any(target["status"] == QUEUED for target in row.branches) else FINISHED
    if row.status == FINISHED:
        row.image = None
