"""track ingresos agregadoras structured sources

Revision ID: a42c792fa63c
Revises: 1478e746caf3
Create Date: 2026-04-22 10:20:13.139750

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a42c792fa63c'
down_revision = '1478e746caf3'
branch_labels = None
depends_on = None


def upgrade():
    # -------------------------------------------------------------------------
    # 1) Snapshots estructurados: ingresos_wellhub
    # -------------------------------------------------------------------------
    op.create_table(
        'ingresos_wellhub_snapshots',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('warehouse_upload_id', sa.BigInteger(), nullable=False),
        sa.Column('report_type_key', sa.Text(), nullable=False),
        sa.Column('business_date', sa.Date(), nullable=False),
        sa.Column('captured_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('snapshot_kind', sa.Text(), nullable=False),
        sa.Column('is_canonical', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('row_count_detected', sa.Integer(), nullable=False),
        sa.Column('row_count_valid', sa.Integer(), nullable=False),
        sa.Column('row_count_rejected', sa.Integer(), nullable=False),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('warehouse_upload_id', name='uq_ingresos_wellhub_snapshots_warehouse_upload_id'),
    )
    op.create_index(
        'ix_iwh_snap_bd_kind_can',
        'ingresos_wellhub_snapshots',
        ['business_date', 'snapshot_kind', 'is_canonical'],
        unique=False,
    )

    op.create_table(
        'ingresos_wellhub_snapshot_rows',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            'snapshot_id',
            sa.BigInteger(),
            sa.ForeignKey('ingresos_wellhub_snapshots.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'sucursal_canon',
            sa.Text(),
            sa.ForeignKey('track_branch_catalog.sucursal_canon', ondelete='RESTRICT'),
            nullable=False,
        ),
        sa.Column('raw_branch_name', sa.Text(), nullable=False),
        sa.Column('visitor_name', sa.Text(), nullable=True),
        sa.Column('wellhub_member_id', sa.Text(), nullable=True),
        sa.Column('total_checkins_mtd', sa.Integer(), nullable=True),
        sa.Column('pago_total_mtd', sa.Numeric(14, 2), nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            'snapshot_id',
            'sucursal_canon',
            'wellhub_member_id',
            name='uq_ingresos_wellhub_snapshot_rows_snapshot_branch_member',
        ),
    )
    op.create_index(
        'ix_ingresos_wellhub_snapshot_rows_snapshot_id',
        'ingresos_wellhub_snapshot_rows',
        ['snapshot_id'],
        unique=False,
    )
    op.create_index(
        'ix_ingresos_wellhub_snapshot_rows_snapshot_id_sucursal_canon',
        'ingresos_wellhub_snapshot_rows',
        ['snapshot_id', 'sucursal_canon'],
        unique=False,
    )

    # -------------------------------------------------------------------------
    # 2) Snapshots estructurados: ingresos_totalpass
    # -------------------------------------------------------------------------
    op.create_table(
        'ingresos_totalpass_snapshots',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('warehouse_upload_id', sa.BigInteger(), nullable=False),
        sa.Column('report_type_key', sa.Text(), nullable=False),
        sa.Column('business_date', sa.Date(), nullable=False),
        sa.Column('captured_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('snapshot_kind', sa.Text(), nullable=False),
        sa.Column('is_canonical', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('row_count_detected', sa.Integer(), nullable=False),
        sa.Column('row_count_valid', sa.Integer(), nullable=False),
        sa.Column('row_count_rejected', sa.Integer(), nullable=False),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('warehouse_upload_id', name='uq_ingresos_totalpass_snapshots_warehouse_upload_id'),
    )
    op.create_index(
        'ix_itp_snap_bd_kind_can',
        'ingresos_totalpass_snapshots',
        ['business_date', 'snapshot_kind', 'is_canonical'],
        unique=False,
    )

    op.create_table(
        'ingresos_totalpass_snapshot_rows',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            'snapshot_id',
            sa.BigInteger(),
            sa.ForeignKey('ingresos_totalpass_snapshots.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'sucursal_canon',
            sa.Text(),
            sa.ForeignKey('track_branch_catalog.sucursal_canon', ondelete='RESTRICT'),
            nullable=False,
        ),
        sa.Column('raw_branch_name', sa.Text(), nullable=False),
        sa.Column('monto_acumulado_mes', sa.Numeric(14, 2), nullable=False, server_default=sa.text('0')),
        sa.Column('usage_count', sa.Integer(), nullable=True),
        sa.Column('student_count', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            'snapshot_id',
            'sucursal_canon',
            name='uq_ingresos_totalpass_snapshot_rows_snapshot_branch',
        ),
    )
    op.create_index(
        'ix_ingresos_totalpass_snapshot_rows_snapshot_id',
        'ingresos_totalpass_snapshot_rows',
        ['snapshot_id'],
        unique=False,
    )
    op.create_index(
        'ix_ingresos_totalpass_snapshot_rows_snapshot_id_sucursal_canon',
        'ingresos_totalpass_snapshot_rows',
        ['snapshot_id', 'sucursal_canon'],
        unique=False,
    )

    # -------------------------------------------------------------------------
    # 3) track_source_ingresos_daily: columnas nuevas
    # -------------------------------------------------------------------------
    op.add_column(
        'track_source_ingresos_daily',
        sa.Column('ingreso_real_base_mtd', sa.Numeric(14, 2), nullable=False, server_default=sa.text('0')),
    )
    op.add_column(
        'track_source_ingresos_daily',
        sa.Column('ingreso_wellhub_mtd', sa.Numeric(14, 2), nullable=False, server_default=sa.text('0')),
    )
    op.add_column(
        'track_source_ingresos_daily',
        sa.Column('ingreso_totalpass_mtd', sa.Numeric(14, 2), nullable=False, server_default=sa.text('0')),
    )
    op.add_column(
        'track_source_ingresos_daily',
        sa.Column('ingreso_real_agregadora_mtd', sa.Numeric(14, 2), nullable=False, server_default=sa.text('0')),
    )
    op.add_column(
        'track_source_ingresos_daily',
        sa.Column('ingreso_real_total_mtd', sa.Numeric(14, 2), nullable=False, server_default=sa.text('0')),
    )
    op.add_column(
        'track_source_ingresos_daily',
        sa.Column('source_snapshot_id_reporte_direccion', sa.BigInteger(), nullable=True),
    )
    op.add_column(
        'track_source_ingresos_daily',
        sa.Column('source_snapshot_id_wellhub', sa.BigInteger(), nullable=True),
    )
    op.add_column(
        'track_source_ingresos_daily',
        sa.Column('source_snapshot_id_totalpass', sa.BigInteger(), nullable=True),
    )
    op.add_column(
        'track_source_ingresos_daily',
        sa.Column('source_report_type_key_reporte_direccion', sa.Text(), nullable=True),
    )
    op.add_column(
        'track_source_ingresos_daily',
        sa.Column('source_report_type_key_wellhub', sa.Text(), nullable=True),
    )
    op.add_column(
        'track_source_ingresos_daily',
        sa.Column('source_report_type_key_totalpass', sa.Text(), nullable=True),
    )

    # Backfill de compatibilidad para histórico existente
    op.execute(
        """
        UPDATE track_source_ingresos_daily
        SET
            ingreso_real_base_mtd = COALESCE(ingreso_real_mtd, 0),
            ingreso_wellhub_mtd = 0,
            ingreso_totalpass_mtd = 0,
            ingreso_real_agregadora_mtd = 0,
            ingreso_real_total_mtd = COALESCE(ingreso_real_mtd, 0),
            source_snapshot_id_reporte_direccion = source_snapshot_id,
            source_report_type_key_reporte_direccion = source_report_type_key
        """
    )

    # -------------------------------------------------------------------------
    # 4) track_daily_mart: columnas nuevas
    # -------------------------------------------------------------------------
    op.add_column(
        'track_daily_mart',
        sa.Column('ingreso_real_base_mtd', sa.Numeric(14, 2), nullable=True),
    )
    op.add_column(
        'track_daily_mart',
        sa.Column('ingreso_real_agregadora_mtd', sa.Numeric(14, 2), nullable=True),
    )
    op.add_column(
        'track_daily_mart',
        sa.Column('ingreso_real_total_mtd', sa.Numeric(14, 2), nullable=True),
    )

    # Backfill de compatibilidad para histórico existente
    op.execute(
        """
        UPDATE track_daily_mart
        SET
            ingreso_real_base_mtd = ingreso_real_mtd,
            ingreso_real_agregadora_mtd = 0,
            ingreso_real_total_mtd = ingreso_real_mtd
        """
    )


def downgrade():
    # -------------------------------------------------------------------------
    # 1) track_daily_mart: quitar columnas nuevas
    # -------------------------------------------------------------------------
    op.drop_column('track_daily_mart', 'ingreso_real_total_mtd')
    op.drop_column('track_daily_mart', 'ingreso_real_agregadora_mtd')
    op.drop_column('track_daily_mart', 'ingreso_real_base_mtd')

    # -------------------------------------------------------------------------
    # 2) track_source_ingresos_daily: quitar columnas nuevas
    # -------------------------------------------------------------------------
    op.drop_column('track_source_ingresos_daily', 'source_report_type_key_totalpass')
    op.drop_column('track_source_ingresos_daily', 'source_report_type_key_wellhub')
    op.drop_column('track_source_ingresos_daily', 'source_report_type_key_reporte_direccion')
    op.drop_column('track_source_ingresos_daily', 'source_snapshot_id_totalpass')
    op.drop_column('track_source_ingresos_daily', 'source_snapshot_id_wellhub')
    op.drop_column('track_source_ingresos_daily', 'source_snapshot_id_reporte_direccion')
    op.drop_column('track_source_ingresos_daily', 'ingreso_real_total_mtd')
    op.drop_column('track_source_ingresos_daily', 'ingreso_real_agregadora_mtd')
    op.drop_column('track_source_ingresos_daily', 'ingreso_totalpass_mtd')
    op.drop_column('track_source_ingresos_daily', 'ingreso_wellhub_mtd')
    op.drop_column('track_source_ingresos_daily', 'ingreso_real_base_mtd')

    # -------------------------------------------------------------------------
    # 3) Drop TotalPass snapshots
    # -------------------------------------------------------------------------
    op.drop_index(
        'ix_ingresos_totalpass_snapshot_rows_snapshot_id_sucursal_canon',
        table_name='ingresos_totalpass_snapshot_rows',
    )
    op.drop_index(
        'ix_ingresos_totalpass_snapshot_rows_snapshot_id',
        table_name='ingresos_totalpass_snapshot_rows',
    )
    op.drop_table('ingresos_totalpass_snapshot_rows')

    op.drop_index(
        'ix_ingresos_totalpass_snapshots_business_date_snapshot_kind_is_canonical',
        table_name='ingresos_totalpass_snapshots',
    )
    op.drop_table('ingresos_totalpass_snapshots')

    # -------------------------------------------------------------------------
    # 4) Drop Wellhub snapshots
    # -------------------------------------------------------------------------
    op.drop_index(
        'ix_itp_snap_bd_kind_can',
        table_name='ingresos_totalpass_snapshots',
    )
    op.drop_index(
        'ix_ingresos_wellhub_snapshot_rows_snapshot_id',
        table_name='ingresos_wellhub_snapshot_rows',
    )
    op.drop_table('ingresos_wellhub_snapshot_rows')

    op.drop_index(
        'ix_iwh_snap_bd_kind_can',
        table_name='ingresos_wellhub_snapshots',
    )
    op.drop_table('ingresos_wellhub_snapshots')