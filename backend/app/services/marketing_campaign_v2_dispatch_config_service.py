"""Backend-owned dispatch configuration for Campaign V2 M1."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db
from app.models.marketing import (
    MarketingCampaignV2ChannelBindingORM,
    MarketingCampaignV2TemplateORM,
)
from app.models.warehouse import TrackBranchCatalogORM


DEFAULT_PROVIDER = "IVENTAS"
ALLOWED_PURPOSES = frozenset(
    {"NEW_SALE", "REACTIVATION", "ACTIVE_MEMBERS", "UNCLASSIFIED"}
)
SUPPORTED_TEMPLATE_VARIABLE_SOURCES = frozenset(
    {
        "first_name",
        "expiration_date",
        "tariff",
        "branch",
        "member_id",
        "member_pin",
        "amount",
    }
)


class MarketingCampaignV2DispatchConfigError(RuntimeError):
    pass


class MarketingCampaignV2DispatchConfigValidationError(
    MarketingCampaignV2DispatchConfigError,
    ValueError,
):
    pass


class MarketingCampaignV2DispatchConfigConflictError(
    MarketingCampaignV2DispatchConfigError
):
    pass


class MarketingCampaignV2DispatchConfigNotFoundError(
    MarketingCampaignV2DispatchConfigError,
    LookupError,
):
    pass


def list_channel_bindings(
    *,
    provider: Any = DEFAULT_PROVIDER,
    active_only: bool = False,
    session: Any | None = None,
) -> list[dict[str, Any]]:
    active_session = session if session is not None else db.session
    normalized_provider = _normalize_provider(provider)
    query = active_session.query(MarketingCampaignV2ChannelBindingORM).filter(
        MarketingCampaignV2ChannelBindingORM.provider == normalized_provider
    )
    if active_only:
        query = query.filter(
            MarketingCampaignV2ChannelBindingORM.is_active.is_(True)
        )
    rows = query.order_by(
        MarketingCampaignV2ChannelBindingORM.sucursal_canon.asc(),
        MarketingCampaignV2ChannelBindingORM.is_default.desc(),
        MarketingCampaignV2ChannelBindingORM.id.asc(),
    ).all()
    return [_serialize_channel_binding(row) for row in rows]


def save_channel_binding(
    *,
    provider: Any,
    sucursal_id: Any,
    provider_channel_id: Any,
    is_active: Any,
    is_default: Any,
    actor_user_id: Any,
    metadata: Any = None,
    binding_id: Any = None,
    session: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    active_session = session if session is not None else db.session
    normalized_provider = _normalize_provider(provider)
    normalized_sucursal_id = _positive_int(sucursal_id, "sucursal_id")
    normalized_channel_id = _required_text(
        provider_channel_id,
        "provider_channel_id",
        255,
    )
    normalized_is_active = _strict_bool(is_active, "is_active")
    normalized_is_default = _strict_bool(is_default, "is_default")
    if not normalized_is_active:
        normalized_is_default = False
    normalized_actor = _positive_int(actor_user_id, "actor_user_id")
    normalized_metadata = _dict_value(metadata, "metadata")
    timestamp = _normalize_now(now)
    catalog = _resolve_active_catalog_branch(
        sucursal_id=normalized_sucursal_id,
        session=active_session,
    )

    row = None
    if binding_id is not None:
        normalized_binding_id = _positive_int(binding_id, "binding_id")
        row = active_session.query(MarketingCampaignV2ChannelBindingORM).filter(
            MarketingCampaignV2ChannelBindingORM.id == normalized_binding_id
        ).one_or_none()
        if row is None:
            raise MarketingCampaignV2DispatchConfigNotFoundError(
                "Channel binding Campaign V2 no encontrado."
            )

    duplicate = active_session.query(MarketingCampaignV2ChannelBindingORM).filter(
        MarketingCampaignV2ChannelBindingORM.provider == normalized_provider,
        MarketingCampaignV2ChannelBindingORM.provider_channel_id
        == normalized_channel_id,
    )
    if row is not None:
        duplicate = duplicate.filter(
            MarketingCampaignV2ChannelBindingORM.id != int(row.id)
        )
    if duplicate.first() is not None:
        raise MarketingCampaignV2DispatchConfigConflictError(
            "provider_channel_id ya está vinculado a otra configuración."
        )

    if normalized_is_default:
        current_defaults = active_session.query(
            MarketingCampaignV2ChannelBindingORM
        ).filter(
            MarketingCampaignV2ChannelBindingORM.provider == normalized_provider,
            MarketingCampaignV2ChannelBindingORM.sucursal_id
            == normalized_sucursal_id,
            MarketingCampaignV2ChannelBindingORM.is_active.is_(True),
            MarketingCampaignV2ChannelBindingORM.is_default.is_(True),
        )
        if row is not None:
            current_defaults = current_defaults.filter(
                MarketingCampaignV2ChannelBindingORM.id != int(row.id)
            )
        for current in current_defaults.all():
            current.is_default = False
            current.updated_by_user_id = normalized_actor
            current.updated_at = timestamp

    if row is None:
        row = MarketingCampaignV2ChannelBindingORM(
            provider=normalized_provider,
            sucursal_id=normalized_sucursal_id,
            sucursal_canon=str(catalog.sucursal_canon),
            provider_channel_id=normalized_channel_id,
            is_active=normalized_is_active,
            is_default=normalized_is_default,
            metadata_json=normalized_metadata,
            created_by_user_id=normalized_actor,
            updated_by_user_id=normalized_actor,
            created_at=timestamp,
            updated_at=timestamp,
        )
        active_session.add(row)
    else:
        row.provider = normalized_provider
        row.sucursal_id = normalized_sucursal_id
        row.sucursal_canon = str(catalog.sucursal_canon)
        row.provider_channel_id = normalized_channel_id
        row.is_active = normalized_is_active
        row.is_default = normalized_is_default
        row.metadata_json = normalized_metadata
        row.updated_by_user_id = normalized_actor
        row.updated_at = timestamp

    _commit_config(active_session)
    return _serialize_channel_binding(row)


def resolve_dispatch_channel_binding(
    *,
    sucursal_id: Any,
    provider: Any = DEFAULT_PROVIDER,
    session: Any | None = None,
) -> MarketingCampaignV2ChannelBindingORM | None:
    active_session = session if session is not None else db.session
    normalized_sucursal_id = _positive_int(sucursal_id, "sucursal_id")
    normalized_provider = _normalize_provider(provider)
    return active_session.query(MarketingCampaignV2ChannelBindingORM).filter(
        MarketingCampaignV2ChannelBindingORM.provider == normalized_provider,
        MarketingCampaignV2ChannelBindingORM.sucursal_id == normalized_sucursal_id,
        MarketingCampaignV2ChannelBindingORM.is_active.is_(True),
        MarketingCampaignV2ChannelBindingORM.is_default.is_(True),
    ).one_or_none()


def list_templates(
    *,
    provider: Any = DEFAULT_PROVIDER,
    active_only: bool = True,
    purpose: Any = None,
    session: Any | None = None,
) -> list[dict[str, Any]]:
    active_session = session if session is not None else db.session
    normalized_provider = _normalize_provider(provider)
    normalized_purpose = (
        _normalize_purpose(purpose) if purpose is not None else None
    )
    query = active_session.query(MarketingCampaignV2TemplateORM).filter(
        MarketingCampaignV2TemplateORM.provider == normalized_provider
    )
    if active_only:
        query = query.filter(MarketingCampaignV2TemplateORM.is_active.is_(True))
    rows = query.order_by(
        MarketingCampaignV2TemplateORM.label.asc(),
        MarketingCampaignV2TemplateORM.id.asc(),
    ).all()
    if normalized_purpose is not None:
        rows = [
            row
            for row in rows
            if _template_allows_purpose(row, normalized_purpose)
        ]
    return [_serialize_template(row) for row in rows]


def save_template(
    *,
    provider: Any,
    template_name: Any,
    label: Any,
    is_active: Any,
    purposes: Any,
    variables: Any,
    compatible_channel_ids: Any,
    actor_user_id: Any,
    metadata: Any = None,
    template_id: Any = None,
    session: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    active_session = session if session is not None else db.session
    normalized_provider = _normalize_provider(provider)
    normalized_name = _required_text(template_name, "template_name", 255)
    normalized_label = _required_text(label, "label", 255)
    normalized_is_active = _strict_bool(is_active, "is_active")
    normalized_purposes = _normalize_purposes(purposes)
    normalized_variables = _normalize_variables(variables)
    normalized_channels = _normalize_channel_ids(compatible_channel_ids)
    normalized_actor = _positive_int(actor_user_id, "actor_user_id")
    normalized_metadata = _dict_value(metadata, "metadata")
    timestamp = _normalize_now(now)

    row = None
    if template_id is not None:
        normalized_template_id = _positive_int(template_id, "template_id")
        row = active_session.query(MarketingCampaignV2TemplateORM).filter(
            MarketingCampaignV2TemplateORM.id == normalized_template_id
        ).one_or_none()
        if row is None:
            raise MarketingCampaignV2DispatchConfigNotFoundError(
                "Template Campaign V2 no encontrado."
            )

    duplicate = active_session.query(MarketingCampaignV2TemplateORM).filter(
        MarketingCampaignV2TemplateORM.provider == normalized_provider,
        MarketingCampaignV2TemplateORM.template_name == normalized_name,
    )
    if row is not None:
        duplicate = duplicate.filter(
            MarketingCampaignV2TemplateORM.id != int(row.id)
        )
    if duplicate.first() is not None:
        raise MarketingCampaignV2DispatchConfigConflictError(
            "Ese template ya existe para el provider."
        )

    if row is None:
        row = MarketingCampaignV2TemplateORM(
            provider=normalized_provider,
            template_name=normalized_name,
            label=normalized_label,
            is_active=normalized_is_active,
            purposes_json=list(normalized_purposes),
            variables_json=normalized_variables,
            compatible_channel_ids_json=list(normalized_channels),
            metadata_json=normalized_metadata,
            created_by_user_id=normalized_actor,
            updated_by_user_id=normalized_actor,
            created_at=timestamp,
            updated_at=timestamp,
        )
        active_session.add(row)
    else:
        row.provider = normalized_provider
        row.template_name = normalized_name
        row.label = normalized_label
        row.is_active = normalized_is_active
        row.purposes_json = list(normalized_purposes)
        row.variables_json = normalized_variables
        row.compatible_channel_ids_json = list(normalized_channels)
        row.metadata_json = normalized_metadata
        row.updated_by_user_id = normalized_actor
        row.updated_at = timestamp

    _commit_config(active_session)
    return _serialize_template(row)


def resolve_dispatch_template(
    *,
    template_id: Any,
    purpose: Any,
    provider: Any = DEFAULT_PROVIDER,
    session: Any | None = None,
) -> MarketingCampaignV2TemplateORM:
    active_session = session if session is not None else db.session
    normalized_template_id = _positive_int(template_id, "template_id")
    normalized_provider = _normalize_provider(provider)
    normalized_purpose = _normalize_purpose(purpose)
    row = active_session.query(MarketingCampaignV2TemplateORM).filter(
        MarketingCampaignV2TemplateORM.id == normalized_template_id,
        MarketingCampaignV2TemplateORM.provider == normalized_provider,
    ).one_or_none()
    if row is None:
        raise MarketingCampaignV2DispatchConfigNotFoundError(
            "Template Campaign V2 no encontrado."
        )
    if not bool(row.is_active):
        raise MarketingCampaignV2DispatchConfigValidationError(
            "El template seleccionado está inactivo."
        )
    if not _template_allows_purpose(row, normalized_purpose):
        raise MarketingCampaignV2DispatchConfigValidationError(
            "El template no está permitido para el purpose de la campaña."
        )
    return row


def template_allows_channel(
    template: MarketingCampaignV2TemplateORM,
    provider_channel_id: str,
) -> bool:
    configured = {
        str(value).strip()
        for value in (template.compatible_channel_ids_json or [])
        if str(value or "").strip()
    }
    return not configured or str(provider_channel_id).strip() in configured


def _resolve_active_catalog_branch(*, sucursal_id: int, session: Any):
    rows = session.query(TrackBranchCatalogORM).filter(
        TrackBranchCatalogORM.sucursal_id == sucursal_id,
        TrackBranchCatalogORM.is_track_active.is_(True),
    ).all()
    if len(rows) != 1:
        raise MarketingCampaignV2DispatchConfigValidationError(
            "La sucursal no tiene una identidad Track activa y única."
        )
    return rows[0]


def _template_allows_purpose(
    template: MarketingCampaignV2TemplateORM,
    purpose: str,
) -> bool:
    configured = {
        str(value).strip().upper()
        for value in (template.purposes_json or [])
        if str(value or "").strip()
    }
    return not configured or purpose in configured


def _serialize_channel_binding(
    row: MarketingCampaignV2ChannelBindingORM,
) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "provider": row.provider,
        "sucursal_id": int(row.sucursal_id),
        "sucursal_canon": row.sucursal_canon,
        "provider_channel_id": row.provider_channel_id,
        "is_active": bool(row.is_active),
        "is_default": bool(row.is_default),
        "metadata": dict(row.metadata_json or {}),
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _serialize_template(row: MarketingCampaignV2TemplateORM) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "provider": row.provider,
        "template_name": row.template_name,
        "label": row.label,
        "is_active": bool(row.is_active),
        "purposes": list(row.purposes_json or []),
        "variables": dict(row.variables_json or {}),
        "compatible_channel_ids": list(row.compatible_channel_ids_json or []),
        "metadata": dict(row.metadata_json or {}),
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _normalize_provider(value: Any) -> str:
    normalized = _required_text(value, "provider", 50).upper()
    return normalized


def _normalize_purpose(value: Any) -> str:
    normalized = _required_text(value, "purpose", 30).upper()
    if normalized not in ALLOWED_PURPOSES:
        raise MarketingCampaignV2DispatchConfigValidationError(
            "purpose Campaign V2 inválido."
        )
    return normalized


def _normalize_purposes(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise MarketingCampaignV2DispatchConfigValidationError(
            "purposes debe ser una lista."
        )
    return tuple(sorted({_normalize_purpose(item) for item in value}))


def _normalize_variables(value: Any) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise MarketingCampaignV2DispatchConfigValidationError(
            "variables debe ser un objeto."
        )
    normalized: dict[str, str] = {}
    for raw_position, raw_source in value.items():
        position = str(raw_position).strip()
        if not position.isdigit() or int(position) <= 0:
            raise MarketingCampaignV2DispatchConfigValidationError(
                "Cada posición de variable debe ser un entero positivo."
            )
        source = str(raw_source or "").strip().lower()
        if source not in SUPPORTED_TEMPLATE_VARIABLE_SOURCES:
            raise MarketingCampaignV2DispatchConfigValidationError(
                f"Fuente de variable no soportada: {source or '<vacía>'}."
            )
        normalized[str(int(position))] = source
    return {
        key: normalized[key]
        for key in sorted(normalized, key=lambda item: int(item))
    }


def _normalize_channel_ids(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise MarketingCampaignV2DispatchConfigValidationError(
            "compatible_channel_ids debe ser una lista."
        )
    normalized = {
        _required_text(item, "provider_channel_id", 255)
        for item in value
    }
    return tuple(sorted(normalized))


def _dict_value(value: Any, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise MarketingCampaignV2DispatchConfigValidationError(
            f"{field_name} debe ser un objeto."
        )
    return dict(value)


def _strict_bool(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise MarketingCampaignV2DispatchConfigValidationError(
            f"{field_name} debe ser boolean."
        )
    return value


def _positive_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise MarketingCampaignV2DispatchConfigValidationError(
            f"{field_name} debe ser entero positivo."
        )
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise MarketingCampaignV2DispatchConfigValidationError(
            f"{field_name} debe ser entero positivo."
        ) from exc
    if normalized <= 0:
        raise MarketingCampaignV2DispatchConfigValidationError(
            f"{field_name} debe ser entero positivo."
        )
    return normalized


def _required_text(value: Any, field_name: str, max_length: int) -> str:
    if not isinstance(value, str):
        raise MarketingCampaignV2DispatchConfigValidationError(
            f"{field_name} debe ser texto."
        )
    normalized = value.strip()
    if not normalized:
        raise MarketingCampaignV2DispatchConfigValidationError(
            f"{field_name} es obligatorio."
        )
    if len(normalized) > max_length:
        raise MarketingCampaignV2DispatchConfigValidationError(
            f"{field_name} excede {max_length} caracteres."
        )
    return normalized


def _normalize_now(value: datetime | None) -> datetime:
    current = value if value is not None else datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _commit_config(session: Any) -> None:
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise MarketingCampaignV2DispatchConfigConflictError(
            "La configuración Campaign V2 entra en conflicto con otra fila."
        ) from exc
    except SQLAlchemyError as exc:
        session.rollback()
        raise MarketingCampaignV2DispatchConfigError(
            "No fue posible guardar configuración Campaign V2."
        ) from exc


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    formatter = getattr(value, "isoformat", None)
    return formatter() if callable(formatter) else str(value)
