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


def test_attendance_detail_supports_non_sortable_identity_columns():
    models = _read("attendance.models.ts")
    component = _read(
        "attendance-detail-dialog.component.ts"
    )
    template = _read(
        "attendance-detail-dialog.component.html"
    )

    assert "sortable?: boolean;" in models
    assert (
        "column.sortable === false"
        in component
    )
    assert (
        "toggleSort(column: AttendanceDetailColumn)"
        in component
    )
    assert (
        '[disabled]="column.sortable === false"'
        in template
    )
    assert '(click)="toggleSort(column)"' in template
    assert (
        '*ngIf="column.sortable !== false"'
        in template
    )
