from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _sql_values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class SystemDailyCheckAnswerValue:
    YES = "YES"
    NO = "NO"
    NA = "NA"
    ALL = (YES, NO, NA)


class SystemDailyCheckGeneralStatus:
    NORMAL = "NORMAL"
    MINOR_FAILURE = "MINOR_FAILURE"
    OPERATIONAL_IMPACT = "OPERATIONAL_IMPACT"
    ALL = (NORMAL, MINOR_FAILURE, OPERATIONAL_IMPACT)


class SystemDailyCheckAffectedScope:
    ONE = "ONE"
    MULTIPLE = "MULTIPLE"
    ALL = (ONE, MULTIPLE)


class SystemDailyCheckORM(db.Model):
    __tablename__ = "system_daily_checks"

    id = db.Column(
        db.BigInteger().with_variant(db.Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    sucursal_id = db.Column(
        db.Integer,
        db.ForeignKey("sucursales.sucursal_id", ondelete="RESTRICT"),
        nullable=False,
    )
    business_date = db.Column(db.Date, nullable=False)
    performed_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    general_status = db.Column(db.String(32), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )
    submitted_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )

    sucursal = db.relationship("Sucursal")
    performed_by_user = db.relationship("UserORM")
    answers = db.relationship(
        "SystemDailyCheckAnswerORM",
        back_populates="check",
        cascade="all, delete-orphan",
        order_by="SystemDailyCheckAnswerORM.id",
    )

    __table_args__ = (
        db.UniqueConstraint(
            "sucursal_id",
            "business_date",
            name="uq_system_daily_checks_branch_date",
        ),
        db.CheckConstraint(
            f"general_status IN ({_sql_values(SystemDailyCheckGeneralStatus.ALL)})",
            name="ck_system_daily_checks_general_status",
        ),
        db.Index(
            "ix_system_daily_checks_business_date_status",
            "business_date",
            "general_status",
        ),
    )


class SystemDailyCheckAnswerORM(db.Model):
    __tablename__ = "system_daily_check_answers"

    id = db.Column(
        db.BigInteger().with_variant(db.Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    check_id = db.Column(
        db.BigInteger,
        db.ForeignKey("system_daily_checks.id", ondelete="CASCADE"),
        nullable=False,
    )
    question_key = db.Column(db.String(80), nullable=False)
    question_label_snapshot = db.Column(db.String(255), nullable=False)
    category_key = db.Column(db.String(80), nullable=True)
    answer = db.Column(db.String(8), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )

    check = db.relationship(
        "SystemDailyCheckORM",
        back_populates="answers",
    )
    issue = db.relationship(
        "SystemDailyCheckIssueORM",
        back_populates="answer_row",
        cascade="all, delete-orphan",
        uselist=False,
    )

    __table_args__ = (
        db.UniqueConstraint(
            "check_id",
            "question_key",
            name="uq_system_daily_check_answers_check_question",
        ),
        db.CheckConstraint(
            f"answer IN ({_sql_values(SystemDailyCheckAnswerValue.ALL)})",
            name="ck_system_daily_check_answers_value",
        ),
        db.CheckConstraint(
            "length(trim(question_key)) > 0",
            name="ck_system_daily_check_answers_question_key_nonempty",
        ),
        db.CheckConstraint(
            "length(trim(question_label_snapshot)) > 0",
            name="ck_system_daily_check_answers_label_nonempty",
        ),
        db.Index(
            "ix_system_daily_check_answers_question_answer",
            "question_key",
            "answer",
        ),
    )


class SystemDailyCheckIssueORM(db.Model):
    __tablename__ = "system_daily_check_issues"

    id = db.Column(
        db.BigInteger().with_variant(db.Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    answer_id = db.Column(
        db.BigInteger,
        db.ForeignKey("system_daily_check_answers.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    affected_scope = db.Column(db.String(16), nullable=True)
    reported_to_support = db.Column(db.Boolean, nullable=False)
    description = db.Column(db.Text, nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )

    answer_row = db.relationship(
        "SystemDailyCheckAnswerORM",
        back_populates="issue",
    )
    attachments = db.relationship(
        "SystemDailyCheckIssueAttachmentORM",
        back_populates="issue",
        cascade="all, delete-orphan",
        order_by="SystemDailyCheckIssueAttachmentORM.id",
    )

    __table_args__ = (
        db.CheckConstraint(
            "affected_scope IS NULL OR "
            f"affected_scope IN ({_sql_values(SystemDailyCheckAffectedScope.ALL)})",
            name="ck_system_daily_check_issues_affected_scope",
        ),
        db.CheckConstraint(
            "length(trim(description)) > 0",
            name="ck_system_daily_check_issues_description_nonempty",
        ),
        db.Index(
            "ix_system_daily_check_issues_reported",
            "reported_to_support",
        ),
    )


class SystemDailyCheckIssueAttachmentORM(db.Model):
    __tablename__ = "system_daily_check_issue_attachments"

    id = db.Column(
        db.BigInteger().with_variant(db.Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    issue_id = db.Column(
        db.BigInteger,
        db.ForeignKey("system_daily_check_issues.id", ondelete="CASCADE"),
        nullable=False,
    )
    original_filename = db.Column(db.String(255), nullable=False)
    storage_key = db.Column(db.String(500), nullable=False, unique=True)
    mime_type = db.Column(db.String(100), nullable=False)
    file_size_bytes = db.Column(db.BigInteger, nullable=False)
    sha256 = db.Column(db.String(64), nullable=False)
    uploaded_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )

    issue = db.relationship(
        "SystemDailyCheckIssueORM",
        back_populates="attachments",
    )
    uploaded_by_user = db.relationship("UserORM")

    __table_args__ = (
        db.CheckConstraint(
            "length(trim(original_filename)) > 0",
            name="ck_system_daily_check_issue_attachments_filename_nonempty",
        ),
        db.CheckConstraint(
            "length(trim(storage_key)) > 0",
            name="ck_system_daily_check_issue_attachments_storage_key_nonempty",
        ),
        db.CheckConstraint(
            "file_size_bytes >= 0",
            name="ck_system_daily_check_issue_attachments_size_nonnegative",
        ),
        db.CheckConstraint(
            "length(sha256) = 64",
            name="ck_system_daily_check_issue_attachments_sha256_length",
        ),
        db.Index(
            "ix_system_daily_check_issue_attachments_issue",
            "issue_id",
        ),
    )


class SystemDailyCheckPromptStateORM(db.Model):
    __tablename__ = "system_daily_check_prompt_states"

    id = db.Column(
        db.BigInteger().with_variant(db.Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    sucursal_id = db.Column(
        db.Integer,
        db.ForeignKey("sucursales.sucursal_id", ondelete="RESTRICT"),
        nullable=False,
    )
    business_date = db.Column(db.Date, nullable=False)
    postpone_count = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    last_postponed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    next_prompt_at = db.Column(db.DateTime(timezone=True), nullable=True)
    mandatory_from_at = db.Column(db.DateTime(timezone=True), nullable=True)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
    )

    sucursal = db.relationship("Sucursal")

    __table_args__ = (
        db.UniqueConstraint(
            "sucursal_id",
            "business_date",
            name="uq_system_daily_check_prompt_branch_date",
        ),
        db.CheckConstraint(
            "postpone_count >= 0 AND postpone_count <= 2",
            name="ck_system_daily_check_prompt_postpone_count",
        ),
        db.Index(
            "ix_system_daily_check_prompt_business_date",
            "business_date",
        ),
    )
