#   backend\app\track_alerts\services\track_alert_region_email_renderer_service.py


from __future__ import annotations

from decimal import Decimal
from typing import Any
import os

from app.track_alerts.services.track_alert_region_rules_service import (
    TrackRegionRankingItem,
)


def render_regional_executive_email(
    *,
    track_date: str,
    income_compliance_ranking: list[TrackRegionRankingItem],
    income_ranking: list[TrackRegionRankingItem],
    new_clients_ranking: list[TrackRegionRankingItem],
    generation_mode: str = "manual_preview",
) -> dict[str, Any]:
    subject = f"Track Intelligence | Ranking Regional | {track_date}"

    html = f"""
    <html>
        <body
            style="
                font-family: Arial, sans-serif;
                background-color: #f5f5f5;
                padding: 24px;
            "
        >
            <div
                style="
                    max-width: 980px;
                    margin: auto;
                    background: white;
                    padding: 32px;
                    border-radius: 12px;
                "
            >
                <h1 style="margin-top: 0;">
                    🏆 Track Intelligence Regional
                </h1>

                <p style="font-size: 14px; color: #444;">
                    Resumen regional automático correspondiente al día:
                    <strong>{track_date}</strong>
                </p>

                {_render_executive_summary(
                    income_compliance_ranking=income_compliance_ranking,
                    income_ranking=income_ranking,
                    new_clients_ranking=new_clients_ranking,
                )}
                                
                {_render_business_rules_block()}

                {_render_suite_detail_cta(
                    track_date=track_date,
                    generation_mode=generation_mode,
                )}

                {_render_region_table(
                    title="Cumplimiento contra meta de ingreso",
                    subtitle="Ranking principal recomendado para comparar regiones de distinto tamaño.",
                    items=income_compliance_ranking,
                    metric_type="compliance",
                )}

                {_render_region_table(
                    title="Ingreso real acumulado",
                    subtitle="Ranking por volumen total acumulado del mes.",
                    items=income_ranking,
                    metric_type="income",
                )}

                {_render_region_table(
                    title="Clientes nuevos acumulados",
                    subtitle="Ranking por captación total acumulada del mes.",
                    items=new_clients_ranking,
                    metric_type="new_clients",
                )}

                <hr style="margin-top: 40px;" />

                <p style="font-size: 12px; color: #777;">
                    Generado automáticamente por Suite Ultra Track Intelligence.
                </p>
            </div>
        </body>
    </html>
    """

    return {
        "subject": subject,
        "html": html,
        "total_regions": len(income_compliance_ranking),
    }


def _render_executive_summary(
    *,
    income_compliance_ranking: list[TrackRegionRankingItem],
    income_ranking: list[TrackRegionRankingItem],
    new_clients_ranking: list[TrackRegionRankingItem],
) -> str:
    compliance_leader = income_compliance_ranking[0] if income_compliance_ranking else None
    income_leader = income_ranking[0] if income_ranking else None
    clients_leader = new_clients_ranking[0] if new_clients_ranking else None
    compliance_risk = income_compliance_ranking[-1] if income_compliance_ranking else None

    return f"""
    <div
        style="
            border: 1px solid #e5e5e5;
            background-color: #fafafa;
            border-radius: 10px;
            padding: 16px;
            margin: 24px 0 28px 0;
        "
    >
        <h2 style="font-size: 18px; margin-top: 0;">
            Lectura ejecutiva
        </h2>

        <ul style="font-size: 14px; line-height: 1.6; margin-bottom: 0;">
            <li>
                Mejor cumplimiento:
                <strong>{_safe_region_label(compliance_leader)}</strong>
                con <strong>{_format_pct(_safe_compliance(compliance_leader))}</strong>.
            </li>
            <li>
                Mayor volumen de ingreso:
                <strong>{_safe_region_label(income_leader)}</strong>
                con <strong>{_format_money(_safe_income(income_leader))}</strong>.
            </li>
            <li>
                Mayor captación de clientes nuevos:
                <strong>{_safe_region_label(clients_leader)}</strong>
                con <strong>{_safe_new_clients(clients_leader)}</strong>.
            </li>
            <li>
                Región con menor cumplimiento:
                <strong>{_safe_region_label(compliance_risk)}</strong>
                con <strong>{_format_pct(_safe_compliance(compliance_risk))}</strong>.
            </li>
        </ul>
    </div>
    """


def _render_region_table(
    *,
    title: str,
    subtitle: str,
    items: list[TrackRegionRankingItem],
    metric_type: str,
) -> str:
    rows = "".join(
        _render_region_row(
            item=item,
            metric_type=metric_type,
        )
        for item in items
    )

    return f"""
    <div style="margin-bottom: 34px;">
        <h2 style="font-size: 18px; margin-bottom: 4px;">
            {title}
        </h2>

        <p style="font-size: 13px; color: #666; margin-top: 0;">
            {subtitle}
        </p>

        <table
            width="100%"
            cellpadding="0"
            cellspacing="0"
            style="
                border-collapse: collapse;
                font-size: 13px;
            "
        >
            <thead>
                <tr style="background-color: #222; color: white;">
                    <th align="left" style="padding: 10px;">#</th>
                    <th align="left" style="padding: 10px;">Región</th>
                    <th align="right" style="padding: 10px;">Indicador</th>
                    <th align="right" style="padding: 10px;">Ingreso</th>
                    <th align="right" style="padding: 10px;">Meta</th>
                    <th align="right" style="padding: 10px;">Clubes</th>
                </tr>
            </thead>

            <tbody>
                {rows}
            </tbody>
        </table>
    </div>
    """


