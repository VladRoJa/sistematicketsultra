from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

COMPONENT_TS = REPOSITORY_ROOT / (
    "frontend/src/app/maintenance-my-program/"
    "maintenance-my-program.component.ts"
)
COMPONENT_HTML = REPOSITORY_ROOT / (
    "frontend/src/app/maintenance-my-program/"
    "maintenance-my-program.component.html"
)
COMPONENT_CSS = REPOSITORY_ROOT / (
    "frontend/src/app/maintenance-my-program/"
    "maintenance-my-program.component.css"
)
SERVICE_TS = REPOSITORY_ROOT / (
    "frontend/src/app/services/maintenance-preventive.service.ts"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_my_program_workload_contract_is_typed_and_visible():
    service = _read(SERVICE_TS)
    component = _read(COMPONENT_TS)
    html = _read(COMPONENT_HTML)
    css = _read(COMPONENT_CSS)

    assert "MaintenanceMyProgramWorkloadDay" in service
    assert "MaintenanceMyProgramWorkload" in service
    assert "workload: MaintenanceMyProgramWorkload" in service

    assert "workloadMinutesLabel" in component
    assert "workloadProgress" in component
    assert "workloadStatus" in component

    assert 'class="workload-panel"' in html
    assert "Carga estimada" in html
    assert "current.workload.estimated_minutes" in html
    assert "current.workload.days" in html
    assert "<progress" in html
    assert '[value]="workloadProgress(day)"' in html
    assert "[style." not in html

    assert ".workload-panel" in css
    assert ".workload-day--over" in css
    assert ".workload-day__progress" in css


def test_my_program_workload_keeps_daily_reference_visible():
    html = _read(COMPONENT_HTML)

    assert "Referencia diaria: 9 h" in html
    assert "sin estimar" in html
    assert "Sobrecarga" not in html or "workloadStatus(day)" in html
