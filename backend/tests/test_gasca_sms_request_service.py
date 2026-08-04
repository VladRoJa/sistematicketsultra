from __future__ import annotations

import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


BACKEND = Path(__file__).resolve().parents[1]

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


from app.models.rpa import GascaSmsRequestStatus
from app.rpa.services import (
    gasca_sms_request_service as service,
)


class _ColumnStub:
    def __init__(self, name: str) -> None:
        self.name = name

    def __eq__(self, other):
        return ("eq", self.name, other)

    def __ge__(self, other):
        return ("ge", self.name, other)

    def in_(self, values):
        return ("in", self.name, tuple(values))

    def desc(self):
        return ("desc", self.name)


class _QueryStub:
    def __init__(self, *first_results) -> None:
        self.first_results = list(first_results)
        self.filters = []
        self.orderings = []
        self.first_call_count = 0

    def filter(self, expression):
        self.filters.append(expression)
        return self

    def order_by(self, *expressions):
        self.orderings.extend(expressions)
        return self

    def first(self):
        self.first_call_count += 1

        if not self.first_results:
            raise AssertionError(
                "No se configuró otro resultado para first()."
            )

        return self.first_results.pop(0)


class _GascaSmsRequestModelStub:
    query = None

    pin_normalized = _ColumnStub(
        "pin_normalized"
    )
    requested_phone_digits = _ColumnStub(
        "requested_phone_digits"
    )
    status = _ColumnStub(
        "status"
    )
    created_at = _ColumnStub(
        "created_at"
    )
    id = _ColumnStub(
        "id"
    )


class GascaSmsRequestServiceTest(
    unittest.TestCase
):
    def test_active_duplicate_is_returned_immediately(
        self,
    ) -> None:
        active_request = SimpleNamespace(
            id=101
        )
        query = _QueryStub(
            active_request
        )
        _GascaSmsRequestModelStub.query = query

        with patch.object(
            service,
            "GascaSmsRequestORM",
            _GascaSmsRequestModelStub,
        ):
            result = (
                service
                ._find_recent_duplicate_request(
                    pin_normalized="12879",
                    requested_phone_digits=(
                        "6861234567"
                    ),
                    now=datetime(
                        2026,
                        8,
                        4,
                        18,
                        0,
                        tzinfo=timezone.utc,
                    ),
                )
            )

        self.assertIs(
            result,
            active_request,
        )
        self.assertEqual(
            query.first_call_count,
            1,
        )
        self.assertIn(
            (
                "eq",
                "requested_phone_digits",
                "6861234567",
            ),
            query.filters,
        )

    def test_recent_duplicate_uses_utc_window(
        self,
    ) -> None:
        recent_request = SimpleNamespace(
            id=102
        )
        query = _QueryStub(
            None,
            recent_request,
        )
        _GascaSmsRequestModelStub.query = query

        now = datetime(
            2026,
            8,
            4,
            18,
            0,
            tzinfo=timezone.utc,
        )

        with patch.object(
            service,
            "GascaSmsRequestORM",
            _GascaSmsRequestModelStub,
        ):
            result = (
                service
                ._find_recent_duplicate_request(
                    pin_normalized="12879",
                    requested_phone_digits=(
                        "6861234567"
                    ),
                    now=now,
                )
            )

        self.assertIs(
            result,
            recent_request,
        )
        self.assertEqual(
            query.first_call_count,
            2,
        )
        self.assertIn(
            (
                "ge",
                "created_at",
                now - timedelta(
                    minutes=(
                        service
                        .DUPLICATE_REQUEST_WINDOW_MINUTES
                    )
                ),
            ),
            query.filters,
        )

    def test_no_duplicate_returns_none(
        self,
    ) -> None:
        query = _QueryStub(
            None,
            None,
        )
        _GascaSmsRequestModelStub.query = query

        with patch.object(
            service,
            "GascaSmsRequestORM",
            _GascaSmsRequestModelStub,
        ):
            result = (
                service
                ._find_recent_duplicate_request(
                    pin_normalized="12879",
                    requested_phone_digits=(
                        "6861234567"
                    ),
                    now=datetime(
                        2026,
                        8,
                        4,
                        18,
                        0,
                        tzinfo=timezone.utc,
                    ),
                )
            )

        self.assertIsNone(result)
        self.assertEqual(
            query.first_call_count,
            2,
        )

    def test_queued_duplicate_is_recorded_as_failed(
        self,
    ) -> None:
        existing_request = SimpleNamespace(
            id=103
        )
        new_request = SimpleNamespace(
            status=None,
            user_message=None,
            internal_error=None,
            processed_at=None,
        )

        commit = Mock()
        processed_at = object()

        fake_db = SimpleNamespace(
            session=SimpleNamespace(
                commit=commit,
            ),
            func=SimpleNamespace(
                now=Mock(
                    return_value=processed_at
                ),
            ),
        )

        with (
            patch.object(
                service,
                "db",
                fake_db,
            ),
            patch.object(
                service,
                "normalize_pin",
                return_value="12879",
            ),
            patch.object(
                service,
                "validate_phone_digits",
                return_value="6861234567",
            ),
            patch.object(
                service,
                "_find_recent_duplicate_request",
                return_value=existing_request,
            ) as duplicate_finder,
            patch.object(
                service,
                "create_gasca_sms_request",
                return_value=new_request,
            ),
        ):
            result = (
                service
                .create_queued_gasca_sms_request(
                    pin_raw="12879",
                    phone_raw="6861234567",
                    motivo="SMS_NO_LLEGA",
                    requested_by_user_id=5,
                    sucursal_id=8,
                )
            )

        duplicate_finder.assert_called_once_with(
            pin_normalized="12879",
            requested_phone_digits=(
                "6861234567"
            ),
        )
        self.assertIs(
            result,
            new_request,
        )
        self.assertEqual(
            result.status,
            GascaSmsRequestStatus.FAILED,
        )
        self.assertIn(
            "existing_request_id=103",
            result.internal_error,
        )
        self.assertIs(
            result.processed_at,
            processed_at,
        )
        commit.assert_called_once_with()

    def test_synchronous_non_duplicate_is_processed(
        self,
    ) -> None:
        new_request = SimpleNamespace(
            id=104
        )
        commit = Mock()
        process_request = Mock()

        fake_db = SimpleNamespace(
            session=SimpleNamespace(
                commit=commit,
            ),
        )

        processing_date = date(
            2026,
            8,
            4,
        )

        with (
            patch.object(
                service,
                "db",
                fake_db,
            ),
            patch.object(
                service,
                "normalize_pin",
                return_value="12879",
            ),
            patch.object(
                service,
                "validate_phone_digits",
                return_value="6861234567",
            ),
            patch.object(
                service,
                "_find_recent_duplicate_request",
                return_value=None,
            ) as duplicate_finder,
            patch.object(
                service,
                "create_gasca_sms_request",
                return_value=new_request,
            ),
            patch.object(
                service,
                "process_gasca_sms_request",
                process_request,
            ),
        ):
            result = (
                service
                .create_and_process_gasca_sms_request(
                    pin_raw="12879",
                    phone_raw="6861234567",
                    motivo="SMS_NO_LLEGA",
                    requested_by_user_id=5,
                    sucursal_id=8,
                    today=processing_date,
                )
            )

        duplicate_finder.assert_called_once_with(
            pin_normalized="12879",
            requested_phone_digits=(
                "6861234567"
            ),
        )
        process_request.assert_called_once_with(
            new_request,
            today=processing_date,
        )
        commit.assert_called_once_with()
        self.assertIs(
            result,
            new_request,
        )


if __name__ == "__main__":
    unittest.main()
