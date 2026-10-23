"""M2: validar contrato de captura multiaparato y rechazo sin persistencia."""

import io
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

from app.models.ticket_model import Ticket
from app.routes import ticket_routes
from app.services import ticket_tapizado_service as tapizado


def payload_valido(**extra):
    data = {
        "descripcion": "Tapizar tres máquinas",
        "departamento_id": 1,
        "criticidad": 3,
        "clasificacion_id": 487,
        "sucursal_id_destino": 4,
        "tipo_trabajo": "TAPIZADO",
        "aparatos_ids": [431, 432, 433],
    }
    data.update(extra)
    return data


class PayloadTapizadoM2Test(unittest.TestCase):
    def test_legacy_no_envia_datos_multiequipo(self):
        self.assertEqual(
            tapizado.normalizar_payload_tapizado({"aparato_id": 431}),
            (None, None),
        )

    def test_normalizar_ids_y_principal(self):
        self.assertEqual(
            tapizado.normalizar_payload_tapizado(
                payload_valido(aparatos_ids=[431, "432", 433], aparato_id="431")
            ),
            ("TAPIZADO", [431, 432, 433]),
        )

    def test_lista_vacia_o_de_mas_de_cincuenta_rechazada(self):
        for ids in ([], list(range(1, 52)), "431,432", None, {}):
            with self.subTest(ids=repr(ids)[:30]):
                with self.assertRaises(ValueError):
                    tapizado.normalizar_payload_tapizado(
                        payload_valido(aparatos_ids=ids)
                    )

    def test_id_duplicado_rechazado(self):
        with self.assertRaisesRegex(ValueError, "duplicados"):
            tapizado.normalizar_payload_tapizado(
                payload_valido(aparatos_ids=[431, "431"])
            )

    def test_ids_invalidos_rechazados(self):
        for invalid in (True, False, -1, 0, 431.0, "431.0", "hola", None):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    tapizado.normalizar_payload_tapizado(
                        payload_valido(aparatos_ids=[invalid])
                    )

    def test_rechaza_aparato_principal_diferente(self):
        with self.assertRaisesRegex(ValueError, "debe coincidir"):
            tapizado.normalizar_payload_tapizado(
                payload_valido(aparato_id=432)
            )

    def test_rechaza_tipo_no_habilitado_y_multiseleccion_sin_tipo(self):
        for p in (
            payload_valido(tipo_trabajo="GENERAL"),
            payload_valido(tipo_trabajo=None),
            payload_valido(tipo_trabajo="tapizado"),
        ):
            with self.subTest(p=p.get("tipo_trabajo")):
                with self.assertRaises(ValueError):
                    tapizado.normalizar_payload_tapizado(p)

    def test_no_se_puede_inyectar_tipo_trabajo_sin_lista(self):
        with self.assertRaises(ValueError):
            tapizado.normalizar_payload_tapizado(
                {"tipo_trabajo": "TAPIZADO", "aparato_id": 431}
            )

    def test_migration_and_orm_type(self):
        column = Ticket.__table__.c.tipo_trabajo
        self.assertTrue(column.nullable)
        self.assertEqual(column.type.length, 24)


