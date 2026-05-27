"""create planning targets governance tables

Revision ID: 50f1c90f156e
Revises: 5ff71f6bff18
Create Date: 2026-05-27 08:11:19.165066

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '50f1c90f156e'
down_revision = '5ff71f6bff18'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "planning_model_configs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="BORRADOR"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("trend_window_months", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("trend_closed_months_only", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("arpu_strategy", sa.Text(), nullable=False, server_default="PROMEDIO_3M"),
        sa.Column(
            "bajas_strategy",
            sa.Text(),
            nullable=False,
            server_default="PROMEDIO_HISTORICO_SUCURSAL",
        ),
        sa.Column(
            "reactivaciones_strategy",
            sa.Text(),
            nullable=False,
            server_default="PROMEDIO_HISTORICO_SUCURSAL",
        ),
        sa.Column(
            "domiciliados_strategy",
            sa.Text(),
            nullable=False,
            server_default="PORCENTAJE_CLIENTES_NUEVOS",
        ),
        sa.Column(
            "aggregators_strategy",
            sa.Text(),
            nullable=False,
            server_default="SEPARADAS_SOLO_INGRESO",
        ),
        sa.Column(
            "new_branch_strategy",
            sa.Text(),
            nullable=False,
            server_default="PROMEDIO_REGIONAL",
        ),
        sa.Column("risk_rules_json", postgresql.JSONB(), nullable=True),
        sa.Column("parameters_json", postgresql.JSONB(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("activated_by_user_id", sa.Integer(), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_config_id", sa.BigInteger(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_planning_model_configs_created_by_user_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["activated_by_user_id"],
            ["users.id"],
            name="fk_planning_model_configs_activated_by_user_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["replaced_by_config_id"],
            ["planning_model_configs.id"],
            name="fk_planning_model_configs_replaced_by_config_id",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "name",
            "version",
            name="uq_planning_model_configs_name_version",
        ),
    )
    op.create_index(
        "ix_planning_model_configs_status",
        "planning_model_configs",
        ["status"],
    )
    op.create_index(
        "ix_planning_model_configs_created_by_user_id",
        "planning_model_configs",
        ["created_by_user_id"],
    )
    op.create_index(
        "ix_planning_model_configs_activated_by_user_id",
        "planning_model_configs",
        ["activated_by_user_id"],
    )
    op.create_index(
        "ix_planning_model_configs_replaced_by_config_id",
        "planning_model_configs",
        ["replaced_by_config_id"],
    )

    op.create_table(
        "planning_target_batches",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("target_month", sa.Date(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="BORRADOR"),
        sa.Column("scope", sa.Text(), nullable=False, server_default="MONTHLY_BATCH"),
        sa.Column("source_type", sa.Text(), nullable=False, server_default="MANUAL"),
        sa.Column("source_upload_id", sa.Integer(), nullable=True),
        sa.Column("model_config_id", sa.BigInteger(), nullable=True),
        sa.Column("scenario_base", sa.Text(), nullable=True),
        sa.Column("proposed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("proposed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by_user_id", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_by_user_id", sa.Integer(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_comment", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_canonical", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["source_upload_id"],
            ["warehouse_uploads.id"],
            name="fk_planning_target_batches_source_upload_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["model_config_id"],
            ["planning_model_configs.id"],
            name="fk_planning_target_batches_model_config_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["proposed_by_user_id"],
            ["users.id"],
            name="fk_planning_target_batches_proposed_by_user_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"],
            ["users.id"],
            name="fk_planning_target_batches_approved_by_user_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["rejected_by_user_id"],
            ["users.id"],
            name="fk_planning_target_batches_rejected_by_user_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_planning_target_batches_created_by_user_id",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "target_month",
            "version",
            name="uq_planning_target_batches_month_version",
        ),
    )
    op.create_index(
        "ix_planning_target_batches_target_month",
        "planning_target_batches",
        ["target_month"],
    )
    op.create_index(
        "ix_planning_target_batches_status",
        "planning_target_batches",
        ["status"],
    )
    op.create_index(
        "ix_planning_target_batches_scope",
        "planning_target_batches",
        ["scope"],
    )
    op.create_index(
        "ix_planning_target_batches_is_canonical",
        "planning_target_batches",
        ["is_canonical"],
    )
    op.create_index(
        "ix_planning_target_batches_source_upload_id",
        "planning_target_batches",
        ["source_upload_id"],
    )
    op.create_index(
        "ix_planning_target_batches_model_config_id",
        "planning_target_batches",
        ["model_config_id"],
    )
    op.create_index(
        "ix_planning_target_batches_proposed_by_user_id",
        "planning_target_batches",
        ["proposed_by_user_id"],
    )
    op.create_index(
        "ix_planning_target_batches_approved_by_user_id",
        "planning_target_batches",
        ["approved_by_user_id"],
    )
    op.create_index(
        "ix_planning_target_batches_rejected_by_user_id",
        "planning_target_batches",
        ["rejected_by_user_id"],
    )
    op.create_index(
        "ix_planning_target_batches_created_by_user_id",
        "planning_target_batches",
        ["created_by_user_id"],
    )

    op.create_table(
        "planning_target_branch_rows",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("batch_id", sa.BigInteger(), nullable=False),
        sa.Column("target_month", sa.Date(), nullable=False),
        sa.Column("sucursal_canon", sa.Text(), nullable=False),
        sa.Column("m2_sin_circulaciones", sa.Numeric(12, 2), nullable=False),
        sa.Column("usuarios_inicio_mes", sa.Integer(), nullable=False),
        sa.Column("proyeccion_usuarios_cierre_mes", sa.Integer(), nullable=False),
        sa.Column("meta_faycgo_mes", sa.Numeric(14, 2), nullable=False),
        sa.Column("meta_clientes_nuevos_mes", sa.Integer(), nullable=False),
        sa.Column("meta_reactivaciones_mes", sa.Integer(), nullable=False),
        sa.Column("meta_bajas_mes", sa.Integer(), nullable=False),
        sa.Column("meta_nuevos_domiciliados_mes", sa.Integer(), nullable=False),
        sa.Column("meta_arpu_mes", sa.Numeric(14, 2), nullable=False),
        sa.Column("meta_venta_tienda_mes", sa.Numeric(14, 2), nullable=False),
        sa.Column("ingreso_agregadoras_estimado", sa.Numeric(14, 2), nullable=True),
        sa.Column("usuarios_agregadoras_estimado", sa.Integer(), nullable=True),
        sa.Column("scenario_used", sa.Text(), nullable=True),
        sa.Column("trend_classification", sa.Text(), nullable=True),
        sa.Column("risk_level", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="PROPUESTA"),
        sa.Column("previous_branch_row_id", sa.BigInteger(), nullable=True),
        sa.Column("published_track_monthly_target_id", sa.BigInteger(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["planning_target_batches.id"],
            name="fk_planning_target_branch_rows_batch_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sucursal_canon"],
            ["track_branch_catalog.sucursal_canon"],
            name="fk_planning_target_branch_rows_sucursal_canon",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["previous_branch_row_id"],
            ["planning_target_branch_rows.id"],
            name="fk_planning_target_branch_rows_previous_branch_row_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["published_track_monthly_target_id"],
            ["track_monthly_targets.id"],
            name="fk_ptbr_published_target_id",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "batch_id",
            "sucursal_canon",
            name="uq_planning_target_branch_rows_batch_branch",
        ),
    )
    op.create_index(
        "ix_planning_target_branch_rows_batch_id",
        "planning_target_branch_rows",
        ["batch_id"],
    )
    op.create_index(
        "ix_planning_target_branch_rows_target_month",
        "planning_target_branch_rows",
        ["target_month"],
    )
    op.create_index(
        "ix_planning_target_branch_rows_sucursal_canon",
        "planning_target_branch_rows",
        ["sucursal_canon"],
    )
    op.create_index(
        "ix_planning_target_branch_rows_status",
        "planning_target_branch_rows",
        ["status"],
    )
    op.create_index(
        "ix_planning_target_branch_rows_previous_branch_row_id",
        "planning_target_branch_rows",
        ["previous_branch_row_id"],
    )
    op.create_index(
        "ix_ptbr_published_target_id",
        "planning_target_branch_rows",
        ["published_track_monthly_target_id"],
    )

    op.create_table(
        "planning_target_adjustments",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("branch_row_id", sa.BigInteger(), nullable=False),
        sa.Column("variable_key", sa.Text(), nullable=False),
        sa.Column("adjustment_value", sa.Numeric(14, 2), nullable=True),
        sa.Column("adjustment_type", sa.Text(), nullable=False),
        sa.Column("driver_type", sa.Text(), nullable=False),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["branch_row_id"],
            ["planning_target_branch_rows.id"],
            name="fk_planning_target_adjustments_branch_row_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_planning_target_adjustments_created_by_user_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_planning_target_adjustments_branch_row_id",
        "planning_target_adjustments",
        ["branch_row_id"],
    )
    op.create_index(
        "ix_planning_target_adjustments_variable_key",
        "planning_target_adjustments",
        ["variable_key"],
    )
    op.create_index(
        "ix_planning_target_adjustments_driver_type",
        "planning_target_adjustments",
        ["driver_type"],
    )
    op.create_index(
        "ix_planning_target_adjustments_created_by_user_id",
        "planning_target_adjustments",
        ["created_by_user_id"],
    )

    op.create_table(
        "planning_target_approval_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("batch_id", sa.BigInteger(), nullable=False),
        sa.Column("branch_row_id", sa.BigInteger(), nullable=True),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("from_status", sa.Text(), nullable=True),
        sa.Column("to_status", sa.Text(), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("actor_username_snapshot", sa.Text(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["planning_target_batches.id"],
            name="fk_planning_target_approval_events_batch_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["branch_row_id"],
            ["planning_target_branch_rows.id"],
            name="fk_planning_target_approval_events_branch_row_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_planning_target_approval_events_actor_user_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_planning_target_approval_events_batch_id",
        "planning_target_approval_events",
        ["batch_id"],
    )
    op.create_index(
        "ix_planning_target_approval_events_branch_row_id",
        "planning_target_approval_events",
        ["branch_row_id"],
    )
    op.create_index(
        "ix_planning_target_approval_events_event_type",
        "planning_target_approval_events",
        ["event_type"],
    )
    op.create_index(
        "ix_planning_target_approval_events_actor_user_id",
        "planning_target_approval_events",
        ["actor_user_id"],
    )
    op.create_index(
        "ix_planning_target_approval_events_created_at",
        "planning_target_approval_events",
        ["created_at"],
    )


def downgrade():
    op.drop_index(
        "ix_planning_target_approval_events_created_at",
        table_name="planning_target_approval_events",
    )
    op.drop_index(
        "ix_planning_target_approval_events_actor_user_id",
        table_name="planning_target_approval_events",
    )
    op.drop_index(
        "ix_planning_target_approval_events_event_type",
        table_name="planning_target_approval_events",
    )
    op.drop_index(
        "ix_planning_target_approval_events_branch_row_id",
        table_name="planning_target_approval_events",
    )
    op.drop_index(
        "ix_planning_target_approval_events_batch_id",
        table_name="planning_target_approval_events",
    )
    op.drop_table("planning_target_approval_events")

    op.drop_index(
        "ix_planning_target_adjustments_created_by_user_id",
        table_name="planning_target_adjustments",
    )
    op.drop_index(
        "ix_planning_target_adjustments_driver_type",
        table_name="planning_target_adjustments",
    )
    op.drop_index(
        "ix_planning_target_adjustments_variable_key",
        table_name="planning_target_adjustments",
    )
    op.drop_index(
        "ix_planning_target_adjustments_branch_row_id",
        table_name="planning_target_adjustments",
    )
    op.drop_table("planning_target_adjustments")

    op.drop_index(
        "ix_ptbr_published_target_id",
        table_name="planning_target_branch_rows",
    )
    op.drop_index(
        "ix_planning_target_branch_rows_previous_branch_row_id",
        table_name="planning_target_branch_rows",
    )
    op.drop_index(
        "ix_planning_target_branch_rows_status",
        table_name="planning_target_branch_rows",
    )
    op.drop_index(
        "ix_planning_target_branch_rows_sucursal_canon",
        table_name="planning_target_branch_rows",
    )
    op.drop_index(
        "ix_planning_target_branch_rows_target_month",
        table_name="planning_target_branch_rows",
    )
    op.drop_index(
        "ix_planning_target_branch_rows_batch_id",
        table_name="planning_target_branch_rows",
    )
    op.drop_table("planning_target_branch_rows")

    op.drop_index(
        "ix_planning_target_batches_created_by_user_id",
        table_name="planning_target_batches",
    )
    op.drop_index(
        "ix_planning_target_batches_rejected_by_user_id",
        table_name="planning_target_batches",
    )
    op.drop_index(
        "ix_planning_target_batches_approved_by_user_id",
        table_name="planning_target_batches",
    )
    op.drop_index(
        "ix_planning_target_batches_proposed_by_user_id",
        table_name="planning_target_batches",
    )
    op.drop_index(
        "ix_planning_target_batches_model_config_id",
        table_name="planning_target_batches",
    )
    op.drop_index(
        "ix_planning_target_batches_source_upload_id",
        table_name="planning_target_batches",
    )
    op.drop_index(
        "ix_planning_target_batches_is_canonical",
        table_name="planning_target_batches",
    )
    op.drop_index(
        "ix_planning_target_batches_scope",
        table_name="planning_target_batches",
    )
    op.drop_index(
        "ix_planning_target_batches_status",
        table_name="planning_target_batches",
    )
    op.drop_index(
        "ix_planning_target_batches_target_month",
        table_name="planning_target_batches",
    )
    op.drop_table("planning_target_batches")

    op.drop_index(
        "ix_planning_model_configs_replaced_by_config_id",
        table_name="planning_model_configs",
    )
    op.drop_index(
        "ix_planning_model_configs_activated_by_user_id",
        table_name="planning_model_configs",
    )
    op.drop_index(
        "ix_planning_model_configs_created_by_user_id",
        table_name="planning_model_configs",
    )
    op.drop_index(
        "ix_planning_model_configs_status",
        table_name="planning_model_configs",
    )
    op.drop_table("planning_model_configs")
