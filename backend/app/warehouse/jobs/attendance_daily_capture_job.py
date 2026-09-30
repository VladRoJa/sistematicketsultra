from __future__ import annotations

from datetime import date

from app.sports_analysis.attendance_capture_service import (
    capture_and_ingest_attendance,
)


def run_job(
    *,
    business_date: date,
) -> dict:
    return capture_and_ingest_attendance(
        business_date=business_date,
        trigger_source="REPORTS_SCHEDULER",
    )
