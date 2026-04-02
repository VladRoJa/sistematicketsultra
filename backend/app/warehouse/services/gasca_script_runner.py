# backend/app/warehouse/services/gasca_script_runner.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import importlib
import inspect
from typing import Any, Callable

from flask import current_app

from app.warehouse.services.gasca_job_orchestrator import GascaProducerError


SUPPORTED_REPORT_TYPES = frozenset(
    {
        "reporte_direccion",
        "kpi_desempeno",
        "kpi_ventas_nuevos_socios",
        "corte_caja"
    }
)

SUPPORTED_STRATEGIES = frozenset(
    {
        "auto",
        "single_report",
        "legacy_main",
    }
)


@dataclass(slots=True)
class GascaScriptRunCommand:
    report_type_key: str
    run_mode: str
    snapshot_kind: str
    requested_by: str | None
    trigger_source: str | None
    requested_at: datetime | None


def register_gasca_script_runner(app) -> None:
    """
    Registra este runner como callable principal para el bridge.

    Uso esperado más adelante, desde init/app factory:
        register_gasca_script_runner(app)

    Esto deja resuelto:
        app.config["WAREHOUSE_GASCA_SCRIPT_RUNNER"] = run_gasca_script_report
    """
    app.config["WAREHOUSE_GASCA_SCRIPT_RUNNER"] = run_gasca_script_report


def _validate_command(command: GascaScriptRunCommand) -> None:
    if command.report_type_key not in SUPPORTED_REPORT_TYPES:
        raise ValueError(
            "El 'report_type_key' no es válido para el runner de Gasca. "
            f"Permitidos: {sorted(SUPPORTED_REPORT_TYPES)}"
        )

    if not command.run_mode:
        raise ValueError("El 'run_mode' es obligatorio.")

    if not command.snapshot_kind:
        raise ValueError("El 'snapshot_kind' es obligatorio.")


def _resolve_strategy() -> str:
    strategy = current_app.config.get("WAREHOUSE_GASCA_SCRIPT_STRATEGY", "auto")
    if not isinstance(strategy, str):
        return "auto"

    normalized = strategy.strip().lower()
    if normalized not in SUPPORTED_STRATEGIES:
        raise GascaProducerError(
            "La estrategia configurada en 'WAREHOUSE_GASCA_SCRIPT_STRATEGY' no es válida. "
            f"Permitidas: {sorted(SUPPORTED_STRATEGIES)}"
        )

    return normalized


def _import_callable(module_path: str, entrypoint_name: str) -> Callable[..., Any]:
    try:
        module = importlib.import_module(module_path)
    except Exception as exc:
        raise GascaProducerError(
            f"No se pudo importar el módulo configurado: {module_path!r}"
        ) from exc

    fn = getattr(module, entrypoint_name, None)
    if not callable(fn):
        raise GascaProducerError(
            f"El entrypoint configurado no es callable: {module_path}.{entrypoint_name}"
        )

    return fn


def _resolve_callable_from_config(
    *,
    direct_callable_key: str,
    module_key: str,
    entrypoint_key: str,
    description: str,
) -> Callable[..., Any] | None:
    direct_callable = current_app.config.get(direct_callable_key)
    if callable(direct_callable):
        return direct_callable

    module_path = current_app.config.get(module_key)
    entrypoint_name = current_app.config.get(entrypoint_key)

    if module_path is None and entrypoint_name is None:
        return None

    if not isinstance(module_path, str) or not module_path.strip():
        raise GascaProducerError(
            f"Para {description} debes configurar '{module_key}' como string."
        )

    if not isinstance(entrypoint_name, str) or not entrypoint_name.strip():
        raise GascaProducerError(
            f"Para {description} debes configurar '{entrypoint_key}' como string."
        )

    return _import_callable(module_path.strip(), entrypoint_name.strip())


def _resolve_single_report_runner() -> Callable[..., Any] | None:
    return _resolve_callable_from_config(
        direct_callable_key="WAREHOUSE_GASCA_SINGLE_REPORT_RUNNER",
        module_key="WAREHOUSE_GASCA_SINGLE_REPORT_MODULE",
        entrypoint_key="WAREHOUSE_GASCA_SINGLE_REPORT_ENTRYPOINT",
        description="single report runner de Gasca",
    )


def _resolve_legacy_main_runner() -> Callable[..., Any] | None:
    return _resolve_callable_from_config(
        direct_callable_key="WAREHOUSE_GASCA_LEGACY_MAIN_RUNNER",
        module_key="WAREHOUSE_GASCA_LEGACY_MAIN_MODULE",
        entrypoint_key="WAREHOUSE_GASCA_LEGACY_MAIN_ENTRYPOINT",
        description="legacy main runner de Gasca",
    )


