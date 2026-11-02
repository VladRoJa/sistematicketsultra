"""WSO-01: retire obsolete Corte de Caja storage and Warehouse lineage.

Revision ID: wso01caja110226
Revises: v2e4b3103026

Destructive migration. Apply ONLY after verified backup/restore, dry-run of
wso01_corte_caja_files.py and physical-file quarantine confirmation.
Downgrade requires restoring the database backup, not empty tables.
"""

from alembic import op
import sqlalchemy as sa


revision = "wso01caja110226"
down_revision = "v2e4b3103026"
branch_labels = None
depends_on = None

_REPORT_KEY = "corte_caja"

# Relations with ON DELETE SET NULL must be checked explicitly: otherwise a
# concurrent reference could be silently unlinked rather than block the purge.
_NULLABLE_REFERENCES_SQL = """
SELECT EXISTS (
    SELECT 1
    FROM public.planning_target_batches p
    JOIN public.warehouse_uploads u ON u.id = p.source_upload_id
    JOIN public.warehouse_report_types rt ON rt.id = u.report_type_id
    WHERE rt.key = :report_key
    UNION ALL
    SELECT 1
    FROM public.routine_control_provider_runs p
    JOIN public.warehouse_uploads u ON u.id = p.raw_warehouse_upload_id
    JOIN public.warehouse_report_types rt ON rt.id = u.report_type_id
    WHERE rt.key = :report_key
)
"""

_SHARED_PATH_SQL = """
SELECT EXISTS (
    SELECT 1
    FROM public.warehouse_uploads target
    JOIN public.warehouse_report_types rt ON rt.id = target.report_type_id
    JOIN public.warehouse_uploads other
      ON other.id <> target.id
     AND other.stored_path = target.stored_path
     AND other.stored_filename = target.stored_filename
    WHERE rt.key = :report_key
)
"""


def upgrade():
    bind = op.get_bind()
    op.execute("SET LOCAL lock_timeout = '5s'")

    # Preserve all data if any unexpected shared paths or SET NULL consumers
    # appeared since the audited 2026-11-02 snapshot.
    if bind.execute(sa.text(_NULLABLE_REFERENCES_SQL), {"report_key": _REPORT_KEY}).scalar():
        raise RuntimeError(
            "WSO-01 blocked: Corte de Caja uploads have live references "
            "in planning_target_batches or routine_control_provider_runs"
        )
    if bind.execute(sa.text(_SHARED_PATH_SQL), {"report_key": _REPORT_KEY}).scalar():
        raise RuntimeError(
            "WSO-01 blocked: at least one Corte de Caja physical path "
            "is shared by another Warehouse upload"
        )

    # Do not CASCADE outside the retired source: PostgreSQL RESTRICT/NO ACTION
    # FKs must abort the whole transaction if any unexpected dependency exists.
    op.drop_table("corte_caja_snapshot_rows", schema="public")
    op.drop_table("corte_caja_snapshots", schema="public")

    # Scoped deletion of only the retired report's own audit and upload rows.
    # Warehouse audit events have a non-cascading FK to warehouse_uploads.
    op.execute("""
        DELETE FROM public.warehouse_audit_logs a
        USING public.warehouse_uploads u, public.warehouse_report_types rt
        WHERE a.upload_id = u.id
          AND u.report_type_id = rt.id
          AND rt.key = 'corte_caja'
    """)
    op.execute("""
        DELETE FROM public.warehouse_uploads u
        USING public.warehouse_report_types rt
        WHERE u.report_type_id = rt.id
          AND rt.key = 'corte_caja'
    """)
    op.execute("""
        DELETE FROM public.warehouse_report_types
        WHERE key = 'corte_caja'
    """)


def downgrade():
    raise RuntimeError(
        "WSO-01 is data-destructive. Recreate the environment from the "
        "verified pre-migration database backup; an empty-table downgrade "
        "would falsely suggest that the historical data was recovered."
    )
