"""M3-C1 reader-invisibility gates against ISOLATED synthetic PostgreSQL 16.

The reserved version type is inserted via ORM strictly as a synthetic
adversarial fixture. No implementation supports staging a real candidate.
"""
from __future__ import annotations

from datetime import date, datetime, timezone, timedelta
import inspect
import os
import uuid
from unittest.mock import MagicMock, patch

from flask import Flask
import pytest
import sqlalchemy as sa

from app.extensions import db
from app.models.warehouse import TrackDailyVersionORM, TrackDailyMartORM
from app.warehouse.services.track_daily_query_version_service import (
    find_latest_effective_track_mart_row_for_branch,
    resolve_preferred_track_daily_version,
)
from app.warehouse.services import planning_targets_service as planning
from app.warehouse.services import kpi_desempeno_query_service as kpi_query
from app.warehouse.services import track_forecast_service as forecast
from app.warehouse.services import scheduler_priority_service as scheduler
from app.track_alerts.services import track_alert_rules_service as alerts
from app.routes import track_routes

DAY = date(2026, 8, 19)
MONTH = DAY.replace(day=1)
BRANCH = "SYNTHETIC_GYM"
CANDIDATE = "kpi_desempeno_candidato"


@pytest.fixture()
def isolated_pg():
    url = os.getenv("M3C1_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Requires isolated synthetic PostgreSQL 16 CI URL")
    schema = "track_m3c1_" + uuid.uuid4().hex[:17]
    admin = sa.create_engine(url)
    with admin.begin() as conn:
        assert int(conn.exec_driver_sql("SHOW server_version_num").scalar()) // 10000 == 16
        conn.exec_driver_sql(f"CREATE SCHEMA {schema}")
    app = Flask(__name__ + schema)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI=url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={"connect_args": {"options": f"-csearch_path={schema}"}},
    )
    db.init_app(app)
    try:
        with app.app_context():
            # The FK target is synthetic; no real branch/user data is loaded.
            db.session.execute(sa.text(
                "CREATE TABLE track_branch_catalog (sucursal_canon TEXT PRIMARY KEY)"
            ))
            db.session.execute(sa.text(
                "INSERT INTO track_branch_catalog VALUES (:branch)"
            ), {"branch": BRANCH})
            db.session.commit()
            TrackDailyVersionORM.__table__.create(bind=db.engine)
            TrackDailyMartORM.__table__.create(bind=db.engine)

            def version(day, vtype, *, current=True, status="success",
                        replaces=None):
                now = datetime.now(timezone.utc)
                row = TrackDailyVersionORM(
                    track_date=day, version_type=vtype, status=status,
                    is_current=current, replaces_version_id=replaces,
                    trigger_source="m3c1_synthetic_only", created_at=now,
                    updated_at=now,
                )
                db.session.add(row)
                db.session.flush()
                return row

            def mart(ver, *, capacity, store=0, income=0, new_clients=0):
                row = TrackDailyMartORM(
                    track_date=ver.track_date, target_month=ver.track_date.replace(day=1),
                    generation_mode="official_closed_day",
                    track_daily_version_id=ver.id, sucursal_canon=BRANCH,
                    m2_sin_circulaciones=capacity,
                    ingreso_real_base_mtd=income,
                    ingreso_real_total_mtd=income,
                    clientes_nuevos_real_mtd=new_clients,
                    meta_faycgo_mes=1000,
                    venta_tienda_real_mtd=store,
                )
                db.session.add(row)
                db.session.flush()
                return row

            candidate_only = version(DAY-timedelta(days=1), CANDIDATE, current=True)
            mart(candidate_only, capacity=99999, store=99999, income=99999)
            old_close = version(DAY, "cierre_canonico", current=False, status="replaced")
            mart(old_close, capacity=8888, store=8888, income=8888)
            base = version(DAY, "base_nocturna_canonica")
            mart(base, capacity=100, store=0, income=100)
            close = version(DAY, "cierre_canonico", replaces=old_close.id)
            mart(close, capacity=200, store=50, income=200, new_clients=4)
            candidate_hidden = version(DAY, CANDIDATE, current=False)
            mart(candidate_hidden, capacity=7777, store=7777, income=7777)
            candidate_wrong_current = version(DAY, CANDIDATE, current=True)
            mart(candidate_wrong_current, capacity=9999, store=9999, income=9999)

            next_base = version(DAY+timedelta(days=1), "base_nocturna_canonica")
            mart(next_base, capacity=220, store=80, income=220)
            db.session.commit()
            yield {
                "app": app, "base": base.id, "close": close.id,
                "old_close": old_close.id, "candidate": candidate_hidden.id,
                "wrong_current": candidate_wrong_current.id,
                "next_base": next_base.id,
            }
            db.session.remove()
    finally:
        admin.dispose()
        cleanup = sa.create_engine(url)
        try:
            with cleanup.begin() as conn:
                conn.exec_driver_sql(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        finally:
            cleanup.dispose()


def test_pg_close_precedes_base_and_both_candidate_states(isolated_pg):
    x = isolated_pg
    selected = resolve_preferred_track_daily_version(track_date=DAY)
    assert selected is not None and selected.id == x["close"]
    assert selected.id not in {x["candidate"], x["wrong_current"]}
    result = find_latest_effective_track_mart_row_for_branch(
        sucursal_canon=BRANCH, exact_target_month=MONTH
    )
    assert result.track_daily_version_id == x["next_base"]
    assert result.m2_sin_circulaciones == 220


def test_pg_month_latest_planning_ignores_higher_candidate_ids(isolated_pg):
    selected = planning._latest_track_mart_row_for_month(
        sucursal_canon=BRANCH, target_month=MONTH,
    )
    assert selected.track_daily_version_id == isolated_pg["next_base"]
    assert selected.m2_sin_circulaciones == 220


def test_pg_capacity_targets_only_use_effective_mart(isolated_pg):
    values = kpi_query._fetch_branch_capacity_targets_by_canon(
        sucursales_canon={BRANCH}, target_month="2026-08"
    )
    assert values[BRANCH]["m2_sin_circulaciones"] == 220.0
    assert values[BRANCH]["source"]["track_daily_mart_id"] > 0


def test_pg_prefill_resolves_effective_version_with_same_public_shape(isolated_pg):
    branch = MagicMock()
    branch.track_label = "Synthetic Gym"
    catalog = MagicMock()
    catalog.query.filter_by.return_value.first.return_value = branch
    with patch.object(planning, "_ensure_branch_exists", return_value=BRANCH):
        with patch.object(planning, "TrackBranchCatalogORM", catalog):
            out = planning.get_branch_prefill(
                sucursal_canon=BRANCH, target_month=MONTH,
            )
    assert out["m2_sin_circulaciones"] == "220.00"
    assert out["track_label"] == "Synthetic Gym"


def test_pg_alerts_only_evaluate_resolved_close_not_base_or_candidate(isolated_pg):
    recorded = []
    def observe(*, track_date, rows):
        recorded.extend(rows)
        return []
    with (
        patch.object(alerts, "_evaluate_income_ranking", side_effect=observe),
        patch.object(alerts, "_evaluate_new_clients_ranking", return_value=[]),
    ):
        result = alerts.evaluate_track_alerts(
            track_date=DAY, generation_mode="official_closed_day",
        )
    assert result == []
    assert len(recorded) == 1
    assert recorded[0].track_daily_version_id == isolated_pg["close"]
    assert recorded[0].ingreso_real_base_mtd == 200


def test_pg_first_store_sale_never_uses_candidate_only_date(isolated_pg):
    result = forecast.load_first_store_income_dates_bulk([BRANCH])
    assert result == {BRANCH: DAY}


def test_pg_scheduler_active_work_ignores_reserved_current_pending(isolated_pg):
    today = DAY+timedelta(days=3)
    v = TrackDailyVersionORM(
        track_date=today, version_type=CANDIDATE, status="pending",
        is_current=True, trigger_source="m3c1_synthetic_only",
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    db.session.add(v)
    db.session.commit()
    assert scheduler.has_active_track_work() is False
    v2 = TrackDailyVersionORM(
        track_date=today, version_type="base_nocturna_canonica", status="running",
        is_current=True, trigger_source="m3c1_synthetic_only",
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    db.session.add(v2)
    db.session.commit()
    assert scheduler.has_active_track_work() is True


def test_pg_fallback_replaced_close_keeps_historic_public_behavior(isolated_pg):
    current = db.session.get(TrackDailyVersionORM, isolated_pg["close"])
    current.status = "running"
    db.session.commit()
    chosen = resolve_preferred_track_daily_version(track_date=DAY)
    assert chosen is not None and chosen.id == isolated_pg["old_close"]
    row = find_latest_effective_track_mart_row_for_branch(
        sucursal_canon=BRANCH,
        exact_target_month=MONTH,
        latest_target_month=date(2026, 8, 1),
    )
    # Latest day in month is next day's nightly base, still ahead of fallback.
    assert row.track_daily_version_id == isolated_pg["next_base"]


def test_branch_history_date_discovery_excludes_candidate_only_days(isolated_pg):
    # Same JOIN/filter used by track_routes.py before the authoritative
    # _resolve_track_branch_history_rows() call.
    sql = sa.text("""
        SELECT DISTINCT m.track_date FROM track_daily_mart m
        JOIN track_daily_versions v ON v.id=m.track_daily_version_id
        WHERE m.sucursal_canon=:branch
          AND v.version_type IN (
            'cierre_canonico','base_nocturna_canonica','preview_operativo'
          )
        ORDER BY m.track_date
    """)
    rows = db.session.execute(sql, {"branch": BRANCH}).scalars().all()
    assert rows == [DAY, DAY + timedelta(days=1)]
    source = inspect.getsource(track_routes.branch_history_endpoint) if hasattr(
        track_routes, "branch_history_endpoint"
    ) else inspect.getsource(track_routes)
    assert "PREFERRED_TRACK_VERSION_TYPES" in source
    assert "TrackDailyVersionORM.version_type.in_" in source


def test_public_resolvers_never_include_reserved_type():
    from app.warehouse.services.track_daily_query_version_service import (
        PREFERRED_TRACK_VERSION_TYPES,
        resolve_track_daily_version_type_candidates,
    )
    assert CANDIDATE not in PREFERRED_TRACK_VERSION_TYPES
    assert CANDIDATE not in resolve_track_daily_version_type_candidates(
        track_date=DAY, generation_mode="official_closed_day",
    )


def test_pg_candidate_only_date_never_generates_public_alerts(isolated_pg):
    with patch.object(alerts, "_evaluate_income_ranking") as ranking:
        result = alerts.evaluate_track_alerts(
            track_date=DAY - timedelta(days=1),
            generation_mode="official_closed_day",
        )
    assert result == []
    ranking.assert_not_called()


def test_pg_manual_close_claim_excludes_reserved_pending_and_running(isolated_pg):
    from app.warehouse.services.track_daily_version_service import (
        claim_next_pending_track_canonical_close,
    )

    # No real canonical-close requests are present in this isolated schema.
    bad_pending = TrackDailyVersionORM(
        track_date=DAY + timedelta(days=3),
        version_type=CANDIDATE, status="pending",
        is_current=False, trigger_source="m3c1_synthetic_only",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    bad_running = TrackDailyVersionORM(
        track_date=DAY + timedelta(days=4),
        version_type=CANDIDATE, status="running",
        is_current=False, trigger_source="m3c1_synthetic_only",
        created_at=datetime.now(timezone.utc)-timedelta(hours=4),
        updated_at=datetime.now(timezone.utc)-timedelta(hours=4),
    )
    db.session.add_all([bad_pending, bad_running])
    db.session.commit()
    assert claim_next_pending_track_canonical_close() is None
    db.session.expire_all()
    assert db.session.get(TrackDailyVersionORM, bad_pending.id).status == "pending"
    assert db.session.get(TrackDailyVersionORM, bad_running.id).status == "running"


def test_pg_historical_manual_preview_replace_twice_keeps_mode_identity(isolated_pg):
    """Real PostgreSQL event roundtrip: manual request resolves official close.

    First reproduces previous mismatch: evaluate candidate has real row mode,
    but deletion of old events is keyed by requested generation mode. Correct
    behavior retains only one generation's events after two replacements.
    """
    from app.models.warehouse import TrackAlertEventORM
    from app.track_alerts.services.track_alert_event_service import (
        generate_track_alert_events,
    )

    TrackAlertEventORM.__table__.create(bind=db.engine)

    # Six current close branches are required for top/bottom alert rankings.
    # Candidate-only and candidate-with-current rows already exist in this
    # fixture, with inflated amounts; none may be used in public alerts.
    for index in range(1, 6):
        branch = f"SYNTHETIC_GYM_{index}"
        db.session.execute(sa.text(
            "INSERT INTO track_branch_catalog (sucursal_canon) VALUES (:branch)"
        ), {"branch": branch})
        db.session.add(TrackDailyMartORM(
            track_date=DAY,
            target_month=MONTH,
            generation_mode="official_closed_day",
            track_daily_version_id=isolated_pg["close"],
            sucursal_canon=branch,
            m2_sin_circulaciones=100,
            ingreso_real_base_mtd=200 + index * 10,
            ingreso_real_total_mtd=200 + index * 10,
            clientes_nuevos_real_mtd=4 + index,
            meta_faycgo_mes=1000,
            venta_tienda_real_mtd=15,
        ))
    db.session.commit()

    requested_mode = "manual_preview"
    for iteration in (1, 2):
        result = generate_track_alert_events(
            track_date=DAY,
            generation_mode=requested_mode,
            replace_existing=True,
        )
        assert result["generation_mode"] == requested_mode
        assert result["created_events"] == 12
        db.session.expire_all()

        stored = (
            db.session.query(TrackAlertEventORM)
            .filter(TrackAlertEventORM.track_date == DAY)
            .order_by(TrackAlertEventORM.id)
            .all()
        )
        assert len(stored) == 12, f"replace_existing failed on iteration {iteration}"
        assert len({(
            event.sucursal_canon, event.alert_code, event.ranking_position
        ) for event in stored}) == 12
        assert all(
            event.metadata_json["generation_mode"] == requested_mode
            and event.metadata_json["source_generation_mode"] == "official_closed_day"
            for event in stored
        )
        assert all(
            (event.metric_value or 0) < 1000 for event in stored
        ), "Candidate values leaked into stored public alert events"

    # The original real source mode must remain independently identifiable.
    # An explicitly official request is a distinct identity, not a replacement
    # of alerts requested as manual_preview.
    official = generate_track_alert_events(
        track_date=DAY, generation_mode="official_closed_day",
        replace_existing=True,
    )
    assert official["created_events"] == 12
    groups = {"manual_preview": 0, "official_closed_day": 0}
    for event in db.session.query(TrackAlertEventORM).filter_by(track_date=DAY):
        groups[event.metadata_json["generation_mode"]] += 1
    assert groups == {"manual_preview": 12, "official_closed_day": 12}
