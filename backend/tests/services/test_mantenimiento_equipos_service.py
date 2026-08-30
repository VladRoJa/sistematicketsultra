from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.services import mantenimiento_equipos_service as service


class _QueryById:
    def __init__(self, values):
        self.values = values

    def get(self, value):
        return self.values.get(int(value))


class _QueryByFilters:
    def __init__(self, value, filters=None):
        self.value = value
        self.filters = filters or {}

    def filter_by(self, **filters):
        return _QueryByFilters(self.value, filters)

    def first(self):
        if self.value is None:
            return None
        return self.value if all(
            getattr(self.value, key, None) == expected
            for key, expected in self.filters.items()
        ) else None


class MantenimientoEquiposServiceTest(unittest.TestCase):
    def setUp(self):
        self.actor = SimpleNamespace(
            id=20,
            username="MANTENIMIENTO",
            rol="MANTENIMIENTO",
            department_id=1,
        )
        self.inventory = SimpleNamespace(id=90, familia_equipo_id=7)
        self.family = SimpleNamespace(id=7, key="CAMINADORA", activo=True)
        self.failure = SimpleNamespace(
            id=70,
            familia_equipo_id=7,
            key="BANDA_DESGASTADA",
            activo=True,
        )
        self.ticket = SimpleNamespace(
            id=300,
            aparato_id=90,
            inventario=self.inventory,
            departamento_id=1,
            estado="abierto",
            familia_equipo_id=None,
            falla_mantenimiento_id=None,
            condicion_operativa=None,
            necesita_refaccion=False,
            descripcion_refaccion=None,
            refaccion_definida_por_jefe=False,
            fecha_solucion=None,
            fecha_en_progreso=None,
            historial_fechas=[],
        )
        self.payload = {
            "fecha_solucion": "2026-09-02T07:00:00-07:00",
            "motivo": "Programación de reparación",
            "falla_mantenimiento_id": 70,
            "condicion_operativa": "NO_TRABAJA",
            "necesita_refaccion": True,
            "descripcion_refaccion": "Banda",
        }
        self.now = datetime(2026, 8, 29, 18, 0, tzinfo=timezone.utc)

    def _prepare(self, *, ticket=None, actor=None, payload=None):
        ticket = ticket or self.ticket
        actor = actor or self.actor
        payload = payload or self.payload

        with (
            patch.object(service, "_ticket_en_scope", return_value=ticket),
            patch.object(
                service,
                "FamiliaEquipoORM",
                SimpleNamespace(query=_QueryById({self.family.id: self.family})),
            ),
            patch.object(
                service,
                "FallaMantenimientoORM",
                SimpleNamespace(query=_QueryById({self.failure.id: self.failure})),
            ),
            patch.object(service, "flag_modified") as flag_modified,
        ):
            result = service.preparar_compromiso_estructurado(
                ticket.id,
                actor,
                payload,
                now=self.now,
            )

        return result, flag_modified

    def test_compromiso_toma_snapshot_de_familia_desde_aparato(self):
        result, flag_modified = self._prepare()

        self.assertIs(result, self.ticket)
        self.assertEqual(self.inventory.familia_equipo_id, 7)
        self.assertEqual(self.ticket.familia_equipo_id, 7)
        self.assertEqual(self.ticket.falla_mantenimiento_id, 70)
        self.assertEqual(self.ticket.condicion_operativa, "NO_TRABAJA")
        self.assertEqual(self.ticket.estado, "en progreso")
        self.assertEqual(self.ticket.descripcion_refaccion, "Banda")
        self.assertEqual(
            self.ticket.historial_fechas[0]["motivo"],
            "Programación de reparación",
        )
        flag_modified.assert_called_once_with(self.ticket, "historial_fechas")

    def test_familia_enviada_por_cliente_no_controla_snapshot(self):
        payload = {**self.payload, "familia_equipo_id": 999}

        self._prepare(payload=payload)

        self.assertEqual(self.inventory.familia_equipo_id, 7)
        self.assertEqual(self.ticket.familia_equipo_id, 7)

    def test_cambiar_familia_actual_no_altera_snapshot_del_ticket(self):
        self._prepare()

        self.inventory.familia_equipo_id = 8

        self.assertEqual(self.inventory.familia_equipo_id, 8)
        self.assertEqual(self.ticket.familia_equipo_id, 7)

    def test_cambio_de_compromiso_conserva_historial_anterior(self):
        self.ticket.historial_fechas = [
            {
                "fecha": "2026-08-15T14:00:00+00:00",
                "fechaCambio": "2026-08-01T18:00:00+00:00",
                "cambiadoPor": "MANTENIMIENTO",
                "motivo": "Compromiso inicial",
            }
        ]

        self._prepare()

        self.assertEqual(len(self.ticket.historial_fechas), 2)
        self.assertEqual(
            [item["motivo"] for item in self.ticket.historial_fechas],
            ["Programación de reparación", "Compromiso inicial"],
        )

    def test_falla_de_otra_familia_es_rechazada(self):
        self.failure.familia_equipo_id = 8

        with self.assertRaisesRegex(
            service.MantenimientoEquiposError,
            "no pertenece",
        ):
            self._prepare()

        self.assertEqual(self.inventory.familia_equipo_id, 7)
        self.assertIsNone(self.ticket.familia_equipo_id)

    def test_aparato_sin_familia_es_rechazado(self):
        self.inventory.familia_equipo_id = None

        with self.assertRaisesRegex(
            service.MantenimientoEquiposError,
            "Clasifícalo primero desde Inventario",
        ):
            self._prepare()

        self.assertIsNone(self.inventory.familia_equipo_id)
        self.assertIsNone(self.ticket.familia_equipo_id)
        self.assertEqual(self.ticket.estado, "abierto")

    def test_condicion_inventada_es_rechazada(self):
        payload = {**self.payload, "condicion_operativa": "PARCIAL"}

        with self.assertRaisesRegex(
            service.MantenimientoEquiposError,
            "TRABAJA o NO_TRABAJA",
        ):
            self._prepare(payload=payload)

    def test_aux_y_sr_no_pueden_capturar(self):
        for role in ("AUX_MANTENIMIENTO", "SR_MANTENIMIENTO"):
            with self.subTest(role=role):
                actor = SimpleNamespace(
                    username=role,
                    rol=role,
                    department_id=1,
                )
                with self.assertRaises(
                    service.MantenimientoEquiposAuthorizationError,
                ):
                    self._prepare(actor=actor)

    def test_mantenimiento_de_otro_departamento_no_puede_capturar(self):
        actor = SimpleNamespace(
            username="MANTENIMIENTO",
            rol="MANTENIMIENTO",
            department_id=7,
        )

        with self.assertRaises(service.MantenimientoEquiposAuthorizationError):
            self._prepare(actor=actor)

    def test_ticket_de_otro_departamento_es_rechazado(self):
        self.ticket.departamento_id = 7

        with self.assertRaises(service.MantenimientoEquiposAuthorizationError):
            self._prepare()

    def test_ticket_sin_aparato_no_exige_diagnostico(self):
        self.ticket.aparato_id = None
        self.ticket.inventario = None
        payload = {
            "fecha_solucion": self.payload["fecha_solucion"],
            "motivo": self.payload["motivo"],
        }

        result, _ = self._prepare(payload=payload)

        self.assertIs(result, self.ticket)
        self.assertEqual(self.ticket.estado, "en progreso")
        self.assertIsNone(self.ticket.familia_equipo_id)

    def test_backfill_clasifica_un_ticket_sin_cambiar_familia_actual(self):
        self.inventory.familia_equipo_id = 6

        with (
            patch.object(
                service,
                "Ticket",
                SimpleNamespace(query=_QueryById({self.ticket.id: self.ticket})),
            ),
            patch.object(
                service,
                "FamiliaEquipoORM",
                SimpleNamespace(query=_QueryByFilters(self.family)),
            ),
            patch.object(
                service,
                "FallaMantenimientoORM",
                SimpleNamespace(query=_QueryByFilters(self.failure)),
            ),
        ):
            result = service.preparar_backfill_ticket_historico(
                self.ticket.id,
                "CAMINADORA",
                "BANDA_DESGASTADA",
                "NO_TRABAJA",
            )

        self.assertIs(result, self.ticket)
        self.assertEqual(self.ticket.familia_equipo_id, 7)
        self.assertEqual(self.ticket.falla_mantenimiento_id, 70)
        self.assertEqual(self.ticket.condicion_operativa, "NO_TRABAJA")
        self.assertEqual(self.inventory.familia_equipo_id, 6)

    def test_backfill_no_sobrescribe_captura_existente(self):
        self.ticket.familia_equipo_id = 7

        with patch.object(
            service,
            "Ticket",
            SimpleNamespace(query=_QueryById({self.ticket.id: self.ticket})),
        ):
            with self.assertRaisesRegex(
                service.MantenimientoEquiposError,
                "no se sobrescribirá",
            ):
                service.preparar_backfill_ticket_historico(
                    self.ticket.id,
                    "CAMINADORA",
                    "BANDA_DESGASTADA",
                    "NO_TRABAJA",
                )

    def test_backfill_rechaza_falla_que_no_pertenece_a_familia(self):
        self.failure.familia_equipo_id = 8

        with (
            patch.object(
                service,
                "Ticket",
                SimpleNamespace(query=_QueryById({self.ticket.id: self.ticket})),
            ),
            patch.object(
                service,
                "FamiliaEquipoORM",
                SimpleNamespace(query=_QueryByFilters(self.family)),
            ),
            patch.object(
                service,
                "FallaMantenimientoORM",
                SimpleNamespace(query=_QueryByFilters(self.failure)),
            ),
        ):
            with self.assertRaisesRegex(
                service.MantenimientoEquiposNotFoundError,
                "para la familia",
            ):
                service.preparar_backfill_ticket_historico(
                    self.ticket.id,
                    "CAMINADORA",
                    "BANDA_DESGASTADA",
                    "NO_TRABAJA",
                )


if __name__ == "__main__":
    unittest.main()
