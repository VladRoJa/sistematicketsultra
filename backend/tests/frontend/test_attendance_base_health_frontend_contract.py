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
