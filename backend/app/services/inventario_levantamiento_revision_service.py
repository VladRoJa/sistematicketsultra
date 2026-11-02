"""E4: conciliación de un Excel contra corte congelado → revisiones únicas.

Una importación puede proponer E2, jamás ejecutar una decisión E3 ni mutar V1.
El bloqueo FOR UPDATE del levantamiento ocurre en el caller y serializa los
uploads del mismo ciclo; las UNIQUE en PostgreSQL refuerzan idempotencia.
"""
from datetime import date, datetime, timezone
import os
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
            if "CODIGO_DIFIERE_DEL_CORTE" in row["diagnosticos"]:
                k = f"REF:{inv_id}:IDENTITY_MISMATCH"
                casos[k] = {
                    "clave": k, "tipo": "IDENTITY_MISMATCH",
                    "inventario_id": inv_id, "campo": "codigo_interno",
                    "codigo": codigo, "hoja": hoja, "fila": row["fila_excel"],
                    "datos": data, "base": ref_by_id[inv_id],
                    "bloqueo": "CODIGO_FISICO_NO_COINCIDE_CORTE",
                }
                continue
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
        if "CODIGO_HALLAZGO_EN_CORTE" in row["diagnosticos"]:
            # La etiqueta pertenece a un aparato oficial del corte.
            # Conservar el hallazgo como discrepancia accionable sin E2,
            # aunque otra fila del mismo Excel sí pueda crear su solicitud.
            blocked = "CODIGO_HALLAZGO_EN_CORTE"
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
        # Solo códigos legados de sucursales 1..99 se derivan del ID.
        # Otros identificadores (p. ej. ULTRA DEMO) necesitan una regla
        # de nomenclatura explícita, no recodificaciones presumidas.
        if not (1 <= lev.sucursal_id <= 99):
            continue
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


def _solicitud_e2(lev, imp, caso, actor, *, reemplazo_key=None, motivo_reemplazo=None):
    """Crea E2 en la transacción de recepción; no llama un endpoint propio."""
    from app.routes.inventario_solicitudes_routes import (
        _validate_payload, _official_snapshot, _canonical_fingerprint,
    )

    payload, blocked = _preparar_solicitud(lev, imp, caso)
    if blocked:
        return None, blocked
    if reemplazo_key is not None:
        payload["idempotency_key"] = str(reemplazo_key)
        payload["motivo"] = (
            f"E4 levantamiento {lev.id}, sustitución auditada de "
            f"{caso['clave']}: {motivo_reemplazo}"
        )
    parsed, invalid = _validate_payload(payload)
    if invalid is not None:
        return None, "EVIDENCIA_O_PROPUESTA_INCOMPLETA"
    if caso["tipo"] == "UNREGISTERED_FIND":
        # Distintos hallazgos no tienen inventario_id: usar la identidad
        # física provisional, no comparar NULL == NULL para todo el club.
        codigo_fisico = norm(caso["codigo"])
        related = db.session.execute(sql_text("""
            SELECT id FROM inventario_correccion_solicitudes
            WHERE sucursal_id=:branch AND tipo='UNREGISTERED_FIND'
              AND estado='PENDING'
              AND lower(btrim(hallazgo_provisional ->> 'codigo_interno'))=:codigo
            LIMIT 1
        """), {"branch": lev.sucursal_id, "codigo": codigo_fisico}).scalar_one_or_none()
    else:
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


def e4_auto_enabled(sucursal_id):
    """Activación independiente para DEMO y sucursales reales, OFF por defecto.

    El origen de verdad del ámbito es sucursales.is_demo en PostgreSQL.
    Activar producción no habilita E4 a gerentes ni autoriza solicitudes E3.
    """
    es_demo = db.session.execute(sql_text("""
        SELECT COALESCE(is_demo, false) FROM sucursales
        WHERE sucursal_id=:sucursal
    """), {"sucursal": sucursal_id}).scalar_one_or_none()
    if es_demo is None:
        return False
    flag = ("INVENTARIO_E4_AUTO_REVIEW_DEMO_ENABLED" if es_demo
            else "INVENTARIO_E4_AUTO_REVIEW_PRODUCTION_ENABLED")
    return os.getenv(flag, "false").strip().lower() in {"1", "true", "yes", "on"}



