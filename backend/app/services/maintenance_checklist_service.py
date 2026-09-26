# backend/app/services/maintenance_checklist_service.py

from __future__ import annotations

from uuid import uuid4

from app.extensions import db
from app.models.maintenance_checklist import (
    MaintenanceChecklistItemORM,
    MaintenanceChecklistTemplateORM,
)
from app.models.mantenimiento_equipo import FamiliaEquipoORM
from app.utils.pm_permissions import can_pm_configure


class MaintenanceChecklistError(ValueError):
    status_code = 400

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code


class MaintenanceChecklistAuthorizationError(MaintenanceChecklistError):
    status_code = 403


class MaintenanceChecklistNotFoundError(MaintenanceChecklistError):
    status_code = 404


def _clean(value) -> str:
    return str(value or "").strip()


def _activity_key(value) -> str | None:
    raw = " ".join(_clean(value).upper().split())
    return raw or None


def _assert_configure(user) -> None:
    if not user or not can_pm_configure(user):
        raise MaintenanceChecklistAuthorizationError(
            "No tienes permiso para configurar checklists."
        )


def _template_key() -> str:
    return f"CHK-{uuid4().hex[:12].upper()}"


def _item_key() -> str:
    return f"ITEM-{uuid4().hex[:12].upper()}"


def _serialize_item(item: MaintenanceChecklistItemORM) -> dict:
    return {
        "id": int(item.id),
        "item_key": str(item.item_key),
        "etiqueta": str(item.etiqueta),
        "orden": int(item.orden or 0),
        "requerido": bool(item.requerido),
        "activo": bool(item.activo),
    }


def _serialize_template(template: MaintenanceChecklistTemplateORM) -> dict:
    return {
        "id": int(template.id),
        "template_key": str(template.template_key),
        "familia_equipo_id": int(template.familia_equipo_id),
        "familia": (
            str(template.familia.nombre)
            if template.familia is not None
            else None
        ),
        "nombre": str(template.nombre),
        "actividad": template.actividad_key,
        "activo": bool(template.activo),
        "items": [
            _serialize_item(item)
            for item in template.items
        ],
    }


def listar_catalogo_checklists(user) -> dict:
    _assert_configure(user)

    templates = (
        MaintenanceChecklistTemplateORM.query
        .order_by(
            MaintenanceChecklistTemplateORM.activo.desc(),
            MaintenanceChecklistTemplateORM.familia_equipo_id.asc(),
            MaintenanceChecklistTemplateORM.nombre.asc(),
        )
        .all()
    )
    families = (
        FamiliaEquipoORM.query
        .filter(FamiliaEquipoORM.activo.is_(True))
        .order_by(FamiliaEquipoORM.nombre.asc())
        .all()
    )

    return {
        "templates": [
            _serialize_template(template)
            for template in templates
        ],
        "families": [
            {
                "id": int(family.id),
                "key": str(family.key),
                "nombre": str(family.nombre),
            }
            for family in families
        ],
    }


