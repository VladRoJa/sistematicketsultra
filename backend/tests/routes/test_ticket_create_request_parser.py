import json
import unittest
from io import BytesIO

from app import create_app
from app.routes.ticket_routes import (
    _parse_create_ticket_request,
)


class TicketCreateRequestParserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()

    def test_legacy_json_remains_supported(self):
        payload = {
            "descripcion": "Ticket tradicional",
            "criticidad": 2,
            "necesita_refaccion": False,
        }

        with self.app.test_request_context(
            "/api/tickets/create",
            method="POST",
            json=payload,
        ):
            data, image = _parse_create_ticket_request()

        self.assertEqual(data, payload)
        self.assertIsNone(image)
        self.assertIs(
            data["necesita_refaccion"],
            False,
        )
        self.assertIsInstance(
            data["criticidad"],
            int,
        )

    def test_multipart_preserves_json_types_and_image(self):
        payload = {
            "descripcion": "Diseño marketing",
            "criticidad": 3,
            "necesita_refaccion": False,
            "aparato_id": None,
        }

        multipart_data = {
            "payload": json.dumps(payload),
            "image": (
                BytesIO(b"fake-image-bytes"),
                "arte.png",
                "image/png",
            ),
        }

        with self.app.test_request_context(
            "/api/tickets/create",
            method="POST",
            data=multipart_data,
            content_type="multipart/form-data",
        ):
            data, image = _parse_create_ticket_request()

            self.assertEqual(data, payload)
            self.assertIsNotNone(image)
            self.assertEqual(image.filename, "arte.png")
            self.assertEqual(
                image.mimetype,
                "image/png",
            )

        self.assertIs(
            data["necesita_refaccion"],
            False,
        )
        self.assertIsNone(data["aparato_id"])
        self.assertIsInstance(
            data["criticidad"],
            int,
        )

    def test_invalid_multipart_payload_is_rejected(self):
        multipart_data = {
            "payload": "{not-json",
        }

        with self.app.test_request_context(
            "/api/tickets/create",
            method="POST",
            data=multipart_data,
            content_type="multipart/form-data",
        ):
            with self.assertRaisesRegex(
                ValueError,
                "JSON válido",
            ):
                _parse_create_ticket_request()

    def test_unexpected_file_field_is_rejected(self):
        multipart_data = {
            "payload": json.dumps(
                {"descripcion": "Prueba"}
            ),
            "document": (
                BytesIO(b"something"),
                "document.pdf",
                "application/pdf",
            ),
        }

        with self.app.test_request_context(
            "/api/tickets/create",
            method="POST",
            data=multipart_data,
            content_type="multipart/form-data",
        ):
            with self.assertRaisesRegex(
                ValueError,
                "archivo no permitidos",
            ):
                _parse_create_ticket_request()


if __name__ == "__main__":
    unittest.main()