def sustituir_propuesta_maestra(levantamiento_id, revision_id, actor_id, data):
    """Sustituye E2 rechazada sin mutar maestro; registra evento E4 inmutable.

    El rechazo anterior requiere E3, nunca lo ejecuta E4. La llave de ciclo
    serializa reemplazos y las reejecuciones no duplican solicitudes.
    """
    from app.models.inventario_levantamiento import (
        InventarioLevantamientoORM as Lev,
        InventarioLevantamientoImportacionORM as Imp,
        InventarioLevantamientoReferenciaORM as Ref,
    )
    from app.services.inventario_levantamientos_service import E4Error, parse_uuid

    if not isinstance(data, dict) or set(data) != {
        "nuevo_codigo", "motivo", "idempotency_key"
    }:
        raise E4Error(400, "DATOS_INVALIDOS", "Indica nuevo código, motivo y llave de idempotencia")
    codigo = data["nuevo_codigo"]
    motivo = data["motivo"]
    key = parse_uuid(data["idempotency_key"])
    if (not isinstance(codigo, str) or len(codigo) > 50
            or not re.fullmatch(r"[A-Z0-9][A-Z0-9-]*", codigo)):
        raise E4Error(422, "CODIGO_INVALIDO", "Se requiere código físico normalizado y no vacío")
    if not isinstance(motivo, str) or not 20 <= len(motivo.strip()) <= 1000:
        raise E4Error(422, "MOTIVO_INVALIDO", "Justifica la sustitución en 20 a 1000 caracteres")
    motivo = motivo.strip()

    lev = Lev.query.filter_by(id=levantamiento_id).with_for_update().first()
    if lev is None:
        raise E4Error(404, "LEVANTAMIENTO_DESCONOCIDO", "Levantamiento inexistente")
    if lev.estado == "CLOSED" or not lev.ultima_importacion_id:
        raise E4Error(409, "EXPEDIENTE_NO_EDITABLE", "El levantamiento no tiene entrega abierta")
    if not e4_auto_enabled(lev.sucursal_id):
        raise E4Error(409, "E4_NO_HABILITADO", "Revisiones automáticas deshabilitadas")
    if 1 <= lev.sucursal_id <= 99 and not codigo.startswith(f"{lev.sucursal_id:02d}"):
        raise E4Error(422, "PREFIJO_INVALIDO", "El código debe corresponder a la sucursal del corte")

    # Se verifica primero la llave histórica, incluso si E4 ya apunta a E2 nueva.
    replay = db.session.execute(sql_text("""
        SELECT e.revision_id, e.valor_observado
        FROM inventario_levantamiento_revision_evidencias e
        JOIN inventario_levantamiento_revisiones r ON r.id=e.revision_id
        WHERE r.levantamiento_id=:lev
          AND e.valor_observado ->> 'evento' = 'SUSTITUCION_E2'
          AND e.valor_observado ->> 'actor_usuario_id' = :actor
          AND e.valor_observado ->> 'idempotency_key' = :key
        LIMIT 1
    """), {"lev": lev.id, "actor": str(actor_id), "key": str(key)}).mappings().first()
    if replay:
        evento = replay["valor_observado"]
        if (replay["revision_id"] != revision_id
                or evento["codigo_nuevo"] != codigo or evento["motivo"] != motivo):
            raise E4Error(409, "IDEMPOTENCIA_CONFLICTO", "La llave ya corresponde a otra sustitución")
        return {
            "revision_id": revision_id, "solicitud_anterior_id": evento["solicitud_anterior_id"],
            "solicitud_nueva_id": evento["solicitud_nueva_id"], "codigo_nuevo": codigo,
        }, True

    revision = Revision.query.filter_by(
        id=revision_id, levantamiento_id=lev.id,
    ).first()
    if (revision is None or revision.tipo != "MASTER_FIELD"
            or revision.campo != "codigo_interno"
            or revision.logical_key != f"REF:{revision.inventario_id}:PREFIX"
            or revision.estado == "SUPERSEDED"
            or revision.ultima_importacion_id != lev.ultima_importacion_id):
        raise E4Error(409, "REVISION_NO_SUSTITUIBLE", "Revisión maestra fuera del corte vigente")
    anterior = db.session.get(Solicitud, revision.solicitud_e2_id) if revision.solicitud_e2_id else None
    if (anterior is None or anterior.estado != "REJECTED"
            or anterior.tipo != "MASTER_FIELD"
            or anterior.sucursal_id != lev.sucursal_id
            or anterior.inventario_id != revision.inventario_id
            or anterior.campo != "codigo_interno"):
        raise E4Error(409, "RECHAZO_E3_REQUERIDO",
                      "Primero rechaza formalmente en E3 la propuesta incorrecta")
    if codigo == anterior.valor_propuesto:
        raise E4Error(422, "MISMA_PROPUESTA", "La sustitución debe proponer un código diferente")
    ref = Ref.query.filter_by(
        levantamiento_id=lev.id, inventario_id_original=revision.inventario_id,
    ).first()
    if ref is None or norm(ref.codigo_interno_original) != norm(revision.codigo_observado):
        raise E4Error(409, "CORTE_INCONSISTENTE", "La identidad histórica no coincide")
    imp = db.session.get(Imp, lev.ultima_importacion_id)
    if imp is None or imp.resultado == "INVALID":
        raise E4Error(409, "ENTREGA_INVALIDA", "La versión actual no permite sustituciones")

    caso = {
        "clave": revision.logical_key, "tipo": "MASTER_FIELD",
        "inventario_id": revision.inventario_id, "campo": "codigo_interno",
        "codigo": ref.codigo_interno_original, "propuesto": codigo,
        "datos": ref.datos_originales, "base": ref,
    }
    e2_key = uuid5(NAMESPACE_URL, f"suite-ultra-e4:reemplazo:{revision.id}:{anterior.id}:{key}")
    nueva, bloqueo = _solicitud_e2(
        lev, imp, caso, actor_id, reemplazo_key=e2_key, motivo_reemplazo=motivo,
    )
    if bloqueo:
        raise E4Error(409, "PROPUESTA_NO_ADMISIBLE",
                      f"No se pudo generar la nueva solicitud: {bloqueo}")
    if nueva.id == anterior.id:
        raise E4Error(409, "SOLICITUD_ANTERIOR", "No puede reutilizarse la propuesta rechazada")

    evento = {
        "evento": "SUSTITUCION_E2",
        "idempotency_key": str(key),
        "actor_usuario_id": str(actor_id),
        "solicitud_anterior_id": anterior.id,
        "solicitud_nueva_id": nueva.id,
        "codigo_anterior": anterior.valor_propuesto,
        "codigo_nuevo": codigo,
        "motivo": motivo,
    }
    db.session.add(Evidencia(
        revision_id=revision.id, importacion_id=imp.id,
        hoja=None, fila_excel=None, valor_observado=evento,
    ))
    revision.solicitud_e2_id = nueva.id
    revision.estado = "AWAITING_E3"
    revision.motivo_bloqueo = None
    revision.actualizado_en_utc = datetime.now(timezone.utc)
    db.session.commit()
    return {
        "revision_id": revision.id, "solicitud_anterior_id": anterior.id,
        "solicitud_nueva_id": nueva.id, "codigo_nuevo": codigo,
    }, False



