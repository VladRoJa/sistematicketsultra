import json
import os
import unittest
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from flask import Flask

from app.routes import ticket_routes


def _call_create_ticket_without_jwt_wrapper():
    fn = ticket_routes.create_ticket

    while hasattr(fn, "__wrapped__"):
        fn = fn.__wrapped__

    return fn()


class TicketCreateAttachmentIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)

        self.user = SimpleNamespace(
            username="tester",
            rol="TIENDA",
            sucursal_id=7,
        )

        self.ticket = SimpleNamespace(
            id=321,
            to_dict=lambda: {"id": 321},
        )

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

        self.ticket_create_patch = patch.object(
            ticket_routes.Ticket,
            "create_ticket",
            return_value=self.ticket,
        )
        self.mock_ticket_create = (
            self.ticket_create_patch.start()
        )

        self.attachment_patch = patch.object(
            ticket_routes,
            "create_ticket_image_attachment",
        )
        self.mock_attachment = self.attachment_patch.start()

        self.session = MagicMock()
        self.db_patch = patch.object(
            ticket_routes,
            "db",
            SimpleNamespace(session=self.session),
        )
        self.db_patch.start()

        self.env_patch = patch.dict(
            os.environ,
            {
                "NOTIFY_EMAIL_ON_UPDATE": "false",
            },
        )
        self.env_patch.start()

    def tearDown(self):
        self.env_patch.stop()
        self.db_patch.stop()
        self.attachment_patch.stop()
        self.ticket_create_patch.stop()
        self.user_patch.stop()
        self.identity_patch.stop()

    def _base_payload(self):
        return {
            "descripcion": "Prueba de ticket",
            "departamento_id": 1,
            "criticidad": 2,
            "clasificacion_id": 55,
            "necesita_refaccion": False,
        }

    def test_legacy_json_keeps_historical_commit(self):
        with self.app.test_request_context(
            "/api/tickets/create",
            method="POST",
            json=self._base_payload(),
        ):
            response, status = (
                _call_create_ticket_without_jwt_wrapper()
            )

        self.assertEqual(status, 201)
        self.assertEqual(
            response.get_json()["ticket_id"],
            321,
        )

        kwargs = self.mock_ticket_create.call_args.kwargs

        self.assertIs(kwargs["commit"], True)
        self.assertEqual(
            kwargs["sucursal_id_destino"],
            7,
        )

        self.mock_attachment.assert_not_called()
        self.session.rollback.assert_not_called()

    def test_multipart_image_uses_deferred_commit(self):
        payload = self._base_payload()

        multipart = {
            "payload": json.dumps(payload),
            "image": (
                BytesIO(b"fake-image-content"),
                "arte.png",
                "image/png",
            ),
        }

        with self.app.test_request_context(
            "/api/tickets/create",
            method="POST",
            data=multipart,
            content_type="multipart/form-data",
        ):
            response, status = (
                _call_create_ticket_without_jwt_wrapper()
            )

        self.assertEqual(status, 201)

        kwargs = self.mock_ticket_create.call_args.kwargs
        self.assertIs(kwargs["commit"], False)

        self.mock_attachment.assert_called_once_with(
            ticket_id=321,
            content=b"fake-image-content",
            original_filename="arte.png",
            declared_mime_type="image/png",
        )

        self.session.rollback.assert_not_called()

    def test_rejected_image_rolls_back_ticket(self):
        self.mock_attachment.side_effect = ValueError(
            "Imagen inválida para prueba"
        )

        multipart = {
            "payload": json.dumps(
                self._base_payload()
            ),
            "image": (
                BytesIO(b"invalid-image"),
                "arte.png",
                "image/png",
            ),
        }

        with self.app.test_request_context(
            "/api/tickets/create",
            method="POST",
            data=multipart,
            content_type="multipart/form-data",
        ):
            response, status = (
                _call_create_ticket_without_jwt_wrapper()
            )

        self.assertEqual(status, 400)
        self.assertEqual(
            response.get_json()["mensaje"],
            "Imagen inválida para prueba",
        )

        kwargs = self.mock_ticket_create.call_args.kwargs
        self.assertIs(kwargs["commit"], False)

        self.session.rollback.assert_called_once_with()

    def test_oversize_upload_is_rejected_before_service(self):
        multipart = {
            "payload": json.dumps(
                self._base_payload()
            ),
            "image": (
                BytesIO(b"123456789"),
                "grande.png",
                "image/png",
            ),
        }

        with patch.object(
            ticket_routes,
            "MAX_TICKET_ATTACHMENT_BYTES",
            8,
        ):
            with self.app.test_request_context(
                "/api/tickets/create",
                method="POST",
                data=multipart,
                content_type="multipart/form-data",
            ):
                response, status = (
                    _call_create_ticket_without_jwt_wrapper()
                )

        self.assertEqual(status, 400)
        self.assertIn(
            "15 MB",
            response.get_json()["mensaje"],
        )

        kwargs = self.mock_ticket_create.call_args.kwargs
        self.assertIs(kwargs["commit"], False)

        self.mock_attachment.assert_not_called()
        self.session.rollback.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
