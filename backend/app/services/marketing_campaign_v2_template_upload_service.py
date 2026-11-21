"""Validate and queue per-account template uploads. The web process has no browser credentials."""

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
import re

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import defer

from app.extensions import db
from app.models.iventas_template_upload import IventasTemplateUploadORM as Upload
from app.models.marketing import MarketingCampaignV2TemplateORM as CatalogTemplate
from app.services.marketing_campaign_v2_dispatch_config_service import (
    ALLOWED_PURPOSES, DEFAULT_PROVIDER, SUPPORTED_TEMPLATE_VARIABLE_SOURCES,
    MarketingCampaignV2DispatchConfigValidationError, list_channel_bindings,
    resolve_dispatch_channel_binding, validate_template_file_url,
)


MAX_IMAGE_BYTES = 5 * 1024 * 1024
CATEGORIES = {"MARKETING", "UTILITY"}
QUEUED, RUNNING, FINISHED = "QUEUED", "RUNNING", "FINISHED"
IN_REVIEW, APPROVED, REJECTED = "IN_REVIEW", "APPROVED", "REJECTED"
UPLOAD_RESULTS = {"SUBMITTED", "EXISTS", "ERROR", "VERIFY", IN_REVIEW}
REVIEW_INTERVAL = timedelta(minutes=15)


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
    template = {"name": name, "message": message, "category": category, "fields": checked_fields,
                "buttons": [label.strip() for label in buttons]}
    if "catalog" in data:
        template["catalog"] = _validate_catalog(data["catalog"], len(checked_fields))
    return template


def _validate_catalog(data, field_count: int) -> dict:
    if not isinstance(data, dict):
        raise TemplateUploadError("La configuración del catálogo debe ser un objeto.")
    purpose = data.get("purpose")
    if not isinstance(purpose, str) or purpose not in ALLOWED_PURPOSES:
        raise TemplateUploadError("Selecciona el uso de la plantilla en Campañas.")
    sources = data.get("sources")
    if not isinstance(sources, list) or len(sources) != field_count or not all(
        isinstance(source, str) and source in SUPPORTED_TEMPLATE_VARIABLE_SOURCES for source in sources
    ):
        raise TemplateUploadError("Selecciona un dato de la Suite para cada campo personalizado.")
    file_url = data.get("file_url", "")
    if not isinstance(file_url, str):
        raise TemplateUploadError("Ingresa la URL HTTPS de la imagen.")
    file_url = file_url.strip()
    if file_url:
        try:
            validate_template_file_url(file_url)
        except MarketingCampaignV2DispatchConfigValidationError as error:
            raise TemplateUploadError("Ingresa la URL HTTPS de la imagen.") from error
    return {"purpose": purpose, "variables": {str(i): value for i, value in enumerate(sources, 1)},
            "file_url": file_url}


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

    if catalog := template.get("catalog"):
        if bool(image) != bool(catalog["file_url"]):
            raise TemplateUploadError("Para usar una plantilla con imagen, adjunta el archivo e indica su URL HTTPS de envío.")
        material = {key: template[key] for key in ("name", "message", "category", "fields", "buttons")}
        material.update(variables=catalog["variables"], file_url=catalog["file_url"],
                        image_sha256=sha256(image).hexdigest() if image else None)
        catalog["fingerprint"] = sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()
        _check_catalog_name(active, template)

    branches = [{**targets[branch_id], "status": QUEUED} for branch_id in dict.fromkeys(selected)]
    row = Upload(requested_by_user_id=actor_id, status=QUEUED, template=template, branches=branches,
                 image=image, image_type=image_type)
    active.add(row)
    active.commit()
    return row


def _check_catalog_name(session, template: dict) -> None:
    name = template["name"]
    fingerprint = template["catalog"]["fingerprint"]
    if session.get_bind().dialect.name == "postgresql":
        lock_key = int.from_bytes(sha256(("iventas-template:" + name).encode()).digest()[:8], "big", signed=True)
        session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
    existing = session.query(CatalogTemplate).filter_by(provider=DEFAULT_PROVIDER, template_name=name).one_or_none()
    if existing is not None and existing.upload_fingerprint != fingerprint:
        raise TemplateUploadError("Ya existe una plantilla con ese nombre en el catálogo. Usa otro nombre o consulta el registro existente.")
    prior_uploads = session.query(Upload).options(defer(Upload.image)).filter(
        Upload.template["name"].as_string() == name,
    )
    for prior in prior_uploads:
        prior_fingerprint = (prior.template.get("catalog") or {}).get("fingerprint")
        if prior_fingerprint and prior_fingerprint != fingerprint and any(
            branch["status"] not in {"ERROR", REJECTED} for branch in prior.branches
        ):
            raise TemplateUploadError("Ya hay una carga con ese nombre y contenido distinto.")


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
        "branches": [{key: value for key, value in branch.items() if key != "review_at"}
                     for branch in row.branches],
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
    if status not in UPLOAD_RESULTS:
        raise ValueError("Estado de carga inválido.")
    row = session.query(Upload).filter_by(id=upload_id, status=RUNNING).with_for_update().one()
    branch = next(target for target in row.branches if target["status"] == RUNNING)
    if branch["sucursal_id"] != branch_id:
        raise ValueError("La sucursal no coincide con la carga en proceso.")
    result = {**branch, "status": status, "detail": detail}
    if status == IN_REVIEW:
        result["review_at"] = datetime.now(timezone.utc).isoformat()
    row.branches = [result if target is branch else target for target in row.branches]
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
    _set_review_due(row)


