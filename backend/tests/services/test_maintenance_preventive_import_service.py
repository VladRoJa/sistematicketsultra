import io
import unittest

from openpyxl import Workbook

from app.services.maintenance_preventive_import_service import (
    TEMPLATE_HEADERS,
    build_preventive_template_xlsx,
    parse_preventive_import,
)
from app.services.maintenance_preventive_service import MaintenancePreventiveError


class MaintenancePreventiveImportServiceTest(unittest.TestCase):
    def test_official_template_roundtrips_expected_headers(self):
        content = build_preventive_template_xlsx()

        parsed = parse_preventive_import(
            filename="plantilla_programacion_preventiva.xlsx",
            content=content,
        )

        self.assertEqual(len(parsed["rows"]), 1)
        row = parsed["rows"][0]
        self.assertEqual(row["source_row_number"], 2)
        self.assertEqual(row["sucursal"], "VILLAS DEL REY")
        self.assertEqual(row["codigo_equipo"], "04CC01")
        self.assertEqual(row["fecha_programada"], "2026-09-20")
        self.assertEqual(
            row["actividad"],
            "Mantenimiento preventivo general",
        )
        self.assertEqual(row["responsable"], "TECNICO_PM")
        self.assertEqual(len(parsed["sha256"]), 64)

    def test_csv_accepts_accented_official_headers(self):
        csv_content = (
            "Sucursal,Código equipo,Fecha programada,Actividad,"
            "Responsable,Observaciones\n"
            "VILLAS DEL REY,04CC01,2026-09-20,"
            "Mantenimiento general,TECNICO_PM,Sin novedad\n"
        ).encode("utf-8")

        parsed = parse_preventive_import(
            filename="preventivos.csv",
            content=csv_content,
        )

        self.assertEqual(len(parsed["rows"]), 1)
        self.assertEqual(
            parsed["rows"][0]["observaciones"],
            "Sin novedad",
        )

    def test_missing_required_header_is_rejected(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(
            [
                "Sucursal",
                "Código equipo",
                "Fecha programada",
                "Actividad",
                # Responsable omitido a propósito.
                "Observaciones",
            ]
        )
        sheet.append(
            [
                "VILLAS DEL REY",
                "04CC01",
                "2026-09-20",
                "Mantenimiento",
                "",
            ]
        )

        stream = io.BytesIO()
        workbook.save(stream)
        workbook.close()

        with self.assertRaisesRegex(
            MaintenancePreventiveError,
            "Responsable",
        ):
            parse_preventive_import(
                filename="incompleta.xlsx",
                content=stream.getvalue(),
            )

    def test_unsupported_extension_is_rejected(self):
        with self.assertRaisesRegex(
            MaintenancePreventiveError,
            "Formato no soportado",
        ):
            parse_preventive_import(
                filename="preventivos.xls",
                content=b"legacy",
            )

    def test_template_contract_has_exact_column_order(self):
        self.assertEqual(
            TEMPLATE_HEADERS,
            (
                "Sucursal",
                "Código equipo",
                "Fecha programada",
                "Actividad",
                "Responsable",
                "Observaciones",
            ),
        )


if __name__ == "__main__":
    unittest.main()
