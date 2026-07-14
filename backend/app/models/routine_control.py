from sqlalchemy.dialects.postgresql import JSONB

from app import db


class RoutineControlPipelineRunORM(db.Model):
    __tablename__ = "routine_control_pipeline_runs"

    __table_args__ = (
        db.CheckConstraint(
            """
            status IN (
                'PENDING',
                'RUNNING',
                'SUCCESS',
                'PARTIAL',
                'FAILED',
                'CANCELLED',
                'REPLACED'
            )
            """,
            name="ck_routine_control_pipeline_runs_status",
        ),
        db.CheckConstraint(
            """
            generation_mode IN (
                'SCHEDULED',
                'MANUAL',
                'BACKFILL',
                'RETRY'
            )
            """,
            name="ck_routine_control_pipeline_runs_generation_mode",
        ),
        db.CheckConstraint(
            "date_from <= date_to",
            name="ck_routine_control_pipeline_runs_date_range",
        ),
        db.CheckConstraint(
            "attempt_number >= 1",
            name="ck_routine_control_pipeline_runs_attempt_number",
        ),
        db.CheckConstraint(
            """
            members_created >= 0
            AND members_updated >= 0
            AND evidences_created >= 0
            AND evidences_updated >= 0
            AND status_changes >= 0
            AND incidents_created >= 0
            AND incidents_reopened >= 0
            AND records_rejected >= 0
            AND records_excluded >= 0
            """,
            name="ck_routine_control_pipeline_runs_nonnegative_counts",
        ),
        db.UniqueConstraint(
            "idempotency_key",
            name="uq_routine_control_pipeline_runs_idempotency_key",
        ),
        db.Index(
            "ix_routine_control_pipeline_runs_business_date_status",
            "business_date",
            "status",
        ),
        db.Index(
            "ix_routine_control_pipeline_runs_status_created_at",
            "status",
            "created_at",
        ),
        db.Index(
            "ix_routine_control_pipeline_runs_root_pipeline_run_id",
            "root_pipeline_run_id",
        ),
    )

    id = db.Column(
        db.BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    business_date = db.Column(
        db.Date,
        nullable=False,
    )
    date_from = db.Column(
        db.Date,
        nullable=False,
    )
    date_to = db.Column(
        db.Date,
        nullable=False,
    )

    generation_mode = db.Column(
        db.String(40),
        nullable=False,
    )
    status = db.Column(
        db.String(40),
        nullable=False,
        default="PENDING",
        server_default="PENDING",
    )
    idempotency_key = db.Column(
        db.String(128),
        nullable=False,
    )

    requested_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    trigger_source = db.Column(
        db.String(80),
        nullable=False,
    )

    retry_of_pipeline_run_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "routine_control_pipeline_runs.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    root_pipeline_run_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "routine_control_pipeline_runs.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    replaces_pipeline_run_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "routine_control_pipeline_runs.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    attempt_number = db.Column(
        db.Integer,
        nullable=False,
        default=1,
        server_default="1",
    )

    current_stage = db.Column(
        db.String(80),
        nullable=True,
    )
    worker_instance_id = db.Column(
        db.String(255),
        nullable=True,
    )
    heartbeat_at_utc = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    started_at_utc = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )
    finished_at_utc = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    cancellation_requested_at_utc = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )
    cancellation_requested_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    cancellation_reason = db.Column(
        db.Text,
        nullable=True,
    )

    members_created = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    members_updated = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    evidences_created = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    evidences_updated = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    status_changes = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    incidents_created = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    incidents_reopened = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    records_rejected = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    records_excluded = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    error_code = db.Column(
        db.String(120),
        nullable=True,
    )
    error_message = db.Column(
        db.Text,
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("now()"),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("now()"),
        onupdate=db.func.now(),
    )

    provider_runs = db.relationship(
        "RoutineControlProviderRunORM",
        back_populates="pipeline_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class RoutineControlProviderRunORM(db.Model):
    __tablename__ = "routine_control_provider_runs"

    __table_args__ = (
        db.CheckConstraint(
            """
            status IN (
                'PENDING',
                'RUNNING',
                'SUCCESS',
                'SUCCESS_EMPTY',
                'PARTIAL',
                'FAILED',
                'BLOCKED',
                'CANCELLED'
            )
            """,
            name="ck_routine_control_provider_runs_status",
        ),
        db.CheckConstraint(
            """
            dataset_key IN (
                'new_members',
                'routine_assignments'
            )
            """,
            name="ck_routine_control_provider_runs_dataset_key",
        ),
        db.CheckConstraint(
            "date_from <= date_to",
            name="ck_routine_control_provider_runs_date_range",
        ),
        db.CheckConstraint(
            "attempt_count >= 0",
            name="ck_routine_control_provider_runs_attempt_count",
        ),
        db.CheckConstraint(
            """
            records_received >= 0
            AND records_valid >= 0
            AND records_rejected >= 0
            AND records_excluded >= 0
            AND records_created >= 0
            AND records_updated >= 0
            """,
            name="ck_routine_control_provider_runs_nonnegative_counts",
        ),
        db.UniqueConstraint(
            "pipeline_run_id",
            "provider_key",
            "dataset_key",
            name="uq_routine_control_provider_runs_pipeline_provider_dataset",
        ),
        db.Index(
            "ix_routine_control_provider_runs_pipeline_run_id",
            "pipeline_run_id",
        ),
        db.Index(
            "ix_routine_control_provider_runs_provider_dataset_status",
            "provider_key",
            "dataset_key",
            "status",
        ),
        db.Index(
            "ix_routine_control_provider_runs_status_created_at",
            "status",
            "created_at",
        ),
    )

    id = db.Column(
        db.BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    pipeline_run_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "routine_control_pipeline_runs.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    provider_key = db.Column(
        db.String(80),
        nullable=False,
    )
    dataset_key = db.Column(
        db.String(80),
        nullable=False,
    )
    status = db.Column(
        db.String(40),
        nullable=False,
        default="PENDING",
        server_default="PENDING",
    )

    date_from = db.Column(
        db.Date,
        nullable=False,
    )
    date_to = db.Column(
        db.Date,
        nullable=False,
    )

    attempt_count = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    last_attempt_at_utc = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )
    next_attempt_at_utc = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    started_at_utc = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )
    finished_at_utc = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    content_hash = db.Column(
        db.String(64),
        nullable=True,
    )
    raw_warehouse_upload_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "warehouse_uploads.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    diagnostic_artifact_path = db.Column(
        db.Text,
        nullable=True,
    )

    records_received = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    records_valid = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    records_rejected = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    records_excluded = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    records_created = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    records_updated = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    error_code = db.Column(
        db.String(120),
        nullable=True,
    )
    error_message = db.Column(
        db.Text,
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("now()"),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("now()"),
        onupdate=db.func.now(),
    )

    pipeline_run = db.relationship(
        "RoutineControlPipelineRunORM",
        back_populates="provider_runs",
    )


