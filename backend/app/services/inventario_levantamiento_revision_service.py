"""E4: conciliación de un Excel contra corte congelado → revisiones únicas.

Una importación puede proponer E2, jamás ejecutar una decisión E3 ni mutar V1.
El bloqueo FOR UPDATE del levantamiento ocurre en el caller y serializa los
uploads del mismo ciclo; las UNIQUE en PostgreSQL refuerzan idempotencia.
"""
from datetime import date, datetime, timezone
from hashlib import sha256
from uuid import uuid5, NAMESPACE_URL
import json
import re

from sqlalchemy import func, text as sql_text
from app.extensions import db
from app.models.inventario_solicitud_correccion import InventarioSolicitudCorreccionORM as Solicitud
from app.models.inventario_levantamiento_revision import (
    InventarioLevantamientoRevisionORM as Revision,
    InventarioLevantamientoRevisionEvidenciaORM as Evidencia,
)
from app.services.inventario_levantamiento_excel_parser import norm


CODIGOS_VACIOS = frozenset({
    "", "sin codigo", "sin etiqueta", "pendiente", "s/c", "n/a", "na",
})


def _key(item):
    return sha256(json.dumps(item, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":")).encode("utf-8")).hexdigest()[:24]


def _casos(lev, parsed, referencias):
    """La clave es identidad lógica, no número de fila o Excel/sucursal específica."""
    ref_by_id = {r.inventario_id_original: r for r in referencias}
    casos = {}
    usados = set()
    for row in parsed["filas"]:
        data = row["datos_crudos"]
        codigo = str(row.get("codigo_declarado") or "").strip()
        inv_id = row["inventario_id_declarado"]
        hoja = row["hoja"]
        if hoja == "APARATOS" and inv_id in ref_by_id:
            if row["respuesta"] != "NO" or row["diagnosticos"]:
                continue
            k = f"REF:{inv_id}:NOT_LOCATED"
            casos[k] = {
                "clave": k, "tipo": "NOT_LOCATED", "inventario_id": inv_id,
                "campo": None, "codigo": codigo,
                "hoja": hoja, "fila": row["fila_excel"], "datos": data,
                "base": ref_by_id[inv_id],
            }
            continue
        if hoja != "HALLAZGOS" and not (
            lev.modalidad == "INICIAL" and hoja == "APARATOS" and inv_id is None
        ):
            continue
        canonical = norm(codigo)
        if canonical and canonical not in CODIGOS_VACIOS:
            k = "FIND:" + _key({"codigo": canonical})
            blocked = None
        else:
            # Sin etiqueta no hay identidad física fiable entre versiones.
            # Agrupar por huella del contenido, NUNCA promover automáticamente.
            k = "AMBIGUOUS:" + _key({
                "nombre": norm(data.get("aparato")),
                "marca": norm(data.get("marca")),
                "categoria": norm(data.get("categoria")),
                "descripcion": norm(data.get("descripcion") or data.get("observaciones")),
            })
            blocked = "IDENTIDAD_FISICA_INSUFICIENTE"
        if k in usados:
            # Se conserva un incidente bloqueado para todo el grupo; no
            # se fusionan supuestos aparatos bajo una identidad oficial.
            blocked = "HALLAZGOS_INDISTINGUIBLES"
            casos[k]["bloqueo"] = blocked
        else:
            casos[k] = {
                "clave": k, "tipo": "UNREGISTERED_FIND", "inventario_id": None,
                "campo": None, "codigo": codigo, "hoja": hoja,
                "fila": row["fila_excel"], "datos": data, "base": None,
                "bloqueo": blocked,
            }
            usados.add(k)
    for ref in referencias:
        codigo = str(ref.codigo_interno_original or "").strip()
        if not re.match(r"^[0-9]{2}", codigo) or codigo[:2] == f"{lev.sucursal_id:02d}":
            continue
        k = f"REF:{ref.inventario_id_original}:PREFIX"
        casos[k] = {
            "clave": k, "tipo": "MASTER_FIELD", "inventario_id": ref.inventario_id_original,
            "campo": "codigo_interno", "codigo": codigo, "hoja": "APARATOS",
            "fila": None, "datos": ref.datos_originales,
            "base": ref, "propuesto": f"{lev.sucursal_id:02d}" + codigo[2:],
        }
    return casos


