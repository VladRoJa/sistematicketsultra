from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from math import ceil
from typing import Any

from app.models.user_model import UserORM
from app.utils.scope_utils import normalize_branch_ids, normalize_role

from .operational_repository import RoutineControlOperationalRepository


GLOBAL_ROLES = frozenset({"ADMIN", "ADMINISTRADOR", "SUPER_ADMIN", "LECTOR_GLOBAL"})
ALLOWED_ROLES = GLOBAL_ROLES | {"GERENTE", "GERENTE_REGIONAL"}
MEMBER_STATUSES = frozenset({"SIN_RUTINA", "CON_RUTINA", "NO_DESEA_RUTINA"})
CLASSIFICATION_STATUSES = frozenset({"CLASSIFIED", "INCIDENT"})
ASSIGNMENT_TYPES = frozenset({"PREEXISTENTE", "MISMO_DIA", "POSTERIOR"})
RUN_STATUSES = frozenset({"PENDING", "RUNNING", "SUCCESS", "PARTIAL", "FAILED", "CANCELLED", "REPLACED"})
SORT_FIELDS = frozenset({
    "id", "member_name", "external_member_id", "sale_date", "current_status",
    "first_routine_at", "latest_routine_at", "instructor", "branch_name",
})


class RoutineControlAuthorizationError(PermissionError):
    pass


class RoutineControlValidationError(ValueError):
    pass


@dataclass(frozen=True)
class RoutineControlScope:
    scope_type: str
    is_global: bool
    allowed_branch_ids: tuple[int, ...]
    fixed_branch_id: int | None
    role: str


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _public_error(value: Any) -> str | None:
    if not value:
        return None
    return str(value).splitlines()[0][:500]


def _parse_date(value: Any, field: str) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise RoutineControlValidationError(f"{field} inválido. Use YYYY-MM-DD.") from exc


def _parse_int(value: Any, field: str) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise RoutineControlValidationError(f"{field} inválido.") from exc


