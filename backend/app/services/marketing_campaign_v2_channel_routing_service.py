"""Audited Campaign V2 cross-branch sender routing, frozen before dispatch.

Original commercial branch is immutable; the alternate sender is a separate
existing iVentas binding. Do not modify unique channel ownership or old frozen
campaigns. The one approved restricted-channel exception is Independencia -> TEC.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from app.models.marketing import MarketingCampaignV2ChannelBindingORM as Binding

METADATA_KEY = "dispatch_via_binding_id"
SNAPSHOT_KEY = "dispatch_channel_routing"
SNAPSHOT_VERSION = "source-sender-v1"
SOURCE = "INDEPENDENCIA"
SENDER = "TEC_MXL"
ALLOWED_ROUTES = frozenset({(SOURCE, SENDER)})


class CampaignV2SenderRoutingConflict(ValueError):
    pass


def _canonical(value: Any) -> str:
    return str(value or "").strip().upper().replace("-", "_").replace(" ", "_")


def _required_binding(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise CampaignV2SenderRoutingConflict(f"{label} debe ser binding_id positivo.")
    return value


def validate_sender_route(source: Any, sender: Any) -> None:
    if (source is None or sender is None or
            _canonical(source.sucursal_canon), _canonical(sender.sucursal_canon)) not in ALLOWED_ROUTES:
        raise CampaignV2SenderRoutingConflict(
            "Solo está autorizada la ruta INDEPENDENCIA -> TEC_MXL."
        )
    if (str(source.provider) != "IVENTAS" or
            str(sender.provider) != "IVENTAS" or
            not bool(source.is_active) or not bool(source.is_default) or
            not bool(sender.is_active) or not bool(sender.is_default) or
            int(source.id) == int(sender.id)):
        raise CampaignV2SenderRoutingConflict(
            "La ruta necesita ambos bindings iVentas activos, predeterminados y distintos."
        )


def validate_binding_route_metadata(
    *, source: Any, metadata: Mapping[str, Any], session: Any,
) -> None:
    if METADATA_KEY not in metadata:
        return
    binding_id = _required_binding(metadata[METADATA_KEY], METADATA_KEY)
    sender = session.get(Binding, binding_id)
    validate_sender_route(source, sender)


def capture_sender_routes(
    *, session: Any, recipient_origins: Iterable[Any],
) -> dict[str, Any] | None:
    """Snapshot only for new frozen cohorts containing Independencia.

    No route configured => no added data, leaving all existing contracts intact.
    """
    if SOURCE not in {_canonical(value) for value in recipient_origins}:
        return None
    source = session.query(Binding).filter(
        Binding.provider == "IVENTAS",
        Binding.sucursal_canon == SOURCE,
        Binding.is_active.is_(True),
        Binding.is_default.is_(True),
    ).one_or_none()
    if source is None:
        # Original dispatch preflight will handle missing source channel.
        return None
    metadata = dict(source.metadata_json or {})
    if METADATA_KEY not in metadata:
        return None
    target_id = _required_binding(metadata[METADATA_KEY], METADATA_KEY)
    target = session.get(Binding, target_id)
    validate_sender_route(source, target)
    return {
        "version": SNAPSHOT_VERSION,
        "routes": {
            SOURCE: {
                "source_binding_id": int(source.id),
                "source_sucursal_id": int(source.sucursal_id),
                "outbound_binding_id": int(target.id),
                "outbound_sucursal_canon": str(target.sucursal_canon),
                "outbound_channel_id": str(target.provider_channel_id),
            }
        },
    }


def resolve_sender_binding(
    *, snapshot: Any, source_binding: Any, branch: Any, session: Any,
) -> tuple[Any, str | None]:
    """Returns real transport binding while preserving branch as the origin.

    A saved route is not enough: fail closed if source/transport binding has
    changed, deactivated or changed channel ownership since freeze.
    """
    if snapshot is None:
        return source_binding, None
    if (not isinstance(snapshot, Mapping) or
            snapshot.get("version") != SNAPSHOT_VERSION or
            not isinstance(snapshot.get("routes"), Mapping)):
        raise CampaignV2SenderRoutingConflict("Snapshot de canal emisor inválido.")
    routes = snapshot["routes"]
    if set(routes) != {SOURCE}:
        raise CampaignV2SenderRoutingConflict("Rutas de emisor fuera de autorización.")
    key = _canonical(branch.sucursal_canon)
    if key not in routes:
        return source_binding, None
    route = routes[key]
    if not isinstance(route, Mapping):
        raise CampaignV2SenderRoutingConflict("Ruta congelada ilegible.")
    if source_binding is None:
        raise CampaignV2SenderRoutingConflict("Falta el binding original de Independencia.")
    if (int(route.get("source_binding_id") or 0) != int(source_binding.id) or
            int(route.get("source_sucursal_id") or 0) != int(branch.sucursal_id)):
        raise CampaignV2SenderRoutingConflict("Cambió el binding canónico de Independencia.")
    target_id = _required_binding(route.get("outbound_binding_id"), "outbound_binding_id")
    target = session.get(Binding, target_id)
    validate_sender_route(source_binding, target)
    if (str(target.sucursal_canon) != route.get("outbound_sucursal_canon") or
            str(target.provider_channel_id) != route.get("outbound_channel_id")):
        raise CampaignV2SenderRoutingConflict("Cambió la identidad del canal TEC_MXL.")
    return target, str(target.sucursal_canon)