def _render_region_row(
    *,
    item: TrackRegionRankingItem,
    metric_type: str,
) -> str:
    indicator = _get_indicator_value(
        item=item,
        metric_type=metric_type,
    )

    return f"""
    <tr style="border-bottom: 1px solid #e5e5e5;">
        <td style="padding: 10px;">
            <strong>{item.ranking_position}</strong>
        </td>

        <td style="padding: 10px;">
            {item.region_label}
        </td>

        <td align="right" style="padding: 10px;">
            <strong>{indicator}</strong>
        </td>

        <td align="right" style="padding: 10px;">
            {_format_money(item.ingreso_real_total_mtd)}
        </td>

        <td align="right" style="padding: 10px;">
            {_format_money(item.meta_faycgo_mes)}
        </td>

        <td align="right" style="padding: 10px;">
            {item.total_branches}
        </td>
    </tr>
    """


def _get_indicator_value(
    *,
    item: TrackRegionRankingItem,
    metric_type: str,
) -> str:
    if metric_type == "compliance":
        return _format_pct(item.cumplimiento_ingreso_pct)

    if metric_type == "income":
        return _format_money(item.ingreso_real_total_mtd)

    if metric_type == "new_clients":
        return f"{item.clientes_nuevos_real_mtd:,}"

    return "-"


def _format_money(value: Decimal | None) -> str:
    if value is None:
        return "-"

    return f"${float(value):,.2f}"


def _format_pct(value: Decimal | None) -> str:
    if value is None:
        return "-"

    return f"{float(value):,.2f}%"


def _safe_region_label(
    item: TrackRegionRankingItem | None,
) -> str:
    if item is None:
        return "-"

    return item.region_label


def _safe_compliance(
    item: TrackRegionRankingItem | None,
) -> Decimal | None:
    if item is None:
        return None

    return item.cumplimiento_ingreso_pct


def _safe_income(
    item: TrackRegionRankingItem | None,
) -> Decimal | None:
    if item is None:
        return None

    return item.ingreso_real_total_mtd


def _safe_new_clients(
    item: TrackRegionRankingItem | None,
) -> str:
    if item is None:
        return "-"

    return f"{item.clientes_nuevos_real_mtd:,}"

def _render_business_rules_block() -> str:
    

    return """
    <div
        style="
            border: 1px solid #d9e2ef;
            background-color: #f8fbff;
            border-radius: 10px;
            padding: 16px;
            margin: 24px 0 28px 0;
        "
    >
        <h2 style="font-size: 18px; margin-top: 0;">
            📌 Criterios usados para este análisis
        </h2>

        <ul style="font-size: 13px; line-height: 1.7; margin-bottom: 0; color: #444;">
            <li>
                Solo participan sucursales con
                <strong>meta FAYCGO mensual mayor a 0</strong>.
            </li>

            <li>
                Las regiones se toman desde la capa de gobernanza de Suite:
                <strong>suite_regions</strong> y
                <strong>suite_sucursal_region_assignments</strong>.
            </li>

            <li>
                El ingreso real acumulado usa
                <strong>ingreso_real_total_mtd</strong>, que integra ingreso base y agregadoras cuando existan.
            </li>

            <li>
                El cumplimiento contra meta se calcula como:
                <strong>ingreso real acumulado / meta FAYCGO mensual × 100</strong>.
            </li>

            <li>
                El ranking por cumplimiento compara
                <strong>eficiencia contra meta</strong>, no tamaño de región.
            </li>

            <li>
                El ranking por ingreso compara
                <strong>volumen total acumulado</strong>.
            </li>

            <li>
                El ranking por clientes nuevos compara
                <strong>captación total acumulada</strong>.
            </li>

            <li>
                Las sucursales nuevas o sin meta vigente pueden quedar fuera del ranking competitivo hasta que se defina su meta oficial.
            </li>
        </ul>
    </div>
    """
    
    
def _render_suite_detail_cta(
    *,
    track_date: str,
    generation_mode: str,
) -> str:
    detail_url = _build_regional_detail_url(
        track_date=track_date,
        generation_mode=generation_mode,
    )

    if not detail_url:
        return ""

    return f"""
    <div
        style="
            text-align: center;
            margin: 26px 0 34px 0;
        "
    >
        <a
            href="{detail_url}"
            style="
                display: inline-block;
                background-color: #e54525;
                color: #ffffff;
                text-decoration: none;
                font-weight: bold;
                padding: 14px 22px;
                border-radius: 10px;
                font-size: 14px;
            "
        >
            Ver detalle regional en Suite Ultra
        </a>

        <p style="font-size: 12px; color: #777; margin-top: 10px;">
            Consulta el desglose por región y club dentro de la plataforma.
        </p>
    </div>
    """


def _build_regional_detail_url(
    *,
    track_date: str,
    generation_mode: str,
) -> str | None:
    frontend_url = os.getenv("SUITE_FRONTEND_URL", "").strip().rstrip("/")

    if not frontend_url:
        return None

    return (
        f"{frontend_url}/#/warehouse/track-intelligence/regional"
        f"?track_date={track_date}"
        f"&generation_mode={generation_mode}"
    )