def corregir_codigo_hallazgo(levantamiento_id, revision_id, actor_id, data):
    """Rectifica un código provisional E4 bloqueado sin cambiar el XLSX histórico.

    Conserva la revisión lógica original y deja evento append-only antes de
    crear la solicitud E2 nueva. Su aprobación E3 y la colocación de etiqueta
    física son pasos independientes.
    """
    from app.models.inventario_levantamiento import (
        InventarioLevantamientoORM as Lev,
        InventarioLevantamientoImportacionORM as Imp,
        InventarioLevantamientoReferenciaORM as Ref,
    )
    from app.services.inventario_levantamientos_service import E4Error, parse_uuid
    if not isinstance(data, dict) or set(data) != {
        "nuevo_codigo", "motivo", "idempotency_key"
    }:
        raise E4Error(400, "DATOS_INVALIDOS", "Indica código corregido, motivo y llave de idempotencia")
    code, reason = data["nuevo_codigo"], data["motivo"]
    key = parse_uuid(data["idempotency_key"])
    if not isinstance(code, str) or len(code) > 50 or not re.fullmatch(r"[A-Z0-9][A-Z0-9-]*", code):
        raise E4Error(422, "CODIGO_INVALIDO", "El nuevo código debe estar normalizado y sin espacios")
    if not isinstance(reason, str) or not 20 <= len(reason.strip()) <= 1000:
        raise E4Error(422, "MOTIVO_INVALIDO", "Justifica el cambio en 20 a 1000 caracteres")
    reason = reason.strip()
    lev = Lev.query.filter_by(id=levantamiento_id).with_for_update().first()
    if not lev:
        raise E4Error(404, "LEVANTAMIENTO_DESCONOCIDO", "Levantamiento inexistente")
    if lev.estado == "CLOSED" or not e4_auto_enabled(lev.sucursal_id):
        raise E4Error(409, "E4_NO_EDITABLE", "El levantamiento no permite nuevas revisiones")
    imp = db.session.get(Imp, lev.ultima_importacion_id)
    if not imp or imp.resultado == "INVALID":
        raise E4Error(409, "ENTREGA_INVALIDA", "La entrega actual no es válida")
    if 1 <= lev.sucursal_id <= 99 and not code.startswith(f"{lev.sucursal_id:02d}"):
        raise E4Error(422, "PREFIJO_INVALIDO", "El código no coincide con la sucursal")
    replay = db.session.execute(sql_text("""
        SELECT e.revision_id, e.valor_observado
        FROM inventario_levantamiento_revision_evidencias e
        JOIN inventario_levantamiento_revisiones r ON r.id=e.revision_id
        WHERE r.levantamiento_id=:lev
          AND e.valor_observado ->> 'evento'='CORRECCION_CODIGO_HALLAZGO'
          AND e.valor_observado ->> 'actor_usuario_id'=:actor
          AND e.valor_observado ->> 'idempotency_key'=:key LIMIT 1
    """), {"lev": lev.id, "actor": str(actor_id), "key": str(key)}).mappings().first()
    if replay:
        event = replay["valor_observado"]
        if (replay["revision_id"] != revision_id or event["codigo_nuevo"] != code
                or event["motivo"] != reason):
            raise E4Error(409, "IDEMPOTENCIA_CONFLICTO", "La llave pertenece a otra operación")
        return {"revision_id": revision_id, "codigo_nuevo": code,
                "solicitud_e2_id": event["solicitud_e2_id"]}, True

    rev = Revision.query.filter_by(id=revision_id, levantamiento_id=lev.id).first()
    if (not rev or rev.tipo != "UNREGISTERED_FIND"
            or rev.solicitud_e2_id is not None or rev.estado != "BLOCKED"
            or rev.ultima_importacion_id != lev.ultima_importacion_id):
        raise E4Error(409, "REVISION_NO_CORREGIBLE", "El hallazgo no está bloqueado sin E2 en la versión actual")
    if code == norm(rev.codigo_observado).upper():
        raise E4Error(422, "CODIGO_SIN_CAMBIO", "El nuevo código debe ser diferente")
    duplicated = db.session.execute(sql_text("""
        SELECT 1 FROM inventario_general
        WHERE upper(btrim(codigo_interno))=:code LIMIT 1
    """), {"code": code}).scalar_one_or_none()
    if duplicated:
        raise E4Error(409, "CODIGO_OCUPADO", "Ya existe un aparato oficial con el código")
    in_cut = Ref.query.filter_by(levantamiento_id=lev.id).all()
    if any(norm(ref.codigo_interno_original).upper() == code for ref in in_cut):
        raise E4Error(409, "CODIGO_EN_CORTE", "El código ya pertenece a una referencia del corte")
    sibling = db.session.execute(sql_text("""
        SELECT 1 FROM inventario_levantamiento_revisiones
        WHERE levantamiento_id=:lev AND id<>:rev
          AND upper(btrim(codigo_observado))=:code AND estado<>'SUPERSEDED'
        LIMIT 1
    """), {"lev": lev.id, "rev": rev.id, "code": code}).scalar_one_or_none()
    if sibling:
        raise E4Error(409, "CODIGO_HALLAZGO_DUPLICADO", "Otra revisión tiene ese código")
    original = rev.codigo_observado
    datos = dict(rev.ultimo_valor)
    datos["codigo"] = code
    case = {
        "clave": rev.logical_key, "tipo": "UNREGISTERED_FIND",
        "inventario_id": None, "campo": None, "codigo": code,
        "hoja": "HALLAZGOS", "fila": None,
        "datos": datos, "base": None, "bloqueo": None,
    }
    request_key = uuid5(NAMESPACE_URL, f"suite-ultra-e4:find-correction:{rev.id}:{key}")
    solicitud, blocked = _solicitud_e2(
        lev, imp, case, actor_id, reemplazo_key=request_key,
        motivo_reemplazo=reason,
    )
    if blocked:
        raise E4Error(409, "CORRECCION_NO_ADMISIBLE", f"No se pudo crear E2: {blocked}")
    event = {
        "evento": "CORRECCION_CODIGO_HALLAZGO",
        "actor_usuario_id": str(actor_id), "idempotency_key": str(key),
        "codigo_anterior": original, "codigo_nuevo": code,
        "motivo": reason, "solicitud_e2_id": solicitud.id,
        "etiqueta_colocada": False,
    }
    db.session.add(Evidencia(
        revision_id=rev.id, importacion_id=imp.id,
        hoja=None, fila_excel=None, valor_observado=event,
    ))
    rev.codigo_observado = code
    rev.ultimo_valor = datos
    rev.solicitud_e2_id = solicitud.id
    rev.estado = "AWAITING_E3"
    rev.motivo_bloqueo = None
    rev.actualizado_en_utc = datetime.now(timezone.utc)
    db.session.commit()
    return {"revision_id": rev.id, "codigo_nuevo": code,
            "solicitud_e2_id": solicitud.id}, False


