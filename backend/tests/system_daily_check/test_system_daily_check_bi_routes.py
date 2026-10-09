from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import system_daily_check_bi_routes as routes


def _app():
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        JWT_SECRET_KEY="system-daily-check-bi-routes-test",
    )
    JWTManager(app)
    app.register_blueprint(
        routes.system_daily_check_bi_bp,
        url_prefix="/api/system-daily-checks/bi",
    )
    return app


def _actor(*, role="SISTEMAS", username="SISTEMAS"):
    return SimpleNamespace(
        id=20,
        username=username,
        rol=role,
        sucursal_id=10,
    )


def _headers(app, actor):
    with app.app_context():
        token = create_access_token(identity=str(actor.id))
    return {"Authorization": f"Bearer {token}"}


def test_bi_context_returns_mvp_universe_and_questions():
    app = _app()
    actor = _actor()
    universe = {
        "as_of_date": "2026-10-09",
        "potential_branches": [],
        "expected_branches": [],
        "potential_count": 0,
        "expected_count": 0,
    }

    with (
        patch.object(
            routes.UserORM,
            "get_by_id",
            return_value=actor,
        ),
        patch.object(
            routes,
            "resolve_business_date",
            return_value=date(2026, 10, 9),
        ),
        patch.object(
            routes,
            "list_system_daily_check_questions",
            return_value=[{"question_key": "GASCA_WORKING"}],
        ),
        patch.object(
            routes,
            "resolve_system_daily_check_branch_universe",
            return_value=universe,
        ),
    ):
        response = app.test_client().get(
            "/api/system-daily-checks/bi/context",
            headers=_headers(app, actor),
        )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["allowed"] is True
    assert payload["business_date"] == "2026-10-09"
    assert payload["universe"] == universe
    assert payload["questions"][0]["question_key"] == "GASCA_WORKING"


def test_bi_context_rejects_manager_before_loading_universe():
    app = _app()
    actor = _actor(
        role="GERENTE",
        username="gerente.demo",
    )

    with (
        patch.object(
            routes.UserORM,
            "get_by_id",
            return_value=actor,
        ),
        patch.object(
            routes,
            "resolve_system_daily_check_branch_universe",
        ) as universe,
    ):
        response = app.test_client().get(
            "/api/system-daily-checks/bi/context",
            headers=_headers(app, actor),
        )

    assert response.status_code == 403
    assert response.get_json()["code"] == (
        "SYSTEM_DAILY_CHECK_BI_NOT_ELIGIBLE"
    )
    universe.assert_not_called()


def test_bi_rollout_commits_replacement_for_mvp_actor():
    app = _app()
    actor = _actor()
    session = MagicMock()
    universe = {
        "as_of_date": "2026-10-09",
        "potential_branches": [],
        "expected_branches": [{"sucursal_id": 10}],
        "potential_count": 0,
        "expected_count": 1,
    }

    with (
        patch.object(
            routes.UserORM,
            "get_by_id",
            return_value=actor,
        ),
        patch.object(
            routes,
            "configure_system_daily_check_rollout_today",
            return_value=universe,
        ) as configure,
        patch.object(
            routes,
            "db",
            SimpleNamespace(session=session),
        ),
    ):
        response = app.test_client().put(
            "/api/system-daily-checks/bi/rollout",
            json={"branch_ids": [10]},
            headers=_headers(app, actor),
        )

    assert response.status_code == 200
    assert response.get_json()["universe"] == universe
    configure.assert_called_once_with(
        actor,
        branch_ids=[10],
    )
    session.commit.assert_called_once_with()
    session.rollback.assert_not_called()


def test_bi_rollout_rejects_manager_and_does_not_commit():
    app = _app()
    actor = _actor(
        role="GERENTE",
        username="gerente.demo",
    )
    session = MagicMock()

    with (
        patch.object(
            routes.UserORM,
            "get_by_id",
            return_value=actor,
        ),
        patch.object(
            routes,
            "configure_system_daily_check_rollout_today",
        ) as configure,
        patch.object(
            routes,
            "db",
            SimpleNamespace(session=session),
        ),
    ):
        response = app.test_client().put(
            "/api/system-daily-checks/bi/rollout",
            json={"branch_ids": [10]},
            headers=_headers(app, actor),
        )

    assert response.status_code == 403
    configure.assert_not_called()
    session.commit.assert_not_called()
    session.rollback.assert_called_once_with()


