"""E3: decisiones atómicas sobre solicitudes E2 con autorizaciones DB.

Aplicar y auditar son una sola transacción. No se crean grants.
Las decisiones para NOT_LOCATED y UNREGISTERED_FIND se pueden rechazar;
su aprobación exige un contrato de resolución separado (422).
"""
import hashlib
import json
from uuid import UUID

from sqlalchemy import func, select, text

from app.extensions import db
from app.models.inventario import InventarioGeneral, InventarioSucursal
from app.models.inventario_codigo_correccion import InventarioCodigoCorreccionORM
from app.models.inventario_solicitud_correccion import InventarioSolicitudCorreccionORM
from app.models.inventario_correccion_decision import (
    InventarioCorreccionLoteORM, InventarioCorreccionDecisionORM,
    InventarioCorreccionAjusteORM, InventarioCorreccionMaestroAuditORM,
)
from app.utils.inventory_correction_permissions import resolver_acceso_autorizacion_e3


class DecisionError(Exception):
    def __init__(self, status, code, detail):
        super().__init__(detail)
        self.status = status
        self.code = code
        self.detail = detail


def _positive_id(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def validar_lote(payload):
    """Contrato cerrado: IDs únicos, UUID, motivo y hasta diez solicitudes."""
    if not isinstance(payload, dict) or set(payload) != {
        "decision", "solicitud_ids", "motivo", "idempotency_key"
    }:
        raise DecisionError(400, "invalid_payload", "Campos de lote inválidos.")
    action = payload["decision"]
    if action not in ("APPROVED", "REJECTED"):
        raise DecisionError(400, "invalid_decision", "Decisión inválida.")
    ids = payload["solicitud_ids"]
    if (not isinstance(ids, list) or not 1 <= len(ids) <= 10
            or not all(_positive_id(item) for item in ids)
            or len(set(ids)) != len(ids)):
        raise DecisionError(400, "invalid_ids", "Se requieren de 1 a 10 IDs únicos y válidos.")
    motivo = payload["motivo"]
    if not isinstance(motivo, str) or not 10 <= len(motivo.strip()) <= 2000:
        raise DecisionError(400, "invalid_reason", "El motivo requiere de 10 a 2000 caracteres.")
    raw_key = payload["idempotency_key"]
    try:
        if not isinstance(raw_key, str):
            raise ValueError()
        key = UUID(raw_key)
        if not key.int:
            raise ValueError()
    except (TypeError, ValueError, AttributeError):
        raise DecisionError(400, "invalid_key", "idempotency_key debe ser UUID válido.")
    canonical = {
        "decision": action, "solicitud_ids": sorted(ids),
        "motivo": motivo.strip(),
    }
    fingerprint = hashlib.sha256(json.dumps(
        canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()
    return canonical, key, fingerprint


def _lock_requests(ids):
    rows = db.session.execute(
        select(InventarioSolicitudCorreccionORM)
        .where(InventarioSolicitudCorreccionORM.id.in_(ids))
        .order_by(InventarioSolicitudCorreccionORM.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalars().all()
    if len(rows) != len(ids):
        raise DecisionError(404, "not_found", "Solicitud inexistente o no disponible.")
    return rows


def _permitir_todas(actor_id, rows):
    for row in rows:
        access = resolver_acceso_autorizacion_e3(
            actor_usuario_id=actor_id,
            solicitud_sucursal_id=row.sucursal_id,
            solicitud_creador_id=row.creado_por_usuario_id,
            tipo=row.tipo,
        )
        if not access.allowed:
            raise DecisionError(403, "forbidden", "Sin facultad para esta solicitud.")


def _replay_if_exists(actor_id, key, fingerprint, ids, action):
    previous = db.session.execute(
        select(InventarioCorreccionLoteORM).where(
            InventarioCorreccionLoteORM.actor_usuario_id == actor_id,
            InventarioCorreccionLoteORM.idempotency_key == key,
        ).with_for_update()
    ).scalar_one_or_none()
    if previous is None:
        return None
    if previous.request_fingerprint != fingerprint or previous.tipo_decision != action:
        raise DecisionError(409, "idempotency_conflict", "La llave corresponde a otro lote.")
    # Tampoco exponer resultados de lotes históricos si se revocó el acceso.
    rows = _lock_requests(ids)
    _permitir_todas(actor_id, rows)
    if not isinstance(previous.resultados, dict):
        raise DecisionError(409, "incomplete_replay", "Lote histórico incompleto; revisar auditoría.")
    return {"lote_id": previous.id, "replayed": True, "items": previous.resultados["items"]}


def _lock_official(rows):
    """Bloqueo ordenado evita deadlocks por diferente orden de IDs del lote."""
    inventory_ids = sorted({x.inventario_id for x in rows if x.inventario_id is not None})
    masters = {}
    stocks = {}
    for inventory_id in inventory_ids:
        master = db.session.execute(
            select(InventarioGeneral).where(InventarioGeneral.id == inventory_id)
            .with_for_update().execution_options(populate_existing=True)
        ).scalar_one_or_none()
        if master is None:
            raise DecisionError(409, "missing_master", "Referencia oficial inexistente.")
        masters[inventory_id] = master
    for inventory_id, branch in sorted({
        (x.inventario_id, x.sucursal_id) for x in rows if x.inventario_id is not None
    }):
        stock = db.session.execute(
            select(InventarioSucursal).where(
                InventarioSucursal.inventario_id == inventory_id,
                InventarioSucursal.sucursal_id == branch,
            ).with_for_update().execution_options(populate_existing=True)
        ).scalar_one_or_none()
        if stock is None or stock.stock is None:
            raise DecisionError(409, "missing_stock", "Existencia oficial no disponible.")
        stocks[(inventory_id, branch)] = stock
    return masters, stocks


_MASTER_FIELDS = frozenset({
    "nombre", "marca", "codigo_interno", "no_equipo", "unidad_medida",
    "tipo", "categoria_inventario_id", "familia_equipo_id",
})
_MASTER_STR_LENGTHS = {
    "nombre": 255, "marca": 100, "codigo_interno": 50,
    "no_equipo": 50, "unidad_medida": 50, "tipo": 20,
}


def _apply_approved(row, decision, masters, stocks, actor_id, reason):
    if row.tipo not in ("QUANTITY_DIFFERENCE", "MASTER_FIELD"):
        raise DecisionError(
            422, "resolution_required",
            "Esta clase exige resolución adicional; no puede autorizarse todavía.",
        )
    baseline = row.baseline_canonico
    if not isinstance(baseline, dict) or baseline.get("inventario_id") != row.inventario_id or baseline.get("sucursal_id") != row.sucursal_id:
        raise DecisionError(409, "baseline_invalid", "Baseline de solicitud inválido.")
    master = masters[row.inventario_id]
    stock_row = stocks[(row.inventario_id, row.sucursal_id)]
    current_stock = stock_row.stock
    expected_stock = baseline.get("stock")
    if type(current_stock) is not int or type(expected_stock) is not int or current_stock != expected_stock:
        raise DecisionError(409, "stale_stock", "Las existencias cambiaron; se requiere nueva solicitud.")

    if row.tipo == "QUANTITY_DIFFERENCE":
        proposed = row.valor_propuesto
        if not isinstance(proposed, dict) or set(proposed) != {"cantidad_fisica"}:
            raise DecisionError(422, "invalid_quantity", "Propuesta de cantidad inválida.")
        final = proposed["cantidad_fisica"]
        if type(final) is not int or final < 0 or current_stock == final:
            raise DecisionError(409, "stale_quantity", "Cantidad física inválida u obsoleta.")
        if row.valor_original != {"stock": current_stock}:
            raise DecisionError(409, "stale_original", "Original de solicitud no coincide.")
        stock_row.stock = final
        decision.efecto_anterior = {"stock": current_stock}
        decision.efecto_posterior = {"stock": final}
        db.session.add(InventarioCorreccionAjusteORM(
            decision_id=decision.id, solicitud_id=row.id,
            inventario_id=row.inventario_id, sucursal_id=row.sucursal_id,
            stock_anterior=current_stock, stock_nuevo=final,
            delta_firmada=final - current_stock, actor_usuario_id=actor_id,
            motivo=reason,
        ))
        return {"tipo": "QUANTITY_DIFFERENCE", "antes": current_stock, "despues": final}

    field = row.campo
    if field not in _MASTER_FIELDS or baseline.get("campo") != field:
        raise DecisionError(422, "invalid_field", "Campo maestro fuera de whitelist.")
    old = getattr(master, field)
    expected = baseline.get("valor")
    if type(old) is not type(expected) or old != expected or type(row.valor_original) is not type(old) or row.valor_original != old:
        raise DecisionError(409, "stale_master", "El valor maestro cambió; no se aplicará.")
    new = row.valor_propuesto
    if field in _MASTER_STR_LENGTHS:
        if not isinstance(new, str) or not new.strip() or len(new) > _MASTER_STR_LENGTHS[field]:
            raise DecisionError(422, "invalid_proposal", "Valor maestro propuesto inválido.")
    elif not _positive_id(new):
        raise DecisionError(422, "invalid_catalog_id", "Clasificación propuesta inválida.")
    if type(old) is type(new) and old == new:
        raise DecisionError(409, "already_applied", "El valor propuesto ya es oficial.")

    if field == "codigo_interno":
        # Usa el mismo advisory lock que las altas y correcciones V1.
        # Se toma ANTES de bloquear filas maestras (en decidir_lote).
        existing_code = str(old or "").strip().upper()
        final_code = new.strip().upper()
        if not existing_code or not final_code or final_code != new:
            raise DecisionError(422, "invalid_code", "El código requiere identidad anterior y nuevo código normalizado.")
        duplicate = db.session.execute(
            select(InventarioGeneral.id).where(
                func.upper(func.trim(InventarioGeneral.codigo_interno)) == final_code,
                InventarioGeneral.id != row.inventario_id,
            ).limit(1)
        ).scalar_one_or_none()
        if duplicate is not None:
            raise DecisionError(409, "duplicate_code", "El código interno ya está registrado.")
        db.session.add(InventarioCodigoCorreccionORM(
            inventario_id=row.inventario_id, actor_usuario_id=actor_id,
            codigo_anterior=existing_code, codigo_nuevo=final_code, motivo=reason,
        ))
        new = final_code
    elif field in ("familia_equipo_id", "categoria_inventario_id"):
        table = "familia_equipo" if field == "familia_equipo_id" else "catalogo_categoria_inventario"
        exists = db.session.execute(text(
            f"SELECT 1 FROM {table} WHERE id = :id AND activo IS TRUE"
        ), {"id": new}).scalar_one_or_none()
        if exists is None:
            raise DecisionError(422, "inactive_catalog", "La clasificación está inexistente o inactiva.")

    setattr(master, field, new)
    decision.efecto_anterior = {field: old}
    decision.efecto_posterior = {field: new}
    db.session.add(InventarioCorreccionMaestroAuditORM(
        decision_id=decision.id, solicitud_id=row.id,
        inventario_id=row.inventario_id, campo=field,
        valor_anterior=old, valor_nuevo=new,
        actor_usuario_id=actor_id, motivo=reason,
    ))
    return {"tipo": "MASTER_FIELD", "campo": field, "antes": old, "despues": new}


def decidir_lote(*, actor_id, payload):
    """Cierra lote completo o nada. El caller maneja rollback de DecisionError."""
    if not _positive_id(actor_id):
        raise DecisionError(401, "invalid_actor", "Sesión inválida.")
    canonical, key, fingerprint = validar_lote(payload)
    ids = canonical["solicitud_ids"]
    action = canonical["decision"]
    reason = canonical["motivo"]

    # Serializar reintentos del mismo actor, sin confiar en claims JWT.
    user_exists = db.session.execute(text(
        "SELECT id FROM users WHERE id = :id FOR UPDATE"
    ), {"id": actor_id}).scalar_one_or_none()
    if user_exists is None:
        raise DecisionError(401, "unknown_actor", "Sesión inválida.")

    replay = _replay_if_exists(actor_id, key, fingerprint, ids, action)
    if replay is not None:
        db.session.rollback()  # solo lecturas y locks
        return replay

    rows = _lock_requests(ids)
    _permitir_todas(actor_id, rows)
    if any(row.estado != "PENDING" for row in rows):
        raise DecisionError(409, "already_decided", "Una solicitud ya fue decidida.")

    if action == "APPROVED" and any(row.tipo == "MASTER_FIELD" and row.campo == "codigo_interno" for row in rows):
        db.session.execute(
            text("SELECT pg_advisory_xact_lock(:domain, :operation)"),
            {"domain": 51022, "operation": 11},
        )
    seen = set()
    if action == "APPROVED":
        for row in rows:
            item = (
                ("quantity", row.inventario_id, row.sucursal_id)
                if row.tipo == "QUANTITY_DIFFERENCE"
                else ("master", row.inventario_id, row.campo)
                if row.tipo == "MASTER_FIELD"
                else ("unsupported", row.id)
            )
            if item in seen:
                raise DecisionError(409, "duplicate_target", "Dos solicitudes modifican la misma referencia del lote.")
            seen.add(item)
    masters, stocks = _lock_official(rows) if action == "APPROVED" else ({}, {})

    lote = InventarioCorreccionLoteORM(
        actor_usuario_id=actor_id, tipo_decision=action,
        motivo_lote=reason, idempotency_key=key,
        request_fingerprint=fingerprint,
    )
    db.session.add(lote)
    db.session.flush()
    results = []
    for row in rows:
        decision = InventarioCorreccionDecisionORM(
            lote_id=lote.id, solicitud_id=row.id, decision=action,
            actor_usuario_id=actor_id, motivo_decision=reason,
        )
        db.session.add(decision)
        db.session.flush()
        effect = None
        if action == "APPROVED":
            effect = _apply_approved(row, decision, masters, stocks, actor_id, reason)
        row.estado = action
        results.append({"solicitud_id": row.id, "estado": action, "efecto": effect})
    lote.resultados = {"items": results}
    db.session.commit()
    return {"lote_id": lote.id, "replayed": False, "items": results}