def reconciliar_importacion(lev, imp, parsed, actor):
    """Idempotencia por ciclo + clave, evidencias por versión. No aplica E3."""
    if not e4_auto_enabled(lev.sucursal_id):
        return {
            "nuevas": 0, "reutilizadas": 0, "bloqueadas": 0, "e2_creadas": 0,
            "auto_revisiones_habilitadas": False,
        }
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


def _estado_efectivo(row):
    if row.solicitud_e2_id is None:
        return row.estado
    solicitud = db.session.get(Solicitud, row.solicitud_e2_id)
    if solicitud is None:
        return "BLOCKED"
    return {
        "PENDING": "AWAITING_E3",
        "APPROVED": "APPROVED",
        "REJECTED": "REJECTED",
    }.get(solicitud.estado, "BLOCKED")


def listado_revisiones(levantamiento_id, page=1, size=20):
    from app.models.inventario_levantamiento import InventarioLevantamientoORM as Lev

    lev = db.session.get(Lev, levantamiento_id)
    if lev is None:
        from app.services.inventario_levantamientos_service import E4Error
        raise E4Error(404, "LEVANTAMIENTO_DESCONOCIDO", "Levantamiento inexistente")
    query = Revision.query.filter_by(levantamiento_id=lev.id)
    total = query.count()
    rows = query.order_by(Revision.id).offset((page - 1) * size).limit(size).all()
    items = [
        {
            "id": r.id, "logical_key": r.logical_key,
            "tipo": r.tipo, "inventario_id": r.inventario_id,
            "codigo_observado": r.codigo_observado, "campo": r.campo,
            "estado": _estado_efectivo(r),
            "motivo_bloqueo": r.motivo_bloqueo,
            "solicitud_e2_id": r.solicitud_e2_id,
            "primera_importacion_id": r.primera_importacion_id,
            "ultima_importacion_id": r.ultima_importacion_id,
            "ultimo_valor": r.ultimo_valor,
        }
        for r in rows
    ]
    resumen = {"total": total, "bloqueadas": 0, "por_autorizar": 0,
               "aprobadas": 0, "rechazadas": 0, "superadas": 0}
    # Un solo join para el conteo; evitar N+1 incluso con miles de aparatos.
    estados = (db.session.query(Revision.estado, Revision.solicitud_e2_id, Solicitud.estado)
               .outerjoin(Solicitud, Revision.solicitud_e2_id == Solicitud.id)
               .filter(Revision.levantamiento_id == lev.id).all())
    for estado_guardado, solicitud_id, estado_e2 in estados:
        estado = estado_guardado
        if solicitud_id is not None:
            estado = {
                "PENDING": "AWAITING_E3", "APPROVED": "APPROVED", "REJECTED": "REJECTED",
            }.get(estado_e2, "BLOCKED")
        if estado == "BLOCKED":
            resumen["bloqueadas"] += 1
        elif estado in ("PENDING", "AWAITING_E3"):
            resumen["por_autorizar"] += 1
        elif estado == "APPROVED":
            resumen["aprobadas"] += 1
        elif estado == "REJECTED":
            resumen["rechazadas"] += 1
        elif estado == "SUPERSEDED":
            resumen["superadas"] += 1
    return {"levantamiento_id": lev.id, "resumen": resumen, "items": items,
            "page": page, "per_page": size, "total": total}
