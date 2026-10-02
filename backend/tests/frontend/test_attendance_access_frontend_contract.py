from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
LAYOUT = (
    REPO_ROOT
    / "frontend"
    / "src"
    / "app"
    / "layout"
    / "layout.component.ts"
)


def test_attendance_menu_is_visible_to_managers_and_regionals():
    text = LAYOUT.read_text(encoding="utf-8")

    assert "sportsAnalysisRole === 'GERENTE'" in text
    assert "sportsAnalysisRole === 'GERENTE_REGIONAL'" in text
    assert "Aforo y Asistencia" in text