class RoutineControlMemberORM(db.Model):
    __tablename__ = "routine_control_members"

    __table_args__ = (
        db.CheckConstraint(
            """
            classification_status IN (
                'CLASSIFIED',
                'INCIDENT'
            )
            """,
            name="ck_routine_control_members_classification_status",
        ),
        db.CheckConstraint(
            """
            current_status IS NULL
            OR current_status IN (
                'SIN_RUTINA',
                'CON_RUTINA',
                'NO_DESEA_RUTINA'
            )
            """,
            name="ck_routine_control_members_current_status",
        ),
        db.CheckConstraint(
            """
            (
                classification_status = 'CLASSIFIED'
                AND current_status IS NOT NULL
            )
            OR
            (
                classification_status = 'INCIDENT'
                AND current_status IS NULL
            )
            """,
            name="ck_routine_control_members_status_consistency",
        ),
        db.CheckConstraint(
            "status_version >= 1",
            name="ck_routine_control_members_status_version",
        ),
        db.CheckConstraint(
            """
            cohort_month
            = date_trunc('month', cohort_month)::date
            """,
            name="ck_routine_control_members_cohort_month",
        ),
        db.CheckConstraint(
            """
            routine_assignment_type IS NULL
            OR routine_assignment_type IN (
                'PREEXISTENTE',
                'MISMO_DIA',
                'POSTERIOR'
            )
            """,
            name="ck_routine_control_members_assignment_type",
        ),
        db.CheckConstraint(
            """
            (
                first_routine_at IS NULL
                AND latest_routine_at IS NULL
                AND routine_assignment_type IS NULL
            )
            OR
            (
                first_routine_at IS NOT NULL
                AND latest_routine_at IS NOT NULL
                AND routine_assignment_type IS NOT NULL
                AND first_routine_at <= latest_routine_at
            )
            """,
            name="ck_routine_control_members_routine_dates",
        ),
        db.UniqueConstraint(
            "source_system",
            "source_record_id",
            name="uq_routine_control_members_source_record",
        ),
        db.UniqueConstraint(
            "source_system",
            "source_identity_key",
            name="uq_routine_control_members_identity_key",
        ),
        db.Index(
            "ix_routine_control_members_cohort_month",
            "cohort_month",
        ),
        db.Index(
            "ix_routine_control_members_sucursal_cohort",
            "sucursal_id",
            "cohort_month",
        ),
        db.Index(
            "ix_routine_control_members_status_cohort",
            "current_status",
            "cohort_month",
        ),
        db.Index(
            "ix_routine_control_members_classification_cohort",
            "classification_status",
            "cohort_month",
        ),
        db.Index(
            "ix_routine_control_members_email_normalized",
            "email_normalized",
        ),
        db.Index(
            "ix_routine_control_members_branch_status_cohort",
            "sucursal_id",
            "current_status",
            "cohort_month",
        ),
        db.Index(
            "ix_routine_control_members_sale_date",
            "sale_date",
        ),
        db.Index(
            "ix_routine_control_members_external_member",
            "source_system",
            "external_member_id",
        ),
    )

    id = db.Column(
        db.BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    source_system = db.Column(
        db.String(80),
        nullable=False,
    )
    source_record_id = db.Column(
        db.String(255),
        nullable=False,
    )
    source_identity_key = db.Column(
        db.String(64),
        nullable=False,
    )

    external_member_id = db.Column(
        db.String(128),
        nullable=False,
    )
    external_sale_id = db.Column(
        db.String(128),
        nullable=True,
    )

    sucursal_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "sucursales.sucursal_id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    source_branch_name = db.Column(
        db.String(255),
        nullable=True,
    )

    member_name = db.Column(
        db.String(255),
        nullable=True,
    )
    email_original = db.Column(
        db.String(320),
        nullable=True,
    )
    email_normalized = db.Column(
        db.String(320),
        nullable=True,
    )

    sale_date = db.Column(
        db.Date,
        nullable=False,
    )
    cohort_month = db.Column(
        db.Date,
        nullable=False,
    )

    classification_status = db.Column(
        db.String(32),
        nullable=False,
        default="CLASSIFIED",
        server_default="CLASSIFIED",
    )
    current_status = db.Column(
        db.String(32),
        nullable=True,
        default="SIN_RUTINA",
        server_default="SIN_RUTINA",
    )
    status_version = db.Column(
        db.Integer,
        nullable=False,
        default=1,
        server_default="1",
    )

    first_routine_at = db.Column(
        db.Date,
        nullable=True,
    )
    latest_routine_at = db.Column(
        db.Date,
        nullable=True,
    )
    current_instructor_name = db.Column(
        db.String(255),
        nullable=True,
    )
    routine_assignment_type = db.Column(
        db.String(32),
        nullable=True,
    )

    first_seen_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("now()"),
    )
    last_seen_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("now()"),
    )
    source_updated_at_utc = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    payload_hash = db.Column(
        db.String(64),
        nullable=False,
    )
    source_metadata = db.Column(
        JSONB,
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("now()"),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("now()"),
        onupdate=db.func.now(),
    )

    sucursal = db.relationship(
        "Sucursal",
        foreign_keys=[sucursal_id],
    )
    evidence_links = db.relationship(
        "RoutineControlMemberEvidenceORM",
        back_populates="member",
        passive_deletes=True,
    )


