from datetime import date, datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import system_daily_check_routes as routes


class SystemDailyCheckRoutesTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            TESTING=True,
            JWT_SECRET_KEY="system-daily-check-routes-test",
        )
        JWTManager(self.app)
        self.app.register_blueprint(
            routes.system_daily_check_bp,
            url_prefix="/api/system-daily-checks",
        )

        self.actor = SimpleNamespace(
            id=20,
            username="SISTEMAS",
            rol="SISTEMAS",
            sucursal_id=10,
        )
        self.session = MagicMock()
        self.db_patch = patch.object(
            routes,
            "db",
            SimpleNamespace(session=self.session),
        )
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)

    def _headers(self):
        with self.app.app_context():
            token = create_access_token(identity=str(self.actor.id))
        return {"Authorization": f"Bearer {token}"}

    def _request(self, path, *, method="GET", json=None):
        with self.app.test_request_context(
            path,
            method=method,
            headers=self._headers(),
            json=json,
        ):
            return self.app.full_dispatch_request()

    def test_status_uses_jwt_actor_and_query_branch_context(self):
        expected = {
            "eligible": True,
            "sucursal_id": 11,
            "business_date": "2026-10-09",
            "completed": False,
            "postpone_count": 0,
            "can_postpone": True,
            "should_prompt": True,
            "mandatory": False,
            "next_prompt_at": None,
            "mandatory_from_at": None,
            "completed_at": None,
            "check_id": None,
        }
        with (
            patch.object(
                routes.UserORM,
                "get_by_id",
                return_value=self.actor,
            ),
            patch.object(
                routes,
                "get_today_status",
                return_value=expected,
            ) as service,
        ):
            response = self._request(
                "/api/system-daily-checks/today/status?sucursal_id=11"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), expected)
        service.assert_called_once_with(
            self.actor,
            requested_branch_id="11",
        )

    def test_questions_rejects_manager_during_mvp(self):
        self.actor.rol = "GERENTE"
        self.actor.username = "manager"

        with patch.object(
            routes.UserORM,
            "get_by_id",
            return_value=self.actor,
        ):
            response = self._request(
                "/api/system-daily-checks/questions"
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.get_json()["code"],
            "SYSTEM_DAILY_CHECK_NOT_ELIGIBLE",
        )
        self.assertIs(
            response.get_json()["eligible"],
            False,
        )

    def test_postpone_commits_and_returns_service_status(self):
        expected = {
            "eligible": True,
            "sucursal_id": 10,
            "business_date": "2026-10-09",
            "completed": False,
            "postpone_count": 1,
            "can_postpone": False,
            "should_prompt": False,
            "mandatory": False,
            "next_prompt_at": "2026-10-09T16:05:00+00:00",
            "mandatory_from_at": None,
            "completed_at": None,
            "check_id": None,
        }
        with (
            patch.object(
                routes.UserORM,
                "get_by_id",
                return_value=self.actor,
            ),
            patch.object(
                routes,
                "postpone_today",
                return_value=expected,
            ) as service,
        ):
            response = self._request(
                "/api/system-daily-checks/today/postpone?sucursal_id=10",
                method="POST",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), expected)
        service.assert_called_once_with(
            self.actor,
            requested_branch_id="10",
        )
        self.session.commit.assert_called_once_with()
        self.session.rollback.assert_not_called()

    def test_postpone_conflict_rolls_back_and_returns_409(self):
        with (
            patch.object(
                routes.UserORM,
                "get_by_id",
                return_value=self.actor,
            ),
            patch.object(
                routes,
                "postpone_today",
                side_effect=routes.SystemDailyCheckConflictError(
                    "Ya se utilizaron los dos aplazamientos permitidos."
                ),
            ),
        ):
            response = self._request(
                "/api/system-daily-checks/today/postpone",
                method="POST",
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.get_json()["code"],
            "SYSTEM_DAILY_CHECK_CONFLICT",
        )
        self.session.commit.assert_not_called()
        self.session.rollback.assert_called_once_with()

    def test_submit_rejects_server_controlled_fields_before_service(self):
        with (
            patch.object(
                routes.UserORM,
                "get_by_id",
                return_value=self.actor,
            ),
            patch.object(routes, "submit_today") as service,
        ):
            response = self._request(
                "/api/system-daily-checks/today/submit",
                method="POST",
                json={
                    "sucursal_id": 999,
                    "performed_by_user_id": 999,
                    "business_date": "2099-01-01",
                    "answers": [],
                    "general_status": "NORMAL",
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json()["code"],
            "SYSTEM_DAILY_CHECK_VALIDATION_ERROR",
        )
        self.assertIn(
            "controlados por el servidor",
            response.get_json()["detail"],
        )
        service.assert_not_called()
        self.session.rollback.assert_called_once_with()

    def test_submit_uses_query_branch_context_and_commits(self):
        check = SimpleNamespace(
            id=44,
            sucursal_id=11,
            business_date=date(2026, 10, 9),
            performed_by_user_id=self.actor.id,
            general_status="MINOR_FAILURE",
            submitted_at=datetime(
                2026,
                10,
                9,
                16,
                0,
                tzinfo=timezone.utc,
            ),
        )
        body = {
            "answers": [
                {
                    "question_key": "GASCA_WORKING",
                    "answer": "NO",
                    "issue": {
                        "reported_to_support": True,
                        "description": "Gasca no abre.",
                    },
                }
            ],
            "general_status": "MINOR_FAILURE",
        }

        with (
            patch.object(
                routes.UserORM,
                "get_by_id",
                return_value=self.actor,
            ),
            patch.object(
                routes,
                "submit_today",
                return_value=check,
            ) as service,
        ):
            response = self._request(
                "/api/system-daily-checks/today/submit?sucursal_id=11",
                method="POST",
                json=body,
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.get_json(),
            {
                "id": 44,
                "sucursal_id": 11,
                "business_date": "2026-10-09",
                "performed_by_user_id": self.actor.id,
                "general_status": "MINOR_FAILURE",
                "submitted_at": "2026-10-09T16:00:00+00:00",
            },
        )
        service.assert_called_once_with(
            self.actor,
            body,
            requested_branch_id="11",
        )
        self.session.commit.assert_called_once_with()
        self.session.rollback.assert_not_called()

    def test_missing_user_is_not_eligible(self):
        with patch.object(
            routes.UserORM,
            "get_by_id",
            return_value=None,
        ):
            response = self._request(
                "/api/system-daily-checks/today/status"
            )

        self.assertEqual(response.status_code, 403)
        self.assertIs(response.get_json()["eligible"], False)


if __name__ == "__main__":
    unittest.main()
