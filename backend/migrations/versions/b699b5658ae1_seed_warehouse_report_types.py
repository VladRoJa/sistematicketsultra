"""seed warehouse report types

Revision ID: b699b5658ae1
Revises: 43907668e3f4
Create Date: 2026-03-18 22:11:16.894569

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b699b5658ae1'
down_revision = '43907668e3f4'
branch_labels = None
depends_on = None


warehouse_report_types_table = sa.table(
    'warehouse_report_types',
    sa.column('key', sa.String(length=80)),
    sa.column('label', sa.String(length=150)),
    sa.column('family_id', sa.Integer()),
    sa.column('default_source_id', sa.Integer()),
    sa.column('default_operational_role_id', sa.Integer()),
    sa.column('default_period_type', sa.String(length=20)),
    sa.column('active', sa.Boolean()),
)


def _get_id(bind, table_name: str, key: str) -> int:
    return bind.execute(
        sa.text(f"SELECT id FROM {table_name} WHERE key = :key"),
        {"key": key},
    ).scalar_one()


def upgrade():
    bind = op.get_bind()

    family_kpi_snapshot_id = _get_id(bind, 'warehouse_families', 'kpi_snapshot')
    family_reportes_transaccionales_id = _get_id(bind, 'warehouse_families', 'reportes_transaccionales')
    family_catalogos_auxiliares_id = _get_id(bind, 'warehouse_families', 'catalogos_auxiliares')

    source_gasca_id = _get_id(bind, 'warehouse_sources', 'gasca')
    source_manual_id = _get_id(bind, 'warehouse_sources', 'manual')

    role_fuente_principal_id = _get_id(bind, 'warehouse_operational_roles', 'FUENTE_PRINCIPAL')
    role_fuente_auxiliar_id = _get_id(bind, 'warehouse_operational_roles', 'FUENTE_AUXILIAR_ENRIQUECIMIENTO')
    role_catalogo_auxiliar_id = _get_id(bind, 'warehouse_operational_roles', 'CATALOGO_AUXILIAR')

    op.bulk_insert(
        warehouse_report_types_table,
        [
            {
                'key': 'reporte_direccion',
                'label': 'Reporte Dirección',
                'family_id': family_kpi_snapshot_id,
                'default_source_id': source_gasca_id,
                'default_operational_role_id': role_fuente_principal_id,
                'default_period_type': 'diario',
                'active': True,
            },
            {
                'key': 'kpi_desempeno',
                'label': 'KPI Desempeño',
                'family_id': family_kpi_snapshot_id,
                'default_source_id': source_gasca_id,
                'default_operational_role_id': role_fuente_principal_id,
                'default_period_type': 'diario',
                'active': True,
            },
            {
                'key': 'kpi_ventas_nuevos',
                'label': 'KPI Ventas Nuevos',
                'family_id': family_kpi_snapshot_id,
                'default_source_id': source_gasca_id,
                'default_operational_role_id': role_fuente_principal_id,
                'default_period_type': 'diario',
                'active': True,
            },
            {
                'key': 'venta_total',
                'label': 'Venta Total',
                'family_id': family_reportes_transaccionales_id,
                'default_source_id': source_gasca_id,
                'default_operational_role_id': role_fuente_principal_id,
                'default_period_type': 'rango',
                'active': True,
            },
            {
                'key': 'corte_de_caja',
                'label': 'Corte de Caja',
                'family_id': family_reportes_transaccionales_id,
                'default_source_id': source_gasca_id,
                'default_operational_role_id': role_fuente_auxiliar_id,
                'default_period_type': 'rango',
                'active': True,
            },
            {
                'key': 'cargos_recurrentes',
                'label': 'Cargos Recurrentes',
                'family_id': family_reportes_transaccionales_id,
                'default_source_id': source_gasca_id,
                'default_operational_role_id': role_fuente_auxiliar_id,
                'default_period_type': 'rango',
                'active': True,
            },
            {
                'key': 'tarifas',
                'label': 'Tarifas',
                'family_id': family_catalogos_auxiliares_id,
                'default_source_id': source_manual_id,
                'default_operational_role_id': role_catalogo_auxiliar_id,
                'default_period_type': 'rango',
                'active': True,
            },
        ]
    )


def downgrade():
    op.execute(
        """
        DELETE FROM warehouse_report_types
        WHERE key IN (
            'reporte_direccion',
            'kpi_desempeno',
            'kpi_ventas_nuevos',
            'venta_total',
            'corte_de_caja',
            'cargos_recurrentes',
            'tarifas'
        )
        """
    )