def _preparar_solicitud(lev, imp, caso):
    """Generación conservadora de propuestas E2; usar sus validadores originales."""
    tipo = caso["tipo"]
    datos = caso["datos"] or {}
    fecha = (imp.control or {}).get("fecha_recorrido") or lev.fecha_corte_local
    fecha = fecha.isoformat() if isinstance(fecha, date) else str(fecha or "")
    obs = str(datos.get("descripcion") or datos.get("observaciones") or "").strip()
    reason = f"E4 levantamiento {lev.id}, diferencia {caso['clave']}; revisar evidencia física"
    payload = {
        "tipo": tipo, "sucursal_id": lev.sucursal_id,
        "motivo": reason,
        "idempotency_key": str(uuid5(NAMESPACE_URL, f"suite-ultra-e4:{lev.id}:{caso['clave']}")),
    }
    if tipo == "NOT_LOCATED":
        ref = caso["base"]
        stock_actual = db.session.execute(sql_text("""
            SELECT stock FROM inventario_sucursal
            WHERE inventario_id=:id AND sucursal_id=:sucursal
        """), {"id": caso["inventario_id"], "sucursal": lev.sucursal_id}).scalar_one_or_none()
        if stock_actual is None or stock_actual != ref.stock_original:
            return None, "INVENTARIO_CAMBIO_DESDE_CORTE"
        payload.update({
            "inventario_id": caso["inventario_id"],
            "valor_original": {"stock": stock_actual},
            "valor_propuesto": {"no_localizado": True},
            "evidencia_descriptiva": obs,
            "fecha_observacion_local": fecha,
        })
    elif tipo == "MASTER_FIELD":
        original = db.session.execute(sql_text("""
            SELECT codigo_interno FROM inventario_general WHERE id=:id
        """), {"id": caso["inventario_id"]}).scalar_one_or_none()
        if original is None or norm(original) != norm(caso["codigo"]):
            return None, "CODIGO_OFICIAL_CAMBIO_DESDE_CORTE"
        proposed = caso["propuesto"]
        clash = db.session.execute(sql_text("""
            SELECT id FROM inventario_general
            WHERE upper(btrim(codigo_interno))=upper(:nuevo) AND id<>:id LIMIT 1
        """), {"nuevo": proposed, "id": caso["inventario_id"]}).scalar_one_or_none()
        if clash is not None:
            return None, "CODIGO_PROPUESTO_OCUPADO"
        payload.update({
            "inventario_id": caso["inventario_id"], "campo": "codigo_interno",
            "valor_original": original, "valor_propuesto": proposed,
        })
    else:
        codigo = str(caso["codigo"] or "").strip()
        if caso.get("bloqueo") or not codigo or norm(codigo) in CODIGOS_VACIOS:
            return None, caso.get("bloqueo") or "IDENTIDAD_FISICA_INSUFICIENTE"
        existing_code = db.session.execute(sql_text("""
            SELECT id FROM inventario_general
            WHERE upper(btrim(codigo_interno))=upper(:codigo) LIMIT 1
        """), {"codigo": codigo}).scalar_one_or_none()
        if existing_code is not None:
            return None, "CODIGO_YA_REGISTRADO"
        nombre = str(datos.get("aparato") or "").strip()
        if not nombre:
            return None, "HALLAZGO_SIN_NOMBRE"
        provisional = {"nombre": nombre, "tipo": "APARATOS", "codigo_interno": codigo}
        marca = str(datos.get("marca") or "").strip()
        if marca:
            provisional["marca"] = marca
        payload["hallazgo_provisional"] = provisional
        payload["fecha_observacion_local"] = fecha
        payload["evidencia_descriptiva"] = obs
    return payload, None


def _solicitud_e2(lev, imp, caso, actor):
    """Crea E2 en la transacción de recepción; no llama un endpoint propio."""
    from app.routes.inventario_solicitudes_routes import (
        _validate_payload, _official_snapshot, _canonical_fingerprint,
    )

    payload, blocked = _preparar_solicitud(lev, imp, caso)
    if blocked:
        return None, blocked
    parsed, invalid = _validate_payload(payload)
    if invalid is not None:
        return None, "EVIDENCIA_O_PROPUESTA_INCOMPLETA"
    related = Solicitud.query.filter_by(
        sucursal_id=lev.sucursal_id, tipo=caso["tipo"],
        inventario_id=caso["inventario_id"], campo=caso["campo"], estado="PENDING",
    ).first()
    if related is not None:
        return None, "SOLICITUD_E2_PREEXISTENTE_REQUIERE_REVISION"
    official, conflict = _official_snapshot(parsed)
    if conflict is not None:
        return None, "CAMBIO_OFICIAL_REQUIERE_REVISION"
    fingerprint_values = {
        k: v.isoformat() if isinstance(v, date) else str(v) if hasattr(v, "hex") else v
        for k, v in parsed.items()
    }
    fingerprint = _canonical_fingerprint(fingerprint_values)
    existing = Solicitud.query.filter_by(
        creado_por_usuario_id=actor, idempotency_key=parsed["idempotency_key"],
    ).first()
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            return None, "IDEMPOTENCIA_E2_EN_CONFLICTO"
        return existing, None
    solicitud = Solicitud(
        tipo=parsed["tipo"], estado="PENDING", sucursal_id=lev.sucursal_id,
        inventario_id=parsed["inventario_id"], campo=parsed["campo"],
        valor_original=official.get("original"),
        valor_propuesto=parsed["valor_propuesto"],
        hallazgo_provisional=parsed["hallazgo_provisional"],
        baseline_canonico=official.get("baseline", official),
        fecha_observacion_local=parsed["fecha_observacion_local"],
        motivo=parsed["motivo"], evidencia_descriptiva=parsed["evidencia_descriptiva"],
        creado_por_usuario_id=actor, idempotency_key=parsed["idempotency_key"],
        request_fingerprint=fingerprint,
    )
    db.session.add(solicitud)
    db.session.flush()
    return solicitud, None