def _set_review_due(row: Upload) -> None:
    row.next_review_at = min(
        (datetime.fromisoformat(branch["review_at"]) for branch in row.branches if branch["status"] == IN_REVIEW),
        default=None,
    )


def claim_due_review(session, *, now=None):
    now = now or datetime.now(timezone.utc)
    row = session.query(Upload).options(defer(Upload.image)).filter(
        Upload.status == FINISHED, Upload.next_review_at <= now,
    ).order_by(Upload.next_review_at, Upload.id).with_for_update(skip_locked=True).first()
    if row is None:
        session.rollback()
        return None
    branch = min((target for target in row.branches if target["status"] == IN_REVIEW), key=lambda item: item["review_at"])
    snapshot = (row.id, dict(branch), row.template)
    row.branches = [
        {**target, "review_at": (now + REVIEW_INTERVAL).isoformat()} if target is branch else target
        for target in row.branches
    ]
    _set_review_due(row)
    session.commit()
    return snapshot


def finish_review(session, upload_id: int, branch_id: int, status: str, detail: str) -> None:
    if status not in {IN_REVIEW, APPROVED, REJECTED, "VERIFY"}:
        raise ValueError("Estado de revisión inválido.")
    row = session.query(Upload).options(defer(Upload.image)).filter_by(
        id=upload_id, status=FINISHED,
    ).with_for_update().one()
    branch = next(target for target in row.branches if target["sucursal_id"] == branch_id)
    if branch["status"] != IN_REVIEW:
        session.rollback()
        return

    if status == APPROVED:
        try:
            with session.begin_nested():
                _publish_approved_channel(session, row, branch)
        except TemplateUploadError as error:
            status, detail = "VERIFY", str(error)
        except IntegrityError:
            status, detail = IN_REVIEW, "Se actualizará el catálogo en la próxima revisión."

    result = {**branch, "status": status, "detail": detail}
    if status != IN_REVIEW:
        result.pop("review_at")
    row.branches = [result if target is branch else target for target in row.branches]
    row.updated_at = datetime.now(timezone.utc)
    _set_review_due(row)
    session.commit()


def _publish_approved_channel(session, upload: Upload, branch: dict) -> None:
    template = upload.template
    catalog = template["catalog"]
    channel = branch["provider_channel_id"]
    binding = resolve_dispatch_channel_binding(sucursal_id=branch["sucursal_id"], session=session, for_update=True)
    if binding is None or binding.provider_channel_id != channel:
        raise TemplateUploadError("iVentas aprobó la plantilla, pero cambió el canal de la sucursal.")

    current = session.query(CatalogTemplate).filter_by(
        provider=DEFAULT_PROVIDER, template_name=template["name"],
    ).with_for_update().one_or_none()
    if current is None:
        session.add(CatalogTemplate(
            provider=DEFAULT_PROVIDER, template_name=template["name"], label=template["name"].replace("_", " "),
            is_active=True, purposes_json=[catalog["purpose"]], variables_json=catalog["variables"],
            compatible_channel_ids_json=[channel],
            metadata_json={"file_url": catalog["file_url"]} if catalog["file_url"] else {},
            upload_fingerprint=catalog["fingerprint"],
            created_by_user_id=upload.requested_by_user_id, updated_by_user_id=upload.requested_by_user_id,
        ))
        return
    if current.upload_fingerprint != catalog["fingerprint"]:
        raise TemplateUploadError("iVentas aprobó la plantilla, pero el catálogo ya tiene otra configuración con ese nombre.")
    if not current.is_active:
        raise TemplateUploadError("iVentas aprobó la plantilla, pero el registro del catálogo está desactivado.")
    channels = set(current.compatible_channel_ids_json)
    if channel not in channels:
        current.compatible_channel_ids_json = sorted(channels | {channel})
        current.updated_by_user_id = upload.requested_by_user_id
