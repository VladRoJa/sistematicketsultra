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