def test_bi_summary_uses_explicit_filters_and_mvp_actor():
    app = _app()
    actor = _actor()
    expected = {
        "filters": {
            "date_from": "2026-10-01",
            "date_to": "2026-10-09",
            "branch_id": 10,
        },
        "summary": {"completed": 1},
    }

    with (
        patch.object(
            routes.UserORM,
            "get_by_id",
            return_value=actor,
        ),
        patch.object(
            routes,
            "resolve_business_date",
            return_value=date(2026, 10, 9),
        ),
        patch.object(
            routes,
            "build_system_daily_check_bi_summary",
            return_value=expected,
        ) as summary,
    ):
        response = app.test_client().get(
            (
                "/api/system-daily-checks/bi/summary"
                "?date_from=2026-10-01"
                "&date_to=2026-10-09"
                "&branch_id=10"
            ),
            headers=_headers(app, actor),
        )

    assert response.status_code == 200
    assert response.get_json() == expected
    summary.assert_called_once_with(
        actor,
        date_from=date(2026, 10, 1),
        date_to=date(2026, 10, 9),
        branch_id=10,
    )


def test_bi_matrix_uses_requested_business_date():
    app = _app()
    actor = _actor()
    expected = {
        "business_date": "2026-10-08",
        "branch_id": None,
        "groups": [],
        "rows": [],
    }

    with (
        patch.object(
            routes.UserORM,
            "get_by_id",
            return_value=actor,
        ),
        patch.object(
            routes,
            "resolve_business_date",
            return_value=date(2026, 10, 9),
        ),
        patch.object(
            routes,
            "build_system_daily_check_bi_matrix",
            return_value=expected,
        ) as matrix,
    ):
        response = app.test_client().get(
            "/api/system-daily-checks/bi/matrix?date=2026-10-08",
            headers=_headers(app, actor),
        )

    assert response.status_code == 200
    assert response.get_json() == expected
    matrix.assert_called_once_with(
        actor,
        business_date=date(2026, 10, 8),
        branch_id=None,
    )


def test_bi_history_passes_filters_and_pagination():
    app = _app()
    actor = _actor()
    expected = {
        "filters": {},
        "page": 2,
        "page_size": 25,
        "total": 0,
        "items": [],
    }

    with (
        patch.object(
            routes.UserORM,
            "get_by_id",
            return_value=actor,
        ),
        patch.object(
            routes,
            "resolve_business_date",
            return_value=date(2026, 10, 9),
        ),
        patch.object(
            routes,
            "list_system_daily_check_bi_history",
            return_value=expected,
        ) as history,
    ):
        response = app.test_client().get(
            (
                "/api/system-daily-checks/bi/history"
                "?date_from=2026-10-01"
                "&date_to=2026-10-09"
                "&branch_id=10"
                "&general_status=MINOR_FAILURE"
                "&question_key=GASCA_WORKING"
                "&answer=NO"
                "&page=2"
                "&page_size=25"
            ),
            headers=_headers(app, actor),
        )

    assert response.status_code == 200
    assert response.get_json() == expected
    history.assert_called_once_with(
        actor,
        date_from=date(2026, 10, 1),
        date_to=date(2026, 10, 9),
        branch_id=10,
        general_status="MINOR_FAILURE",
        question_key="GASCA_WORKING",
        answer="NO",
        page="2",
        page_size="25",
    )


def test_bi_detail_returns_reconstructed_check():
    app = _app()
    actor = _actor()
    expected = {
        "id": 44,
        "sucursal_id": 10,
        "answers": [],
    }

    with (
        patch.object(
            routes.UserORM,
            "get_by_id",
            return_value=actor,
        ),
        patch.object(
            routes,
            "get_system_daily_check_bi_detail",
            return_value=expected,
        ) as detail,
    ):
        response = app.test_client().get(
            "/api/system-daily-checks/bi/checks/44",
            headers=_headers(app, actor),
        )

    assert response.status_code == 200
    assert response.get_json() == expected
    detail.assert_called_once_with(
        actor,
        check_id=44,
    )


