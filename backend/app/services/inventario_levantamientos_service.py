"""E4 Bloque 1: cortes separados de V1 y recepción de evidencia sin efectos oficiales."""
from datetime import date, datetime, timezone
from pathlib import Path
from hashlib import sha256
from uuid import UUID
from zoneinfo import ZoneInfo
import os

from flask import current_app
from sqlalchemy import text as sql_text
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.inventario_levantamiento import (
    InventarioLevantamientoORM as Lev,
    InventarioLevantamientoReferenciaORM as Ref,
    InventarioLevantamientoImportacionORM as Imp,
    InventarioLevantamientoFilaORM as Fila,
)
from app.services.inventario_levantamiento_excel_parser import (
    ArchivoE4Error, parse_historical_csv, parse_xlsx_v01, MAX_XLSX_BYTES,
)


class E4Error(ValueError):
    def __init__(self, status, code, message):
        self.status = status
        self.code = code
        super().__init__(message)


def parse_uuid(raw):
    try:
        key = UUID(str(raw))
        if key.int == 0:
            raise ValueError()
        return key
    except (TypeError, ValueError, AttributeError):
        raise E4Error(400, "IDEMPOTENCY_KEY_INVALIDA", "Se requiere llave UUID de idempotencia válida")


def parse_date(raw):
    if not raw:
        return None
    try:
        value = date.fromisoformat(str(raw))
    except ValueError:
        raise E4Error(400, "FECHA_INVALIDA", "La fecha del corte debe ser AAAA-MM-DD")
    if value > datetime.now(ZoneInfo("America/Tijuana")).date():
        raise E4Error(400, "FECHA_FUTURA", "La fecha del corte no puede ser futura")
    return value


def e4_private_root():
    root = os.environ.get("E4_UPLOAD_DIR")
    if not root:
        root = str(Path(__file__).resolve().parents[2] / "runtime" / "inventario-e4")
    return Path(root).expanduser().resolve()


def _private_path(key):
    if not isinstance(key, str) or not key.startswith("levantamientos/") or ".." in Path(key).parts:
        raise E4Error(500, "STORAGE_KEY_INVALIDA", "Ruta de evidencia inválida")
    target = (e4_private_root() / key).resolve()
    if not target.is_relative_to(e4_private_root()):
        raise E4Error(500, "STORAGE_KEY_INVALIDA", "Ruta fuera del almacenamiento privado")
    return target


def _write_original(key, raw):
    target = _private_path(key)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as out:
        out.write(raw)
        out.flush()
        os.fsync(out.fileno())
    return target


def ensure_branch(sucursal_id):
    exists = db.session.execute(
        sql_text("SELECT 1 FROM sucursales WHERE sucursal_id=:branch"),
        {"branch": sucursal_id},
    ).scalar_one_or_none()
    if exists is None:
        raise E4Error(404, "SUCURSAL_DESCONOCIDA", "La sucursal no existe")


def _current_branch(sucursal_id):
    """Consulta ACTUAL, nunca se presenta como la base histórica distribuida."""
    rows = db.session.execute(sql_text("""
        SELECT i.id, i.codigo_interno, i.tipo, i.nombre, i.marca,
               i.categoria, s.stock
        FROM inventario_sucursal s JOIN inventario_general i
             ON i.id = s.inventario_id
        WHERE s.sucursal_id=:branch AND s.stock > 0
          AND lower(btrim(i.tipo)) IN ('aparato','aparatos')
        ORDER BY i.id
    """), {"branch": sucursal_id}).mappings().all()
    return [dict(row) for row in rows]


def _references_from_live(sucursal_id):
    items = []
    for row in _current_branch(sucursal_id):
        items.append({
            "inventario_id_original": row["id"],
            "codigo_interno_original": row["codigo_interno"],
            "stock_original": row["stock"],
            "datos_originales": {**row, "corte": "DB_ACTUAL"},
        })
    return items


def _refdict(row):
    return {
        "inventario_id_original": row.inventario_id_original,
        "codigo_interno_original": row.codigo_interno_original,
        "stock_original": row.stock_original,
        "datos_originales": row.datos_originales,
    }


def _serialize_lev(row):
    return {
        "id": row.id, "cycle_key": str(row.cycle_key),
        "sucursal_id": row.sucursal_id, "modalidad": row.modalidad,
        "origen_corte": row.origen_corte, "estado": row.estado,
        "responsable": row.responsable,
        "fecha_corte_local": row.fecha_corte_local.isoformat() if row.fecha_corte_local else None,
        "baseline_sha256": row.baseline_sha256,
        "baseline_capturado_en_utc": row.baseline_capturado_en_utc.isoformat() if row.baseline_capturado_en_utc else None,
        "baseline_resumen": row.baseline_resumen,
        "ultima_importacion_id": row.ultima_importacion_id,
    }


