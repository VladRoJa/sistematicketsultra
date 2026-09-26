from __future__ import annotations

from app.extensions import db


ATTENDANCE_RUN_STATUSES = ("RUNNING", "SUCCESS", "FAILED")
ATTENDANCE_VISIT_STATUSES = (
    "CLOSED",
    "OPEN",
    "INVALID_TIME",
    "CROSS_DAY",
)


class WarehouseAttendanceRunORM(db.Model):
    __tablename__ = "warehouse_attendance_runs"
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('RUNNING', 'SUCCESS', 'FAILED')",
            name="ck_wh_attendance_runs_status",
        ),
        db.CheckConstraint(
            """
            source_rows >= 0
            AND inserted_rows >= 0
            AND updated_rows >= 0
            AND rejected_rows >= 0
            """,
            name="ck_wh_attendance_runs_nonnegative_counts",
        ),
        db.Index(
            "ix_wh_attendance_runs_date_status",
            "business_date",
            "status",
        ),
    )

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    business_date = db.Column(db.Date, nullable=False)
    status = db.Column(
        db.String(20),
        nullable=False,
        default="RUNNING",
        server_default="RUNNING",
    )
    trigger_source = db.Column(
        db.String(40),
        nullable=False,
        default="MANUAL_FILE",
        server_default="MANUAL_FILE",
    )
    source_sha256 = db.Column(db.String(64), nullable=True)
    parser_version = db.Column(
        db.String(32),
        nullable=False,
        default="v1",
        server_default="v1",
    )

    source_rows = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    inserted_rows = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    updated_rows = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    rejected_rows = db.Column(db.Integer, nullable=False, default=0, server_default="0")

    error_message = db.Column(db.Text, nullable=True)
    started_at_utc = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("now()"),
    )
    finished_at_utc = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at_utc = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("now()"),
    )


class WarehouseAttendanceVisitORM(db.Model):
    __tablename__ = "warehouse_attendance_visits"
    __table_args__ = (
        db.CheckConstraint(
            """
            visit_status IN (
                'CLOSED',
                'OPEN',
                'INVALID_TIME',
                'CROSS_DAY'
            )
            """,
            name="ck_wh_attendance_visits_status",
        ),
        db.CheckConstraint(
            "duration_seconds IS NULL OR duration_seconds >= 0",
            name="ck_wh_attendance_visits_duration",
        ),
        db.UniqueConstraint(
            "source_fingerprint",
            name="uq_wh_attendance_visits_fingerprint",
        ),
        db.Index(
            "ix_wh_attendance_visits_date_branch_type",
            "business_date",
            "sucursal_id",
            "attendance_type",
        ),
        db.Index(
            "ix_wh_attendance_visits_pin_date",
            "member_pin",
            "business_date",
        ),
        db.Index(
            "ix_wh_attendance_visits_entered_at",
            "entered_at_utc",
        ),
        db.Index(
            "ix_wh_attendance_visits_date_status",
            "business_date",
            "visit_status",
        ),
    )

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    business_date = db.Column(db.Date, nullable=False)

    sucursal_id = db.Column(
        db.Integer,
        db.ForeignKey("sucursales.sucursal_id", ondelete="SET NULL"),
        nullable=True,
    )
    source_branch_name = db.Column(db.String(255), nullable=False)

    member_pin = db.Column(db.String(64), nullable=True)
    entered_at_utc = db.Column(db.DateTime(timezone=True), nullable=False)
    exited_at_utc = db.Column(db.DateTime(timezone=True), nullable=True)
    duration_seconds = db.Column(db.Integer, nullable=True)
    visit_status = db.Column(db.String(24), nullable=False)

    age = db.Column(db.SmallInteger, nullable=True)
    age_is_valid = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default=db.text("true"),
    )
    city = db.Column(db.String(160), nullable=True)
    postal_code = db.Column(db.String(32), nullable=True)
    member_since = db.Column(db.Date, nullable=True)

    attendance_type = db.Column(db.String(100), nullable=False)
    has_opening = db.Column(db.Boolean, nullable=True)

    source_row_number = db.Column(db.Integer, nullable=False)
    source_fingerprint = db.Column(db.String(64), nullable=False)
    last_run_id = db.Column(
        db.BigInteger,
        db.ForeignKey("warehouse_attendance_runs.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at_utc = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("now()"),
    )
    updated_at_utc = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("now()"),
        onupdate=db.func.now(),
    )

    sucursal = db.relationship("Sucursal", foreign_keys=[sucursal_id])
    last_run = db.relationship("WarehouseAttendanceRunORM", foreign_keys=[last_run_id])


