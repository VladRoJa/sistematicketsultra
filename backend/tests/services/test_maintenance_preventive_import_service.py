import io
import unittest

from openpyxl import Workbook, load_workbook

from app.services.maintenance_preventive_import_service import (
    TEMPLATE_HEADERS,
    build_preventive_template_xlsx,
    parse_preventive_import,
)
from app.services.maintenance_preventive_service import MaintenancePreventiveError


class MaintenancePreventiveImportServiceTest(unittest.TestCase):
    def test_official_template_has_catalogs_validations_and_date_format(self):
        content = build_preventive_template_xlsx(
            sucursales=["Paseo 2000", "Pabellon rosarito"],
            responsables=["SR_MANT_TIJ", "AUX_MANT_TIJ"],
            equipos=[
                {
                    "sucursal": "Paseo 2000",
                    "codigo_interno": "09CBRLF03",
                    "nombre": "Bicicleta Recumbente",
                    "familia": "Bicicleta Recumbente",
                }
            ],
        )

        workbook = load_workbook(io.BytesIO(content))
        try:
            self.assertEqual(
                workbook.sheetnames,
                ["Programacion preventiva", "Catálogos"],
            )

            sheet = workbook["Programacion preventiva"]
            self.assertEqual(
                tuple(cell.value for cell in sheet[1]),
                TEMPLATE_HEADERS,
            )
            self.assertIsNone(sheet["A2"].value)
            self.assertEqual(sheet["C2"].number_format, "dd/mm/yyyy")
            self.assertEqual(sheet.freeze_panes, "A2")

            validations = list(
                sheet.data_validations.dataValidation
            )
            validation_types = {
                validation.type
                for validation in validations
            }
            self.assertIn("list", validation_types)
            self.assertIn("date", validation_types)

            formulas = {
                validation.formula1
                for validation in validations
                if validation.type == "list"
            }
            self.assertEqual(
                formulas,
                {"=CatalogoSucursales", "=CatalogoResponsables"},
            )

            catalogs = workbook["Catálogos"]
            self.assertEqual(catalogs["A2"].value, "Paseo 2000")
            self.assertEqual(catalogs["B2"].value, "SR_MANT_TIJ")
            self.assertEqual(catalogs["D2"].value, "Paseo 2000")
            self.assertEqual(catalogs["E2"].value, "09CBRLF03")
            self.assertEqual(
                catalogs["F2"].value,
                "Bicicleta Recumbente",
            )
            self.assertIn(
                "CatalogoSucursales",
                workbook.defined_names,
            )
            self.assertIn(
                "CatalogoResponsables",
                workbook.defined_names,
            )
        finally:
            workbook.close()

    def test_generated_template_roundtrips_dd_mm_yyyy_date(self):
        content = build_preventive_template_xlsx(
            sucursales=["Paseo 2000"],
            responsables=["SR_MANT_TIJ"],
        )
        workbook = load_workbook(io.BytesIO(content))
        sheet = workbook["Programacion preventiva"]
        sheet.append(
            [
                "Paseo 2000",
                "09CBRLF03",
                "25/09/2026",
                "Mantenimiento general",
                "SR_MANT_TIJ",
                "",
            ]
        )

        stream = io.BytesIO()
        workbook.save(stream)
        workbook.close()

        parsed = parse_preventive_import(
            filename="plantilla_programacion_preventiva.xlsx",
            content=stream.getvalue(),
        )

        self.assertEqual(len(parsed["rows"]), 1)
        self.assertEqual(
            parsed["rows"][0]["fecha_programada"],
            "2026-09-25",
        )

    def test_csv_accepts_accented_official_headers(self):
        csv_content = (
            "Sucursal,Código equipo,Fecha programada,Actividad,"
            "Responsable,Observaciones\n"
            "VILLAS DEL REY,04CC01,20/09/2026,"
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
        self.assertEqual(
            parsed["rows"][0]["fecha_programada"],
            "2026-09-20",
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
