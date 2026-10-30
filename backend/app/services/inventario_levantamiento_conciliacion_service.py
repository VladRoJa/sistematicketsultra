"""E4: casos verificables, evidencia de resolución y cierre sin efectos V1."""
from uuid import UUID
from sqlalchemy import text as sql_text
from sqlalchemy.exc import IntegrityError
from app.extensions import db
from app.models.inventario_levantamiento import (
    InventarioLevantamientoORM as Lev, InventarioLevantamientoImportacionORM as Imp,
    InventarioLevantamientoReferenciaORM as Ref, InventarioLevantamientoFilaORM as Fila,
)
from app.models.inventario_levantamiento_conciliacion import (
    InventarioLevantamientoResolucionORM as Rev, InventarioLevantamientoCierreORM as Cierre,
)
from app.models.inventario_solicitud_correccion import InventarioSolicitudCorreccionORM as Solicitud
from app.models.inventario_levantamiento_revision import InventarioLevantamientoRevisionORM as RevisionAuto
from app.services.inventario_levantamientos_service import E4Error, parse_uuid


def _levantar(identificador, lock=False):
    q = Lev.query.filter_by(id=identificador)
    lev = (q.with_for_update().first() if lock else q.first())
    if lev is None:
        raise E4Error(404, "LEVANTAMIENTO_DESCONOCIDO", "Levantamiento inexistente")
    return lev


def _version_actual(lev):
    if lev.ultima_importacion_id is None:
        raise E4Error(409, "SIN_ENTREGA", "Primero registra un archivo de levantamiento")
    imp = Imp.query.filter_by(id=lev.ultima_importacion_id, levantamiento_id=lev.id).first()
    if imp is None or imp.resultado == "INVALID":
        raise E4Error(409, "VERSION_NO_VALIDA", "Se requiere una entrega estructuralmente válida")
    return imp


def casos_e4(lev, imp):
    """Casos de resolución por versión, nunca derivados del inventario vivo."""
    refs = {x.inventario_id_original: x for x in Ref.query.filter_by(
        levantamiento_id=lev.id).all()}
    filas = Fila.query.filter_by(importacion_id=imp.id).order_by(Fila.hoja, Fila.fila_excel).all()
    casos = {}
    presentes = set()
    for fila in filas:
        if fila.hoja == "APARATOS":
            if fila.inventario_id_declarado in refs:
                presentes.add(fila.inventario_id_declarado)
                if fila.respuesta == "NO" and not fila.diagnosticos:
                    clave = "NO:" + str(fila.inventario_id_declarado)
                    casos[clave] = {
                        "caso": clave, "tipo": "NO", "inventario_id": fila.inventario_id_declarado,
                        "fila_excel": fila.fila_excel,
                        "codigo": fila.codigo_declarado,
                        "aparato": fila.datos_crudos.get("aparato"),
                        "observacion": fila.datos_crudos.get("observaciones"),
                    }
            elif lev.modalidad == "INICIAL" and fila.inventario_id_declarado is None:
                clave = "INICIAL:" + str(fila.fila_excel)
                casos[clave] = {
                    "caso": clave, "tipo": "INICIAL", "inventario_id": None,
                    "fila_excel": fila.fila_excel, "codigo": fila.codigo_declarado,
                    "aparato": fila.datos_crudos.get("aparato"),
                    "observacion": fila.datos_crudos.get("observaciones"),
                }
        elif fila.hoja == "HALLAZGOS":
            clave = "HALLAZGO:" + str(fila.fila_excel)
            casos[clave] = {
                "caso": clave, "tipo": "HALLAZGO", "inventario_id": None,
                "fila_excel": fila.fila_excel, "codigo": fila.codigo_declarado,
                "aparato": fila.datos_crudos.get("aparato"),
                "observacion": fila.datos_crudos.get("descripcion"),
            }
    for referencia in refs.values():
        codigo = (referencia.codigo_interno_original or "").strip()
        if len(codigo) >= 2 and codigo[:2].isdigit() and codigo[:2] != f"{lev.sucursal_id:02d}":
            clave = "PREFIJO:" + str(referencia.inventario_id_original)
            casos[clave] = {
                "caso": clave, "tipo": "PREFIJO",
                "inventario_id": referencia.inventario_id_original,
                "fila_excel": None, "codigo": codigo,
                "aparato": (referencia.datos_originales or {}).get("aparato"),
                "observacion": "Código del corte con prefijo de otra sucursal",
            }
    return casos


def _ultima_resolucion(imp_id):
    """Eventos append-only: la última resolución para cada caso gobierna el estado."""
    revisiones = Rev.query.filter_by(importacion_id=imp_id).order_by(Rev.id).all()
    return {row.caso: row for row in revisiones}