class EndpointTapizadoM2Test(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.user = SimpleNamespace(
            rol="GERENTE",
            sucursal_id=4,
            username="gerente_tester",
        )
        self.creado = SimpleNamespace(
            id=90001,
            aparato_id=431,
            historial_fechas=None,
        )
        self.patches = [
            patch.object(ticket_routes, "get_jwt_identity", return_value=10),
            patch.object(ticket_routes.UserORM, "get_by_id", return_value=self.user),
            patch.object(
                ticket_routes, "is_regional_maintenance_lead",
                return_value=False,
            ),
            patch.object(ticket_routes, "CatalogoClasificacion"),
            patch.object(ticket_routes, "InventarioGeneral"),
            patch.object(ticket_routes, "InventarioSucursal"),
            patch.object(ticket_routes.Ticket, "create_ticket", return_value=self.creado),
            patch.object(ticket_routes.db, "session"),
            patch.object(tapizado, "flag_modified"),
            patch.object(ticket_routes, "pick_recipients", return_value=[]),
        ]
        self.started = [p.start() for p in self.patches]
        self.catalogo = self.started[3]
        self.inventario = self.started[4]
        self.sucursal = self.started[5]
        self.create = self.started[6]
        self.session = self.started[7]

        self.catalogo.query.get.return_value = SimpleNamespace(
            id=487, departamento_id=1, padre=None
        )
        self.inventario.query.get.side_effect = (
            lambda equipment_id: SimpleNamespace(id=equipment_id, tipo="aparatos")
        )
        self.sucursal.query.filter_by.return_value.first.return_value = (
            SimpleNamespace(inventario_id=431, sucursal_id=4)
        )

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()

    def enviar(self, data=None, *, imagen=False):
        data = payload_valido() if data is None else data
        kwargs = (
            {
                "data": {
                    "payload": json.dumps(data),
                    "image": (io.BytesIO(b"PNG-FALSO"), "foto.png"),
                },
                "content_type": "multipart/form-data",
            }
            if imagen else {"json": data}
        )
        with self.app.test_request_context(
            "/api/tickets/create", method="POST", **kwargs
        ):
            return ticket_routes.create_ticket.__wrapped__()

    def test_creacion_json_en_una_transaccion_con_tres_aparatos(self):
        response, status = self.enviar()
        self.assertEqual(status, 201)
        self.assertEqual(response.get_json()["aparatos_ids"], [431, 432, 433])
        self.assertEqual(response.get_json()["aparato_id"], 431)
        self.assertEqual(response.get_json()["tipo_trabajo"], "TAPIZADO")
        self.assertFalse(self.create.call_args.kwargs["commit"])
        self.assertEqual(self.create.call_args.kwargs["tipo_trabajo"], "TAPIZADO")
        self.assertEqual(self.create.call_args.kwargs["aparato_id"], 431)
        self.session.add_all.assert_called_once()
        links = self.session.add_all.call_args.args[0]
        self.assertEqual([x.ticket_id for x in links], [90001] * 3)
        self.assertEqual([x.inventario_id for x in links], [431, 432, 433])
        self.assertEqual(self.creado.historial_fechas[-1]["cambiadoPor"], "gerente_tester")
        self.assertEqual(self.creado.historial_fechas[-1]["aparatos_ids_nuevos"], [431, 432, 433])
        self.session.flush.assert_called_once()
        self.session.commit.assert_called_once()

    def test_con_imagen_no_hace_commit_antes_del_servicio(self):
        with patch.object(
            ticket_routes, "create_ticket_image_attachment"
        ) as attachment:
            _, status = self.enviar(imagen=True)
        self.assertEqual(status, 201)
        self.assertFalse(self.create.call_args.kwargs["commit"])
        attachment.assert_called_once()
        self.assertEqual(attachment.call_args.kwargs["ticket_id"], 90001)
        # En el flujo real, el servicio de adjuntos hace el único commit.
        self.session.commit.assert_not_called()

    def test_aparato_inexistente_no_crea_ticket(self):
        self.inventario.query.get.side_effect = (
            lambda x: None if x == 432 else SimpleNamespace(id=x, tipo="aparatos")
        )
        response, status = self.enviar()
        self.assertEqual(status, 400)
        self.assertIn("Aparato 432", response.get_json()["mensaje"])
        self.create.assert_not_called()
        self.session.add_all.assert_not_called()

    def test_aparato_fuera_de_sucursal_no_crea_ticket(self):
        self.sucursal.query.filter_by.return_value.first.side_effect = [
            SimpleNamespace(inventario_id=431, sucursal_id=4),
            None,
        ]
        response, status = self.enviar()
        self.assertEqual(status, 400)
        self.assertIn("Aparato 432", response.get_json()["mensaje"])
        self.create.assert_not_called()

    def test_no_admite_tapizado_en_edificio(self):
        self.catalogo.query.get.return_value = SimpleNamespace(
            id=34, departamento_id=1, padre=None
        )
        response, status = self.enviar(payload_valido(clasificacion_id=34))
        self.assertEqual(status, 400)
        self.assertIn("solo está permitido", response.get_json()["mensaje"])
        self.create.assert_not_called()

    def test_no_admite_tapizado_en_sistemas(self):
        response, status = self.enviar(payload_valido(departamento_id=7))
        self.assertEqual(status, 400)
        self.create.assert_not_called()

    def test_no_admite_multiselect_sin_tipo(self):
        response, status = self.enviar(payload_valido(tipo_trabajo=None))
        self.assertEqual(status, 400)
        self.create.assert_not_called()

    def test_no_admite_ids_duplicados_antes_de_escribir(self):
        response, status = self.enviar(
            payload_valido(aparatos_ids=[431, 431])
        )
        self.assertEqual(status, 400)
        self.create.assert_not_called()

    def test_aparato_de_sucursal_propia_del_gerente(self):
        self.assertEqual(self.enviar()[1], 201)
        self.assertEqual(
            self.sucursal.query.filter_by.call_args.kwargs["sucursal_id"], 4
        )

    def test_error_en_alta_de_vinculos_hace_rollback(self):
        with patch.object(
            ticket_routes, "registrar_vinculos_tapizado",
            side_effect=RuntimeError("fallo controlado"),
        ), patch.object(
            ticket_routes, "manejar_error",
            return_value=("ERROR", 500),
        ):
            self.assertEqual(self.enviar()[1], 500)
        self.session.rollback.assert_called()

    def test_error_de_adjunto_no_deja_ticket_parcial(self):
        with patch.object(
            ticket_routes, "create_ticket_image_attachment",
            side_effect=ValueError("imagen inválida"),
        ):
            response, status = self.enviar(imagen=True)
        self.assertEqual(status, 400)
        self.session.rollback.assert_called()
        self.session.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