def _serialize_import(row):
    return {
        "id": row.id, "levantamiento_id": row.levantamiento_id,
        "version": row.version, "resultado": row.resultado,
        "file_sha256": row.file_sha256, "filename": row.original_filename,
        "cargado_por_usuario_id": row.cargado_por_usuario_id,
        "cargado_en_utc": row.cargado_en_utc.isoformat() if row.cargado_en_utc else None,
        "control": row.control, "resumen": row.resumen,
        "diagnosticos": row.diagnosticos,
    }


def crear_levantamiento(actor_id, sucursal_id, origen, cycle_key, fecha_raw=None, responsable=None, baseline_csv=None):
    ensure_branch(sucursal_id)
    if origen not in {"CSV_HISTORICO", "DB_ACTUAL", "INICIAL"}:
        raise E4Error(400, "ORIGEN_INVALIDO", "Origen de corte no permitido")
    existing = Lev.query.filter_by(cycle_key=cycle_key).first()
    if existing:
        if existing.sucursal_id != sucursal_id or existing.origen_corte != origen:
            raise E4Error(409, "CYCLE_KEY_CONFLICT", "La llave ya pertenece a otro corte")
        return _serialize_lev(existing), True
    fecha = parse_date(fecha_raw)
    if origen == "CSV_HISTORICO":
        if not baseline_csv:
            raise E4Error(400, "BASELINE_REQUERIDO", "Se requiere CSV histórico de distribución")
        try:
            references, excluded = parse_historical_csv(baseline_csv, sucursal_id)
        except ArchivoE4Error as exc:
            raise E4Error(422, "CSV_HISTORICO_INVALIDO", str(exc)) from exc
        modalidad = "VERIFICACION"
        digest = sha256(baseline_csv).hexdigest()
    elif origen == "DB_ACTUAL":
        if baseline_csv is not None:
            raise E4Error(400, "BASELINE_INESPERADO", "No enviar CSV para un corte actual")
        references = _references_from_live(sucursal_id)
        if not references:
            raise E4Error(409, "UNIVERSO_VACIO", "No hay APARATOS actuales; use modalidad inicial")
        excluded = []
        modalidad = "VERIFICACION"
        digest = None
    else:
        if baseline_csv is not None:
            raise E4Error(400, "BASELINE_INESPERADO", "Un levantamiento inicial no recibe CSV oficial")
        if _current_branch(sucursal_id):
            raise E4Error(409, "REFERENCIAS_EXISTENTES", "La sucursal tiene APARATOS oficiales vigentes")
        references, excluded, modalidad, digest = [], [], "INICIAL", None

    row = Lev(cycle_key=cycle_key, sucursal_id=sucursal_id,
              origen_corte=origen, modalidad=modalidad,
              responsable=(responsable or "").strip()[:200] or None,
              fecha_corte_local=fecha, creado_por_usuario_id=actor_id,
              baseline_sha256=digest, estado="IN_PROGRESS",
              baseline_resumen={"referencias_esperadas": len(references),
                                "excluidas_stock_cero": len(excluded),
                                "fuente": origen})
    stored = None
    try:
        db.session.add(row)
        db.session.flush()
        if baseline_csv is not None:
            key = f"levantamientos/{row.id}/baseline/{digest}.csv"
            stored = _write_original(key, baseline_csv)
            row.baseline_storage_key = key
        for data in references:
            db.session.add(Ref(levantamiento_id=row.id, **data))
        db.session.commit()
    except (OSError, IntegrityError):
        db.session.rollback()
        if stored:
            stored.unlink(missing_ok=True)
        raise
    return _serialize_lev(row), False


def _official_drift(lev, refs):
    """La deriva NO reescribe el corte ni vuelve falso el SI/NO histórico."""
    if not refs:
        return []
    now_rows = {row["id"]: row for row in _current_branch(lev.sucursal_id)}
    warnings = []
    for ref in refs:
        now = now_rows.get(ref["inventario_id_original"])
        if now is None:
            warnings.append({"severidad": "AVISO", "codigo": "SIN_REFERENCIA_ACTUAL",
                             "inventario_id": ref["inventario_id_original"]})
        else:
            if (now["codigo_interno"] or "").strip().casefold() != (ref["codigo_interno_original"] or "").strip().casefold():
                warnings.append({"severidad": "AVISO", "codigo": "CODIGO_CAMBIO_POSTERIOR",
                                 "inventario_id": ref["inventario_id_original"],
                                 "codigo_del_corte": ref["codigo_interno_original"],
                                 "codigo_actual": now["codigo_interno"]})
            if now["stock"] != ref["stock_original"]:
                warnings.append({"severidad": "AVISO", "codigo": "STOCK_CAMBIO_POSTERIOR",
                                 "inventario_id": ref["inventario_id_original"],
                                 "stock_del_corte": ref["stock_original"], "stock_actual": now["stock"]})
    return warnings


