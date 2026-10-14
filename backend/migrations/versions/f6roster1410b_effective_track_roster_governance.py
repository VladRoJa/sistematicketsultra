"""M1-F6 stage 3: future-only, operator-attested effective Track roster.

Revision ID: f6roster1410b
Revises: f6roster1014

No backfill, seed, retroactive reconstruction, or automatic attestation.
The Track catalog is not a historized source until explicitly attested.
"""
from alembic import op
import sqlalchemy as sa

revision = "f6roster1410b"
down_revision = "f6roster1014"
branch_labels = None
depends_on = None

EPOCHS = "track_roster_effective_epochs"
MEMBERS = "track_roster_effective_members"


def upgrade():
    op.create_table(
        EPOCHS,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("attested_at_utc", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("attested_by_user_id", sa.Integer(), nullable=False),
        sa.Column("source_reference", sa.String(255), nullable=False),
        sa.Column("source_kind", sa.String(40), nullable=False,
                  server_default="CORPORATE_ROSTER_ATTESTATION"),
        sa.Column("expected_branch_count", sa.Integer(), nullable=False),
        sa.Column("roster_sha256", sa.String(64), nullable=False),
        sa.Column("sealed_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("effective_from", name="uq_track_roster_epoch_effective_from"),
        sa.ForeignKeyConstraint(["attested_by_user_id"], ["users.id"],
                                ondelete="RESTRICT",
                                name="fk_track_roster_epoch_attestor"),
        sa.CheckConstraint("expected_branch_count > 0",
                           name="ck_track_epoch_positive_count"),
        sa.CheckConstraint("roster_sha256 ~ '^[0-9a-f]{64}$'",
                           name="ck_track_epoch_sha256"),
        sa.CheckConstraint("length(trim(source_reference)) >= 8",
                           name="ck_track_epoch_source_reference"),
        sa.CheckConstraint("source_kind = 'CORPORATE_ROSTER_ATTESTATION'",
                           name="ck_track_epoch_corporate_only"),
        sa.CheckConstraint("sealed_at_utc IS NULL OR sealed_at_utc >= attested_at_utc",
                           name="ck_track_epoch_seal_time"),
    )
    op.create_table(
        MEMBERS,
        sa.Column("epoch_id", sa.BigInteger(), nullable=False),
        sa.Column("sucursal_canon", sa.Text(), nullable=False),
        sa.Column("sucursal_id_at_attestation", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("epoch_id", "sucursal_canon",
                                name="pk_track_roster_effective_members"),
        sa.ForeignKeyConstraint(["epoch_id"], [EPOCHS + ".id"],
                                ondelete="RESTRICT", name="fk_track_epoch_members_epoch"),
        sa.CheckConstraint("length(trim(sucursal_canon)) > 0",
                           name="ck_track_epoch_branch_nonblank"),
    )
    op.create_index("ix_track_roster_effective_epochs_date", EPOCHS,
                    ["effective_from"])

    # This guard is deliberately in the database, not just the API. Even a
    # direct script running as the application role cannot claim yesterday
    # was formally attested at today's time. Later epochs must start after
    # all earlier epochs, not insert a new decision between old ones.
    op.execute("""
CREATE FUNCTION m1f6_guard_effective_roster_epoch() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  newest_date date;
  member_count bigint;
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Track effective roster attestation is immutable';
  END IF;
  IF TG_OP = 'INSERT' THEN
    PERFORM pg_advisory_xact_lock(1410066);
    SELECT MAX(effective_from) INTO newest_date
      FROM track_roster_effective_epochs;
    IF NEW.effective_from < ((CURRENT_TIMESTAMP AT TIME ZONE 'America/Tijuana')::date + 1)
       OR (newest_date IS NOT NULL AND NEW.effective_from <= newest_date) THEN
      RAISE EXCEPTION 'Track roster attestations are prospective and sequential';
    END IF;
    IF NEW.sealed_at_utc IS NOT NULL THEN
      RAISE EXCEPTION 'New Track effective roster cannot begin sealed';
    END IF;
    NEW.attested_at_utc := CURRENT_TIMESTAMP;
    RETURN NEW;
  END IF;
  IF OLD.sealed_at_utc IS NOT NULL
     OR NEW.sealed_at_utc IS NULL
     OR NEW.id IS DISTINCT FROM OLD.id
     OR NEW.effective_from IS DISTINCT FROM OLD.effective_from
     OR NEW.attested_at_utc IS DISTINCT FROM OLD.attested_at_utc
     OR NEW.attested_by_user_id IS DISTINCT FROM OLD.attested_by_user_id
     OR NEW.source_reference IS DISTINCT FROM OLD.source_reference
     OR NEW.source_kind IS DISTINCT FROM OLD.source_kind
     OR NEW.expected_branch_count IS DISTINCT FROM OLD.expected_branch_count
     OR NEW.roster_sha256 IS DISTINCT FROM OLD.roster_sha256 THEN
    RAISE EXCEPTION 'Track effective roster decision cannot be changed';
  END IF;
  SELECT COUNT(*) INTO member_count
    FROM track_roster_effective_members
   WHERE epoch_id = OLD.id;
  IF member_count <> OLD.expected_branch_count THEN
    RAISE EXCEPTION 'Track effective roster attestation has incomplete members';
  END IF;
  RETURN NEW;
END;
$$;
""")
    op.execute("""
CREATE TRIGGER trg_m1f6_guard_effective_roster_epoch
BEFORE INSERT OR UPDATE OR DELETE ON track_roster_effective_epochs
FOR EACH ROW EXECUTE FUNCTION m1f6_guard_effective_roster_epoch();
""")
    op.execute("""
CREATE FUNCTION m1f6_guard_effective_roster_member() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  epoch_sealed timestamptz;
BEGIN
  IF TG_OP <> 'INSERT' THEN
    RAISE EXCEPTION 'Track effective roster members are append-only';
  END IF;
  SELECT sealed_at_utc INTO epoch_sealed
    FROM track_roster_effective_epochs
    WHERE id = NEW.epoch_id FOR UPDATE;
  IF NOT FOUND OR epoch_sealed IS NOT NULL THEN
    RAISE EXCEPTION 'Effective roster is sealed or missing';
  END IF;
  RETURN NEW;
END;
$$;
""")
    op.execute("""
CREATE TRIGGER trg_m1f6_guard_effective_roster_member
BEFORE INSERT OR UPDATE OR DELETE ON track_roster_effective_members
FOR EACH ROW EXECUTE FUNCTION m1f6_guard_effective_roster_member();
""")


def downgrade():
    bind = op.get_bind()
    for table in (MEMBERS, EPOCHS):
        if bind.execute(sa.text("SELECT EXISTS(SELECT 1 FROM " + table + ")")).scalar():
            raise RuntimeError("No se elimina evidencia de vigencia Track atestada.")
    op.execute("DROP TRIGGER trg_m1f6_guard_effective_roster_member ON " + MEMBERS)
    op.execute("DROP FUNCTION m1f6_guard_effective_roster_member()")
    op.execute("DROP TRIGGER trg_m1f6_guard_effective_roster_epoch ON " + EPOCHS)
    op.execute("DROP FUNCTION m1f6_guard_effective_roster_epoch()")
    op.drop_index("ix_track_roster_effective_epochs_date", table_name=EPOCHS)
    op.drop_table(MEMBERS)
    op.drop_table(EPOCHS)
