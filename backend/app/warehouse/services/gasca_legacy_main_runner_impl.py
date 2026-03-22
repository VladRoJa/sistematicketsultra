# backend/app/warehouse/services/gasca_legacy_main_runner_impl.py

from __future__ import annotations

from datetime import datetime
import importlib
from typing import Any, Callable

from flask import current_app


class GascaLegacyMainRunnerError(RuntimeError):
    """Error base del bridge hacia el main legado de Gasca."""


def register_gasca_legacy_main_runner_impl(app) -> None:
    """
    Registra esta implementación como runner real para estrategia legacy_main.

    Uso esperado más adelante en init/app factory:
        register_gasca_legacy_main_runner_impl(app)

    Esto deja resuelto:
        app.config["WAREHOUSE_GASCA_LEGACY_MAIN_RUNNER"] = run_gasca_legacy_main
    """
    app.config["WAREHOUSE_GASCA_LEGACY_MAIN_RUNNER"] = run_gasca_legacy_main


def _import_callable(module_path: str, entrypoint_name: str) -> Callable[..., Any]:
    try:
        module = importlib.import_module(module_path)
    except Exception as exc:
        raise GascaLegacyMainRunnerError(
            f"No se pudo importar el módulo legado de Gasca: {module_path!r}"
        ) from exc

    fn = getattr(module, entrypoint_name, None)
    if not callable(fn):
        raise GascaLegacyMainRunnerError(
            f"El entrypoint legado configurado no es callable: {module_path}.{entrypoint_name}"
        )

    return fn


def _resolve_legacy_main_callable() -> Callable[..., Any]:
    """
    Caminos soportados:
    1) app.config["WAREHOUSE_GASCA_LEGACY_MAIN_CALLABLE"] = callable
    2) app.config["WAREHOUSE_GASCA_LEGACY_MAIN_MODULE"] + ENTRYPOINT
    """
    direct_callable = current_app.config.get("WAREHOUSE_GASCA_LEGACY_MAIN_CALLABLE")
    if callable(direct_callable):
        return direct_callable

    module_path = current_app.config.get("WAREHOUSE_GASCA_LEGACY_MAIN_MODULE")
    entrypoint_name = current_app.config.get("WAREHOUSE_GASCA_LEGACY_MAIN_ENTRYPOINT")

    if module_path is None and entrypoint_name is None:
        raise NotImplementedError(
            "No hay main legado de Gasca configurado. "
            "Configura uno de estos caminos:\n"
            "1) app.config['WAREHOUSE_GASCA_LEGACY_MAIN_CALLABLE'] = callable\n"
            "2) app.config['WAREHOUSE_GASCA_LEGACY_MAIN_MODULE'] + "
            "app.config['WAREHOUSE_GASCA_LEGACY_MAIN_ENTRYPOINT']"
        )

    if not isinstance(module_path, str) or not module_path.strip():
        raise GascaLegacyMainRunnerError(
            "Debes configurar 'WAREHOUSE_GASCA_LEGACY_MAIN_MODULE' como string."
        )

    if not isinstance(entrypoint_name, str) or not entrypoint_name.strip():
        raise GascaLegacyMainRunnerError(
            "Debes configurar 'WAREHOUSE_GASCA_LEGACY_MAIN_ENTRYPOINT' como string."
        )

    return _import_callable(module_path.strip(), entrypoint_name.strip())


def _build_log_context(
    *,
    report_type_key: str,
    run_mode: str,
    snapshot_kind: str,
    requested_by: str | None,
    trigger_source: str | None,
    requested_at: datetime | None,
) -> dict[str, Any]:
    return {
        "report_type_key": report_type_key,
        "run_mode": run_mode,
        "snapshot_kind": snapshot_kind,
        "requested_by": requested_by,
        "trigger_source": trigger_source,
        "requested_at": requested_at.isoformat() if isinstance(requested_at, datetime) else None,
    }


def run_gasca_legacy_main(
    *,
    report_type_key: str,
    run_mode: str,
    snapshot_kind: str,
    requested_by: str | None = None,
    trigger_source: str | None = None,
    requested_at: datetime | None = None,
) -> None:
    """
    Ejecuta el main legado multi-reporte de Gasca.

    Decisión importante:
    - este runner NO intenta filtrar aquí qué reporte bajar
    - ejecuta el main legado completo
    - el bridge superior después localiza el archivo correcto por carpeta/prefijo

    Eso nos permite integrar el script actual sin reescribirlo todavía.
    """
    legacy_main = _resolve_legacy_main_callable()

    log_context = _build_log_context(
        report_type_key=report_type_key,
        run_mode=run_mode,
        snapshot_kind=snapshot_kind,
        requested_by=requested_by,
        trigger_source=trigger_source,
        requested_at=requested_at,
    )

    current_app.logger.info(
        "Executing Gasca legacy main runner: report_type_key=%s run_mode=%s snapshot_kind=%s callable=%s",
        report_type_key,
        run_mode,
        snapshot_kind,
        getattr(legacy_main, "__name__", legacy_main.__class__.__name__),
    )

    try:
        # El main legado normalmente no acepta argumentos.
        # Si en el futuro decides exponer uno que sí acepte kwargs,
        # aquí lo podemos extender. Por ahora, lo mantenemos simple y explícito.
        result = legacy_main()
    except NotImplementedError:
        raise
    except SystemExit as exc:
        # Muchos scripts legacy hacen sys.exit() al fallar.
        raise GascaLegacyMainRunnerError(
            f"El main legado de Gasca terminó con SystemExit: {exc}"
        ) from exc
    except Exception as exc:
        raise GascaLegacyMainRunnerError(
            "Falló la ejecución del main legado de Gasca."
        ) from exc

    current_app.logger.info(
        "Gasca legacy main runner finished: report_type_key=%s result_type=%s context=%s",
        report_type_key,
        type(result).__name__,
        log_context,
    )

    # Lo normal aquí es devolver None, para que el bridge superior
    # resuelva el archivo correcto por output_dir + prefijo.
    return None