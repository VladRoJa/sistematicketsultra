"""Exportaciones operativas del expediente E4; solo lectura, sin alterar corte.

Dos XLSX distintos: decisiones/cambios con columna de reetiquetado manual,
e inventario oficial vigente de la sucursal (incluidas existencias cero).
"""
from io import BytesIO
from datetime import datetime
from zoneinfo import ZoneInfo

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.worksheet.datavalidation import DataValidation
from sqlalchemy import text

from app.extensions import db
from app.models.inventario_levantamiento import (
    InventarioLevantamientoORM as Lev,
    InventarioLevantamientoImportacionORM as Imp,
)
from app.models.inventario_levantamiento_revision import (
    InventarioLevantamientoRevisionORM as Revision,
    InventarioLevantamientoRevisionEvidenciaORM as Evidencia,
)
from app.models.inventario_solicitud_correccion import InventarioSolicitudCorreccionORM as Solicitud
from app.services.inventario_levantamientos_service import E4Error


def _cell(value):
    """Los valores de usuario nunca deben ejecutarse como fórmulas Excel."""
    if value is None:
        return ""
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def _sheet(book, name, headings, data, *, confirmacion=False):
    ws = book.create_sheet(name)
    ws.append(headings)
    for item in data:
        ws.append([_cell(v) for v in item])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{ws.cell(max(1, ws.max_row), len(headings)).coordinate}"
    for header in ws[1]:
        header.fill = PatternFill("solid", fgColor="21486E")
        header.font = Font(color="FFFFFF", bold=True)
        header.alignment = Alignment(wrap_text=True)
    for idx, heading in enumerate(headings, 1):
        column = ws.cell(1, idx).column_letter
        width = max(14, min(42, len(heading) + 5))
        ws.column_dimensions[column].width = width
    if confirmacion and ws.max_row > 1:
        col = ws.cell(1, len(headings)).column_letter
        validation = DataValidation(type="list", formula1='"SI,NO"', allow_blank=True)
        validation.error = "Seleccionar SI o NO"
        validation.errorTitle = "Confirmación de etiqueta"
        validation.showErrorMessage = True
        ws.add_data_validation(validation)
        validation.add(f"{col}2:{col}{ws.max_row}")
    return ws


def _changes(lev):
    revisions = (Revision.query.filter_by(levantamiento_id=lev.id)
                 .order_by(Revision.id).all())
    sol_ids = [r.solicitud_e2_id for r in revisions if r.solicitud_e2_id]
    requests = {
        item.id: item for item in
        Solicitud.query.filter(Solicitud.id.in_(sol_ids)).all()
    } if sol_ids else {}
    decisions = {}
    if sol_ids:
        decisions = {
            item["solicitud_id"]: item for item in db.session.execute(text("""
                SELECT solicitud_id, actor_usuario_id, decidido_en_utc, motivo_decision
                FROM inventario_correccion_decisiones
                WHERE solicitud_id IN :ids
            """).bindparams(__import__("sqlalchemy").bindparam("ids", expanding=True)),
            {"ids": sol_ids}).mappings().all()
        }
    original_codes = {}
    for r in revisions:
        history = (Evidencia.query.filter_by(revision_id=r.id)
                   .order_by(Evidencia.id).all())
        for entry in history:
            event = entry.valor_observado or {}
            if event.get("evento") == "CORRECCION_CODIGO_HALLAZGO":
                original_codes[r.id] = event.get("codigo_anterior")

    rows = []
    for r in revisions:
        if r.estado == "SUPERSEDED" and not r.solicitud_e2_id:
            continue
        s = requests.get(r.solicitud_e2_id)
        state = s.estado if s else r.estado
        resolved_id = r.inventario_id
        effect_code = ""
        if r.tipo == "UNREGISTERED_FIND" and s and s.estado == "APPROVED":
            alta = db.session.execute(text("""
                SELECT inventario_id_resultante FROM inventario_correccion_altas_auditoria
                WHERE solicitud_id=:id
            """), {"id": s.id}).scalar_one_or_none()
            resolved_id = alta
        master = (db.session.execute(text("""
            SELECT id, nombre, codigo_interno FROM inventario_general WHERE id=:id
        """), {"id": resolved_id}).mappings().first() if resolved_id else None)
        code = master["codigo_interno"] if master else ""
        current_stock = (db.session.execute(text("""
            SELECT stock FROM inventario_sucursal
            WHERE inventario_id=:id AND sucursal_id=:branch
        """), {"id": resolved_id, "branch": lev.sucursal_id}).scalar_one_or_none()
                         if resolved_id else None)
        old_code = original_codes.get(r.id, r.codigo_observado or "")
        if r.tipo == "MASTER_FIELD":
            effect_code = str(s.valor_propuesto or "") if s else ""
            action = "CAMBIAR_ETIQUETA"
        elif r.tipo == "NOT_LOCATED":
            action = "BAJA_EXISTENCIA"
        elif r.tipo == "UNREGISTERED_FIND":
            effect_code = r.codigo_observado or ""
            action = ("ETIQUETAR_ALTA" if old_code != effect_code
                      else "VERIFICAR_ETIQUETA_ALTA")
        else:
            action = "REVISAR_IDENTIDAD"
        valid_effect = (
            state == "APPROVED"
            and (
                (r.tipo == "MASTER_FIELD" and code == effect_code)
                or (r.tipo == "UNREGISTERED_FIND"
                    and resolved_id is not None and code == effect_code and
                    current_stock is not None and current_stock > 0)
                or (r.tipo == "NOT_LOCATED" and current_stock == 0)
            )
        )
        stage = "AUTORIZADO" if valid_effect else "PENDIENTE"
        observed = r.ultimo_valor or {}
        name = (master["nombre"] if master else str(observed.get("aparato") or ""))
        approved_by = decisions.get(r.solicitud_e2_id)
        rows.append([
            lev.sucursal_id, lev.id, r.id, r.solicitud_e2_id or "",
            resolved_id or "", name, r.tipo, action, old_code,
            effect_code, code, current_stock, stage,
            approved_by["actor_usuario_id"] if approved_by else "",
            (approved_by["decidido_en_utc"].isoformat() if approved_by else ""),
            "NO APLICAR HASTA AUTORIZAR" if stage != "AUTORIZADO"
            else ("SIN REETIQUETADO" if action == "BAJA_EXISTENCIA"
                  else "VERIFICAR/COLOCAR ETIQUETA EN PISO"),
            "",
        ])
    return rows


