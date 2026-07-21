from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session, selectinload

from app.models.routine_control import (
    RoutineAssignmentEvidenceORM,
    RoutineControlDecisionORM,
    RoutineControlIncidentORM,
    RoutineControlMemberEvidenceORM,
    RoutineControlMemberORM,
    RoutineControlPipelineRunORM,
    RoutineControlProviderRunORM,
)
from app.models.sucursal_model import Sucursal, SucursalOperationalStatus
from app.models.suite_governance import (
    SuiteRegionORM,
    SuiteSucursalRegionAssignmentORM,
)
from app.models.warehouse import TrackBranchCatalogORM


class RoutineControlOperationalRepository:
    """Consultas operativas de solo lectura; nunca confirma ni revierte."""

    def __init__(self, session: Session):
        self.session = session

    def list_operational_branches(self) -> list[dict]:
        rows = (
            self.session.query(
                Sucursal.sucursal_id,
                Sucursal.sucursal,
                SuiteRegionORM.region_key,
                SuiteRegionORM.region_label,
            )
            .join(
                TrackBranchCatalogORM,
                TrackBranchCatalogORM.sucursal_id == Sucursal.sucursal_id,
            )
            .outerjoin(
                SuiteSucursalRegionAssignmentORM,
                and_(
                    SuiteSucursalRegionAssignmentORM.sucursal_id == Sucursal.sucursal_id,
                    SuiteSucursalRegionAssignmentORM.is_current.is_(True),
                ),
            )
            .outerjoin(
                SuiteRegionORM,
                and_(
                    SuiteRegionORM.id == SuiteSucursalRegionAssignmentORM.region_id,
                    SuiteRegionORM.is_active.is_(True),
                ),
            )
            .filter(
                Sucursal.operational_status == SucursalOperationalStatus.ACTIVA,
                TrackBranchCatalogORM.is_track_active.is_(True),
                func.upper(TrackBranchCatalogORM.sucursal_canon) != "LA_VIGA",
            )
            .order_by(TrackBranchCatalogORM.display_order, Sucursal.sucursal)
            .all()
        )
        branches: dict[int, dict] = {}
        for branch_id, name, region_key, region_label in rows:
            normalized_id = int(branch_id)
            existing = branches.get(normalized_id)
            if existing is None:
                branches[normalized_id] = {
                    "id": normalized_id,
                    "name": name,
                    "region_key": region_key,
                    "region_name": region_label,
                }
            elif existing["region_key"] != region_key:
                existing["region_key"] = None
                existing["region_name"] = None
        return list(branches.values())

    @staticmethod
    def _active_evidence_counts():
        return (
            RoutineControlMemberEvidenceORM.query.with_entities(
                RoutineControlMemberEvidenceORM.member_id.label("member_id"),
                func.count(RoutineControlMemberEvidenceORM.id).label("active_evidence_count"),
            )
            .join(
                RoutineAssignmentEvidenceORM,
                RoutineAssignmentEvidenceORM.id == RoutineControlMemberEvidenceORM.evidence_id,
            )
            .filter(
                RoutineControlMemberEvidenceORM.is_active.is_(True),
                RoutineAssignmentEvidenceORM.is_valid.is_(True),
            )
            .group_by(RoutineControlMemberEvidenceORM.member_id)
            .subquery()
        )

    @staticmethod
    def _active_incident_counts():
        return (
            RoutineControlIncidentORM.query.with_entities(
                RoutineControlIncidentORM.member_id.label("member_id"),
                func.count(RoutineControlIncidentORM.id).label("active_incident_count"),
            )
            .filter(RoutineControlIncidentORM.is_active.is_(True))
            .group_by(RoutineControlIncidentORM.member_id)
            .subquery()
        )

    def _members_query(self):
        evidence_counts = self._active_evidence_counts()
        incident_counts = self._active_incident_counts()
        return (
            self.session.query(
                RoutineControlMemberORM,
                Sucursal.sucursal.label("branch_name"),
                func.coalesce(incident_counts.c.active_incident_count, 0).label("active_incident_count"),
                func.coalesce(evidence_counts.c.active_evidence_count, 0).label("active_evidence_count"),
            )
            .outerjoin(Sucursal, Sucursal.sucursal_id == RoutineControlMemberORM.sucursal_id)
            .outerjoin(incident_counts, incident_counts.c.member_id == RoutineControlMemberORM.id)
            .outerjoin(evidence_counts, evidence_counts.c.member_id == RoutineControlMemberORM.id)
        )

    @staticmethod
    def apply_member_filters(query, filters: dict, branch_ids: tuple[int, ...]):
        query = query.filter(RoutineControlMemberORM.sucursal_id.in_(branch_ids or (-1,)))
        if filters.get("branch_id") is not None:
            query = query.filter(RoutineControlMemberORM.sucursal_id == filters["branch_id"])
        if filters.get("sale_date_from"):
            query = query.filter(RoutineControlMemberORM.sale_date >= filters["sale_date_from"])
        if filters.get("sale_date_to"):
            query = query.filter(RoutineControlMemberORM.sale_date <= filters["sale_date_to"])
        for key, column in (
            ("classification_status", RoutineControlMemberORM.classification_status),
            ("current_status", RoutineControlMemberORM.current_status),
            ("assignment_type", RoutineControlMemberORM.routine_assignment_type),
        ):
            if filters.get(key):
                query = query.filter(column == filters[key])
        if filters.get("instructor"):
            query = query.filter(
                RoutineControlMemberORM.current_instructor_name.ilike(
                    f"%{filters['instructor']}%"
                )
            )
        if filters.get("search"):
            pattern = f"%{filters['search']}%"
            query = query.filter(
                or_(
                    RoutineControlMemberORM.member_name.ilike(pattern),
                    RoutineControlMemberORM.external_member_id.ilike(pattern),
                    RoutineControlMemberORM.email_normalized.ilike(pattern),
                    RoutineControlMemberORM.external_sale_id.ilike(pattern),
                )
            )
        return query

    def get_summary(self, filters: dict, branch_ids: tuple[int, ...]) -> dict:
        visible_status = case(
            (RoutineControlMemberORM.classification_status == "INCIDENT", "INCIDENT"),
            else_=RoutineControlMemberORM.current_status,
        )
        query = self.apply_member_filters(
            self.session.query(
                RoutineControlMemberORM.sucursal_id,
                Sucursal.sucursal,
                visible_status.label("visible_status"),
                RoutineControlMemberORM.routine_assignment_type,
                func.count(RoutineControlMemberORM.id).label("count"),
            ).outerjoin(Sucursal, Sucursal.sucursal_id == RoutineControlMemberORM.sucursal_id),
            filters,
            branch_ids,
        )
        rows = query.group_by(
            RoutineControlMemberORM.sucursal_id,
            Sucursal.sucursal,
            visible_status,
            RoutineControlMemberORM.routine_assignment_type,
        ).all()
        return {"rows": rows}

    def list_members(
        self,
        filters: dict,
        branch_ids: tuple[int, ...],
        *,
        page: int | None,
        page_size: int | None,
        sort: str,
        direction: str,
    ) -> tuple[list, int]:
        query = self.apply_member_filters(self._members_query(), filters, branch_ids)
        total = query.count()
        sort_columns = {
            "id": RoutineControlMemberORM.id,
            "member_name": RoutineControlMemberORM.member_name,
            "external_member_id": RoutineControlMemberORM.external_member_id,
            "sale_date": RoutineControlMemberORM.sale_date,
            "current_status": RoutineControlMemberORM.current_status,
            "first_routine_at": RoutineControlMemberORM.first_routine_at,
            "latest_routine_at": RoutineControlMemberORM.latest_routine_at,
            "instructor": RoutineControlMemberORM.current_instructor_name,
            "branch_name": Sucursal.sucursal,
        }
        column = sort_columns[sort]
        query = query.order_by(
            (column.desc() if direction == "desc" else column.asc()),
            RoutineControlMemberORM.id.asc(),
        )
        if page is not None and page_size is not None:
            query = query.offset((page - 1) * page_size).limit(page_size)
        return query.all(), total

    def get_member(self, member_id: int):
        return self._members_query().filter(RoutineControlMemberORM.id == member_id).one_or_none()

    def get_member_detail_relations(self, member_id: int) -> dict:
        evidences = (
            self.session.query(RoutineControlMemberEvidenceORM, RoutineAssignmentEvidenceORM)
            .join(
                RoutineAssignmentEvidenceORM,
                RoutineAssignmentEvidenceORM.id == RoutineControlMemberEvidenceORM.evidence_id,
            )
            .filter(RoutineControlMemberEvidenceORM.member_id == member_id)
            .order_by(RoutineAssignmentEvidenceORM.routine_activity_date.desc())
            .all()
        )
        incidents = (
            self.session.query(RoutineControlIncidentORM)
            .filter(RoutineControlIncidentORM.member_id == member_id)
            .order_by(RoutineControlIncidentORM.detected_at_utc.desc())
            .all()
        )
        decisions = (
            self.session.query(RoutineControlDecisionORM)
            .filter(RoutineControlDecisionORM.member_id == member_id)
            .order_by(RoutineControlDecisionORM.decided_at_utc.desc())
            .all()
        )
        return {"evidences": evidences, "incidents": incidents, "decisions": decisions}

    def list_runs(
        self,
        *,
        status: str | None,
        date_from: date | None,
        date_to: date | None,
        page: int,
        page_size: int,
    ) -> tuple[list[RoutineControlPipelineRunORM], int]:
        query = self.session.query(RoutineControlPipelineRunORM)
        if status:
            query = query.filter(RoutineControlPipelineRunORM.status == status)
        if date_from:
            query = query.filter(func.date(RoutineControlPipelineRunORM.created_at) >= date_from)
        if date_to:
            query = query.filter(func.date(RoutineControlPipelineRunORM.created_at) <= date_to)
        total = query.count()
        items = (
            query.options(selectinload(RoutineControlPipelineRunORM.provider_runs))
            .order_by(RoutineControlPipelineRunORM.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return items, total

    def get_freshness(self) -> dict:
        pipeline_at = self.session.query(
            func.max(RoutineControlPipelineRunORM.finished_at_utc)
        ).filter(RoutineControlPipelineRunORM.status == "SUCCESS").scalar()

        def provider_at(provider_key: str):
            return self.session.query(func.max(RoutineControlProviderRunORM.finished_at_utc)).filter(
                func.lower(RoutineControlProviderRunORM.provider_key) == provider_key,
                RoutineControlProviderRunORM.status.in_(("SUCCESS", "SUCCESS_EMPTY")),
            ).scalar()

        return {
            "last_successful_pipeline_at_utc": pipeline_at,
            "last_gasca_success_at_utc": provider_at("gasca"),
            "last_trainingym_success_at_utc": provider_at("trainingym"),
        }
