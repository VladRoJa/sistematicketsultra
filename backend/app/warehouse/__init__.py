# backend/app/warehouse/__init__.py

from __future__ import annotations

from flask import Flask

from app.warehouse.services.gasca_extractor_adapter import (register_gasca_extractor_adapter,)
from app.warehouse.services.gasca_legacy_main_runner_impl import register_gasca_legacy_main_runner_impl
from app.warehouse.services.gasca_script_bridge import (register_gasca_script_bridge,)
from app.warehouse.services.gasca_script_runner import (register_gasca_script_runner,)
from app.warehouse.services.warehouse_upload_creator import (register_warehouse_upload_creator,)
from app.warehouse.services.reporte_direccion_ingestion_service import (register_reporte_direccion_ingestor,)
from app.warehouse.services.reporte_direccion_parser import (register_reporte_direccion_parser,)
from app.warehouse.services.reporte_direccion_repository import (register_reporte_direccion_repository,)
from app.warehouse.services.warehouse_upload_creator_existing_service import register_warehouse_upload_creator_existing_service_impl
from app.warehouse.services.warehouse_upload_loader import register_warehouse_upload_loader
from app.warehouse.services.warehouse_upload_loader_sql import register_warehouse_upload_loader_sql_impl
from app.warehouse.services.reporte_direccion_advisory_lock import ( register_reporte_direccion_advisory_lock,)

from app.warehouse.services.kpi_desempeno_ingestion_service import ( register_kpi_desempeno_ingestor,)
from app.warehouse.services.kpi_desempeno_repository import (register_kpi_desempeno_repository,)
from app.warehouse.services.kpi_ventas_nuevos_socios_ingestion_service import (register_kpi_ventas_nuevos_socios_ingestor,)
from app.warehouse.services.kpi_ventas_nuevos_socios_repository import (register_kpi_ventas_nuevos_socios_repository,)

from app.warehouse.services.corte_caja_parser import (register_corte_caja_parser,)
from app.warehouse.services.corte_caja_repository import (register_corte_caja_repository,)
from app.warehouse.services.corte_caja_ingestion_service import (register_corte_caja_ingestor,)

from app.warehouse.services.cargos_recurrentes_parser import (register_cargos_recurrentes_parser,)
from app.warehouse.services.cargos_recurrentes_repository import (register_cargos_recurrentes_repository,)
from app.warehouse.services.cargos_recurrentes_ingestion_service import (register_cargos_recurrentes_ingestor,)


from app.warehouse.services.kpi_daily_canonicality_resolver import (register_kpi_daily_canonicality_resolvers,)
from app.warehouse.services.gasca_single_report_runner_impl import (register_gasca_single_report_runner_impl,)





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
        "reporte_direccion_advisory_lock": True,
        "kpi_desempeno_ingestor": True,
        "kpi_desempeno_repository": True,
        "kpi_ventas_nuevos_socios_ingestor": True,
        "kpi_ventas_nuevos_socios_repository": True,
        "kpi_daily_canonicality_resolvers": True,
        "corte_caja_parser": True,
        "corte_caja_repository": True,
        "corte_caja_ingestor": True,
        "gasca_single_report_runner_impl": True,
        "cargos_recurrentes_parser": True,
        "cargos_recurrentes_repository": True,
        "cargos_recurrentes_ingestor": True,
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
    register_kpi_daily_canonicality_resolvers(app)
    
    register_reporte_direccion_ingestor(app)
    register_reporte_direccion_parser(app)
    register_reporte_direccion_repository(app)
    register_reporte_direccion_advisory_lock(app)
    
    register_kpi_desempeno_ingestor(app)
    register_kpi_desempeno_repository(app)
    register_kpi_ventas_nuevos_socios_ingestor(app)
    register_kpi_ventas_nuevos_socios_repository(app)
    
    register_corte_caja_parser(app)
    register_corte_caja_repository(app)
    register_corte_caja_ingestor(app)
    
    register_cargos_recurrentes_parser(app)
    register_cargos_recurrentes_repository(app)
    register_cargos_recurrentes_ingestor(app)
    
    register_gasca_single_report_runner_impl(app)

    _mark_runtime_hooks_registered(app)

    app.logger.info("Warehouse runtime hooks registrados correctamente.")