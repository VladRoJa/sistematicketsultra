import pytest

from app.warehouse.scheduler import track_scheduler_worker as worker


@pytest.mark.parametrize(
    "status",
    ["generated", "up_to_date"],
)
def test_execute_agregadoras_export_always_publishes(
    monkeypatch,
    status,
):
    export_result = {
        "status": status,
        "output_path": "/tmp/agregadoras.xlsx",
        "cutoff_date": "2026-09-29",
        "download_filename": (
            "Agregadoras 1 enero - 29 septiembre 2026.xlsx"
        ),
    }
    publish_calls = []

    monkeypatch.setattr(
        worker,
        "generate_agregadoras_consolidado",
        lambda: export_result,
    )

    def fake_publish(**kwargs):
        publish_calls.append(kwargs)
        return {
            "action": "already_published",
            "warehouse_upload_id": 55,
            "document_id": 88,
        }

    monkeypatch.setattr(
        worker,
        "publish_agregadoras_consolidado_output",
        fake_publish,
    )

    result = worker.execute_agregadoras_consolidado_export()

    assert result["export"] is export_result
    assert result["publication"]["action"] == "already_published"
    assert publish_calls == [
        {
            "file_path": "/tmp/agregadoras.xlsx",
            "cutoff_date": "2026-09-29",
            "download_filename": (
                "Agregadoras 1 enero - 29 septiembre 2026.xlsx"
            ),
        }
    ]