def reconciliar_importacion(lev, imp, parsed, actor):
    """Idempotencia por ciclo + clave, evidencias por versión. No aplica E3."""
    if imp.resultado == "INVALID":
        return {"nuevas": 0, "reutilizadas": 0, "bloqueadas": 0, "e2_creadas": 0}
    from app.models.inventario_levantamiento import InventarioLevantamientoReferenciaORM as Ref

    referencias = Ref.query.filter_by(levantamiento_id=lev.id).all()
    casos = _casos(lev, parsed, referencias)
    actuales = {
        revision.logical_key: revision
        for revision in Revision.query.filter_by(levantamiento_id=lev.id).all()
    }
    nuevos = reutilizados = bloqueados = e2_creadas = 0
    presentes = set()
    for clave, caso in sorted(casos.items()):
        presentes.add(clave)
        row = actuales.get(clave)
        if row is None:
            row = Revision(
                levantamiento_id=lev.id, logical_key=clave, tipo=caso["tipo"],
                inventario_id=caso["inventario_id"], codigo_observado=caso["codigo"],
                campo=caso["campo"], estado="PENDING", actor_creador_id=actor,
                primera_importacion_id=imp.id, ultima_importacion_id=imp.id,
                ultimo_valor=caso["datos"],
            )
            db.session.add(row)
            db.session.flush()
            nuevos += 1
        else:
            reutilizados += 1
            row.ultima_importacion_id = imp.id
            row.ultimo_valor = caso["datos"]
            row.actualizado_en_utc = datetime.now(timezone.utc)
        if row.solicitud_e2_id is None:
            solicitud, razon = _solicitud_e2(lev, imp, caso, actor)
            if razon:
                row.estado = "BLOCKED"
                row.motivo_bloqueo = razon
                bloqueados += 1
            else:
                row.solicitud_e2_id = solicitud.id
                row.estado = "AWAITING_E3"
                row.motivo_bloqueo = None
                e2_creadas += 1
        else:
            vinculada = db.session.get(Solicitud, row.solicitud_e2_id)
            row.estado = {
                "PENDING": "AWAITING_E3", "APPROVED": "APPROVED", "REJECTED": "REJECTED"
            }.get(vinculada.estado if vinculada else "", "BLOCKED")
            if row.estado == "BLOCKED":
                row.motivo_bloqueo = "SOLICITUD_E2_DESAPARECIDA"
                bloqueados += 1
        db.session.add(Evidencia(
            revision_id=row.id, importacion_id=imp.id,
            hoja=caso["hoja"], fila_excel=caso["fila"],
            valor_observado={
                "datos": caso["datos"], "respuesta": (
                    "NO" if caso["tipo"] == "NOT_LOCATED" else None),
                "codigo": caso["codigo"], "tipo": caso["tipo"],
            },
        ))
    for clave, row in actuales.items():
        if clave in presentes or row.estado in ("APPROVED", "REJECTED"):
            continue
        if row.solicitud_e2_id:
            solicitud = db.session.get(Solicitud, row.solicitud_e2_id)
            if solicitud and solicitud.estado == "PENDING":
                row.estado = "BLOCKED"
                row.motivo_bloqueo = "E2_PENDIENTE_PERO_EXCEL_CORREGIDO"
                bloqueados += 1
                continue
        row.estado = "SUPERSEDED"
        row.motivo_bloqueo = None
        row.ultima_importacion_id = imp.id
    return {"nuevas": nuevos, "reutilizadas": reutilizados,
            "bloqueadas": bloqueados, "e2_creadas": e2_creadas}
