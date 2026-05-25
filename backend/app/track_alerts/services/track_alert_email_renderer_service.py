#   backend\app\track_alerts\services\track_alert_email_renderer_service.py


from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.models.warehouse import TrackAlertEventORM


SEVERITY_EMOJIS = {
    "SUCCESS": "🟢",
    "INFO": "🔵",
    "WARNING": "🟠",
    "CRITICAL": "🔴",
}


SEVERITY_TITLES = {
    "SUCCESS": "Reconocimientos",
    "INFO": "Información",
    "WARNING": "Riesgos Operativos",
    "CRITICAL": "Alertas Críticas",
}

METRIC_SECTION_TITLES = {
    "ingreso_real_total_mtd": "Ingreso real acumulado",
    "ingreso_real_mtd": "Ingreso real acumulado",
    "clientes_nuevos_real_mtd": "Clientes nuevos acumulados",
    "reactivaciones_real_mtd": "Reactivaciones acumuladas",
    "nuevos_domiciliados_real_mtd": "Nuevos domiciliados acumulados",
}


METRIC_SECTION_ORDER = {
    "ingreso_real_total_mtd": 10,
    "ingreso_real_mtd": 10,
    "clientes_nuevos_real_mtd": 20,
    "reactivaciones_real_mtd": 30,
    "nuevos_domiciliados_real_mtd": 40,
}

def render_executive_alert_email(
    *,
    track_date: str,
    events: list[TrackAlertEventORM],
) -> dict[str, Any]:
    grouped_events = _group_events_by_severity(events)

    subject = (
        f"Track Intelligence | Resumen Operativo | {track_date}"
    )

    html = _build_html(
        track_date=track_date,
        grouped_events=grouped_events,
    )

    return {
        "subject": subject,
        "html": html,
        "total_events": len(events),
    }


def _group_events_by_severity(
    events: list[TrackAlertEventORM],
) -> dict[str, list[TrackAlertEventORM]]:
    grouped: dict[str, list[TrackAlertEventORM]] = defaultdict(list)

    for event in events:
        grouped[event.severity].append(event)

    return grouped


def _build_html(
    *,
    track_date: str,
    grouped_events: dict[str, list[TrackAlertEventORM]],
) -> str:
    sections: list[str] = []

    for severity in ["CRITICAL", "WARNING", "SUCCESS", "INFO"]:
        events = grouped_events.get(severity, [])

        if not events:
            continue

        emoji = SEVERITY_EMOJIS.get(severity, "⚪")
        title = SEVERITY_TITLES.get(severity, severity)

        metric_sections = _render_metric_sections(
            events=events,
            severity=severity,
        )

        sections.append(
            f"""
            <div style="margin-bottom: 32px;">
                <h2 style="margin-bottom: 16px;">
                    {emoji} {title}
                </h2>

                {metric_sections}
            </div>
            """
        )

    return f"""
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
                    max-width: 900px;
                    margin: auto;
                    background: white;
                    padding: 32px;
                    border-radius: 12px;
                "
            >
                <h1 style="margin-top: 0;">
                    📊 Track Intelligence
                </h1>

                <p>
                    Resumen operativo automático correspondiente al día:
                    <strong>{track_date}</strong>
                </p>

                {''.join(sections)}

                <hr style="margin-top: 40px;" />

                <p style="font-size: 12px; color: #777;">
                    Generado automáticamente por Suite Ultra Track Intelligence.
                </p>
            </div>
        </body>
    </html>
    """


def _format_metric_value(
    event: TrackAlertEventORM,
) -> str:
    if event.metric_value is None:
        return "-"

    metadata = event.metadata_json or {}
    metric = metadata.get("metric")

    value = event.metric_value

    money_metrics = {
        "ingreso_real_total_mtd",
        "ingreso_real_mtd",
        "ingreso_real_base_mtd",
        "ingreso_real_agregadora_mtd",
    }

    integer_metrics = {
        "clientes_nuevos_real_mtd",
        "reactivaciones_real_mtd",
        "bajas_reales_mtd",
        "nuevos_domiciliados_real_mtd",
    }

    if metric in money_metrics:
        return f"${float(value):,.2f}"

    if metric in integer_metrics:
        return f"{int(float(value)):,}"

    return str(value)
