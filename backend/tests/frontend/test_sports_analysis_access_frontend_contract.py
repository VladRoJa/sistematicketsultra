from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
LAYOUT_COMPONENT = (
    REPO_ROOT
    / "frontend"
    / "src"
    / "app"
    / "layout"
    / "layout.component.ts"
)


def test_attendance_menu_allows_sports_management_role():
    source = LAYOUT_COMPONENT.read_text(
        encoding="utf-8"
    )

    assert (
        "sportsAnalysisRole === 'GERENCIA DEPORTIVA'"
        in source
    )
    assert (
        "sportsAnalysisUsername === 'ADMICORP'"
        in source
    )
    assert (
        "path: '/analisis-deportivo/aforo-asistencia'"
        in source
    )
