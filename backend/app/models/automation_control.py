"""Worker liveness metadata; distinct from job outcome and dataset freshness."""
from app.extensions import db


class SystemWorkerHeartbeatORM(db.Model):
    __tablename__ = "system_worker_heartbeats"

    worker_key = db.Column(db.String(64), primary_key=True)
    instance_id = db.Column(db.String(32), primary_key=True)
    started_at = db.Column(db.DateTime(timezone=True), nullable=False)
    last_seen_at = db.Column(db.DateTime(timezone=True), nullable=False)
    poll_interval_seconds = db.Column(db.Integer, nullable=False)
    enabled = db.Column(db.Boolean, nullable=False)
    # Typed, sanitized summaries reported by the worker itself, never raw env.
    job_schedules = db.Column(db.JSON, nullable=True)

    __table_args__ = (
        db.CheckConstraint(
            "poll_interval_seconds BETWEEN 10 AND 3600",
            name="ck_system_worker_heartbeat_poll",
        ),
        db.Index("ix_system_worker_heartbeat_last_seen", "last_seen_at"),
    )
