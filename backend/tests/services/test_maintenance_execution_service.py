from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from app import create_app
from app.services import maintenance_execution_service as service


class MaintenanceExecutionServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()

    def _ticket(self):
        return SimpleNamespace(
            id=500,
            tipo_mantenimiento="PREVENTIVO",
            estado="abierto",
            estado_cierre=None,
            fecha_en_progreso=None,
            fecha_finalizado=None,
            familia_equipo_id=7,
            inventario=SimpleNamespace(
                id=90,
                familia_equipo_id=7,
                codigo_interno="04CC01",
                nombre="Caminadora",
            ),
            aparato_id=90,
            sucursal_id=1000,
            sucursal_id_destino=4,
            sucursal_destino=SimpleNamespace(sucursal="VILLAS DEL REY"),
            sucursal=None,
            descripcion="Mantenimiento general",
            equipo="Caminadora",
            ubicacion=None,
            problema_detectado=None,
            necesita_refaccion=False,
            descripcion_refaccion=None,
            historial_fechas=[],
        )

    def _user(self):
        return SimpleNamespace(
            id=20,
            username="TECNICO_PM",
            sucursal_id=1000,
            department_id=1,
        )

    def test_required_checklist_items_must_be_answered(self):
        template = SimpleNamespace(
            items=[
                SimpleNamespace(
                    item_key="LIMPIEZA",
                    activo=True,
                    requerido=True,
                ),
                SimpleNamespace(
                    item_key="RUIDOS",
                    activo=True,
                    requerido=False,
                ),
            ]
        )

        with patch.object(
            service,
            "resolve_checklist",
            return_value=template,
        ):
            with self.assertRaisesRegex(
                service.MaintenanceExecutionError,
                "LIMPIEZA",
            ):
                service._validated_checks(
                    self._ticket(),
                    {"RUIDOS": "OK"},
                )

    def test_checklist_rejects_unknown_item(self):
        template = SimpleNamespace(
            items=[
                SimpleNamespace(
                    item_key="LIMPIEZA",
                    activo=True,
                    requerido=True,
                ),
            ]
        )

        with patch.object(
            service,
            "resolve_checklist",
            return_value=template,
        ):
            with self.assertRaisesRegex(
                service.MaintenanceExecutionError,
                "NO_EXISTE",
            ):
                service._validated_checks(
                    self._ticket(),
                    {
                        "LIMPIEZA": "OK",
                        "NO_EXISTE": "OK",
                    },
                )

    def test_hallazgo_can_generate_linked_corrective(self):
        ticket = self._ticket()
        user = self._user()
        fake_session = MagicMock()
        corrective = SimpleNamespace(id=700)

        with (
            patch.object(service, "_owned_ticket", return_value=ticket),
            patch.object(
                service,
                "resolve_checklist",
                return_value=None,
            ),
            patch.object(
                service,
                "_validated_checks",
                return_value={"LIMPIEZA": "OK"},
            ),
            patch.object(
                service,
                "_create_derived_corrective",
                return_value=corrective,
            ) as create_corrective,
            patch.object(
                service,
                "db",
                SimpleNamespace(session=fake_session),
            ),
        ):
            result = service.create_preventive_bitacora(
                user,
                500,
                {
                    "estado_encontrado": "REQUIERE_ATENCION",
                    "notas": "Se realizó limpieza y revisión.",
                    "checks": {"LIMPIEZA": "OK"},
                    "hallazgo_detectado": True,
                    "hallazgo_descripcion": "Banda desgastada",
                    "generar_correctivo": True,
                    "criticidad_correctivo": 2,
                },
            )

        self.assertIs(result["corrective"], corrective)
        create_corrective.assert_called_once()
        kwargs = create_corrective.call_args.kwargs
        self.assertIs(kwargs["preventive"], ticket)
        self.assertEqual(kwargs["description"], "Banda desgastada")
        self.assertEqual(ticket.estado, "en progreso")
        self.assertIsNotNone(ticket.fecha_en_progreso)

    def test_complete_requires_bitacora_by_current_technician(self):
        ticket = self._ticket()
        user = self._user()
        query = MagicMock()
        query.filter.return_value = query
        query.order_by.return_value = query
        query.first.return_value = None

        with self.app.app_context():
            with (
                patch.object(service, "_owned_ticket", return_value=ticket),
                patch.object(
                    service.PmBitacoraORM,
                    "query",
                    query,
                ),
            ):
                with self.assertRaisesRegex(
                    service.MaintenanceExecutionStateError,
                    "bitácora",
                ):
                    service.complete_preventive(user, 500)

    def test_manager_rejection_creates_new_attempt_boundary(self):
        ticket = self._ticket()
        ticket.historial_fechas = [
            {
                "evento": "rechazo_cierre_gerente",
                "fechaCambio": "2026-09-20T18:00:00+00:00",
            }
        ]

        boundary = service._last_manager_rejection_at(ticket)

        self.assertEqual(
            boundary,
            datetime(2026, 9, 20, 18, 0, tzinfo=timezone.utc),
        )
        self.assertFalse(
            service._after_attempt_boundary(
                datetime(2026, 9, 20, 17, 59, tzinfo=timezone.utc),
                boundary,
            )
        )
        self.assertTrue(
            service._after_attempt_boundary(
                datetime(2026, 9, 20, 18, 1, tzinfo=timezone.utc),
                boundary,
            )
        )

    def test_complete_allows_missing_optional_evidence(self):
        ticket = self._ticket()
        ticket.estado = "en progreso"
        user = self._user()

        bitacora = SimpleNamespace(id=900)
        bitacora_query = MagicMock()
        bitacora_query.filter.return_value = bitacora_query
        bitacora_query.order_by.return_value = bitacora_query
        bitacora_query.first.return_value = bitacora

        def record_history(**kwargs):
            ticket.historial_fechas.append(kwargs)

        ticket._agregar_evento_historial_cierre = record_history

        with self.app.app_context():
            with (
                patch.object(service, "_owned_ticket", return_value=ticket),
                patch.object(
                    service.PmBitacoraORM,
                    "query",
                    bitacora_query,
                ),
            ):
                result = service.complete_preventive(user, 500)

        self.assertIs(result, ticket)
        self.assertEqual(ticket.estado, "por_validar")
        self.assertEqual(ticket.estado_cierre, "pendiente_creador")

    def test_complete_moves_ticket_to_existing_manager_validation_flow(self):
        ticket = self._ticket()
        ticket.estado = "en progreso"
        user = self._user()
        bitacora = SimpleNamespace(id=900)
        query = MagicMock()
        query.filter.return_value = query
        query.order_by.return_value = query
        query.first.return_value = bitacora

        def record_history(**kwargs):
            ticket.historial_fechas.append(kwargs)

        ticket._agregar_evento_historial_cierre = record_history

        with self.app.app_context():
            with (
                patch.object(service, "_owned_ticket", return_value=ticket),
                patch.object(
                    service.PmBitacoraORM,
                    "query",
                    query,
                ),
            ):
                result = service.complete_preventive(user, 500)

        self.assertIs(result, ticket)
        self.assertEqual(ticket.estado, "por_validar")
        self.assertEqual(ticket.estado_cierre, "pendiente_creador")
        self.assertIsNotNone(ticket.fecha_finalizado)
        self.assertEqual(
            ticket.historial_fechas[-1]["evento"],
            "preventivo_realizado",
        )


if __name__ == "__main__":
    unittest.main()
