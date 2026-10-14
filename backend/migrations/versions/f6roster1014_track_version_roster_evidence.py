"""M1-F6 stage 1: version-bound, immutable expected Track roster evidence.

Revision ID: f6roster1014
Revises: c856map1014

Empty schema only. Never infer historical rosters from today's Track catalog.
Capture and SLA certification are separate, later review gates.
"""
from alembic import op
import sqlalchemy as sa

revision = "f6roster1014"
down_revision = "c856map1014"
branch_labels = None
depends_on = None

SNAPSHOT = "track_version_roster_snapshots"
MEMBER = "track_version_roster_members"


def upgrade():
    op.create_table(
        SNAPSHOT,
        sa.Column("version_id", sa.BigInteger(), nullable=False, primary_key=True),
        sa.Column("track_date", sa.Date(), nullable=False),
        sa.Column("captured_at_utc", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("sealed_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expected_branch_count", sa.Integer(), nullable=False),
        sa.Column("roster_sha256", sa.String(64), nullable=False),
        sa.Column("source_kind", sa.String(64), nullable=False,
                  server_default="LIVE_TRACK_CATALOG_NON_DEMO_AT_CAPTURE"),
        sa.Column("historical_roster_verified", sa.Boolean(), nullable=False,
                  server_default=sa.text("FALSE")),
        sa.ForeignKeyConstraint(["version_id"], ["track_daily_versions.id"],
                                ondelete="RESTRICT",
                                name="fk_track_roster_snapshot_version"),
        sa.CheckConstraint("expected_branch_count > 0",
                           name="ck_track_roster_expected_positive"),
        sa.CheckConstraint("roster_sha256 ~ '^[0-9a-f]{64}$'",
                           name="ck_track_roster_sha256"),
        sa.CheckConstraint(
            "source_kind = 'LIVE_TRACK_CATALOG_NON_DEMO_AT_CAPTURE'",
            name="ck_track_roster_source_kind"),
        sa.CheckConstraint("historical_roster_verified = FALSE",
                           name="ck_track_roster_no_unverified_green"),
        sa.CheckConstraint("sealed_at_utc IS NULL OR sealed_at_utc >= captured_at_utc",
                           name="ck_track_roster_seal_not_before_capture"),
    )
    op.create_table(
        MEMBER,
        sa.Column("version_id", sa.BigInteger(), nullable=False),
        sa.Column("sucursal_canon", sa.Text(), nullable=False),
        sa.Column("sucursal_id_at_capture", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("version_id", "sucursal_canon",
                                name="pk_track_roster_members"),
        sa.ForeignKeyConstraint(["version_id"], [SNAPSHOT + ".version_id"],
                                ondelete="RESTRICT",
                                name="fk_track_roster_member_snapshot"),
        sa.CheckConstraint("length(trim(sucursal_canon)) > 0",
                           name="ck_track_roster_member_nonblank"),
    )

    # Only a running version can receive contemporary roster evidence.
    # Historical versions that already succeeded cannot be retroactively
    # decorated with an assumed roster by the normal application role.
    op.execute("""
CREATE FUNCTION m1f6_guard_roster_snapshot() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    version_date date;
    version_status text;
    version_started timestamptz;
    member_count bigint;
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Track roster evidence is immutable';
    END IF;
    IF TG_OP = 'INSERT' THEN
        SELECT track_date, status, started_at_utc
          INTO version_date, version_status, version_started
          FROM track_daily_versions WHERE id = NEW.version_id FOR SHARE;
        IF NOT FOUND OR version_status <> 'running'
           OR version_started IS NULL OR version_date IS DISTINCT FROM NEW.track_date THEN
            RAISE EXCEPTION 'Roster capture requires a running version of the same business date';
        END IF;
        NEW.captured_at_utc := CURRENT_TIMESTAMP;
        IF NEW.sealed_at_utc IS NOT NULL OR NEW.historical_roster_verified THEN
            RAISE EXCEPTION 'New Track roster evidence must start unsealed and uncertified';
        END IF;
        RETURN NEW;
    END IF;
    IF OLD.sealed_at_utc IS NOT NULL OR NEW.sealed_at_utc IS NULL
       OR NEW.version_id IS DISTINCT FROM OLD.version_id
       OR NEW.track_date IS DISTINCT FROM OLD.track_date
       OR NEW.captured_at_utc IS DISTINCT FROM OLD.captured_at_utc
       OR NEW.expected_branch_count IS DISTINCT FROM OLD.expected_branch_count
       OR NEW.roster_sha256 IS DISTINCT FROM OLD.roster_sha256
       OR NEW.source_kind IS DISTINCT FROM OLD.source_kind
       OR NEW.historical_roster_verified IS DISTINCT FROM OLD.historical_roster_verified THEN
        RAISE EXCEPTION 'Track roster metadata cannot be modified or resealed';
    END IF;
    SELECT count(*) INTO member_count FROM track_version_roster_members
      WHERE version_id = OLD.version_id;
    IF member_count <> OLD.expected_branch_count THEN
        RAISE EXCEPTION 'Cannot seal Track roster: member count mismatch';
    END IF;
    RETURN NEW;
END;
$$;
""")
    op.execute("""
CREATE TRIGGER trg_m1f6_guard_roster_snapshot
BEFORE INSERT OR UPDATE OR DELETE ON track_version_roster_snapshots
FOR EACH ROW EXECUTE FUNCTION m1f6_guard_roster_snapshot();
""")
    op.execute("""
CREATE FUNCTION m1f6_guard_roster_member() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    sealed_at timestamptz;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'Track roster members are append-only';
    END IF;
    SELECT sealed_at_utc INTO sealed_at FROM track_version_roster_snapshots
      WHERE version_id = NEW.version_id FOR UPDATE;
    IF NOT FOUND OR sealed_at IS NOT NULL THEN
        RAISE EXCEPTION 'Cannot add Track roster member after sealing or without snapshot';
    END IF;
    RETURN NEW;
END;
$$;
""")
    op.execute("""
CREATE TRIGGER trg_m1f6_guard_roster_member
BEFORE INSERT OR UPDATE OR DELETE ON track_version_roster_members
FOR EACH ROW EXECUTE FUNCTION m1f6_guard_roster_member();
""")


def downgrade():
    bind = op.get_bind()
    for table in (MEMBER, SNAPSHOT):
        if bind.execute(sa.text("SELECT EXISTS (SELECT 1 FROM " + table + ")")).scalar():
            raise RuntimeError("No se elimina evidencia histórica Track registrada.")
    op.execute("DROP TRIGGER trg_m1f6_guard_roster_member ON " + MEMBER)
    op.execute("DROP FUNCTION m1f6_guard_roster_member()")
    op.execute("DROP TRIGGER trg_m1f6_guard_roster_snapshot ON " + SNAPSHOT)
    op.execute("DROP FUNCTION m1f6_guard_roster_snapshot()")
    op.drop_table(MEMBER)
    op.drop_table(SNAPSHOT)
