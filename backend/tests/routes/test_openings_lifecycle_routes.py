import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from flask import Flask

from app.models import OpeningStatus, SucursalOperationalStatus
from app.routes import openings_lifecycle_routes as lifecycle


class OpeningLifecycleRoutesTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)

    def _call_mark_opened(self, opening, sucursal, payload):
        session = MagicMock()
        session.get.side_effect = [opening, sucursal]
        fake_db = SimpleNamespace(session=session)

        def serialize(current_opening):
            opening_date = current_opening.actual_opening_date
            return {
                "status": current_opening.status,
                "actual_opening_date": (
                    opening_date.isoformat() if opening_date else None
                ),
                "sucursal": {
                    "operational_status": sucursal.operational_status,
                },
            }

        with self.app.test_request_context(
            "/api/openings/1/mark-opened",
            method="POST",
            json=payload,
        ):
            with (
                patch.object(lifecycle, "db", fake_db),
                patch.object(lifecycle, "_require_openings_admin", return_value=None),
                patch.object(lifecycle, "_current_user_id", return_value=99),
                patch.object(lifecycle, "_serialize_opening", side_effect=serialize),
                patch.object(lifecycle, "_audit_opening") as audit_mock,
            ):
                response, status_code = lifecycle.mark_opening_opened.__wrapped__(1)

        return response, status_code, session, audit_mock

    def test_mark_opened_activates_branch_and_sets_actual_date_atomically(self):
        opening = SimpleNamespace(
            id=1,
            sucursal_id=26,
            status=OpeningStatus.IN_PROGRESS,
            actual_opening_date=None,
            updated_by=None,
        )
        sucursal = SimpleNamespace(
            sucursal_id=26,
            operational_status=SucursalOperationalStatus.EN_APERTURA,
        )

        response, status_code, session, audit_mock = self._call_mark_opened(
            opening,
            sucursal,
            {"actual_opening_date": "2026-09-14"},
        )

        self.assertEqual(status_code, 200)
        self.assertEqual(opening.status, OpeningStatus.OPENED)
        self.assertEqual(opening.actual_opening_date, date(2026, 9, 14))
        self.assertEqual(opening.updated_by, 99)
        self.assertEqual(
            sucursal.operational_status,
            SucursalOperationalStatus.ACTIVA,
        )
        session.commit.assert_called_once_with()
        session.rollback.assert_not_called()
        audit_mock.assert_called_once()

        audit_kwargs = audit_mock.call_args.kwargs
        self.assertEqual(audit_kwargs["metadata_json"]["transition"], "MARK_OPENED")
        self.assertEqual(
            audit_kwargs["metadata_json"]["previous_operational_status"],
            SucursalOperationalStatus.EN_APERTURA,
        )
        self.assertEqual(
            audit_kwargs["metadata_json"]["new_operational_status"],
            SucursalOperationalStatus.ACTIVA,
        )
        self.assertEqual(
            response.get_json()["item"]["actual_opening_date"],
            "2026-09-14",
        )

    def test_mark_opened_rejects_non_opening_branch_status(self):
        opening = SimpleNamespace(
            id=1,
            sucursal_id=26,
            status=OpeningStatus.IN_PROGRESS,
            actual_opening_date=None,
            updated_by=None,
        )
        sucursal = SimpleNamespace(
            sucursal_id=26,
            operational_status=SucursalOperationalStatus.CANCELADA,
        )

        _, status_code, session, audit_mock = self._call_mark_opened(
            opening,
            sucursal,
            {"actual_opening_date": "2026-09-14"},
        )

        self.assertEqual(status_code, 409)
        session.commit.assert_not_called()
        audit_mock.assert_not_called()

    def test_mark_opened_requires_explicit_actual_opening_date(self):
        opening = SimpleNamespace(
            id=1,
            sucursal_id=26,
            status=OpeningStatus.IN_PROGRESS,
            actual_opening_date=None,
            updated_by=None,
        )
        sucursal = SimpleNamespace(
            sucursal_id=26,
            operational_status=SucursalOperationalStatus.EN_APERTURA,
        )

        _, status_code, session, audit_mock = self._call_mark_opened(
            opening,
            sucursal,
            {},
        )

        self.assertEqual(status_code, 400)
        session.commit.assert_not_called()
        audit_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