class WarehouseAttendanceRejectionORM(db.Model):
    __tablename__ = "warehouse_attendance_rejections"
    __table_args__ = (
        db.Index(
            "ix_wh_attendance_rejections_run",
            "run_id",
            "source_row_number",
        ),
    )

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    run_id = db.Column(
        db.BigInteger,
        db.ForeignKey("warehouse_attendance_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    business_date = db.Column(db.Date, nullable=False)
    source_row_number = db.Column(db.Integer, nullable=False)
    reason_code = db.Column(db.String(64), nullable=False)
    detail = db.Column(db.String(500), nullable=True)

    member_pin = db.Column(db.String(64), nullable=True)
    source_branch_name = db.Column(db.String(255), nullable=True)
    entered_at_raw = db.Column(db.String(100), nullable=True)
    attendance_type_raw = db.Column(db.String(100), nullable=True)

    created_at_utc = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("now()"),
    )


class TrackAttendanceIntervalMartORM(db.Model):
    __tablename__ = "track_attendance_interval_mart"
    __table_args__ = (
        db.CheckConstraint(
            "bucket_minute >= 0 AND bucket_minute < 1440",
            name="ck_track_att_interval_bucket_minute",
        ),
        db.CheckConstraint(
            "bucket_minute % 15 = 0",
            name="ck_track_att_interval_bucket_15m",
        ),
        db.CheckConstraint(
            """
            entries >= 0
            AND exits >= 0
            AND occupancy >= 0
            AND unique_entries >= 0
            """,
            name="ck_track_att_interval_nonnegative",
        ),
        db.UniqueConstraint(
            "business_date",
            "sucursal_id",
            "attendance_type",
            "bucket_minute",
            name="uq_track_att_interval_date_branch_type_bucket",
        ),
        db.Index(
            "ix_track_att_interval_date_branch",
            "business_date",
            "sucursal_id",
        ),
    )

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    business_date = db.Column(db.Date, nullable=False)
    sucursal_id = db.Column(
        db.Integer,
        db.ForeignKey("sucursales.sucursal_id", ondelete="CASCADE"),
        nullable=False,
    )
    attendance_type = db.Column(db.String(100), nullable=False)
    bucket_minute = db.Column(db.SmallInteger, nullable=False)

    entries = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    exits = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    occupancy = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    unique_entries = db.Column(db.Integer, nullable=False, default=0, server_default="0")

    source_run_id = db.Column(
        db.BigInteger,
        db.ForeignKey("warehouse_attendance_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_at_utc = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("now()"),
        onupdate=db.func.now(),
    )


class TrackAttendanceDailyMartORM(db.Model):
    __tablename__ = "track_attendance_daily_mart"
    __table_args__ = (
        db.CheckConstraint(
            """
            visits >= 0
            AND unique_members >= 0
            AND closed_visits >= 0
            AND open_visits >= 0
            AND cross_day_visits >= 0
            AND invalid_time_visits >= 0
            AND peak_occupancy >= 0
            """,
            name="ck_track_att_daily_nonnegative",
        ),
        db.CheckConstraint(
            """
            peak_minute IS NULL
            OR (peak_minute >= 0 AND peak_minute < 1440)
            """,
            name="ck_track_att_daily_peak_minute",
        ),
        db.UniqueConstraint(
            "business_date",
            "sucursal_id",
            "attendance_type",
            name="uq_track_att_daily_date_branch_type",
        ),
        db.Index(
            "ix_track_att_daily_date_branch",
            "business_date",
            "sucursal_id",
        ),
    )

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    business_date = db.Column(db.Date, nullable=False)
    sucursal_id = db.Column(
        db.Integer,
        db.ForeignKey("sucursales.sucursal_id", ondelete="CASCADE"),
        nullable=False,
    )
    attendance_type = db.Column(db.String(100), nullable=False)

    visits = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    unique_members = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    closed_visits = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    open_visits = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    cross_day_visits = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    invalid_time_visits = db.Column(db.Integer, nullable=False, default=0, server_default="0")

    average_duration_seconds = db.Column(db.Integer, nullable=True)
    median_duration_seconds = db.Column(db.Integer, nullable=True)
    peak_occupancy = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    peak_minute = db.Column(db.SmallInteger, nullable=True)

    source_run_id = db.Column(
        db.BigInteger,
        db.ForeignKey("warehouse_attendance_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_at_utc = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.text("now()"),
        onupdate=db.func.now(),
    )