def test_bi_detail_returns_domain_404():
    app = _app()
    actor = _actor()

    with (
        patch.object(
            routes.UserORM,
            "get_by_id",
            return_value=actor,
        ),
        patch.object(
            routes,
            "get_system_daily_check_bi_detail",
            side_effect=routes.SystemDailyCheckNotFoundError(
                "Checklist no encontrado."
            ),
        ),
    ):
        response = app.test_client().get(
            "/api/system-daily-checks/bi/checks/999",
            headers=_headers(app, actor),
        )

    assert response.status_code == 404
    assert response.get_json()["code"] == (
        "SYSTEM_DAILY_CHECK_BI_NOT_FOUND"
    )


def test_bi_attachment_serves_inline_file(tmp_path):
    app = _app()
    actor = _actor()
    file_path = tmp_path / "gasca.png"
    file_path.write_bytes(b"abc")

    with (
        patch.object(
            routes.UserORM,
            "get_by_id",
            return_value=actor,
        ),
        patch.object(
            routes,
            "get_system_daily_check_bi_attachment",
            return_value={
                "path": file_path,
                "original_filename": "gasca.png",
                "mime_type": "image/png",
                "file_size_bytes": 3,
                "sha256": "a" * 64,
            },
        ) as attachment,
    ):
        response = app.test_client().get(
            "/api/system-daily-checks/bi/attachments/7",
            headers=_headers(app, actor),
        )

    assert response.status_code == 200
    assert response.data == b"abc"
    assert response.mimetype == "image/png"
    assert "inline" in response.headers["Content-Disposition"]
    attachment.assert_called_once_with(
        actor,
        attachment_id=7,
    )


def test_bi_trends_passes_granularity_and_filters():
    app = _app()
    actor = _actor()
    expected = {
        "filters": {
            "date_from": "2026-10-01",
            "date_to": "2026-10-09",
            "branch_id": 10,
            "granularity": "WEEK",
        },
        "trend": [],
        "question_ranking": [],
        "branch_ranking": [],
        "recurrence": [],
    }

    with (
        patch.object(
            routes.UserORM,
            "get_by_id",
            return_value=actor,
        ),
        patch.object(
            routes,
            "resolve_business_date",
            return_value=date(2026, 10, 9),
        ),
        patch.object(
            routes,
            "build_system_daily_check_bi_trends",
            return_value=expected,
        ) as trends,
    ):
        response = app.test_client().get(
            (
                "/api/system-daily-checks/bi/trends"
                "?date_from=2026-10-01"
                "&date_to=2026-10-09"
                "&branch_id=10"
                "&granularity=WEEK"
            ),
            headers=_headers(app, actor),
        )

    assert response.status_code == 200
    assert response.get_json() == expected
    trends.assert_called_once_with(
        actor,
        date_from=date(2026, 10, 1),
        date_to=date(2026, 10, 9),
        granularity="WEEK",
        branch_id=10,
    )


def test_bi_pending_passes_range_and_pagination():
    app = _app()
    actor = _actor()
    expected = {
        "filters": {
            "date_from": "2026-10-01",
            "date_to": "2026-10-09",
            "branch_id": 10,
        },
        "page": 1,
        "page_size": 20,
        "total": 0,
        "items": [],
    }

    with (
        patch.object(
            routes.UserORM,
            "get_by_id",
            return_value=actor,
        ),
        patch.object(
            routes,
            "resolve_business_date",
            return_value=date(2026, 10, 9),
        ),
        patch.object(
            routes,
            "list_system_daily_check_bi_pending",
            return_value=expected,
        ) as pending,
    ):
        response = app.test_client().get(
            (
                "/api/system-daily-checks/bi/pending"
                "?date_from=2026-10-01"
                "&date_to=2026-10-09"
                "&branch_id=10"
                "&page=1"
                "&page_size=20"
            ),
            headers=_headers(app, actor),
        )

    assert response.status_code == 200
    assert response.get_json() == expected
    pending.assert_called_once_with(
        actor,
        date_from=date(2026, 10, 1),
        date_to=date(2026, 10, 9),
        branch_id=10,
        page="1",
        page_size="20",
    )