class RoutineAssignmentEvidenceORM(db.Model):
    __tablename__ = "routine_assignment_evidences"

    __table_args__ = (
        db.CheckConstraint(
            "routine_count > 0",
            name="ck_routine_assignment_evidences_routine_count",
        ),
        db.CheckConstraint(
            "weighing_count >= 0",
            name="ck_routine_assignment_evidences_weighing_count",
        ),
        db.CheckConstraint(
            """
            (
                is_valid = true
                AND invalidated_at_utc IS NULL
                AND invalidated_by_user_id IS NULL
                AND invalidation_reason IS NULL
            )
            OR
            (
                is_valid = false
                AND invalidated_at_utc IS NOT NULL
                AND invalidated_by_user_id IS NOT NULL
                AND invalidation_reason IS NOT NULL
            )
            """,
            name="ck_routine_assignment_evidences_invalidation",
        ),
        db.UniqueConstraint(
            "provider_key",
            "evidence_identity_key",
            name="uq_routine_assignment_evidences_identity",
        ),
        db.Index(
            "ix_routine_assignment_evidences_external_member_date",
            "external_member_id",
            "routine_activity_date",
        ),
        db.Index(
            "ix_routine_assignment_evidences_email",
            "email_normalized",
        ),
        db.Index(
            "ix_routine_assignment_evidences_provider_date",
            "provider_key",
            "routine_activity_date",
        ),
        db.Index(
            "ix_routine_assignment_evidences_valid_date",
            "is_valid",
            "routine_activity_date",
        ),
        db.Index(
            "ix_routine_assignment_evidences_provider_member_date",
            "provider_member_id",
            "routine_activity_date",
        ),
        db.Index(
            "ix_routine_assignment_evidences_center_date",
            "provider_center_key",
            "routine_activity_date",
        ),
    )

    id = db.Column(
        db.BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    provider_key = db.Column(
        db.String(80),
        nullable=False,
    )
    provider_member_id = db.Column(
        db.String(128),
        nullable=False,
    )
    evidence_identity_key = db.Column(
        db.String(64),
        nullable=False,
    )

    external_member_id = db.Column(
        db.String(128),
        nullable=True,
    )
    external_routine_id = db.Column(
        db.String(128),
        nullable=True,
    )

    email_original = db.Column(
        db.String(320),
        nullable=True,
    )
    email_normalized = db.Column(
        db.String(320),
        nullable=True,
    )

    provider_center_key = db.Column(
        db.String(255),
        nullable=False,
    )
    provider_center_name = db.Column(
        db.String(255),
        nullable=False,
    )
    sucursal_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "sucursales.sucursal_id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    routine_activity_date = db.Column(
        db.Date,
        nullable=False,
    )
    instructor_name = db.Column(
        db.String(255),
        nullable=False,
    )
    instructor_name_normalized = db.Column(
        db.String(255),
        nullable=False,
    )

    routine_count = db.Column(
        db.Integer,
        nullable=False,
    )
    weighing_count = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    first_observed_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("now()"),
    )
    last_observed_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("now()"),
    )

    first_provider_run_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "routine_control_provider_runs.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    last_provider_run_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "routine_control_provider_runs.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    payload_hash = db.Column(
        db.String(64),
        nullable=False,
    )
    source_metadata = db.Column(
        JSONB,
        nullable=True,
    )

    is_valid = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default=db.text("true"),
    )
    invalidated_at_utc = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )
    invalidated_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "users.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    invalidation_reason = db.Column(
        db.Text,
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("now()"),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("now()"),
        onupdate=db.func.now(),
    )

    sucursal = db.relationship(
        "Sucursal",
        foreign_keys=[sucursal_id],
    )
    first_provider_run = db.relationship(
        "RoutineControlProviderRunORM",
        foreign_keys=[first_provider_run_id],
    )
    last_provider_run = db.relationship(
        "RoutineControlProviderRunORM",
        foreign_keys=[last_provider_run_id],
    )
    invalidated_by = db.relationship(
        "UserORM",
        foreign_keys=[invalidated_by_user_id],
    )
    member_links = db.relationship(
        "RoutineControlMemberEvidenceORM",
        back_populates="evidence",
        passive_deletes=True,
    )


