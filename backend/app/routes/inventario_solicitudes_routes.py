"""Inventarios V2 E2 — solicitudes de corrección, sin aplicación automática.

El guard real vive aquí: la matriz diagnóstica de permisos no habilita rutas.
Solo se persisten propuestas PENDING. El inventario oficial es inmutable en E2.
"""
from datetime import date, datetime, timezone
import hashlib
import json
import uuid
from zoneinfo import ZoneInfo

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import text, bindparam, and_, or_, func
from sqlalchemy.exc import IntegrityError, OperationalError
from flask import current_app
from app.services.inventario_correccion_decisiones_service import decidir_lote, DecisionError
from app.utils.inventory_correction_permissions import (
    alcance_revision_e3, aliases_clase_inventario_e3,
)

from app.extensions import db
from app.models.inventario_solicitud_correccion import InventarioSolicitudCorreccionORM
from app.models.inventario import InventarioGeneral


inventario_solicitudes_bp = Blueprint("inventario_solicitudes", __name__)

# Acceso E2 independiente de inventory.read / inventory.movement_write.
# No incluir GERENTE/GERENTE_REGIONAL/COORDINADOR antes de E5.
_GLOBAL_ROLES = frozenset({"ADMIN", "ADMINISTRADOR", "SUPER_ADMIN"})
# E2: personal técnico opera exclusivamente sus sucursales M:N asignadas.
_M2M_SCOPED_ROLES = frozenset({
    "SR_MANTENIMIENTO", "MANTENIMIENTO", "SISTEMAS", "TECNICO",
})
_SCOPED_ROLES = _M2M_SCOPED_ROLES | frozenset({"AUX_MANTENIMIENTO"})
_TYPES = frozenset({
    "MASTER_FIELD", "QUANTITY_DIFFERENCE", "NOT_LOCATED", "UNREGISTERED_FIND",
})
_STATUSES = frozenset({"PENDING", "APPROVED", "REJECTED"})
_MASTER_TEXT = {
    "nombre": 255,
    "marca": 100,
    "codigo_interno": 50,
    "no_equipo": 50,
    "unidad_medida": 50,
    "tipo": 20,
}
_MASTER_INT = frozenset({"categoria_inventario_id", "familia_equipo_id"})
_ALLOWED_KEYS = frozenset({
    "tipo", "sucursal_id", "inventario_id", "campo", "valor_original",
    "valor_propuesto", "hallazgo_provisional", "motivo",
    "evidencia_descriptiva", "fecha_observacion_local", "idempotency_key",
})
_FIND_FIELDS = {
    "nombre": 255,
    "tipo": 40,
    "marca": 100,
    "codigo_interno": 50,
    "descripcion": 2000,
}


def _error(status, detail):
    return jsonify({"error": (
        "Unauthorized" if status == 401 else
        "Forbidden" if status == 403 else
        "Conflict" if status == 409 else
        "Not Found" if status == 404 else
        "Bad Request"
    ), "detail": detail}), status