def _resumen_resolucion(row):
    return {
        "id": row.id, "caso": row.caso, "accion": row.accion,
        "solicitud_id": row.solicitud_id,
        "movimiento_id": row.movimiento_id,
        "inventario_id_resultante": row.inventario_id_resultante,
        "motivo": row.motivo, "actor_usuario_id": row.actor_usuario_id,
        "creado_en_utc": row.creado_en_utc.isoformat() if row.creado_en_utc else None,
    }


def _evidencia_aprobada(lev, caso, row):
    if caso["tipo"] == "NO" and row.accion == "BAJA_PREVIA" and row.movimiento_id:
        salida = db.session.execute(sql_text("""
            SELECT 1 FROM movimientos_inventario m
            JOIN detalle_movimiento d ON d.movimiento_id=m.id
            JOIN inventario_sucursal s
              ON s.inventario_id=d.inventario_id AND s.sucursal_id=m.sucursal_id
            WHERE m.id=:mov AND m.sucursal_id=:sucursal
              AND m.tipo_movimiento='salida' AND m.anulado=false
              AND d.inventario_id=:inventario AND d.cantidad>0 AND s.stock=0
            LIMIT 1
        """), {"mov": row.movimiento_id, "sucursal": lev.sucursal_id,
               "inventario": caso["inventario_id"]}).scalar_one_or_none()
        return salida is not None
    if caso["tipo"] in {"NO", "PREFIJO"}:
        solicitud = db.session.get(Solicitud, row.solicitud_id) if row.solicitud_id else None
        tipo = "NOT_LOCATED" if caso["tipo"] == "NO" else "MASTER_FIELD"
        if not (solicitud and solicitud.estado == "APPROVED"
                and solicitud.tipo == tipo
                and solicitud.sucursal_id == lev.sucursal_id
                and solicitud.inventario_id == caso["inventario_id"]):
            return False
        if caso["tipo"] == "PREFIJO" and solicitud.campo != "codigo_interno":
            return False
        actual = db.session.execute(sql_text("""
            SELECT i.codigo_interno, s.stock
            FROM inventario_general i JOIN inventario_sucursal s
              ON i.id=s.inventario_id
            WHERE i.id=:id AND s.sucursal_id=:sucursal
        """), {"id": caso["inventario_id"], "sucursal": lev.sucursal_id}).first()
        if actual is None:
            return False
        if caso["tipo"] == "NO":
            return actual[1] == 0
        codigo_nuevo = str(actual[0] or "").strip().upper()
        propuesta = solicitud.valor_propuesto
        # El proceso de aprobación E3 es el que escribe/audita el código.
        return (codigo_nuevo.startswith(f"{lev.sucursal_id:02d}")
                and isinstance(propuesta, str)
                and propuesta.strip().upper() == codigo_nuevo)
    if caso["tipo"] in {"HALLAZGO", "INICIAL"}:
        if not row.inventario_id_resultante:
            return False
        codigo_fisico = str(caso["codigo"] or "").strip().upper()
        if not codigo_fisico or codigo_fisico in {"SIN CÓDIGO", "SIN CODIGO", "PENDIENTE", "N/A"}:
            return False
        destino = db.session.execute(sql_text("""
            SELECT i.codigo_interno, i.tipo, s.stock
            FROM inventario_general i JOIN inventario_sucursal s
              ON i.id=s.inventario_id
            WHERE i.id=:id AND s.sucursal_id=:sucursal
        """), {"id": row.inventario_id_resultante, "sucursal": lev.sucursal_id}).first()
        if not destino or (destino[2] or 0) <= 0:
            return False
        if str(destino[0] or "").strip().upper() != codigo_fisico:
            return False
        if str(destino[1] or "").strip().casefold() not in {"aparato", "aparatos"}:
            return False
        # Evitar que una referencia del propio corte se haga pasar por alta.
        if Ref.query.filter_by(levantamiento_id=lev.id,
                               inventario_id_original=row.inventario_id_resultante).first():
            return False
        n = db.session.execute(sql_text("""
            SELECT count(*) FROM inventario_general
            WHERE upper(btrim(codigo_interno))=:codigo
        """), {"codigo": codigo_fisico}).scalar()
        return n == 1
    return False