def crear_template_checklist(user, payload: dict) -> MaintenanceChecklistTemplateORM:
    _assert_configure(user)

    try:
        family_id = int((payload or {}).get("familia_equipo_id"))
    except (TypeError, ValueError) as exc:
        raise MaintenanceChecklistError(
            "familia_equipo_id inválido."
        ) from exc

    family = db.session.get(FamiliaEquipoORM, family_id)
    if family is None or not bool(family.activo):
        raise MaintenanceChecklistError(
            "La familia indicada no existe o está inactiva."
        )

    name = _clean((payload or {}).get("nombre"))
    if not name:
        raise MaintenanceChecklistError("nombre es obligatorio.")

    activity = _activity_key((payload or {}).get("actividad"))
    initial_items = (payload or {}).get("items") or []
    if not isinstance(initial_items, list):
        raise MaintenanceChecklistError("items debe ser una lista.")

    template = MaintenanceChecklistTemplateORM(
        template_key=_template_key(),
        familia_equipo_id=family_id,
        nombre=name,
        actividad_key=activity,
        activo=True,
    )
    db.session.add(template)
    db.session.flush()

    for index, raw_item in enumerate(initial_items, start=1):
        if isinstance(raw_item, str):
            label = _clean(raw_item)
            required = True
        elif isinstance(raw_item, dict):
            label = _clean(raw_item.get("etiqueta"))
            required = bool(raw_item.get("requerido", True))
        else:
            raise MaintenanceChecklistError(
                f"Ítem {index} inválido."
            )

        if not label:
            raise MaintenanceChecklistError(
                f"Ítem {index} sin etiqueta."
            )

        db.session.add(
            MaintenanceChecklistItemORM(
                template_id=template.id,
                item_key=_item_key(),
                etiqueta=label,
                orden=index,
                requerido=required,
                activo=True,
            )
        )

    db.session.flush()
    return template


def actualizar_template_checklist(
    user,
    template_id: int,
    payload: dict,
) -> MaintenanceChecklistTemplateORM:
    _assert_configure(user)

    template = db.session.get(
        MaintenanceChecklistTemplateORM,
        int(template_id),
    )
    if template is None:
        raise MaintenanceChecklistNotFoundError(
            "Plantilla de checklist no encontrada."
        )

    if "nombre" in payload:
        name = _clean(payload.get("nombre"))
        if not name:
            raise MaintenanceChecklistError("nombre es obligatorio.")
        template.nombre = name

    if "actividad" in payload:
        template.actividad_key = _activity_key(payload.get("actividad"))

    if "activo" in payload:
        template.activo = bool(payload.get("activo"))

    db.session.flush()
    return template


def agregar_item_checklist(
    user,
    template_id: int,
    payload: dict,
) -> MaintenanceChecklistItemORM:
    _assert_configure(user)

    template = db.session.get(
        MaintenanceChecklistTemplateORM,
        int(template_id),
    )
    if template is None:
        raise MaintenanceChecklistNotFoundError(
            "Plantilla de checklist no encontrada."
        )

    label = _clean((payload or {}).get("etiqueta"))
    if not label:
        raise MaintenanceChecklistError("etiqueta es obligatoria.")

    max_order = max(
        [int(item.orden or 0) for item in template.items],
        default=0,
    )

    item = MaintenanceChecklistItemORM(
        template_id=template.id,
        item_key=_item_key(),
        etiqueta=label,
        orden=max_order + 1,
        requerido=bool((payload or {}).get("requerido", True)),
        activo=True,
    )
    db.session.add(item)
    db.session.flush()
    return item


def actualizar_item_checklist(
    user,
    template_id: int,
    item_id: int,
    payload: dict,
) -> MaintenanceChecklistItemORM:
    _assert_configure(user)

    item = db.session.get(
        MaintenanceChecklistItemORM,
        int(item_id),
    )
    if item is None or int(item.template_id) != int(template_id):
        raise MaintenanceChecklistNotFoundError(
            "Ítem de checklist no encontrado."
        )

    if "etiqueta" in payload:
        label = _clean(payload.get("etiqueta"))
        if not label:
            raise MaintenanceChecklistError(
                "etiqueta es obligatoria."
            )
        item.etiqueta = label

    if "orden" in payload:
        try:
            item.orden = int(payload.get("orden"))
        except (TypeError, ValueError) as exc:
            raise MaintenanceChecklistError("orden inválido.") from exc

    if "requerido" in payload:
        item.requerido = bool(payload.get("requerido"))

    if "activo" in payload:
        item.activo = bool(payload.get("activo"))

    db.session.flush()
    return item


def serialize_template(template: MaintenanceChecklistTemplateORM) -> dict:
    return _serialize_template(template)


def serialize_item(item: MaintenanceChecklistItemORM) -> dict:
    return _serialize_item(item)
