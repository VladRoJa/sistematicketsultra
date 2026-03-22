# backend/app/warehouse/__init__.py

from __future__ import annotations

from flask import Flask

from app.warehouse.services.gasca_extractor_adapter import (
    register_gasca_extractor_adapter,
)
from app.warehouse.services.gasca_legacy_main_runner_impl import register_gasca_legacy_main_runner_impl
from app.warehouse.services.gasca_script_bridge import (
    register_gasca_script_bridge,
)
from app.warehouse.services.gasca_script_runner import (
    register_gasca_script_runner,
)
from app.warehouse.services.warehouse_upload_creator import (
    register_warehouse_upload_creator,
)
from app.warehouse.services.reporte_direccion_ingestion_service import (
    register_reporte_direccion_ingestor,
)
from app.warehouse.services.reporte_direccion_parser import (
    register_reporte_direccion_parser,
)
from app.warehouse.services.reporte_direccion_repository import (
    register_reporte_direccion_repository,
)
from app.warehouse.services.warehouse_upload_creator_existing_service import register_warehouse_upload_creator_existing_service_impl
from app.warehouse.services.warehouse_upload_loader import register_warehouse_upload_loader
from app.warehouse.services.warehouse_upload_loader_sql import register_warehouse_upload_loader_sql_impl

WAREHOUSE_RUNTIME_HOOKS_EXTENSION_KEY = "warehouse_runtime_hooks"


def _is_runtime_hooks_registered(app: Flask) -> bool:
    return bool(app.extensions.get(WAREHOUSE_RUNTIME_HOOKS_EXTENSION_KEY))


def _mark_runtime_hooks_registered(app: Flask) -> None:
    app.extensions[WAREHOUSE_RUNTIME_HOOKS_EXTENSION_KEY] = {
        "gasca_extractor_adapter": True,
        "gasca_script_bridge": True,
        "gasca_script_runner": True,
        "warehouse_upload_creator": True,
        "reporte_direccion_ingestor": True,
        "reporte_direccion_parser": True,
        "reporte_direccion_repository": True,
    }


def register_warehouse_runtime_hooks(app: Flask) -> None:
    """
    Registra los hooks runtime base del módulo Warehouse.

    Este registro está separado del registro de blueprints para mantener
    responsabilidades limpias:

    - routes -> endpoints Flask
    - warehouse runtime hooks -> wiring interno de servicios/adaptadores

    Hooks que deja configurados:
    - app.config["WAREHOUSE_GASCA_EXTRACTOR"]
    - app.config["WAREHOUSE_GASCA_MULTI_REPORT_EXTRACTOR"]
    - app.config["WAREHOUSE_GASCA_SCRIPT_RUNNER"]
    - app.config["WAREHOUSE_INTERNAL_UPLOAD_CREATOR"]
    - app.config["WAREHOUSE_REPORTE_DIRECCION_INGESTOR"]
    - app.config["WAREHOUSE_REPORTE_DIRECCION_PARSER"]
    - app.config["WAREHOUSE_REPORTE_DIRECCION_REPOSITORY"]

    Debe llamarse una sola vez desde la app factory.
    """
    if _is_runtime_hooks_registered(app):
        app.logger.info("Warehouse runtime hooks ya estaban registrados.")
        return

    register_gasca_extractor_adapter(app)
    register_gasca_script_bridge(app)
    register_gasca_script_runner(app)
    register_gasca_legacy_main_runner_impl(app)
    register_warehouse_upload_creator(app)
    register_warehouse_upload_loader(app)
    register_warehouse_upload_loader_sql_impl(app)
    register_warehouse_upload_creator_existing_service_impl(app)
    
    register_reporte_direccion_ingestor(app)
    register_reporte_direccion_parser(app)
    register_reporte_direccion_repository(app)
    

    _mark_runtime_hooks_registered(app)

    app.logger.info("Warehouse runtime hooks registrados correctamente.")