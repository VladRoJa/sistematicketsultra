import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from flask import Flask

from app.routes import ticket_routes


def _unwrap(fn):
    while hasattr(fn, "__wrapped__"):
        fn = fn.__wrapped__
    return fn


class TicketAttachmentPrivateAccessTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)

        self.user = SimpleNamespace(
            username="tester",
            rol="TIENDA",
            sucursal_id=7,
        )

        self.ticket = SimpleNamespace(id=321)

        self.attachment = SimpleNamespace(
            id=99,
            ticket_id=321,
            original_filename="arte-final.png",
            storage_key=(
                "tickets/321/"
                "0123456789abcdef0123456789abcdef.png"
            ),
            mime_type="image/png",
            size_bytes=1234,
            width=1080,
            height=1350,
            sha256="a" * 64,
            optimization_mode="original",
            created_at=None,
            emailed_at=None,
            delete_after=None,
            deleted_at=None,
        )

        self.temp_dir = tempfile.TemporaryDirectory()

        self.env_patch = patch.dict(
            os.environ,
            {
                "TICKET_ATTACHMENT_DIR": self.temp_dir.name,
            },
        )
        self.env_patch.start()

        self.identity_patch = patch.object(
            ticket_routes,
            "get_jwt_identity",
            return_value="user-id",
        )
        self.identity_patch.start()

        self.user_patch = patch.object(
            ticket_routes.UserORM,
            "get_by_id",
            return_value=self.user,
        )
        self.user_patch.start()

        self.visible_patch = patch.object(
            ticket_routes,
            "_get_visible_ticket_for_attachment",
            return_value=self.ticket,
        )
        self.mock_visible = self.visible_patch.start()

        self.attachment_patch = patch.object(
            ticket_routes,
            "_get_ticket_attachment",
            return_value=self.attachment,
        )
        self.mock_attachment = self.attachment_patch.start()

    def tearDown(self):
        self.attachment_patch.stop()
        self.visible_patch.stop()
        self.user_patch.stop()
        self.identity_patch.stop()
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def _physical_path(self):
        root = Path(self.temp_dir.name)

        return (
            root
            / "tickets"
            / "321"
            / "0123456789abcdef0123456789abcdef.png"
        )

    def test_metadata_reports_available_file(self):
        path = self._physical_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"png-content")

        with self.app.test_request_context(
            "/api/tickets/321/attachment",
            method="GET",
        ):
            response, status = _unwrap(
                ticket_routes.get_ticket_attachment_metadata
            )(321)

        self.assertEqual(status, 200)

        data = response.get_json()

        self.assertEqual(data["id"], 99)
        self.assertEqual(
            data["original_filename"],
            "arte-final.png",
        )
        self.assertTrue(data["available"])

    def test_hidden_ticket_returns_404(self):
        self.mock_visible.return_value = None

        with self.app.test_request_context(
            "/api/tickets/321/attachment",
            method="GET",
        ):
            response, status = _unwrap(
                ticket_routes.get_ticket_attachment_metadata
            )(321)

        self.assertEqual(status, 404)
        self.assertEqual(
            response.get_json()["mensaje"],
            "Ticket no encontrado",
        )

        self.mock_attachment.assert_not_called()

    def test_file_is_served_inline_when_authorized(self):
        path = self._physical_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"png-content")

        with self.app.test_request_context(
            "/api/tickets/321/attachment/file",
            method="GET",
        ):
            response = _unwrap(
                ticket_routes.get_ticket_attachment_file
            )(321)

        try:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.mimetype,
                "image/png",
            )

            # send_file() usa direct_passthrough para que el servidor
            # transmita el archivo sin materializarlo en memoria.
            # En este test directo necesitamos desactivarlo para
            # inspeccionar los bytes.
            response.direct_passthrough = False

            self.assertEqual(
                response.get_data(),
                b"png-content",
            )
        finally:
            # En Windows el archivo permanece bloqueado mientras
            # la Response de send_file siga abierta.
            response.close()

    def test_deleted_file_returns_410(self):
        self.attachment.deleted_at = object()

        with self.app.test_request_context(
            "/api/tickets/321/attachment/file",
            method="GET",
        ):
            response, status = _unwrap(
                ticket_routes.get_ticket_attachment_file
            )(321)

        self.assertEqual(status, 410)
        self.assertIn(
            "retención",
            response.get_json()["mensaje"],
        )


if __name__ == "__main__":
    unittest.main()
