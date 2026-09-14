from collections import Counter
from datetime import date
from types import SimpleNamespace

from app.warehouse.services import (
    socios_vencidos_current_status_resolver as current_status,
)
from app.warehouse.services import (
    socios_vencidos_reactivation_candidate_resolver as resolver,
)


def test_preview_reuses_current_status_from_phone_count_pass(monkeypatch):
    vencido = SimpleNamespace(
        id=101,
        telefono_raw="6861000001",
        fecha_vencimiento_date=date(2026, 8, 31),
    )
    current_row = current_status.SocioVencidoCurrentStatus(
        vencido_row_id=101,
        status=current_status.STATUS_NOT_FOUND,
        active_id_socio=None,
    )
    calls = {"active_resolution": 0}

    def fake_resolve_current_rows(**_kwargs):
        calls["active_resolution"] += 1
        return (current_row,)

    monkeypatch.setattr(
        resolver,
        "resolve_socios_vencidos_rows_with_context",
        fake_resolve_current_rows,
    )
    monkeypatch.setattr(
        resolver,
        "_read_iventas_contacts",
        lambda **_kwargs: {},
    )

    context = resolver.SociosVencidosReactivationResolutionContext(
        current_status=SimpleNamespace(),
        iventas_sync_run_id=41,
        iventas_period_key="IVENTAS-2026-09-13",
    )

    phone_counts = resolver.count_socios_vencidos_not_found_phones(
        vencidos_rows=[vencido],
        context=context,
        session=object(),
    )

    assert phone_counts == Counter({"6861000001": 1})
    assert 101 in context.current_rows_by_vencido_id
    assert calls["active_resolution"] == 1

    result = resolver.resolve_socios_vencidos_reactivation_candidate_batch(
        vencidos_rows=[vencido],
        context=context,
        phone_counts=phone_counts,
        session=object(),
    )

    assert calls["active_resolution"] == 1
    assert result[0].vencido_row_id == 101
    assert result[0].reason == resolver.REASON_NO_MATCH_CURRENT_IVENTAS_RUN
