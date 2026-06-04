#   backend\app\models\openings.py


from datetime import datetime, timezone

from app.extensions import db


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class OpeningStatus:
    DRAFT = "BORRADOR"
    PLANNED = "PLANEADA"
    IN_PROGRESS = "EN_EJECUCION"
    AT_RISK = "EN_RIESGO"
    PAUSED = "PAUSADA"
    OPENED = "ABIERTA"
    CANCELLED = "CANCELADA"
    CLOSED = "CERRADA"

    ALL = (
        DRAFT,
        PLANNED,
        IN_PROGRESS,
        AT_RISK,
        PAUSED,
        OPENED,
        CANCELLED,
        CLOSED,
    )


class OpeningPhaseStatus:
    NOT_STARTED = "NO_INICIADA"
    IN_PROGRESS = "EN_PROCESO"
    BLOCKED = "BLOQUEADA"
    AT_RISK = "EN_RIESGO"
    COMPLETED = "COMPLETADA"
    CANCELLED = "CANCELADA"

    ALL = (
        NOT_STARTED,
        IN_PROGRESS,
        BLOCKED,
        AT_RISK,
        COMPLETED,
        CANCELLED,
    )


class OpeningTaskStatus:
    NOT_STARTED = "NO_INICIADA"
    IN_PROGRESS = "EN_PROCESO"
    BLOCKED = "BLOQUEADA"
    IN_REVIEW = "EN_REVISION"
    COMPLETED = "COMPLETADA"
    CANCELLED = "CANCELADA"

    ALL = (
        NOT_STARTED,
        IN_PROGRESS,
        BLOCKED,
        IN_REVIEW,
        COMPLETED,
        CANCELLED,
    )


class OpeningTaskPriority:
    LOW = "BAJA"
    MEDIUM = "MEDIA"
    HIGH = "ALTA"
    CRITICAL = "CRITICA"

    ALL = (
        LOW,
        MEDIUM,
        HIGH,
        CRITICAL,
    )


class OpeningDependencyType:
    BLOCKER = "BLOCKER"
    FINISH_TO_START = "FINISH_TO_START"
    START_TO_START = "START_TO_START"
    FINISH_TO_FINISH = "FINISH_TO_FINISH"

    ALL = (
        BLOCKER,
        FINISH_TO_START,
        START_TO_START,
        FINISH_TO_FINISH,
    )


class OpeningAuditAction:
    OPENING_CREATED = "OPENING_CREATED"
    OPENING_UPDATED = "OPENING_UPDATED"
    PHASE_CREATED = "PHASE_CREATED"
    PHASE_UPDATED = "PHASE_UPDATED"
    TASK_CREATED = "TASK_CREATED"
    TASK_UPDATED = "TASK_UPDATED"
    TASK_STATUS_CHANGED = "TASK_STATUS_CHANGED"
    TASK_DUE_DATE_CHANGED = "TASK_DUE_DATE_CHANGED"
    TASK_OWNER_CHANGED = "TASK_OWNER_CHANGED"
    TASK_DEPENDENCY_CREATED = "TASK_DEPENDENCY_CREATED"
    TASK_DEPENDENCY_DELETED = "TASK_DEPENDENCY_DELETED"
    TASK_COMMENT_CREATED = "TASK_COMMENT_CREATED"
    DOCUMENT_LINKED = "DOCUMENT_LINKED"
    DOCUMENT_UNLINKED = "DOCUMENT_UNLINKED"

    ALL = (
        OPENING_CREATED,
        OPENING_UPDATED,
        PHASE_CREATED,
        PHASE_UPDATED,
        TASK_CREATED,
        TASK_UPDATED,
        TASK_STATUS_CHANGED,
        TASK_DUE_DATE_CHANGED,
        TASK_OWNER_CHANGED,
        TASK_DEPENDENCY_CREATED,
        TASK_DEPENDENCY_DELETED,
        TASK_COMMENT_CREATED,
        DOCUMENT_LINKED,
        DOCUMENT_UNLINKED,
    )