def _build_callable_kwargs(command: GascaScriptRunCommand) -> dict[str, Any]:
    return {
        "report_type_key": command.report_type_key,
        "run_mode": command.run_mode,
        "snapshot_kind": command.snapshot_kind,
        "requested_by": command.requested_by,
        "trigger_source": command.trigger_source,
        "requested_at": command.requested_at,
    }


def _invoke_callable_flexibly(
    fn: Callable[..., Any],
    *,
    kwargs: dict[str, Any],
    description: str,
) -> Any:
    """
    Permite convivir con dos realidades:

    1) entrypoints nuevos que aceptan kwargs explícitos
    2) legacy main() que probablemente no acepta argumentos

    Regla:
    - si acepta **kwargs -> se mandan todos
    - si no, se mandan solo los kwargs compatibles
    - si no acepta nada, se llama sin args
    """
    try:
        signature = inspect.signature(fn)
    except (TypeError, ValueError):
        # Caso raro: builtins o callables extraños. Intentamos con kwargs completos.
        return fn(**kwargs)

    parameters = signature.parameters

    if not parameters:
        return fn()

    accepts_var_kwargs = any(
        p.kind == inspect.Parameter.VAR_KEYWORD
        for p in parameters.values()
    )
    if accepts_var_kwargs:
        return fn(**kwargs)

    accepted_kwargs: dict[str, Any] = {}
    required_params_without_default: list[str] = []

    for name, param in parameters.items():
        if param.kind not in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        ):
            continue

        if name in kwargs:
            accepted_kwargs[name] = kwargs[name]
        elif param.default is inspect.Parameter.empty:
            required_params_without_default.append(name)

    # Si el callable pide exactamente un parámetro "command", soportamos ese estilo.
    if (
        len(parameters) == 1
        and "command" in parameters
        and "command" in required_params_without_default
    ):
        return fn(kwargs)

    if required_params_without_default:
        raise GascaProducerError(
            f"El callable configurado para {description} requiere parámetros "
            f"no soportados por el runner actual: {required_params_without_default}"
        )

    return fn(**accepted_kwargs)


def _select_strategy_callable(strategy: str) -> tuple[str, Callable[..., Any]]:
    single_runner = _resolve_single_report_runner()
    legacy_runner = _resolve_legacy_main_runner()

    if strategy == "single_report":
        if single_runner is None:
            raise NotImplementedError(
                "La estrategia 'single_report' está configurada, pero no existe "
                "runner configurado. Usa alguno de estos caminos:\n"
                "1) app.config['WAREHOUSE_GASCA_SINGLE_REPORT_RUNNER'] = callable\n"
                "2) app.config['WAREHOUSE_GASCA_SINGLE_REPORT_MODULE'] + "
                "app.config['WAREHOUSE_GASCA_SINGLE_REPORT_ENTRYPOINT']"
            )
        return "single_report", single_runner

    if strategy == "legacy_main":
        if legacy_runner is None:
            raise NotImplementedError(
                "La estrategia 'legacy_main' está configurada, pero no existe "
                "runner configurado. Usa alguno de estos caminos:\n"
                "1) app.config['WAREHOUSE_GASCA_LEGACY_MAIN_RUNNER'] = callable\n"
                "2) app.config['WAREHOUSE_GASCA_LEGACY_MAIN_MODULE'] + "
                "app.config['WAREHOUSE_GASCA_LEGACY_MAIN_ENTRYPOINT']"
            )
        return "legacy_main", legacy_runner

    # strategy == "auto"
    if single_runner is not None:
        return "single_report", single_runner

    if legacy_runner is not None:
        return "legacy_main", legacy_runner

    raise NotImplementedError(
        "No hay runner configurado para Gasca. Configura alguno de estos caminos:\n"
        "A) Single report:\n"
        "   - WAREHOUSE_GASCA_SINGLE_REPORT_RUNNER\n"
        "   - o WAREHOUSE_GASCA_SINGLE_REPORT_MODULE + "
        "WAREHOUSE_GASCA_SINGLE_REPORT_ENTRYPOINT\n"
        "B) Legacy main:\n"
        "   - WAREHOUSE_GASCA_LEGACY_MAIN_RUNNER\n"
        "   - o WAREHOUSE_GASCA_LEGACY_MAIN_MODULE + "
        "WAREHOUSE_GASCA_LEGACY_MAIN_ENTRYPOINT"
    )


