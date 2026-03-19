"""add warehouse base tables

Revision ID: 05c40fcc57f4
Revises: bc8a50c3add0
Create Date: 2026-03-18 20:40:11.610613

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '05c40fcc57f4'
down_revision = 'bc8a50c3add0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'warehouse_sources',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(length=50), nullable=False),
        sa.Column('label', sa.String(length=100), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key')
    )

    op.create_table(
        'warehouse_families',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(length=80), nullable=False),
        sa.Column('label', sa.String(length=150), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key')
    )

    op.create_table(
        'warehouse_operational_roles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(length=80), nullable=False),
        sa.Column('label', sa.String(length=150), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key')
    )

    op.create_table(
        'warehouse_report_types',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(length=80), nullable=False),
        sa.Column('label', sa.String(length=150), nullable=False),
        sa.Column('family_id', sa.Integer(), nullable=False),
        sa.Column('default_source_id', sa.Integer(), nullable=True),
        sa.Column('default_operational_role_id', sa.Integer(), nullable=True),
        sa.Column('default_period_type', sa.String(length=20), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(['family_id'], ['warehouse_families.id']),
        sa.ForeignKeyConstraint(['default_source_id'], ['warehouse_sources.id']),
        sa.ForeignKeyConstraint(['default_operational_role_id'], ['warehouse_operational_roles.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key')
    )

    op.create_table(
        'warehouse_uploads',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('original_filename', sa.String(length=255), nullable=False),
        sa.Column('stored_filename', sa.String(length=255), nullable=False),
        sa.Column('stored_path', sa.Text(), nullable=False),
        sa.Column('file_size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('file_hash_sha256', sa.String(length=64), nullable=False),
        sa.Column('mime_type', sa.String(length=100), nullable=True),
        sa.Column('extension', sa.String(length=10), nullable=False),
        sa.Column('source_id', sa.Integer(), nullable=False),
        sa.Column('family_id', sa.Integer(), nullable=False),
        sa.Column('operational_role_id', sa.Integer(), nullable=False),
        sa.Column('report_type_id', sa.Integer(), nullable=False),
        sa.Column('period_type', sa.String(length=20), nullable=False),
        sa.Column('cutoff_date', sa.Date(), nullable=True),
        sa.Column('date_from', sa.Date(), nullable=True),
        sa.Column('date_to', sa.Date(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('uploaded_by_user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['source_id'], ['warehouse_sources.id']),
        sa.ForeignKeyConstraint(['family_id'], ['warehouse_families.id']),
        sa.ForeignKeyConstraint(['operational_role_id'], ['warehouse_operational_roles.id']),
        sa.ForeignKeyConstraint(['report_type_id'], ['warehouse_report_types.id']),
        sa.ForeignKeyConstraint(['uploaded_by_user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_index('idx_warehouse_uploads_source_id', 'warehouse_uploads', ['source_id'], unique=False)
    op.create_index('idx_warehouse_uploads_report_type_id', 'warehouse_uploads', ['report_type_id'], unique=False)
    op.create_index('idx_warehouse_uploads_created_at', 'warehouse_uploads', ['created_at'], unique=False)

    op.create_table(
        'warehouse_operators',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('can_upload', sa.Boolean(), nullable=True),
        sa.Column('can_view', sa.Boolean(), nullable=True),
        sa.Column('can_archive', sa.Boolean(), nullable=True),
        sa.Column('added_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['added_by_user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )

    op.create_table(
        'warehouse_audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('upload_id', sa.Integer(), nullable=True),
        sa.Column('action', sa.String(length=30), nullable=False),
        sa.Column('performed_by_user_id', sa.Integer(), nullable=False),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['upload_id'], ['warehouse_uploads.id']),
        sa.ForeignKeyConstraint(['performed_by_user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('warehouse_audit_logs')
    op.drop_table('warehouse_operators')

    op.drop_index('idx_warehouse_uploads_created_at', table_name='warehouse_uploads')
    op.drop_index('idx_warehouse_uploads_report_type_id', table_name='warehouse_uploads')
    op.drop_index('idx_warehouse_uploads_source_id', table_name='warehouse_uploads')
    op.drop_table('warehouse_uploads')

    op.drop_table('warehouse_report_types')
    op.drop_table('warehouse_operational_roles')
    op.drop_table('warehouse_families')
    op.drop_table('warehouse_sources')