def recibir_excel(actor_id, levantamiento_id, key, filename, raw):
    if not filename or not filename.lower().endswith(".xlsx"):
        raise E4Error(400, "EXTENSION_INVALIDA", "Se requiere archivo XLSX")
    if not raw or len(raw) > MAX_XLSX_BYTES:
        raise E4Error(413, "TAMANO_INVALIDO", "XLSX vacío o mayor a 10 MB")
    digest = sha256(raw).hexdigest()
    # El bloqueo del padre serializa número de versión y reintentos concurrentes.
    lev = Lev.query.filter_by(id=levantamiento_id).with_for_update().first()
    if lev is None:
        raise E4Error(404, "LEVANTAMIENTO_DESCONOCIDO", "Levantamiento inexistente")
    reused = Imp.query.filter_by(levantamiento_id=lev.id, idempotency_key=key).first()
    if reused:
        if reused.file_sha256 != digest:
            raise E4Error(409, "IDEMPOTENCY_CONFLICT", "Llave reutilizada con contenido diferente")
        return _serialize_import(reused), True
    repeated = Imp.query.filter_by(levantamiento_id=lev.id, file_sha256=digest).first()
    if repeated:
        return _serialize_import(repeated), True
    refs = [_refdict(x) for x in Ref.query.filter_by(levantamiento_id=lev.id).order_by(Ref.inventario_id_original).all()]
    try:
        parsed = parse_xlsx_v01(raw, lev.sucursal_id, refs, lev.modalidad)
    except ArchivoE4Error as exc:
        raise E4Error(422, "ARCHIVO_ESTRUCTURAL_INVALIDO", str(exc)) from exc

    drift = _official_drift(lev, refs)
    parsed["diagnosticos"].extend(drift)
    parsed["resumen"]["avisos"] += len(drift)
    version = db.session.query(db.func.coalesce(db.func.max(Imp.version), 0)).filter(
        Imp.levantamiento_id == lev.id).scalar() + 1
    path = f"levantamientos/{lev.id}/versiones/{digest}.xlsx"
    saved = None
    try:
        saved = _write_original(path, raw)
        imp = Imp(levantamiento_id=lev.id, version=version,
                  idempotency_key=key, file_sha256=digest,
                  original_filename=Path(filename).name[:255],
                  storage_key=path, cargado_por_usuario_id=actor_id,
                  resultado=parsed["resultado"], control=parsed["control"],
                  resumen=parsed["resumen"], diagnosticos=parsed["diagnosticos"])
        db.session.add(imp)
        db.session.flush()
        db.session.add_all([Fila(importacion_id=imp.id, **row) for row in parsed["filas"]])
        if parsed["resultado"] != "INVALID":
            lev.ultima_importacion_id = imp.id
        db.session.commit()
    except (OSError, IntegrityError):
        db.session.rollback()
        if saved:
            saved.unlink(missing_ok=True)
        raise
    return _serialize_import(imp), False


def detalle_levantamiento(lev_id):
    lev = db.session.get(Lev, lev_id)
    if lev is None:
        raise E4Error(404, "LEVANTAMIENTO_DESCONOCIDO", "Levantamiento inexistente")
    imports = Imp.query.filter_by(levantamiento_id=lev.id).order_by(Imp.version.desc()).all()
    return {"levantamiento": _serialize_lev(lev),
            "versiones": [_serialize_import(item) for item in imports]}


def detalle_importacion(lev_id, import_id):
    row = Imp.query.filter_by(id=import_id, levantamiento_id=lev_id).first()
    if row is None:
        raise E4Error(404, "IMPORTACION_DESCONOCIDA", "Versión fuera del levantamiento")
    return {"importacion": _serialize_import(row),
            "filas": [{"hoja": r.hoja, "fila_excel": r.fila_excel,
                       "inventario_id_declarado": r.inventario_id_declarado,
                       "codigo_declarado": r.codigo_declarado, "respuesta": r.respuesta,
                       "datos_crudos": r.datos_crudos, "diagnosticos": r.diagnosticos}
                      for r in Fila.query.filter_by(importacion_id=row.id).order_by(Fila.hoja, Fila.fila_excel).all()]}