def _efecto_e3_confirmado(lev, revision, solicitud):
    """La aprobación NO basta: cotejar que E3 aplicó el efecto correcto."""
    if not solicitud or solicitud.estado != "APPROVED":
        return False
    if solicitud.sucursal_id != lev.sucursal_id or solicitud.tipo != revision.tipo:
        return False
    if revision.inventario_id != solicitud.inventario_id:
        return False
    if revision.tipo == "NOT_LOCATED":
        return db.session.execute(sql_text("""
            SELECT 1 FROM inventario_sucursal
            WHERE inventario_id=:id AND sucursal_id=:branch AND stock=0
        """), {"id": revision.inventario_id, "branch": lev.sucursal_id}).scalar_one_or_none() is not None
    if revision.tipo == "MASTER_FIELD":
        if solicitud.campo != "codigo_interno" or revision.campo != "codigo_interno":
            return False
        codigo = db.session.execute(sql_text("""
            SELECT codigo_interno FROM inventario_general WHERE id=:id
        """), {"id": revision.inventario_id}).scalar_one_or_none()
        return (codigo is not None and
                str(codigo).strip().upper() == str(solicitud.valor_propuesto).strip().upper())
    if revision.tipo == "UNREGISTERED_FIND":
        # Solo vale la vinculación formal auditada de E3, nunca un ID escrito
        # por el operador en E4.
        codigo = str(revision.codigo_observado or "").strip().upper()
        if not codigo:
            return False
        evidencia = db.session.execute(sql_text("""
            SELECT 1 FROM inventario_correccion_altas_auditoria a
            JOIN inventario_general i ON i.id=a.inventario_id_resultante
            JOIN inventario_sucursal s
              ON s.inventario_id=i.id AND s.sucursal_id=a.sucursal_id
            WHERE a.solicitud_id=:solicitud AND a.sucursal_id=:branch
              AND a.modalidad='VINCULACION' AND s.stock>0
              AND upper(btrim(i.codigo_interno))=:codigo
            LIMIT 1
        """), {"solicitud": solicitud.id, "branch": lev.sucursal_id,
               "codigo": codigo}).scalar_one_or_none()
        return evidencia is not None
    return False


def tablero_e4(lev_id):
    lev = _levantar(lev_id)
    if not lev.ultima_importacion_id:
        return {"levantamiento_id": lev_id, "estado": lev.estado,
                "importacion_id": None, "casos": [],
                "pendientes_respuesta": [], "bloqueos": ["SIN_ENTREGA"],
                "puede_cerrar": False}
    imp = _version_actual(lev)
    revisiones = RevisionAuto.query.filter_by(levantamiento_id=lev.id).order_by(RevisionAuto.id).all()
    casos = []
    for revision in revisiones:
        if revision.estado == "SUPERSEDED":
            continue
        solicitud = db.session.get(Solicitud, revision.solicitud_e2_id) if revision.solicitud_e2_id else None
        aprobado = _efecto_e3_confirmado(lev, revision, solicitud)
        casos.append({
            "caso": revision.logical_key, "tipo": revision.tipo,
            "inventario_id": revision.inventario_id,
            "codigo": revision.codigo_observado,
            "resuelto": aprobado, "estado_e2": solicitud.estado if solicitud else None,
            "solicitud_e2_id": revision.solicitud_e2_id,
            "motivo_bloqueo": revision.motivo_bloqueo,
        })
    pendientes = (imp.resumen or {}).get("pendientes", [])
    bloqueos = []
    if imp.resultado == "INVALID" or (imp.resumen or {}).get("errores", 0):
        bloqueos.append("ENTREGA_INVALIDA")
    if pendientes:
        bloqueos.append("SIN_REVISAR")
    if any(not x["resuelto"] for x in casos):
        bloqueos.append("REVISIONES_SIN_AUTORIZACION")
    if not (imp.resumen or {}).get("referencias_esperadas", 0) and not casos:
        bloqueos.append("SIN_EVIDENCIA_FISICA")
    return {
        "levantamiento_id": lev_id, "estado": lev.estado,
        "importacion_id": imp.id, "version": imp.version,
        "resultado": imp.resultado, "casos": casos,
        "pendientes_respuesta": pendientes, "bloqueos": bloqueos,
        "puede_cerrar": not bloqueos and lev.estado != "CLOSED",
    }

