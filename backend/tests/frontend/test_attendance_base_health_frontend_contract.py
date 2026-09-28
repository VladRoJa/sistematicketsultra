from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
ATTENDANCE_DIR = (
    REPO_ROOT
    / "frontend"
    / "src"
    / "app"
    / "sports-analysis"
    / "attendance"
)


def _read(name: str) -> str:
    return (
        ATTENDANCE_DIR / name
    ).read_text(encoding="utf-8")


def test_base_health_view_has_separate_frontend_contract():
    models = _read("attendance.models.ts")
    service = _read("attendance.service.ts")
    component = _read(
        "attendance-dashboard.component.ts"
    )
    template = _read(
        "attendance-dashboard.component.html"
    )

    assert "AttendanceDashboardView" in models
    assert "'base-health'" in models
    assert "/attendance/base-health" in service
    assert "/attendance/base-health/members" in service

    assert (
        "loadBaseHealth(): void"
        in component
    )
    assert (
        "openBaseHealthDetail("
        in component
    )

    assert "Salud de la base" in template
    assert "Operación deportiva" in template
    assert "Próximamente" in template
    assert (
        '[disabled]="!isSummaryView"'
        in template
    )
    assert (
        "openBaseHealthDetail('WITH_VISIT')"
        in template
    )
    assert (
        "openBaseHealthDetail('WITHOUT_VISIT')"
        in template
    )


def test_base_health_dialog_uses_external_template_and_styles():
    component = _read(
        "attendance-base-health-detail-dialog.component.ts"
    )

    assert (
        "templateUrl: "
        "'./attendance-base-health-detail-dialog.component.html'"
        in component
    )
    assert (
        "styleUrls: "
        "['./attendance-base-health-detail-dialog.component.css']"
        in component
    )
    assert "template:" not in component
    assert "styles:" not in component


def test_base_health_behavior_metrics_are_wired_to_ui():
    models = _read("attendance.models.ts")
    component = _read(
        "attendance-dashboard.component.ts"
    )
    template = _read(
        "attendance-dashboard.component.html"
    )

    assert "frequency_median_per_week" in models
    assert "members_14_plus_days_without_visit" in models
    assert "follow_up_members" in models
    assert "frequency_distribution" in models
    assert "recency_distribution" in models
    assert "activation" in models

    assert "openFrequencyBucket(" in component
    assert "openRecencyBucket(" in component

    assert "Visitas por semana" in template
    assert "Mediana · Promedio general:" in template
    assert "14+ días sin venir" in template
    assert "Frecuencia de visita" in template
    assert "Tiempo desde la última visita" in template
    assert "Tiempo para venir por primera vez" in template
    assert "Socios para seguimiento" in template
    assert (
        "openBaseHealthDetail('FOLLOW_UP')"
        in template
    )
    assert (
        "openBaseHealthDetail('RECENCY_14_PLUS')"
        in template
    )


def test_base_health_detail_shows_behavior_fields():
    component = _read(
        "attendance-base-health-detail-dialog.component.ts"
    )
    template = _read(
        "attendance-base-health-detail-dialog.component.html"
    )

    assert "formatDecimal(" in component
    assert "formatOptionalNumber(" in component

    assert ">Visitas<" in template
    assert ">Última visita<" in template
    assert ">Días sin venir<" in template
    assert ">Frecuencia/semana<" in template

    assert "row.visit_count" in template
    assert "row.last_visit_date" in template
    assert "row.days_since_last_visit" in template
    assert "row.frequency_per_week" in template
