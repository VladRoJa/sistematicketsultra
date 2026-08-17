import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from flask import Flask

from app.routes import ticket_routes


def _unwrap(fn):
    while hasattr(fn, "__wrapped__"):
        fn = fn.__wrapped__
    return fn


class _FakeColumn:
    def desc(self):
        return "id_desc"


class _FakeQuery:
    def __init__(self, tickets):
        self.tickets = tickets

    def count(self):
        return len(self.tickets)

    def order_by(self, *_args):
        return self

    def limit(self, _limit):
        return self

    def offset(self, _offset):
        return self

    def all(self):
        return self.tickets


class _FakeTicket:
    def __init__(
        self,
        ticket_id: int,
        estado: str,
    ):
        self.id = ticket_id
        self.estado = estado

    def to_dict(self):
        return {
            "id": self.id,
            "estado": self.estado,
        }


class TicketAllAttachmentFlagTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)

        self.user = SimpleNamespace(
            id=1,
            username="admin_test",
        )

        self.ticket_with_image = _FakeTicket(
            137,
            "finalizado",
        )
        self.ticket_without_image = _FakeTicket(
            138,
            "finalizado",
        )

        self.query = _FakeQuery([
            self.ticket_with_image,
            self.ticket_without_image,
        ])

    def test_all_preserves_attachment_flag_for_finalized_ticket(self):
        attachment_ids = {137}

        with (
            patch.object(
                ticket_routes,
                "get_jwt_identity",
                return_value="1",
            ),
            patch.object(
                ticket_routes.UserORM,
                "get_by_id",
                return_value=self.user,
            ),
            patch.object(
                ticket_routes,
                "filtrar_tickets_por_usuario",
                return_value=self.query,
            ),
            patch.object(
                ticket_routes,
                "_apply_ticket_year_scope",
                return_value=(self.query, "2026"),
            ),
            patch.object(
                ticket_routes,
                "_get_ticket_ids_with_active_attachments",
                return_value=attachment_ids,
            ) as attachment_mock,
            patch.object(
                ticket_routes,
                "Ticket",
                SimpleNamespace(
                    id=_FakeColumn(),
                ),
            ),
        ):
            with self.app.test_request_context(
                "/api/tickets/all"
                "?limit=1000&offset=0&year=2026",
                method="GET",
            ):
                response, status = _unwrap(
                    ticket_routes.get_tickets
                )()

        self.assertEqual(status, 200)

        payload = response.get_json()

        self.assertEqual(
            payload["total_tickets"],
            2,
        )

        by_id = {
            item["id"]: item
            for item in payload["tickets"]
        }

        self.assertEqual(
            by_id[137]["estado"],
            "finalizado",
        )
        self.assertTrue(
            by_id[137]["has_attachment"],
        )

        self.assertEqual(
            by_id[138]["estado"],
            "finalizado",
        )
        self.assertFalse(
            by_id[138]["has_attachment"],
        )

        attachment_mock.assert_called_once_with(
            [137, 138]
        )


if __name__ == "__main__":
    unittest.main()