def _positive_id(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return value
    return None


def _query_positive(raw):
    if not isinstance(raw, str) or not raw.isascii() or not raw.isdecimal():
        return None
    parsed = int(raw)
    return parsed if parsed > 0 else None


def _actor():
    """DB autoritativa; NO confiar en claims JWT de rol/sucursales."""
    identity = get_jwt_identity()
    if isinstance(identity, bool):
        return None, _error(401, "Sesión inválida.")
    try:
        user_id = int(identity)
    except (TypeError, ValueError, OverflowError):
        return None, _error(401, "Sesión inválida.")
    if user_id <= 0:
        return None, _error(401, "Sesión inválida.")

    row = db.session.execute(
        text("SELECT id, rol, sucursal_id FROM users WHERE id = :id"),
        {"id": user_id},
    ).mappings().first()
    if row is None:
        return None, _error(401, "Usuario no encontrado.")

    role = str(row["rol"] or "").strip().upper()
    if role in _GLOBAL_ROLES:
        return {"id": user_id, "scope": None, "role": role}, None
    if role not in _SCOPED_ROLES:
        return None, _error(403, "Inventarios V2 E2 no habilitado para este rol.")

    if role in _M2M_SCOPED_ROLES:
        # Solo la asignación M:N real. Nunca sumar la sucursal primaria.
        ids = db.session.execute(
            text("SELECT sucursal_id FROM usuario_sucursal WHERE user_id = :id"),
            {"id": user_id},
        ).scalars().all()
        scope = sorted({int(value) for value in ids if value is not None and int(value) > 0})
    else:
        primary = _positive_id(row["sucursal_id"])
        scope = [primary] if primary else []
    if not scope:
        return None, _error(403, "No tienes sucursales habilitadas para E2.")
    return {"id": user_id, "scope": scope, "role": role}, None


def _is_allowed(actor, branch):
    return actor["scope"] is None or branch in actor["scope"]


def _canonical_fingerprint(payload):
    serialized = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _strict_equal(a, b):
    return type(a) is type(b) and a == b


def _serialize(row):
    return {
        "id": row.id, "tipo": row.tipo, "estado": row.estado,
        "sucursal_id": row.sucursal_id, "inventario_id": row.inventario_id,
        "campo": row.campo,
        "valor_original": row.valor_original,
        "valor_propuesto": row.valor_propuesto,
        "hallazgo_provisional": row.hallazgo_provisional,
        "baseline_canonico": row.baseline_canonico,
        "motivo": row.motivo,
        "evidencia_descriptiva": row.evidencia_descriptiva,
        "fecha_observacion_local": (
            row.fecha_observacion_local.isoformat() if row.fecha_observacion_local else None
        ),
        "creado_por_usuario_id": row.creado_por_usuario_id,
        "creado_en_utc": (
            row.creado_en_utc.isoformat() if row.creado_en_utc else None
        ),
    }


def _validate_payload(payload):
    """Validar forma sin leer DB. Idempotencia puede evaluarse antes de baseline."""
    if not isinstance(payload, dict):
        return None, _error(400, "El cuerpo debe ser un objeto JSON.")
    if set(payload) - _ALLOWED_KEYS:
        return None, _error(400, "El cuerpo contiene campos no permitidos.")
    if not isinstance(payload.get("tipo"), str) or payload["tipo"] not in _TYPES:
        return None, _error(400, "Tipo de solicitud inválido.")
    branch = _positive_id(payload.get("sucursal_id"))
    if branch is None:
        return None, _error(400, "sucursal_id debe ser entero positivo.")

    try:
        if not isinstance(payload.get("idempotency_key"), str):
            raise ValueError()
        key = uuid.UUID(payload["idempotency_key"])
        if key.int == 0:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        return None, _error(400, "idempotency_key debe ser UUID válido.")

    reason = payload.get("motivo")
    if not isinstance(reason, str) or not 10 <= len(reason.strip()) <= 2000:
        return None, _error(400, "motivo requiere de 10 a 2000 caracteres.")
    evidence = payload.get("evidencia_descriptiva")
    if evidence is not None and (
        not isinstance(evidence, str) or len(evidence) > 2000
    ):
        return None, _error(400, "evidencia_descriptiva excede 2000 caracteres.")

    observed = None
    if payload.get("fecha_observacion_local") is not None:
        raw = payload["fecha_observacion_local"]
        if not isinstance(raw, str) or len(raw) != 10:
            return None, _error(400, "fecha_observacion_local debe ser AAAA-MM-DD.")
        try:
            observed = date.fromisoformat(raw)
        except ValueError:
            return None, _error(400, "fecha_observacion_local inválida.")
        if observed > datetime.now(ZoneInfo("America/Tijuana")).date():
            return None, _error(400, "La observación no puede ser futura.")

    kind = payload["tipo"]
    # Para estos dos ajustes con efecto patrimonial se exige evidencia
    # de observación desde E2; E3 no puede aportarla a posteriori en silencio.
    if kind in ("NOT_LOCATED", "UNREGISTERED_FIND"):
        if observed is None or not isinstance(evidence, str) or not 20 <= len(evidence.strip()) <= 2000:
            return None, _error(
                400,
                "No localizado y hallazgo requieren fecha de observación "
                "y evidencia física descriptiva de 20 a 2000 caracteres.",
            )
    inventory = payload.get("inventario_id")
    field = payload.get("campo")
    proposed = payload.get("valor_propuesto")
    provisional = payload.get("hallazgo_provisional")
    original = payload.get("valor_original")

    if kind == "UNREGISTERED_FIND":
        if inventory is not None or field is not None or proposed is not None or original is not None:
            return None, _error(400, "Un hallazgo provisional no tiene referencia ni campo canónico.")
        if not isinstance(provisional, dict) or (
            set(provisional) - set(_FIND_FIELDS)
        ):
            return None, _error(400, "hallazgo_provisional inválido.")
        if not isinstance(provisional.get("nombre"), str) or not provisional["nombre"].strip():
            return None, _error(400, "El hallazgo necesita nombre.")
        if any(
            not isinstance(value, str) or not value.strip() or len(value) > _FIND_FIELDS[key]
            for key, value in provisional.items()
        ):
            return None, _error(400, "Los campos del hallazgo exceden los límites.")
    else:
        if _positive_id(inventory) is None or provisional is not None:
            return None, _error(400, "Se necesita inventario_id válido, sin hallazgo provisional.")
        if "valor_original" not in payload:
            return None, _error(400, "valor_original es obligatorio para contrastar el dato oficial.")
        if kind == "MASTER_FIELD":
            if not isinstance(field, str) or field not in set(_MASTER_TEXT) | _MASTER_INT:
                return None, _error(400, "Campo maestro fuera de la lista permitida.")
            if field in _MASTER_TEXT:
                if (not isinstance(proposed, str) or not proposed.strip()
                        or len(proposed) > _MASTER_TEXT[field]):
                    return None, _error(400, "Valor propuesto inválido para el campo maestro.")
            elif _positive_id(proposed) is None:
                return None, _error(400, "La propuesta de clasificación debe ser ID positivo.")
            if isinstance(original, (list, dict)):
                return None, _error(400, "valor_original debe ser escalar para maestro.")
        else:
            if field is not None or not isinstance(original, dict) or set(original) != {"stock"}:
                return None, _error(400, "Se requiere valor_original={stock: entero} sin campo maestro.")
            if isinstance(original["stock"], bool) or not isinstance(original["stock"], int):
                return None, _error(400, "stock original inválido.")
            if kind == "QUANTITY_DIFFERENCE":
                if not isinstance(proposed, dict) or set(proposed) != {"cantidad_fisica"}:
                    return None, _error(400, "Se requiere cantidad_fisica.")
                qty = proposed["cantidad_fisica"]
                if isinstance(qty, bool) or not isinstance(qty, int) or qty <= 0:
                    return None, _error(
                        400, "Diferencia de cantidad requiere al menos una unidad física. "
                        "Si no se encontró ninguna, registra NOT_LOCATED con evidencia.",
                    )
            else:
                if proposed != {"no_localizado": True}:
                    return None, _error(400, "NOT_LOCATED necesita no_localizado=true.")
    return {
        "tipo": kind, "sucursal_id": branch, "inventario_id": inventory,
        "campo": field, "valor_original": original, "valor_propuesto": proposed,
        "hallazgo_provisional": provisional, "motivo": reason.strip(),
        "evidencia_descriptiva": evidence.strip() if isinstance(evidence, str) else None,
        "fecha_observacion_local": observed, "idempotency_key": key,
    }, None


def _official_snapshot(data):
    """Leer solo valores oficiales; ninguna actualización a V1."""
    branch = data["sucursal_id"]
    inventory = data["inventario_id"]
    if inventory is None:
        found = db.session.execute(
            text("SELECT 1 FROM sucursales WHERE sucursal_id = :sucursal"),
            {"sucursal": branch},
        ).scalar_one_or_none()
        if found is None:
            return None, _error(404, "Sucursal inexistente.")
        return {"inventario_id": None, "sucursal_id": branch}, None

    row = db.session.execute(
        text(
            "SELECT stock FROM inventario_sucursal "
            "WHERE inventario_id = :inventario AND sucursal_id = :sucursal"
        ),
        {"inventario": inventory, "sucursal": branch},
    ).first()
    if row is None:
        return None, _error(404, "La referencia no pertenece a esta sucursal.")
    stock = row[0]
    if stock is None:
        return None, _error(409, "El stock oficial está indefinido; revisar referencia.")
    snapshot = {"inventario_id": inventory, "sucursal_id": branch, "stock": stock}
    if data["tipo"] == "MASTER_FIELD":
        field = data["campo"]  # allowlist estricta comprobada antes de interpolar SQL
        if field not in set(_MASTER_TEXT) | _MASTER_INT:
            return None, _error(400, "Campo maestro no autorizado.")
        value = db.session.execute(
            text(f"SELECT {field} FROM inventario_general WHERE id = :inventario"),
            {"inventario": inventory},
        ).scalar_one_or_none()
        # Un NULL válido no significa que la fila no exista (la FK existente sí la exige).
        if not _strict_equal(value, data["valor_original"]):
            return None, _error(409, "El dato maestro cambió; vuelve a cargar el formulario.")
        if _strict_equal(value, data["valor_propuesto"]):
            return None, _error(400, "El dato propuesto es igual al oficial.")
        snapshot["campo"] = field
        snapshot["valor"] = value
        return {"baseline": snapshot, "original": value}, None

    expected = data["valor_original"]["stock"]
    if not _strict_equal(stock, expected):
        return None, _error(409, "El stock oficial cambió; vuelve a cargar el formulario.")
    if data["tipo"] == "QUANTITY_DIFFERENCE":
        if stock == data["valor_propuesto"]["cantidad_fisica"]:
            return None, _error(400, "La cantidad física es igual al stock oficial.")
    if data["tipo"] == "NOT_LOCATED" and stock <= 0:
        return None, _error(
            400, "No localizado requiere stock oficial positivo; "
            "la referencia ya está en cero.",
        )
    return {"baseline": snapshot, "original": {"stock": stock}}, None


@inventario_solicitudes_bp.post("")
@jwt_required()
def crear_solicitud():
    actor, denied = _actor()
    if denied:
        return denied
    payload = request.get_json(silent=True)
    if payload is None:
        return _error(400, "Se requiere JSON válido.")
    try:
        if len(json.dumps(payload, ensure_ascii=False, allow_nan=False)) > 12000:
            return _error(400, "Solicitud demasiado grande.")
    except (TypeError, ValueError):
        return _error(400, "JSON inválido.")
    data, invalid = _validate_payload(payload)
    if invalid:
        return invalid
    branch = data["sucursal_id"]
    if not _is_allowed(actor, branch):
        return _error(403, "No tienes autorización para esta sucursal.")

    fingerprint_input = {
        k: (v.isoformat() if isinstance(v, date) else str(v) if isinstance(v, uuid.UUID) else v)
        for k, v in data.items()
    }
    fingerprint = _canonical_fingerprint(fingerprint_input)
    key = data["idempotency_key"]
    existing = InventarioSolicitudCorreccionORM.query.filter_by(
        creado_por_usuario_id=actor["id"], idempotency_key=key,
    ).first()
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            return _error(409, "idempotency_key ya corresponde a otra solicitud.")
        if not _is_allowed(actor, existing.sucursal_id):
            return _error(403, "La solicitud pertenece a una sucursal no autorizada.")
        return jsonify({"solicitud": _serialize(existing), "replayed": True}), 200

    official, conflict = _official_snapshot(data)
    if conflict:
        return conflict

    # Advertencia no bloqueante de propuesta PENDING similar; E3 decidirá la resolución.
    related = False
    if data["inventario_id"] is not None:
        related = db.session.query(
            InventarioSolicitudCorreccionORM.id
        ).filter_by(
            sucursal_id=branch, inventario_id=data["inventario_id"],
            tipo=data["tipo"], campo=data["campo"], estado="PENDING",
        ).first() is not None

    entry = InventarioSolicitudCorreccionORM(
        tipo=data["tipo"], estado="PENDING",
        sucursal_id=branch, inventario_id=data["inventario_id"],
        campo=data["campo"], valor_original=official.get("original"),
        valor_propuesto=data["valor_propuesto"],
        hallazgo_provisional=data["hallazgo_provisional"],
        baseline_canonico=official.get("baseline", official),
        motivo=data["motivo"], evidencia_descriptiva=data["evidencia_descriptiva"],
        fecha_observacion_local=data["fecha_observacion_local"],
        creado_por_usuario_id=actor["id"],
        creado_en_utc=datetime.now(timezone.utc),
        idempotency_key=key, request_fingerprint=fingerprint,
    )
    db.session.add(entry)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        # La UNIQUE resuelve dos POST concurrentes con la misma llave.
        existing = InventarioSolicitudCorreccionORM.query.filter_by(
            creado_por_usuario_id=actor["id"], idempotency_key=key,
        ).first()
        if existing:
            if existing.request_fingerprint != fingerprint:
                return _error(409, "idempotency_key ya corresponde a otra solicitud.")
            if not _is_allowed(actor, existing.sucursal_id):
                return _error(403, "La solicitud pertenece a una sucursal no autorizada.")
            return jsonify({"solicitud": _serialize(existing), "replayed": True}), 200
        return _error(409, "La referencia cambió o la solicitud entró en conflicto.")

    return jsonify({
        "solicitud": _serialize(entry), "replayed": False,
        "possible_pending_duplicate": related,
    }), 201


@inventario_solicitudes_bp.get("")
@jwt_required()
def listar_solicitudes():
    actor, denied = _actor()
    if denied:
        return denied
    raw_branch = request.args.get("sucursal_id")
    branch = None if raw_branch is None else _query_positive(raw_branch)
    if raw_branch is not None and branch is None:
        return _error(400, "sucursal_id inválido.")
    if branch is not None and not _is_allowed(actor, branch):
        return _error(403, "No tienes autorización para esta sucursal.")

    kind = request.args.get("tipo")
    status = request.args.get("estado")
    if kind is not None and kind not in _TYPES:
        return _error(400, "Filtro tipo inválido.")
    if status is not None and status not in _STATUSES:
        return _error(400, "Filtro estado inválido.")
    page = _query_positive(request.args.get("page", "1"))
    per_page = _query_positive(request.args.get("per_page", "25"))
    if page is None or per_page is None or per_page > 100 or page > 100000:
        return _error(400, "Paginación inválida.")

    query = InventarioSolicitudCorreccionORM.query
    if actor["scope"] is not None:
        query = query.filter(
            InventarioSolicitudCorreccionORM.sucursal_id.in_(actor["scope"])
        )
    if branch is not None:
        query = query.filter(InventarioSolicitudCorreccionORM.sucursal_id == branch)
    if kind:
        query = query.filter(InventarioSolicitudCorreccionORM.tipo == kind)
    if status:
        query = query.filter(InventarioSolicitudCorreccionORM.estado == status)
    total = query.count()
    rows = (query.order_by(
        InventarioSolicitudCorreccionORM.creado_en_utc.desc(),
        InventarioSolicitudCorreccionORM.id.desc(),
    ).offset((page - 1) * per_page).limit(per_page).all())
    return jsonify({
        "items": [_serialize(row) for row in rows],
        "total": total, "page": page, "per_page": per_page,
    }), 200


@inventario_solicitudes_bp.get("/<int:solicitud_id>")
@jwt_required()
def detalle_solicitud(solicitud_id):
    actor, denied = _actor()
    if denied:
        return denied
    query = InventarioSolicitudCorreccionORM.query.filter_by(id=solicitud_id)
    if actor["scope"] is not None:
        query = query.filter(
            InventarioSolicitudCorreccionORM.sucursal_id.in_(actor["scope"])
        )
    row = query.first()
    if row is None:
        return _error(404, "Solicitud inexistente o fuera de tu alcance.")
    return jsonify({"solicitud": _serialize(row)}), 200




def _actor_revision():
    identity = get_jwt_identity()
    if isinstance(identity, bool):
        return None, _error(401, "Sesión inválida.")
    try:
        actor_id = int(identity)
    except (TypeError, ValueError, OverflowError):
        return None, _error(401, "Sesión inválida.")
    access = alcance_revision_e3(actor_id)
    if access is None:
        return None, _error(403, "No tienes permiso para revisar correcciones.")
    return access, None


def _query_revision(access):
    # No filtrar en frontend: el límite real se aplica en SQL ANTES de paginar.
    query = InventarioSolicitudCorreccionORM.query.filter(
        InventarioSolicitudCorreccionORM.sucursal_id.in_(access["sucursales"]),
    )
    if not access["corporativo"]:
        # Los operativos no revisan solicitudes propias. La excepción
        # corporativa depende del grant individual global verificado en backend.
        query = query.filter(
            InventarioSolicitudCorreccionORM.creado_por_usuario_id != access["actor_id"]
        )
        # Competencia por clase REAL en SQL antes de contar/paginar/detallar:
        # Mantenimiento: aparatos. Sistemas: dispositivos. Familia no participa.
        aliases = aliases_clase_inventario_e3(access["clase_activo"])
        if not aliases:
            return query.filter(False)
        actual_type = func.lower(func.btrim(InventarioGeneral.tipo))
        provisional_type = func.lower(func.btrim(
            InventarioSolicitudCorreccionORM.hallazgo_provisional.op("->>")("tipo")
        ))
        query = query.outerjoin(
            InventarioGeneral,
            InventarioGeneral.id == InventarioSolicitudCorreccionORM.inventario_id,
        ).filter(or_(
            and_(
                InventarioSolicitudCorreccionORM.tipo == "UNREGISTERED_FIND",
                provisional_type.in_(aliases),
            ),
            and_(
                InventarioSolicitudCorreccionORM.tipo.in_(
                    ("QUANTITY_DIFFERENCE", "NOT_LOCATED")
                ),
                actual_type.in_(aliases),
            ),
        ))
    return query


@inventario_solicitudes_bp.get("/revision/contexto")
@jwt_required()
def contexto_revision_e3():
    access, denied = _actor_revision()
    if denied:
        return denied
    names = db.session.execute(text(
        "SELECT sucursal_id, sucursal FROM sucursales "
        "WHERE sucursal_id IN :ids ORDER BY sucursal"
    ).bindparams(bindparam(
        "ids", expanding=True
    )), {"ids": access["sucursales"]}).mappings().all()
    return jsonify({
        "can_review": True, "corporativo": access["corporativo"],
        "sucursales": [
            {"sucursal_id": row["sucursal_id"], "sucursal": row["sucursal"]}
            for row in names
        ],
    }), 200


@inventario_solicitudes_bp.get("/revision")
@jwt_required()
def listar_revision_e3():
    access, denied = _actor_revision()
    if denied:
        return denied
    raw_branch = request.args.get("sucursal_id")
    branch = None if raw_branch is None else _query_positive(raw_branch)
    if raw_branch is not None and branch is None:
        return _error(400, "Sucursal inválida.")
    if branch is not None and branch not in access["sucursales"]:
        return _error(403, "Sucursal fuera de tu alcance.")
    kind = request.args.get("tipo")
    status = request.args.get("estado", "PENDING")
    if kind is not None and kind not in _TYPES:
        return _error(400, "Tipo inválido.")
    if status not in _STATUSES:
        return _error(400, "Estado inválido.")
    page = _query_positive(request.args.get("page", "1"))
    per_page = _query_positive(request.args.get("per_page", "10"))
    if page is None or page > 100000 or per_page is None or per_page > 100:
        return _error(400, "Paginación inválida.")
    query = _query_revision(access).filter(
        InventarioSolicitudCorreccionORM.estado == status
    )
    if branch is not None:
        query = query.filter(InventarioSolicitudCorreccionORM.sucursal_id == branch)
    if kind:
        query = query.filter(InventarioSolicitudCorreccionORM.tipo == kind)
    total = query.count()
    rows = (query.order_by(
        InventarioSolicitudCorreccionORM.creado_en_utc.desc(),
        InventarioSolicitudCorreccionORM.id.desc(),
    ).offset((page - 1) * per_page).limit(per_page).all())
    return jsonify({
        "items": [_serialize(row) for row in rows], "total": total,
        "page": page, "per_page": per_page,
    }), 200


@inventario_solicitudes_bp.get("/revision/<int:solicitud_id>")
@jwt_required()
def detalle_revision_e3(solicitud_id):
    access, denied = _actor_revision()
    if denied:
        return denied
    row = _query_revision(access).filter(
        InventarioSolicitudCorreccionORM.id == solicitud_id
    ).first()
    if row is None:
        return _error(404, "Solicitud inexistente o fuera de tu alcance.")
    return jsonify({"solicitud": _serialize(row)}), 200

@inventario_solicitudes_bp.post("/decisiones/lote")
@jwt_required()
def decidir_solicitudes_lote():
    """E3: backend es fuente de permisos; autorizaciones atomicas o rollback."""
    identity = get_jwt_identity()
    if isinstance(identity, bool):
        return _error(401, "Sesión inválida.")
    try:
        actor_id = int(identity)
    except (ValueError, TypeError, OverflowError):
        return _error(401, "Sesión inválida.")
    if actor_id <= 0:
        return _error(401, "Sesión inválida.")
    payload = request.get_json(silent=True)
    if payload is None:
        return _error(400, "Se requiere JSON válido.")
    try:
        if len(json.dumps(payload, ensure_ascii=False, allow_nan=False)) > 16000:
            return _error(400, "Lote demasiado grande.")
    except (ValueError, TypeError):
        return _error(400, "JSON inválido.")
    try:
        result = decidir_lote(actor_id=actor_id, payload=payload)
        return jsonify(result), 200 if result["replayed"] else 201
    except DecisionError as exc:
        db.session.rollback()
        return jsonify({"error": exc.code, "detail": exc.detail}), exc.status
    except (IntegrityError, OperationalError):
        db.session.rollback()
        return _error(409, "La operación entró en conflicto; revisa y reintenta con la misma llave.")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("E3: error al decidir lote de inventario")
        return _error(500, "No se pudo procesar la decisión.")
