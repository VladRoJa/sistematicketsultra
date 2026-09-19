from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.models.ticket_model import Ticket
from app.services import maintenance_reprogram_service as service


class MaintenanceReprogramServiceTest(unittest.TestCase):
    def _user(self):
        return SimpleNamespace(
            id=10,
            username="MANT_BOSS",
            rol="MANTENIMIENTO",
            sucursal_id=1000,
            sucursales_ids=[],
        )

    def _reason(
        self,
        *,
        reason_id=1,
        key="FALTA_TECNICO",
        name="Falta de técnico",
        requires_comment=False,
    ):
        return SimpleNamespace(
            id=reason_id,
            key=key,
            nombre=name,
            requiere_comentario=requires_comment,
            activo=True,
        )

    def test_preventive_reprogram_preserves_original_date_and_writes_audit(self):
        original = datetime(2026, 9, 20, 14, 0, tzinfo=timezone.utc)
        current = datetime(2026, 9, 22, 14, 0, tzinfo=timezone.utc)

        ticket = SimpleNamespace(
            id=501,
            departamento_id=1,
            tipo_mantenimiento="PREVENTIVO",
            estado="en progreso",
            sucursal_id=4,
            sucursal_id_destino=4,
            fecha_programada_original=original,
            fecha_programada_actual=current,
            fecha_solucion=None,
            historial_fechas=[],
        )
        reason = self._reason()

        with (
            patch.object(service, "_assert_can_configure"),
            patch.object(service, "_assert_ticket_scope"),
            patch.object(
                service.db.session,
                "get",
                side_effect=[ticket, reason],
            ),
            patch.object(service.db.session, "flush"),
            patch.object(service, "flag_modified"),
        ):
            result = service.reprogramar_ticket_mantenimiento(
                self._user(),
                501,
                {
                    "nueva_fecha": "2026-09-29",
                    "reason_id": 1,
                    "comentario": "Cobertura regional",
                },
            )

        self.assertIs(result, ticket)
        self.assertEqual(ticket.fecha_programada_original, original)
        self.assertEqual(
            ticket.fecha_programada_actual.astimezone(
                service.BUSINESS_TZ
            ).date().isoformat(),
            "2026-09-29",
        )
        self.assertEqual(len(ticket.historial_fechas), 1)

        event = ticket.historial_fechas[0]
        self.assertEqual(
            event["evento"],
            "reprogramacion_mantenimiento",
        )
        self.assertEqual(event["tipo_mantenimiento"], "PREVENTIVO")
        self.assertEqual(event["motivo_key"], "FALTA_TECNICO")
        self.assertEqual(event["comentario"], "Cobertura regional")
        self.assertEqual(event["cambiadoPor"], "MANT_BOSS")
        self.assertIn("fecha_anterior", event)
        self.assertIn("fecha_nueva", event)

    def test_corrective_reprogram_preserves_original_commitment(self):
        original = datetime(2026, 9, 20, 14, 0, tzinfo=timezone.utc)
        ticket = Ticket(
            id=601,
            departamento_id=1,
            tipo_mantenimiento="CORRECTIVO",
            origen_correctivo="REACTIVO",
            estado="en progreso",
            sucursal_id=4,
            sucursal_id_destino=4,
            fecha_solucion=original,
            fecha_compromiso_original=original,
            historial_fechas=[],
        )
        reason = self._reason(
            reason_id=2,
            key="REFACCION_PENDIENTE",
            name="Refacción pendiente",
        )

        with (
            patch.object(service, "_assert_can_configure"),
            patch.object(service, "_assert_ticket_scope"),
            patch.object(
                service.db.session,
                "get",
                side_effect=[ticket, reason],
            ),
            patch.object(service.db.session, "flush"),
            patch.object(service, "flag_modified"),
        ):
            service.reprogramar_ticket_mantenimiento(
                self._user(),
                601,
                {
                    "nueva_fecha": "2026-09-30",
                    "reason_id": 2,
                },
            )

        self.assertEqual(ticket.fecha_compromiso_original, original)
        self.assertEqual(
            ticket.fecha_solucion.astimezone(
                service.BUSINESS_TZ
            ).date().isoformat(),
            "2026-09-30",
        )
        self.assertEqual(
            ticket.historial_fechas[0]["motivo_key"],
            "REFACCION_PENDIENTE",
        )

    def test_reason_can_require_comment(self):
        ticket = SimpleNamespace(
            id=701,
            departamento_id=1,
            tipo_mantenimiento="PREVENTIVO",
            estado="abierto",
            sucursal_id=4,
            sucursal_id_destino=4,
            fecha_programada_original=datetime(
                2026, 9, 20, 14, 0, tzinfo=timezone.utc
            ),
            fecha_programada_actual=datetime(
                2026, 9, 20, 14, 0, tzinfo=timezone.utc
            ),
            historial_fechas=[],
        )
        reason = self._reason(
            reason_id=6,
            key="OTRO",
            name="Otro",
            requires_comment=True,
        )

        with (
            patch.object(service, "_assert_can_configure"),
            patch.object(service, "_assert_ticket_scope"),
            patch.object(
                service.db.session,
                "get",
                side_effect=[ticket, reason],
            ),
        ):
            with self.assertRaisesRegex(
                service.MaintenanceReprogramError,
                "comentario",
            ):
                service.reprogramar_ticket_mantenimiento(
                    self._user(),
                    701,
                    {
                        "nueva_fecha": "2026-09-25",
                        "reason_id": 6,
                    },
                )

    def test_auxiliary_can_reprogram_without_configuration_access(self):
        user = SimpleNamespace(
            id=11,
            username="AUX_PM",
            rol="AUX_MANTENIMIENTO",
            sucursal_id=4,
            sucursales_ids=[4],
        )
        ticket = SimpleNamespace(
            id=750,
            departamento_id=1,
            tipo_mantenimiento="CORRECTIVO",
            estado="en progreso",
            sucursal_id=4,
            sucursal_id_destino=4,
            fecha_solucion=datetime(
                2026, 9, 20, 14, 0, tzinfo=timezone.utc
            ),
            fecha_compromiso_original=datetime(
                2026, 9, 20, 14, 0, tzinfo=timezone.utc
            ),
            historial_fechas=[],
        )
        reason = self._reason()

        with (
            patch.object(
                service.db.session,
                "get",
                side_effect=[ticket, reason],
            ),
            patch.object(service.db.session, "flush"),
            patch.object(service, "flag_modified"),
        ):
            result = service.reprogramar_ticket_mantenimiento(
                user,
                750,
                {
                    "nueva_fecha": "2026-09-22",
                    "reason_id": 1,
                },
            )

        self.assertIs(result, ticket)
        self.assertEqual(
            ticket.fecha_solucion.astimezone(
                service.BUSINESS_TZ
            ).date().isoformat(),
            "2026-09-22",
        )

        with self.assertRaises(
            service.MaintenanceReprogramAuthorizationError
        ):
            service.crear_motivo_reprogramacion(
                user,
                {
                    "key": "NO_DEBERIA",
                    "nombre": "No debería",
                },
            )

    def test_same_date_is_rejected(self):
        current = datetime(2026, 9, 20, 14, 0, tzinfo=timezone.utc)
        ticket = SimpleNamespace(
            id=801,
            departamento_id=1,
            tipo_mantenimiento="PREVENTIVO",
            estado="abierto",
            sucursal_id=4,
            sucursal_id_destino=4,
            fecha_programada_original=current,
            fecha_programada_actual=current,
            historial_fechas=[],
        )

        with (
            patch.object(service, "_assert_can_configure"),
            patch.object(service, "_assert_ticket_scope"),
            patch.object(
                service.db.session,
                "get",
                side_effect=[ticket, self._reason()],
            ),
        ):
            with self.assertRaisesRegex(
                service.MaintenanceReprogramStateError,
                "igual",
            ):
                service.reprogramar_ticket_mantenimiento(
                    self._user(),
                    801,
                    {
                        "nueva_fecha": "2026-09-20",
                        "reason_id": 1,
                    },
                )


if __name__ == "__main__":
    unittest.main()
