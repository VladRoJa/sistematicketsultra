import hashlib
import unittest
from io import BytesIO
from unittest.mock import patch

from PIL import Image

from app.services.ticket_attachment_image_service import (
    MAX_TICKET_ATTACHMENT_BYTES,
    validate_ticket_attachment_image,
)


def _make_image_bytes(
    image_format: str,
    *,
    size=(40, 30),
) -> bytes:
    image = Image.new(
        "RGB",
        size,
        (120, 80, 40),
    )

    buffer = BytesIO()
    image.save(
        buffer,
        format=image_format,
    )

    return buffer.getvalue()


class TicketAttachmentImageServiceTest(unittest.TestCase):
    def test_png_is_validated_without_modifying_bytes(self):
        content = _make_image_bytes(
            "PNG",
            size=(320, 180),
        )

        result = validate_ticket_attachment_image(
            content=content,
            original_filename=r"C:\fakepath\arte-final.PNG",
            declared_mime_type="image/png",
        )

        self.assertEqual(
            result.original_filename,
            "arte-final.PNG",
        )
        self.assertEqual(result.format, "PNG")
        self.assertEqual(result.mime_type, "image/png")
        self.assertEqual(result.extension, ".png")
        self.assertEqual(result.width, 320)
        self.assertEqual(result.height, 180)
        self.assertEqual(result.size_bytes, len(content))
        self.assertEqual(result.content, content)
        self.assertEqual(
            result.sha256,
            hashlib.sha256(content).hexdigest(),
        )
        self.assertEqual(
            result.optimization_mode,
            "original",
        )

    def test_jpeg_is_validated(self):
        content = _make_image_bytes(
            "JPEG",
            size=(60, 90),
        )

        result = validate_ticket_attachment_image(
            content=content,
            original_filename="foto.jpeg",
            declared_mime_type="image/jpeg",
        )

        self.assertEqual(result.format, "JPEG")
        self.assertEqual(result.mime_type, "image/jpeg")
        self.assertEqual(result.extension, ".jpg")
        self.assertEqual(result.width, 60)
        self.assertEqual(result.height, 90)

    def test_webp_is_validated(self):
        content = _make_image_bytes(
            "WEBP",
            size=(75, 50),
        )

        result = validate_ticket_attachment_image(
            content=content,
            original_filename="diseno.webp",
            declared_mime_type="image/webp",
        )

        self.assertEqual(result.format, "WEBP")
        self.assertEqual(result.mime_type, "image/webp")
        self.assertEqual(result.extension, ".webp")
        self.assertEqual(result.width, 75)
        self.assertEqual(result.height, 50)

    def test_fake_image_is_rejected(self):
        with self.assertRaisesRegex(
            ValueError,
            "no es una imagen",
        ):
            validate_ticket_attachment_image(
                content=b"this-is-not-an-image",
                original_filename="archivo.png",
                declared_mime_type="image/png",
            )

    def test_extension_mismatch_is_rejected(self):
        content = _make_image_bytes("PNG")

        with self.assertRaisesRegex(
            ValueError,
            "extensión",
        ):
            validate_ticket_attachment_image(
                content=content,
                original_filename="disfraz.jpg",
                declared_mime_type="image/png",
            )

    def test_declared_mime_mismatch_is_rejected(self):
        content = _make_image_bytes("JPEG")

        with self.assertRaisesRegex(
            ValueError,
            "MIME",
        ):
            validate_ticket_attachment_image(
                content=content,
                original_filename="foto.jpg",
                declared_mime_type="image/png",
            )

    def test_size_limit_is_checked_before_decode(self):
        content = b"x" * (
            MAX_TICKET_ATTACHMENT_BYTES + 1
        )

        with self.assertRaisesRegex(
            ValueError,
            "15 MB",
        ):
            validate_ticket_attachment_image(
                content=content,
                original_filename="grande.jpg",
                declared_mime_type="image/jpeg",
            )

    def test_decompression_bomb_warning_is_rejected(self):
        content = _make_image_bytes(
            "PNG",
            size=(20, 20),
        )

        with patch.object(
            Image,
            "MAX_IMAGE_PIXELS",
            100,
        ):
            with self.assertRaisesRegex(
                ValueError,
                "límites seguros",
            ):
                validate_ticket_attachment_image(
                    content=content,
                    original_filename="grande.png",
                    declared_mime_type="image/png",
                )


if __name__ == "__main__":
    unittest.main()