def generar_reporte_e4(levantamiento_id, tipo):
    if tipo not in {"cambios", "existencias"}:
        raise E4Error(404, "REPORTE_DESCONOCIDO", "Reporte no disponible")
    lev = db.session.get(Lev, levantamiento_id)
    if not lev:
        raise E4Error(404, "LEVANTAMIENTO_DESCONOCIDO", "Levantamiento inexistente")
    imp = db.session.get(Imp, lev.ultima_importacion_id) if lev.ultima_importacion_id else None
    if not imp:
        raise E4Error(409, "SIN_ENTREGA", "Primero recibe un inventario para este levantamiento")

    book = Workbook()
    book.remove(book.active)
    generated = datetime.now(ZoneInfo("America/Tijuana")).strftime("%Y-%m-%d %H:%M")
    _sheet(book, "CONTROL", ["Campo", "Valor"], [
        ["Sucursal ID", lev.sucursal_id],
        ["Levantamiento", lev.id],
        ["Versión del Excel recibido", imp.version],
        ["Fecha de corte físico", str(lev.fecha_corte_local or "")],
        ["Fecha de generación local", generated],
        ["Estado E4", lev.estado],
        ["Aviso", "No considera autorizado ningún cambio PENDIENTE."],
        ["Etiquetado", "La última columna es para verificación física manual; llenar el Excel no actualiza Suite."],
    ])
    if tipo == "cambios":
        _sheet(book, "CAMBIOS_Y_ETIQUETAS", [
            "Sucursal", "Corte E4", "Revisión E4", "Solicitud E2",
            "Inventario oficial ID", "Aparato", "Tipo de revisión", "Acción",
            "Código observado en corte/Excel", "Código propuesto/autorizado",
            "Código oficial actual", "Existencia oficial actual", "Estado de decisión",
            "Autorizó E3 (usuario)", "Fecha decisión E3 UTC",
            "Instrucción para sucursal", "Etiqueta verificada físicamente (SI/NO)"
        ], _changes(lev), confirmacion=True)
    else:
        rows = db.session.execute(text("""
            SELECT i.id, i.codigo_interno, i.nombre, i.marca, i.categoria,
                   s.stock
            FROM inventario_general i JOIN inventario_sucursal s ON s.inventario_id=i.id
            WHERE s.sucursal_id=:branch
            ORDER BY i.codigo_interno, i.id
        """), {"branch": lev.sucursal_id}).mappings().all()
        _sheet(book, "EXISTENCIAS_OFICIALES", [
            "Sucursal", "Inventario ID", "Código interno", "Aparato",
            "Marca", "Categoría", "Existencia oficial", "Estado existencia"
        ], [
            [lev.sucursal_id, row["id"], row["codigo_interno"], row["nombre"],
             row["marca"], row["categoria"], row["stock"],
             "SIN EXISTENCIA" if row["stock"] == 0 else "CON EXISTENCIA"]
            for row in rows
        ])
    output = BytesIO()
    book.save(output)
    return output.getvalue(), f"E4_sucursal_{lev.sucursal_id}_corte_{lev.id}_{tipo}.xlsx"
