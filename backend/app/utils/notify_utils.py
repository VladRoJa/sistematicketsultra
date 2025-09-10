# app/utils/notify_utils.py
from datetime import datetime
import pytz
from dateutil import parser  # 👈 nuevo

TZ = pytz.timezone("America/Tijuana")

def _as_dt(x):
    if not x: return None
    if isinstance(x, str):
        try: return parser.isoparse(x)
        except Exception: return None
    return x

def fmt_dt(dt):
    dt = _as_dt(dt)
    if not dt: return "—"
    try:
        if getattr(dt, "tzinfo", None):
            return dt.astimezone(TZ).strftime("%d/%m/%Y %I:%M %p")
        return dt.strftime("%d/%m/%Y %I:%M %p")
    except Exception:
        return "—"

def fmt_d(d):
    d = _as_dt(d)
    if not d: return "—"
    try:
        if getattr(d, "tzinfo", None):
            return d.astimezone(TZ).strftime("%d/%m/%y")
        return d.strftime("%d/%m/%y")
    except Exception:
        return "—"


def render_ticket_html(t: dict) -> str:
    # t: dict de ticket (t.to_dict()) con inventario anidado y lista historial_fechas
    aparato = (t.get("inventario") or {}).get("nombre") or t.get("equipo") or "—"
    codigo  = (t.get("inventario") or {}).get("codigo_interno")
    estado  = (t.get("estado") or "").title()

    hist_rows = ""
    for item in t.get("historial_fechas") or []:
        hist_rows += f"""
        <tr>
          <td>{fmt_d(item.get("fecha"))}</td>
          <td>{item.get("cambiadoPor") or "—"}</td>
          <td>{fmt_dt(item.get("fechaCambio"))}</td>
          <td>{(item.get("motivo") or "Sin motivo")}</td>
        </tr>"""

    cod = f" <span style='color:#0073c2'>({codigo})</span>" if codigo else ""

    return f"""
<!doctype html>
<html>
  <body style="font-family:Arial,Helvetica,sans-serif; color:#222;">
    <div style="max-width:720px;margin:auto;border:1px solid #e5e7eb;border-radius:12px;padding:16px;">
      <h2 style="margin:0 0 6px 0;">🗓 Historial de Fecha Solución</h2>
      <hr style="border:none;border-top:1px solid #e5e7eb;margin:10px 0;">
      <p><b>ID:</b> {t.get("id")}</p>
      <p><b>Aparato:</b> {aparato}{cod}</p>
      <p><b>Descripción:</b> {t.get("descripcion")}</p>
      <p><b>Estado:</b> {estado}</p>
      {"<p><b>Refacción:</b> " + (t.get("descripcion_refaccion") or "") + "</p>" if t.get("necesita_refaccion") else ""}
      <p><b>Fecha Creación:</b> {fmt_dt(t.get("fecha_creacion"))}</p>
      <p><b>En Progreso:</b> {fmt_dt(t.get("fecha_en_progreso"))}</p>
      <p><b>Finalizado:</b> {fmt_dt(t.get("fecha_finalizado"))}</p>

      <hr style="border:none;border-top:1px solid #e5e7eb;margin:12px 0;">
      <table style="width:100%;border-collapse:collapse;font-size:14px;">
        <thead>
          <tr style="background:#f3f4f6;">
            <th style="text-align:left;padding:8px;border:1px solid #e5e7eb;">Fecha Solución</th>
            <th style="text-align:left;padding:8px;border:1px solid #e5e7eb;">Usuario</th>
            <th style="text-align:left;padding:8px;border:1px solid #e5e7eb;">Fecha de Cambio</th>
            <th style="text-align:left;padding:8px;border:1px solid #e5e7eb;">Motivo</th>
          </tr>
        </thead>
        <tbody>
          {hist_rows or '<tr><td colspan="4" style="padding:8px;border:1px solid #e5e7eb;">Sin cambios</td></tr>'}
        </tbody>
      </table>
    </div>
  </body>
</html>
"""
def render_ticket_whatsapp_text(t: dict) -> str:
    aparato = (t.get("inventario") or {}).get("nombre") or t.get("equipo") or "—"
    codigo  = (t.get("inventario") or {}).get("codigo_interno")
    estado  = (t.get("estado") or "").title()
    cod     = f" ({codigo})" if codigo else ""

    lines = [
        f"🗓 *Ticket #{t.get('id')}*",
        f"*Aparato:* {aparato}{cod}",
        f"*Descripción:* {t.get('descripcion')}",
        f"*Estado:* {estado}",
        f"*Creación:* {fmt_dt(t.get('fecha_creacion'))}",
        f"*En Progreso:* {fmt_dt(t.get('fecha_en_progreso'))}",
        f"*Finalizado:* {fmt_dt(t.get('fecha_finalizado'))}",
    ]
    if t.get("necesita_refaccion"):
        lines.append(f"*Refacción:* {t.get('descripcion_refaccion') or 'Sí'}")

    lines.append("\n*Historial:*")
    hist = t.get("historial_fechas") or []
    if not hist:
        lines.append("— Sin cambios —")
    else:
        for item in hist[:10]:  # por no alargar demasiado
            lines.append(f"- {fmt_d(item.get('fecha'))} · {item.get('cambiadoPor') or '—'} · {fmt_dt(item.get('fechaCambio'))} · {item.get('motivo') or 'Sin motivo'}")

    return "\n".join(lines)