class RoutineControlOperationalService:
    def __init__(self, repository: RoutineControlOperationalRepository):
        self.repository = repository

    def resolve_scope(self, user: UserORM | None) -> RoutineControlScope:
        if user is None:
            raise RoutineControlAuthorizationError("Usuario no encontrado.")
        role = normalize_role(user.rol)
        if role not in ALLOWED_ROLES:
            raise RoutineControlAuthorizationError("No tienes acceso a Control de Rutinas.")
        if role in GLOBAL_ROLES:
            branches = self.repository.list_operational_branches()
            return RoutineControlScope("GLOBAL", True, tuple(item["id"] for item in branches), None, role)
        if role == "GERENTE":
            try:
                branch_id = int(user.sucursal_id)
            except (TypeError, ValueError) as exc:
                raise RoutineControlAuthorizationError("El gerente no tiene una sucursal válida.") from exc
            return RoutineControlScope("BRANCH", False, (branch_id,), branch_id, role)
        assigned = normalize_branch_ids(user.sucursales_ids)
        if not assigned:
            try:
                assigned = (int(user.sucursal_id),)
            except (TypeError, ValueError) as exc:
                raise RoutineControlAuthorizationError(
                    "El gerente regional no tiene sucursales autorizadas."
                ) from exc
        return RoutineControlScope("REGIONAL", False, assigned, None, role)

    def catalogs(self, user: UserORM) -> dict:
        scope = self.resolve_scope(user)
        allowed = set(scope.allowed_branch_ids)
        branches = [item for item in self.repository.list_operational_branches() if item["id"] in allowed]
        regions: dict[str, dict] = {}
        for branch in branches:
            key = branch["region_key"]
            if not key:
                continue
            region = regions.setdefault(key, {"key": key, "name": branch["region_name"] or key, "branch_ids": []})
            region["branch_ids"].append(branch["id"])
        return {
            "scope": {
                "scope_type": scope.scope_type,
                "allowed_branch_ids": list(scope.allowed_branch_ids),
                "fixed_branch_id": scope.fixed_branch_id,
            },
            "branches": branches,
            "regions": list(regions.values()),
            "statuses": ["SIN_RUTINA", "CON_RUTINA", "NO_DESEA_RUTINA", "INCIDENT"],
            "assignment_types": ["PREEXISTENTE", "MISMO_DIA", "POSTERIOR"],
        }

    def _filters(self, user: UserORM, raw: dict, *, listing: bool) -> tuple[RoutineControlScope, dict]:
        scope = self.resolve_scope(user)
        catalogs = self.catalogs(user)
        branch_id = _parse_int(raw.get("branch_id"), "branch_id")
        region_key = str(raw.get("region_key") or "").strip() or None
        allowed = set(scope.allowed_branch_ids)
        if branch_id is not None and branch_id not in allowed:
            raise RoutineControlAuthorizationError("Sucursal fuera del alcance autorizado.")
        region_branch_ids: set[int] | None = None
        if region_key:
            region = next((item for item in catalogs["regions"] if item["key"] == region_key), None)
            if region is None:
                if any(item["region_key"] == region_key for item in self.repository.list_operational_branches()):
                    raise RoutineControlAuthorizationError("Región fuera del alcance autorizado.")
                raise RoutineControlValidationError("region_key inválido.")
            region_branch_ids = set(region["branch_ids"])
            if branch_id is not None and branch_id not in region_branch_ids:
                raise RoutineControlValidationError("branch_id no pertenece a region_key.")
            if branch_id is None:
                allowed &= region_branch_ids
        date_from = _parse_date(raw.get("sale_date_from"), "sale_date_from")
        date_to = _parse_date(raw.get("sale_date_to"), "sale_date_to")
        if date_from and date_to and date_from > date_to:
            raise RoutineControlValidationError("sale_date_from no puede ser mayor que sale_date_to.")
        filters = {
            "branch_id": branch_id,
            "region_key": region_key,
            "sale_date_from": date_from,
            "sale_date_to": date_to,
        }
        if listing:
            for key, allowed_values in (
                ("classification_status", CLASSIFICATION_STATUSES),
                ("current_status", MEMBER_STATUSES),
                ("assignment_type", ASSIGNMENT_TYPES),
            ):
                value = str(raw.get(key) or "").strip().upper() or None
                if value and value not in allowed_values:
                    raise RoutineControlValidationError(f"{key} inválido.")
                filters[key] = value
            filters["instructor"] = str(raw.get("instructor") or "").strip() or None
            filters["search"] = str(raw.get("search") or "").strip() or None
        return scope, {**filters, "effective_branch_ids": tuple(sorted(allowed))}

    @staticmethod
    def _member_dto(row) -> dict:
        member, branch_name, incident_count, evidence_count = row
        return {
            "id": int(member.id),
            "external_member_id": member.external_member_id,
            "external_sale_id": member.external_sale_id,
            "member_name": member.member_name,
            "email": member.email_normalized or member.email_original,
            "branch_id": member.sucursal_id,
            "branch_name": branch_name,
            "source_branch_name": member.source_branch_name,
            "sale_date": _iso(member.sale_date),
            "classification_status": member.classification_status,
            "current_status": member.current_status,
            "first_routine_at": _iso(member.first_routine_at),
            "latest_routine_at": _iso(member.latest_routine_at),
            "current_instructor_name": member.current_instructor_name,
            "routine_assignment_type": member.routine_assignment_type,
            "status_version": int(member.status_version),
            "active_incident_count": int(incident_count),
            "active_evidence_count": int(evidence_count),
        }

    def summary(self, user: UserORM, raw: dict) -> dict:
        _, filters = self._filters(user, raw, listing=False)
        rows = self.repository.get_summary(filters, filters.pop("effective_branch_ids"))["rows"]
        statuses = {key: 0 for key in ("SIN_RUTINA", "CON_RUTINA", "NO_DESEA_RUTINA", "INCIDENT")}
        assignments = {key: 0 for key in ("PREEXISTENTE", "MISMO_DIA", "POSTERIOR", "SIN_EVIDENCIA")}
        branches: dict[int, dict] = {}
        total = 0
        for branch_id, branch_name, status, assignment, count in rows:
            count = int(count)
            total += count
            statuses[status] = statuses.get(status, 0) + count
            assignments[assignment or "SIN_EVIDENCIA"] = assignments.get(assignment or "SIN_EVIDENCIA", 0) + count
            branch = branches.setdefault(int(branch_id) if branch_id is not None else -1, {
                "branch_id": branch_id, "branch_name": branch_name or "Sin sucursal", "total_members": 0,
                "sin_rutina": 0, "con_rutina": 0, "no_desea_rutina": 0, "incidents": 0,
            })
            branch["total_members"] += count
            key = {"SIN_RUTINA": "sin_rutina", "CON_RUTINA": "con_rutina", "NO_DESEA_RUTINA": "no_desea_rutina", "INCIDENT": "incidents"}[status]
            branch[key] += count
        freshness = {key: _iso(value) for key, value in self.repository.get_freshness().items()}
        return {
            "filters_applied": {key: _iso(value) if isinstance(value, date) else value for key, value in filters.items()},
            "total_members": total,
            "classified_members": total - statuses["INCIDENT"],
            "incident_members": statuses["INCIDENT"],
            "status_counts": statuses,
            "assignment_type_counts": assignments,
            "branches": list(branches.values()),
            "freshness": freshness,
        }

    def members(
        self,
        user: UserORM,
        raw: dict,
        *,
        paginate: bool = True,
        row_limit: int | None = None,
    ) -> dict:
        _, filters = self._filters(user, raw, listing=True)
        branch_ids = filters.pop("effective_branch_ids")
        page = _parse_int(raw.get("page"), "page") or 1
        page_size = _parse_int(raw.get("page_size"), "page_size") or 25
        if page < 1:
            raise RoutineControlValidationError("page debe ser al menos 1.")
        if page_size < 1 or page_size > 100:
            raise RoutineControlValidationError("page_size debe estar entre 1 y 100.")
        sort = str(raw.get("sort") or "sale_date").strip()
        if sort not in SORT_FIELDS:
            raise RoutineControlValidationError("sort inválido.")
        direction = str(raw.get("direction") or "desc").strip().lower()
        if direction not in {"asc", "desc"}:
            raise RoutineControlValidationError("direction inválido.")
        query_page = page if paginate else (1 if row_limit is not None else None)
        query_page_size = page_size if paginate else row_limit
        rows, total = self.repository.list_members(
            filters, branch_ids, page=query_page,
            page_size=query_page_size, sort=sort, direction=direction,
        )
        return {
            "items": [self._member_dto(row) for row in rows],
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": ceil(total / page_size) if total else 0,
        }

    def member_detail(self, user: UserORM, member_id: int) -> dict | None:
        scope = self.resolve_scope(user)
        row = self.repository.get_member(member_id)
        if row is None:
            return None
        if row[0].sucursal_id not in set(scope.allowed_branch_ids):
            raise RoutineControlAuthorizationError("Socio fuera del alcance autorizado.")
        relations = self.repository.get_member_detail_relations(member_id)
        return {
            "member": self._member_dto(row),
            "evidences": [{
                "id": int(evidence.id), "provider_key": evidence.provider_key,
                "provider_member_id": evidence.provider_member_id,
                "external_member_id": evidence.external_member_id,
                "routine_activity_date": _iso(evidence.routine_activity_date),
                "instructor_name": evidence.instructor_name,
                "routine_count": int(evidence.routine_count), "weighing_count": int(evidence.weighing_count),
                "provider_center_name": evidence.provider_center_name,
                "match_method": link.match_method, "linked_at_utc": _iso(link.linked_at_utc),
                "is_valid": bool(evidence.is_valid),
            } for link, evidence in relations["evidences"]],
            "incidents": [{
                "id": int(item.id), "incident_type": item.incident_type,
                "is_blocking": bool(item.is_blocking), "is_active": bool(item.is_active),
                "detected_at_utc": _iso(item.detected_at_utc), "resolved_at_utc": _iso(item.resolved_at_utc),
                "resolution_note": item.resolution_note,
            } for item in relations["incidents"]],
            "decisions": [{
                "id": int(item.id), "decision_type": item.decision_type, "is_active": bool(item.is_active),
                "decided_at_utc": _iso(item.decided_at_utc), "effective_from_utc": _iso(item.effective_from_utc),
                "effective_to_utc": _iso(item.effective_to_utc), "revoked_at_utc": _iso(item.revoked_at_utc),
                "decision_reason": item.decision_reason,
            } for item in relations["decisions"]],
        }

    def runs(self, user: UserORM, raw: dict) -> dict:
        self.resolve_scope(user)
        status = str(raw.get("status") or "").strip().upper() or None
        if status and status not in RUN_STATUSES:
            raise RoutineControlValidationError("status inválido.")
        date_from = _parse_date(raw.get("date_from"), "date_from")
        date_to = _parse_date(raw.get("date_to"), "date_to")
        if date_from and date_to and date_from > date_to:
            raise RoutineControlValidationError("date_from no puede ser mayor que date_to.")
        page = _parse_int(raw.get("page"), "page") or 1
        page_size = _parse_int(raw.get("page_size"), "page_size") or 25
        if page < 1 or page_size < 1 or page_size > 100:
            raise RoutineControlValidationError("Paginación inválida.")
        items, total = self.repository.list_runs(status=status, date_from=date_from, date_to=date_to, page=page, page_size=page_size)

        def provider_dto(item):
            return {
                "id": int(item.id), "provider_key": item.provider_key, "dataset_key": item.dataset_key,
                "status": item.status, "started_at_utc": _iso(item.started_at_utc),
                "finished_at_utc": _iso(item.finished_at_utc), "records_read": int(item.records_received),
                "records_accepted": int(item.records_valid), "records_rejected": int(item.records_rejected),
                "error_message": _public_error(item.error_message),
            }

        result = []
        for item in items:
            providers = [provider_dto(provider) for provider in item.provider_runs]
            result.append({
                "id": int(item.id), "mode": item.generation_mode, "status": item.status,
                "started_at_utc": _iso(item.started_at_utc), "finished_at_utc": _iso(item.finished_at_utc),
                "created_at_utc": _iso(item.created_at),
                "records_read": sum(provider["records_read"] for provider in providers),
                "records_accepted": sum(provider["records_accepted"] for provider in providers),
                "records_rejected": int(item.records_rejected), "error_message": _public_error(item.error_message),
                "provider_runs": providers,
            })
        return {"items": result, "page": page, "page_size": page_size, "total": total, "total_pages": ceil(total / page_size) if total else 0}