def _render_event_card(
    event: TrackAlertEventORM,
) -> str:
    metric_value = _format_metric_value(event)
    ranking = (
        f"#{event.ranking_position}"
        if event.ranking_position
        else "-"
    )

    sucursal_display_name = _get_branch_display_name(event)

    message = _render_message_with_display_name(
        event=event,
        display_name=sucursal_display_name,
    )

    return f"""
    <div
        style="
            border: 1px solid #ddd;
            border-radius: 10px;
            padding: 16px;
            margin-bottom: 12px;
            background-color: #fafafa;
        "
    >
        <table
            width="100%"
            cellpadding="0"
            cellspacing="0"
            style="border-collapse: collapse; margin-bottom: 8px;"
        >
            <tr>
                <td
                    style="
                        font-weight: bold;
                        font-size: 14px;
                        padding-right: 12px;
                        vertical-align: top;
                    "
                >
                    {event.title}
                </td>

                <td
                    align="right"
                    style="
                        font-size: 13px;
                        font-weight: bold;
                        white-space: nowrap;
                        vertical-align: top;
                        color: #333;
                    "
                >
                    {sucursal_display_name}
                </td>
            </tr>
        </table>

        <div style="margin-bottom: 8px; font-size: 14px;">
            {message}
        </div>

        <div style="font-size: 13px; color: #555;">
            Métrica: <strong>{metric_value}</strong>
            &nbsp;&nbsp;|&nbsp;&nbsp;
            Ranking: <strong>{ranking}</strong>
        </div>
    </div>
    """    
def _get_branch_display_name(
    event: TrackAlertEventORM,
) -> str:
    branch = getattr(event, "branch", None)

    if branch is not None:
        sucursal = getattr(branch, "sucursal", None)

        if sucursal is not None:
            sucursal_name = getattr(sucursal, "sucursal", None)

            if sucursal_name:
                return str(sucursal_name).strip()

        track_label = getattr(branch, "track_label", None)

        if track_label:
            return _format_sucursal_canon(str(track_label))

    return _format_sucursal_canon(event.sucursal_canon)

def _format_sucursal_canon(
    sucursal_canon: str | None,
) -> str:
    if not sucursal_canon:
        return "-"

    return sucursal_canon.replace("_", " ").strip().title()

def _render_message_with_display_name(
    event: TrackAlertEventORM,
    display_name: str,
) -> str:
    message = event.message or ""

    if event.sucursal_canon:
        return message.replace(
            event.sucursal_canon,
            display_name,
        )

    return message

def _render_metric_sections(
    events: list[TrackAlertEventORM],
    severity: str,
) -> str:
    grouped = _group_events_by_metric(events)

    rendered_sections: list[str] = []

    for metric in sorted(
        grouped.keys(),
        key=lambda item: METRIC_SECTION_ORDER.get(item, 999),
    ):
        metric_events = _sort_metric_events_for_display(
            events=grouped[metric],
            severity=severity,
        )

        metric_title = METRIC_SECTION_TITLES.get(
            metric,
            _format_sucursal_canon(metric),
        )

        cards = "".join(
            _render_event_card(event)
            for event in metric_events
        )

        rendered_sections.append(
            f"""
            <div style="margin-bottom: 22px;">
                <h3
                    style="
                        margin: 0 0 10px 0;
                        font-size: 15px;
                        color: #444;
                    "
                >
                    {metric_title}
                </h3>

                {cards}
            </div>
            """
        )

    return "".join(rendered_sections)

def _group_events_by_metric(
    events: list[TrackAlertEventORM],
) -> dict[str, list[TrackAlertEventORM]]:
    grouped: dict[str, list[TrackAlertEventORM]] = {}

    for event in events:
        metadata = event.metadata_json or {}
        metric = metadata.get("metric") or "sin_metrica"

        if metric not in grouped:
            grouped[metric] = []

        grouped[metric].append(event)

    return grouped

def _sort_metric_events_for_display(
    events: list[TrackAlertEventORM],
    severity: str,
) -> list[TrackAlertEventORM]:
    is_bottom_ranking = any(
        (event.alert_code or "").startswith("BOTTOM_")
        for event in events
    )

    if severity in {"WARNING", "CRITICAL"} and is_bottom_ranking:
        return sorted(
            events,
            key=lambda event: (
                -(event.ranking_position or 0),
                event.id,
            ),
        )

    return sorted(
        events,
        key=lambda event: (
            event.ranking_position or 9999,
            event.id,
        ),
    )