class OpeningORM(db.Model):
    __tablename__ = "openings"

    id = db.Column(db.Integer, primary_key=True)

    sucursal_id = db.Column(
        db.Integer,
        db.ForeignKey("sucursales.sucursal_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    opening_key = db.Column(db.String(80), nullable=False, unique=True, index=True)
    name = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, nullable=True)

    status = db.Column(
        db.String(32),
        nullable=False,
        default=OpeningStatus.DRAFT,
        server_default=OpeningStatus.DRAFT,
        index=True,
    )

    planned_start_date = db.Column(db.Date, nullable=True)
    target_opening_date = db.Column(db.Date, nullable=True)
    actual_opening_date = db.Column(db.Date, nullable=True)

    general_owner_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    budget_authorized_total = db.Column(db.Numeric(14, 2), nullable=True)
    budget_currency_code = db.Column(
        db.String(3),
        nullable=False,
        default="MXN",
        server_default="MXN",
    )

    created_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    updated_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    sucursal = db.relationship("Sucursal", lazy="joined")
    general_owner_user = db.relationship(
        "UserORM",
        foreign_keys=[general_owner_user_id],
    )
    creator = db.relationship("UserORM", foreign_keys=[created_by])
    updater = db.relationship("UserORM", foreign_keys=[updated_by])

    phases = db.relationship(
        "OpeningPhaseORM",
        back_populates="opening",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    tasks = db.relationship(
        "OpeningTaskORM",
        back_populates="opening",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    __table_args__ = (
        db.Index("idx_openings_status_target_date", "status", "target_opening_date"),
    )

    def __repr__(self) -> str:
        return f"<Opening key={self.opening_key!r} status={self.status!r}>"


class OpeningPhaseORM(db.Model):
    __tablename__ = "opening_phases"

    id = db.Column(db.Integer, primary_key=True)

    opening_id = db.Column(
        db.Integer,
        db.ForeignKey("openings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name = db.Column(db.String(140), nullable=False)
    description = db.Column(db.Text, nullable=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0, server_default="0")

    planned_start_date = db.Column(db.Date, nullable=True)
    planned_end_date = db.Column(db.Date, nullable=True)
    actual_start_date = db.Column(db.Date, nullable=True)
    actual_end_date = db.Column(db.Date, nullable=True)

    status = db.Column(
        db.String(32),
        nullable=False,
        default=OpeningPhaseStatus.NOT_STARTED,
        server_default=OpeningPhaseStatus.NOT_STARTED,
        index=True,
    )

    owner_department_id = db.Column(
        db.Integer,
        db.ForeignKey("departamentos.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    owner_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    progress_percent = db.Column(
        db.Numeric(5, 2),
        nullable=False,
        default=0,
        server_default="0",
    )

    created_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    updated_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    opening = db.relationship("OpeningORM", back_populates="phases")
    owner_department = db.relationship("Departamento", foreign_keys=[owner_department_id])
    owner_user = db.relationship("UserORM", foreign_keys=[owner_user_id])
    creator = db.relationship("UserORM", foreign_keys=[created_by])
    updater = db.relationship("UserORM", foreign_keys=[updated_by])

    tasks = db.relationship(
        "OpeningTaskORM",
        back_populates="phase",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    __table_args__ = (
        db.UniqueConstraint(
            "opening_id",
            "name",
            name="uq_opening_phases_opening_name",
        ),
        db.Index("idx_opening_phases_opening_order", "opening_id", "sort_order"),
    )

    def __repr__(self) -> str:
        return f"<OpeningPhase opening_id={self.opening_id} name={self.name!r}>"


class OpeningTaskORM(db.Model):
    __tablename__ = "opening_tasks"

    id = db.Column(db.Integer, primary_key=True)

    opening_id = db.Column(
        db.Integer,
        db.ForeignKey("openings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    phase_id = db.Column(
        db.Integer,
        db.ForeignKey("opening_phases.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    parent_task_id = db.Column(
        db.Integer,
        db.ForeignKey("opening_tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    title = db.Column(db.String(220), nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)

    status = db.Column(
        db.String(32),
        nullable=False,
        default=OpeningTaskStatus.NOT_STARTED,
        server_default=OpeningTaskStatus.NOT_STARTED,
        index=True,
    )
    priority = db.Column(
        db.String(20),
        nullable=False,
        default=OpeningTaskPriority.MEDIUM,
        server_default=OpeningTaskPriority.MEDIUM,
        index=True,
    )

    owner_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    owner_department_id = db.Column(
        db.Integer,
        db.ForeignKey("departamentos.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    planned_start_date = db.Column(db.Date, nullable=True)
    planned_due_date = db.Column(db.Date, nullable=True, index=True)
    actual_start_date = db.Column(db.Date, nullable=True)
    actual_completed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    progress_percent = db.Column(
        db.Numeric(5, 2),
        nullable=False,
        default=0,
        server_default="0",
    )

    sort_order = db.Column(db.Integer, nullable=False, default=0, server_default="0")

    requires_document = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    requires_payment = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )

    created_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    updated_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    opening = db.relationship("OpeningORM", back_populates="tasks")
    phase = db.relationship("OpeningPhaseORM", back_populates="tasks")
    parent_task = db.relationship(
        "OpeningTaskORM",
        remote_side=[id],
        foreign_keys=[parent_task_id],
    )

    owner_user = db.relationship("UserORM", foreign_keys=[owner_user_id])
    owner_department = db.relationship("Departamento", foreign_keys=[owner_department_id])
    creator = db.relationship("UserORM", foreign_keys=[created_by])
    updater = db.relationship("UserORM", foreign_keys=[updated_by])

    dependencies = db.relationship(
        "OpeningTaskDependencyORM",
        foreign_keys="OpeningTaskDependencyORM.task_id",
        back_populates="task",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    
    comments = db.relationship(
        "OpeningTaskCommentORM",
        back_populates="task",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )    

    __table_args__ = (
        db.Index("idx_opening_tasks_opening_phase_order", "opening_id", "phase_id", "sort_order"),
        db.Index("idx_opening_tasks_status_due", "status", "planned_due_date"),
        db.CheckConstraint(
            "progress_percent >= 0 AND progress_percent <= 100",
            name="ck_opening_tasks_progress_range",
        ),
    )

    def __repr__(self) -> str:
        return f"<OpeningTask opening_id={self.opening_id} title={self.title!r}>"


class OpeningTaskDependencyORM(db.Model):
    __tablename__ = "opening_task_dependencies"

    id = db.Column(db.Integer, primary_key=True)

    task_id = db.Column(
        db.Integer,
        db.ForeignKey("opening_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    depends_on_task_id = db.Column(
        db.Integer,
        db.ForeignKey("opening_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    dependency_type = db.Column(
        db.String(32),
        nullable=False,
        default=OpeningDependencyType.BLOCKER,
        server_default=OpeningDependencyType.BLOCKER,
    )

    created_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    task = db.relationship(
        "OpeningTaskORM",
        foreign_keys=[task_id],
        back_populates="dependencies",
    )
    depends_on_task = db.relationship(
        "OpeningTaskORM",
        foreign_keys=[depends_on_task_id],
    )
    creator = db.relationship("UserORM", foreign_keys=[created_by])

    __table_args__ = (
        db.UniqueConstraint(
            "task_id",
            "depends_on_task_id",
            name="uq_opening_task_dependencies_pair",
        ),
        db.CheckConstraint(
            "task_id <> depends_on_task_id",
            name="ck_opening_task_dependencies_no_self",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<OpeningTaskDependency task_id={self.task_id} "
            f"depends_on_task_id={self.depends_on_task_id}>"
        )

class OpeningTaskCommentORM(db.Model):
    __tablename__ = "opening_task_comments"

    id = db.Column(db.Integer, primary_key=True)

    opening_id = db.Column(
        db.Integer,
        db.ForeignKey("openings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    task_id = db.Column(
        db.Integer,
        db.ForeignKey("opening_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    comment = db.Column(db.Text, nullable=False)

    is_system_event = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        server_default="false",
        index=True,
    )

    created_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        index=True,
    )

    opening = db.relationship("OpeningORM")
    task = db.relationship("OpeningTaskORM", back_populates="comments")
    creator = db.relationship("UserORM", foreign_keys=[created_by])

    __table_args__ = (
        db.Index("idx_opening_task_comments_task_created", "task_id", "created_at"),
        db.Index("idx_opening_task_comments_opening_created", "opening_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<OpeningTaskComment task_id={self.task_id} created_by={self.created_by}>"

class OpeningAuditLogORM(db.Model):
    __tablename__ = "opening_audit_logs"

    id = db.Column(db.Integer, primary_key=True)

    opening_id = db.Column(
        db.Integer,
        db.ForeignKey("openings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    entity_type = db.Column(db.String(40), nullable=False, index=True)
    entity_id = db.Column(db.Integer, nullable=True, index=True)
    action = db.Column(db.String(80), nullable=False, index=True)

    old_value_json = db.Column(db.JSON, nullable=True)
    new_value_json = db.Column(db.JSON, nullable=True)
    metadata_json = db.Column(db.JSON, nullable=True)

    actor_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        index=True,
    )

    opening = db.relationship("OpeningORM")
    actor_user = db.relationship("UserORM", foreign_keys=[actor_user_id])

    __table_args__ = (
        db.Index("idx_opening_audit_logs_opening_action", "opening_id", "action"),
        db.Index("idx_opening_audit_logs_entity", "entity_type", "entity_id"),
    )

    def __repr__(self) -> str:
        return f"<OpeningAuditLog opening_id={self.opening_id} action={self.action!r}>"