def registrar_resolucion(lev_id, actor, data):
    if not isinstance(data, dict):
        raise E4Error(400, "PAYLOAD_INVALIDO", "La resolución debe ser un objeto")
    clave = data.get("caso")
    accion = data.get("accion")
    motivo = data.get("motivo")
    key = parse_uuid(data.get("idempotency_key"))
    if not isinstance(clave, str) or len(clave) > 80:
        raise E4Error(400, "CASO_INVALIDO", "Clave de caso inválida")
    if not isinstance(motivo, str) or not 20 <= len(motivo.strip()) <= 2000:
        raise E4Error(400, "MOTIVO_INVALIDO", "Motivo requiere 20 a 2000 caracteres")
    lev = _levantar(lev_id, lock=True)
    if lev.estado == "CLOSED":
        raise E4Error(409, "LEVANTAMIENTO_CERRADO", "Este levantamiento está cerrado")
    imp = _version_actual(lev)
    existente = Rev.query.filter_by(actor_usuario_id=actor, idempotency_key=key).first()
    if existente:
        if existente.levantamiento_id != lev.id or existente.importacion_id != imp.id or (
                existente.caso != clave or existente.accion != accion
                or existente.motivo != motivo.strip()
                or existente.solicitud_id != data.get("solicitud_id")
                or existente.movimiento_id != data.get("movimiento_id")
                or existente.inventario_id_resultante != data.get("inventario_id_resultante")):
            raise E4Error(409, "IDEMPOTENCIA_CONFLICTO", "La llave pertenece a otra resolución")
        return _resumen_resolucion(existente), True
    casos = casos_e4(lev, imp)
    caso = casos.get(clave)
    if not caso:
        raise E4Error(404, "CASO_DESCONOCIDO", "El caso no pertenece a esta entrega")
    movimiento = None
    if caso["tipo"] == "NO" and accion == "BAJA_PREVIA":
        if (type(data.get("movimiento_id")) is not int or data["movimiento_id"] <= 0
                or data.get("solicitud_id") is not None
                or data.get("inventario_id_resultante") is not None):
            raise E4Error(422, "RESOLUCION_INVALIDA", "Se requiere movimiento V1 de baja no anulado")
        movimiento = data["movimiento_id"]
        solicitud_id = destino = None
    elif caso["tipo"] in {"NO", "PREFIJO"}:
        if (accion != "E2_APROBADA" or type(data.get("solicitud_id")) is not int
                or data["solicitud_id"] <= 0 or data.get("movimiento_id") is not None
                or data.get("inventario_id_resultante") is not None):
            raise E4Error(422, "RESOLUCION_INVALIDA", "Se requiere solicitud E2 aprobada de esta referencia")
        solicitud_id = data["solicitud_id"]
        destino = None
    else:
        if accion != "REGISTRADO_OFICIAL" or type(data.get("inventario_id_resultante")) is not int or data["inventario_id_resultante"] <= 0 or data.get("solicitud_id") is not None or data.get("movimiento_id") is not None:
            raise E4Error(422, "RESOLUCION_INVALIDA", "Se requiere referencia oficial vinculada a la sucursal")
        solicitud_id = None
        destino = data["inventario_id_resultante"]
    resolucion = Rev(levantamiento_id=lev.id, importacion_id=imp.id, caso=clave,
                     accion=accion, solicitud_id=solicitud_id, movimiento_id=movimiento,
                     inventario_id_resultante=destino, motivo=motivo.strip(),
                     actor_usuario_id=actor, idempotency_key=key)
    if not _evidencia_aprobada(lev, caso, resolucion):
        raise E4Error(409, "EVIDENCIA_NO_CONFIRMADA",
                      "La autorización E2/E3 o referencia oficial no coincide con el caso")
    db.session.add(resolucion)
    lev.estado = "IN_REVIEW"
    db.session.commit()
    return _resumen_resolucion(resolucion), False


def cerrar_e4(lev_id, actor, data):
    if not isinstance(data, dict):
        raise E4Error(400, "PAYLOAD_INVALIDO", "Solicitud de cierre inválida")
    motivo = data.get("motivo")
    key = parse_uuid(data.get("idempotency_key"))
    if not isinstance(motivo, str) or not 20 <= len(motivo.strip()) <= 2000:
        raise E4Error(400, "MOTIVO_INVALIDO", "El motivo requiere 20 a 2000 caracteres")
    lev = _levantar(lev_id, lock=True)
    anterior = Cierre.query.filter_by(levantamiento_id=lev.id).first()
    if anterior:
        if anterior.actor_usuario_id == actor and anterior.idempotency_key == key and anterior.motivo == motivo.strip():
            return {"cierre_id": anterior.id, "estado": "CLOSED"}, True
        raise E4Error(409, "YA_CERRADO", "El levantamiento ya tiene cierre oficial")
    tablero = tablero_e4(lev.id)
    if not tablero["puede_cerrar"]:
        raise E4Error(409, "CIERRE_BLOQUEADO",
                      "No se puede cerrar: " + ", ".join(tablero["bloqueos"]))
    imp = _version_actual(lev)
    cierre = Cierre(levantamiento_id=lev.id, importacion_id=imp.id,
                    actor_usuario_id=actor, motivo=motivo.strip(),
                    idempotency_key=key, resumen_cierre={
                        "version": imp.version, "file_sha256": imp.file_sha256,
                        "referencias": (imp.resumen or {}).get("referencias_esperadas", 0),
                        "si": (imp.resumen or {}).get("si", 0),
                        "no": (imp.resumen or {}).get("no", 0),
                        "hallazgos": (imp.resumen or {}).get("hallazgos", 0),
                        "casos_resueltos": len(tablero["casos"]),
                    })
    db.session.add(cierre)
    lev.estado = "CLOSED"
    db.session.commit()
    return {"cierre_id": cierre.id, "estado": lev.estado}, False