class RoutineControlMemberEvidenceORM(db.Model):
    __tablename__ = "routine_control_member_evidences"

    __table_args__ = (
        db.CheckConstraint(
            """
            match_method IN (
                'EXTERNAL_ID',
                'EMAIL'
            )
            """,
            name="ck_routine_control_member_evidences_match_method",
        ),
        db.CheckConstraint(
            """
            (
                is_active = true
                AND unlinked_at_utc IS NULL
                AND unlink_reason IS NULL
            )
            OR
            (
                is_active = false
                AND unlinked_at_utc IS NOT NULL
                AND unlink_reason IS NOT NULL
            )
            """,
            name="ck_routine_control_member_evidences_active",
        ),
        db.UniqueConstraint(
            "member_id",
            "evidence_id",
            name="uq_routine_control_member_evidences_pair",
        ),
        db.Index(
            "ix_routine_control_member_evidences_member_active",
            "member_id",
            "is_active",
        ),
        db.Index(
            "ix_routine_control_member_evidences_evidence_active",
            "evidence_id",
            "is_active",
        ),
        db.Index(
            "ix_routine_control_member_evidences_method_active",
            "match_method",
            "is_active",
        ),
    )

    id = db.Column(
        db.BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    member_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "routine_control_members.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    evidence_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "routine_assignment_evidences.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    match_method = db.Column(
        db.String(32),
        nullable=False,
    )
    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default=db.text("true"),
    )

    linked_by_provider_run_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "routine_control_provider_runs.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    linked_at_utc = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("now()"),
    )

    unlinked_by_provider_run_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "routine_control_provider_runs.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    unlinked_at_utc = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )
    unlink_reason = db.Column(
        db.Text,
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("now()"),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("now()"),
        onupdate=db.func.now(),
    )

    member = db.relationship(
        "RoutineControlMemberORM",
        back_populates="evidence_links",
    )
    evidence = db.relationship(
        "RoutineAssignmentEvidenceORM",
        back_populates="member_links",
    )
    linked_by_provider_run = db.relationship(
        "RoutineControlProviderRunORM",
        foreign_keys=[linked_by_provider_run_id],
    )
    unlinked_by_provider_run = db.relationship(
        "RoutineControlProviderRunORM",
        foreign_keys=[unlinked_by_provider_run_id],
    )