def _extract_requested_report_from_legacy_result(
    *,
    result: Any,
    report_type_key: str,
) -> Any:
    """
    Soporta resultados más ricos del legacy main si en el futuro decides devolver:
    - dict con reportes
    - lista de artifacts
    - dict directo del reporte solicitado

    Si no hay forma clara de extraer uno, se devuelve el resultado tal cual.
    El bridge de arriba todavía puede resolver por escaneo de disco si resulta None.
    """
    if result is None:
        return None

    if isinstance(result, dict):
        if result.get("report_type_key") == report_type_key:
            return result

        reports_block = result.get("reports")
        if isinstance(reports_block, dict) and report_type_key in reports_block:
            return reports_block[report_type_key]

        if report_type_key in result:
            return result[report_type_key]

        return result

    if isinstance(result, (list, tuple)):
        for item in result:
            if isinstance(item, dict) and item.get("report_type_key") == report_type_key:
                return item
        return None

    return result


def _run_single_report_strategy(
    *,
    runner: Callable[..., Any],
    command: GascaScriptRunCommand,
) -> Any:
    current_app.logger.info(
        "Gasca script runner using single_report strategy: report_type_key=%s",
        command.report_type_key,
    )

    kwargs = _build_callable_kwargs(command)
    return _invoke_callable_flexibly(
        runner,
        kwargs=kwargs,
        description="single_report runner",
    )


def _run_legacy_main_strategy(
    *,
    runner: Callable[..., Any],
    command: GascaScriptRunCommand,
) -> Any:
    current_app.logger.info(
        "Gasca script runner using legacy_main strategy: report_type_key=%s "
        "run_mode=%s snapshot_kind=%s",
        command.report_type_key,
        command.run_mode,
        command.snapshot_kind,
    )

    kwargs = _build_callable_kwargs(command)
    raw_result = _invoke_callable_flexibly(
        runner,
        kwargs=kwargs,
        description="legacy_main runner",
    )

    selected_result = _extract_requested_report_from_legacy_result(
        result=raw_result,
        report_type_key=command.report_type_key,
    )

    if selected_result is None:
        current_app.logger.info(
            "Legacy main no devolvió artifact directo para %s; "
            "el bridge superior intentará resolverlo por carpeta/prefijo.",
            command.report_type_key,
        )

    return selected_result


def run_gasca_script_report(
    *,
    report_type_key: str,
    run_mode: str,
    snapshot_kind: str,
    requested_by: str | None = None,
    trigger_source: str | None = None,
    requested_at: datetime | None = None,
) -> Any:
    """
    Runner wrapper principal entre Suite y el script real de Gasca.

    Estrategias soportadas:
    - auto
    - single_report
    - legacy_main

    Config keys soportadas:
    - WAREHOUSE_GASCA_SCRIPT_STRATEGY

    Single report:
    - WAREHOUSE_GASCA_SINGLE_REPORT_RUNNER
    - WAREHOUSE_GASCA_SINGLE_REPORT_MODULE
    - WAREHOUSE_GASCA_SINGLE_REPORT_ENTRYPOINT

    Legacy main:
    - WAREHOUSE_GASCA_LEGACY_MAIN_RUNNER
    - WAREHOUSE_GASCA_LEGACY_MAIN_MODULE
    - WAREHOUSE_GASCA_LEGACY_MAIN_ENTRYPOINT
    """
    command = GascaScriptRunCommand(
        report_type_key=report_type_key,
        run_mode=run_mode,
        snapshot_kind=snapshot_kind,
        requested_by=requested_by,
        trigger_source=trigger_source,
        requested_at=requested_at,
    )
    _validate_command(command)

    strategy = _resolve_strategy()
    resolved_strategy, runner = _select_strategy_callable(strategy)

    current_app.logger.info(
        "Gasca script runner dispatch: strategy=%s report_type_key=%s run_mode=%s snapshot_kind=%s runner=%s",
        resolved_strategy,
        command.report_type_key,
        command.run_mode,
        command.snapshot_kind,
        getattr(runner, "__name__", runner.__class__.__name__),
    )

    try:
        if resolved_strategy == "single_report":
            return _run_single_report_strategy(runner=runner, command=command)

        if resolved_strategy == "legacy_main":
            return _run_legacy_main_strategy(runner=runner, command=command)

        raise GascaProducerError(
            f"Estrategia no soportada resuelta internamente: {resolved_strategy!r}"
        )
    except NotImplementedError:
        raise
    except GascaProducerError:
        raise
    except Exception as exc:
        raise GascaProducerError(
            f"Falló la ejecución del runner del script Gasca para {command.report_type_key!r}."
        ) from exc