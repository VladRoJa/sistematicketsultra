import logging
from logging.config import fileConfig

from flask import current_app

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
fileConfig(config.config_file_name)
logger = logging.getLogger('alembic.env')

# Tablas existentes en DB que Alembic no debe administrar automáticamente
# durante autogenerate. Son tablas legacy/staging/BI o tablas aún no
# representadas completamente en SQLAlchemy metadata.
IGNORE_TABLES = {
    "migraciones_aplicadas",

    # Track legacy / BI raw
    "track_dim_sucursal",
    "track_fact_ingresos_daily",
    "track_raw_snapshots",
    "track_raw_ingresos_rows",

    # Staging inventario
    "stg_inventario_general",
    "stg_inventario_sucursal",
}

# Índices conocidos que PostgreSQL refleja, pero que Alembic puede detectar
# como falsos positivos si no están declarados exactamente igual en modelos.
IGNORE_INDEXES = {
    "uq_domiciliados_total_snapshot_rows_snapshot_row_index",
    "uq_domiciliados_total_snapshots_warehouse_upload_id",
    "ix_itp_snap_bd_kind_can",
    "ix_iwh_snap_bd_kind_can",
    "uq_sucursales_orden_apertura_not_null",
    "uq_suite_sucursal_region_current",
    "uq_track_branch_catalog_active_display_order",
    "uq_track_branch_catalog_active_label",
    "ix_track_daily_mart_track_daily_version_id",
    "ix_track_daily_versions_track_date_version_type_status",
    "uq_track_daily_versions_current_per_day_type",
    "uq_track_monthly_targets_active_month_branch",
    "uq_track_source_desempeno_daily_business_date_branch",
    "uq_ts_domic_efec_daily_date_branch",
    "uq_track_source_nuevos_daily_business_date_branch",
        # Planning / operadores
    "ix_planning_operators_is_active",
    "ix_planning_operators_user_id",
    "ix_ptbr_published_target_id",
    "ix_planning_target_branch_rows_published_track_monthly_target_id",

    # PM índices manuales/compuestos
    "idx_pm_bitacoras_equipo",
    "idx_pm_config_equipo",

    # Reporte Dirección índices existentes
    "ix_reporte_direccion_snapshot_rows_sucursal",
    "ix_reporte_direccion_snapshots_business_date_captured_at",
    "ix_reporte_direccion_snapshots_captured_at",
    "uq_reporte_direccion_snapshots_business_date_canonical",

    # Track índice/constraint equivalente
    "uq_track_source_ingresos_daily_business_date_branch",
}

IGNORE_CONSTRAINTS = {
    "uq_reporte_direccion_snapshots_warehouse_upload_id",
    "fk_reporte_direccion_snapshots_warehouse_upload_id",
    "uq_reporte_direccion_snapshot_rows_snapshot_id_sucursal",

    # Planning / operadores
    "uq_planning_operators_user_id",

    # Track índice/constraint equivalente
    "uq_track_source_ingresos_daily_business_date_branch",
}

def include_object(object_, name, type_, reflected, compare_to):
    # Ignorar tablas externas/no modeladas
    if type_ == "table" and name in IGNORE_TABLES:
        return False

    # Ignorar índices del sistema por limpieza visual
    if type_ == "index" and name.startswith("pg_"):
        return False

    # Ignorar índices conocidos no administrados por autogenerate
    if type_ == "index" and name in IGNORE_INDEXES:
        return False

    # Ignorar constraints conocidos no administrados por autogenerate
    if type_ in {"unique_constraint", "foreign_key_constraint"} and name in IGNORE_CONSTRAINTS:
        return False

    return True


def get_engine():
    try:
        # this works with Flask-SQLAlchemy<3 and Alchemical
        return current_app.extensions['migrate'].db.get_engine()
    except (TypeError, AttributeError):
        # this works with Flask-SQLAlchemy>=3
        return current_app.extensions['migrate'].db.engine


def get_engine_url():
    try:
        return get_engine().url.render_as_string(hide_password=False).replace(
            '%', '%%')
    except AttributeError:
        return str(get_engine().url).replace('%', '%%')


# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
config.set_main_option('sqlalchemy.url', get_engine_url())
target_db = current_app.extensions['migrate'].db

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def get_metadata():
    if hasattr(target_db, 'metadatas'):
        return target_db.metadatas[None]
    return target_db.metadata


def run_migrations_offline():
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url, target_metadata=get_metadata(), literal_binds=True, include_object=include_object
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    # this callback is used to prevent an auto-migration from being generated
    # when there are no changes to the schema
    # reference: http://alembic.zzzcomputing.com/en/latest/cookbook.html
    def process_revision_directives(context, revision, directives):
        if getattr(config.cmd_opts, 'autogenerate', False):
            script = directives[0]
            if script.upgrade_ops.is_empty():
                directives[:] = []
                logger.info('No changes in schema detected.')

    conf_args = current_app.extensions['migrate'].configure_args
    if conf_args.get("process_revision_directives") is None:
        conf_args["process_revision_directives"] = process_revision_directives
        
    if conf_args.get("include_object") is None:
        conf_args["include_object"] = include_object    

    connectable = get_engine()

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=get_metadata(),
            **conf_args
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
