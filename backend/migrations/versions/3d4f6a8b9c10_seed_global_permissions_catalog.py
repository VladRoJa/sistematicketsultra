"""seed global permissions catalog

Revision ID: 3d4f6a8b9c10
Revises: 9a7c3d5e1b2f
Create Date: 2026-06-25

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "3d4f6a8b9c10"
down_revision = "9a7c3d5e1b2f"
branch_labels = None
depends_on = None


MODULES = [
    ("tickets", "Tickets", "Gestión de tickets, estados, cierres y notificaciones."),
    ("inventory", "Inventario", "Inventario general, existencias y movimientos."),
    ("pm", "Mantenimiento Preventivo", "Programación, ejecución, validación e historial PM."),
    ("warehouse", "Warehouse", "Carga documental, snapshots, catálogos y archivo de reportes."),
    ("internal_documents", "Nube Corporativa", "Biblioteca interna, manuales, documentos y recursos externos."),
    ("track", "Track / BI", "Mart diario, integraciones y tableros Track."),
    ("planning", "Planeación / Metas", "Modelos, metas, aprobaciones y publicación de objetivos."),
    ("openings", "Aperturas", "Coordinación digital de aperturas y tareas."),
    ("catalogs", "Catálogos", "Catálogos maestros del sistema."),
    ("users", "Usuarios", "Administración de usuarios, roles y sucursales."),
    ("reports", "Reportes", "Reportes operativos y creación de reportes de error."),
]


ACTIONS = [
    ("tickets", "create", "tickets.create", "Crear ticket", "Crear tickets operativos.", "medium"),
    ("tickets", "update", "tickets.update", "Actualizar ticket", "Editar datos generales del ticket.", "medium"),
    ("tickets", "update_status", "tickets.update_status", "Cambiar estado de ticket", "Actualizar estado del ticket.", "medium"),
    ("tickets", "close", "tickets.close", "Cerrar ticket", "Ejecutar flujos de cierre o validación.", "high"),
    ("tickets", "notify", "tickets.notify", "Notificar ticket", "Enviar notificaciones asociadas a tickets.", "medium"),

    ("inventory", "read", "inventory.read", "Consultar inventario", "Consultar inventario y existencias.", "low"),
    ("inventory", "master_write", "inventory.master_write", "Modificar inventario maestro", "Crear, editar, importar o eliminar inventario maestro.", "high"),
    ("inventory", "movement_write", "inventory.movement_write", "Registrar movimientos", "Crear o eliminar movimientos de inventario.", "high"),

    ("pm", "read", "pm.read", "Consultar PM", "Consultar bitácoras, configuraciones, dashboard y calendario PM.", "low"),
    ("pm", "execute", "pm.execute", "Ejecutar PM", "Registrar ejecución o bitácora de mantenimiento preventivo.", "medium"),
    ("pm", "validate", "pm.validate", "Validar PM", "Crear validaciones de mantenimiento preventivo.", "high"),
    ("pm", "configure", "pm.configure", "Configurar PM", "Crear o editar configuraciones preventivas.", "high"),

    ("warehouse", "view", "warehouse.view", "Ver Warehouse", "Consultar uploads, snapshots y reportes Warehouse.", "low"),
    ("warehouse", "upload", "warehouse.upload", "Subir reportes Warehouse", "Cargar archivos y reportes al Warehouse.", "high"),
    ("warehouse", "archive", "warehouse.archive", "Archivar reportes Warehouse", "Archivar o desactivar cargas Warehouse.", "high"),
    ("warehouse", "catalogs", "warehouse.catalogs", "Gestionar catálogos Warehouse", "Consultar o modificar catálogos comerciales/Warehouse.", "medium"),

    ("internal_documents", "view", "internal_documents.view", "Ver Nube Corporativa", "Consultar documentos internos visibles.", "low"),
    ("internal_documents", "manage", "internal_documents.manage", "Gestionar Nube Corporativa", "Crear, editar, publicar, archivar o cambiar visibilidad de documentos.", "high"),

    ("track", "read", "track.read", "Consultar Track", "Consultar dashboard y mart diario Track.", "low"),
    ("track", "run_daily_pipeline", "track.run_daily_pipeline", "Ejecutar pipeline diario", "Ejecutar pipeline diario Track.", "critical"),
    ("track", "run_agregadoras", "track.run_agregadoras", "Ejecutar integración agregadoras", "Ejecutar integración manual de agregadoras.", "critical"),

    ("planning", "read", "planning.read", "Consultar planeación", "Consultar modelos, batches y metas.", "low"),
    ("planning", "edit", "planning.edit", "Editar planeación", "Editar modelos o filas de metas.", "medium"),
    ("planning", "submit", "planning.submit", "Enviar planeación", "Enviar metas a revisión.", "medium"),
    ("planning", "approve", "planning.approve", "Aprobar planeación", "Aprobar o rechazar metas.", "high"),
    ("planning", "publish", "planning.publish", "Publicar planeación", "Publicar metas hacia fuente operativa.", "critical"),
    ("planning", "configure_model", "planning.configure_model", "Configurar modelo de planeación", "Configurar modelos de metas.", "high"),

    ("openings", "read", "openings.read", "Consultar aperturas", "Consultar proyectos, fases y tareas de aperturas.", "low"),
    ("openings", "manage", "openings.manage", "Gestionar aperturas", "Crear, editar o eliminar entidades de aperturas.", "high"),
    ("openings", "comment", "openings.comment", "Comentar aperturas", "Crear comentarios en tareas de apertura.", "medium"),

    ("catalogs", "manage", "catalogs.manage", "Gestionar catálogos", "Crear, editar, importar o eliminar catálogos.", "high"),

    ("users", "manage", "users.manage", "Gestionar usuarios", "Crear, editar, eliminar usuarios o asignar sucursales.", "critical"),

    ("reports", "read", "reports.read", "Consultar reportes", "Consultar reportes operativos.", "low"),
    ("reports", "create_error_report", "reports.create_error_report", "Reportar error", "Crear reportes de error operativos.", "medium"),
]


def upgrade():
    for key, name, description in MODULES:
        op.execute(
            sa.text(
                """
                INSERT INTO permission_modules (
                    key,
                    name,
                    description,
                    is_active,
                    created_at,
                    updated_at
                )
                VALUES (
                    :key,
                    :name,
                    :description,
                    true,
                    now(),
                    now()
                )
                ON CONFLICT (key) DO UPDATE SET
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    is_active = true,
                    updated_at = now()
                """
            ).bindparams(
                key=key,
                name=name,
                description=description,
            )
        )

    for module_key, key, full_key, name, description, risk_level in ACTIONS:
        op.execute(
            sa.text(
                """
                INSERT INTO permission_actions (
                    module_id,
                    key,
                    full_key,
                    name,
                    description,
                    risk_level,
                    is_active,
                    created_at,
                    updated_at
                )
                SELECT
                    pm.id,
                    :key,
                    :full_key,
                    :name,
                    :description,
                    :risk_level,
                    true,
                    now(),
                    now()
                FROM permission_modules pm
                WHERE pm.key = :module_key
                ON CONFLICT (full_key) DO UPDATE SET
                    key = EXCLUDED.key,
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    risk_level = EXCLUDED.risk_level,
                    is_active = true,
                    updated_at = now()
                """
            ).bindparams(
                module_key=module_key,
                key=key,
                full_key=full_key,
                name=name,
                description=description,
                risk_level=risk_level,
            )
        )


def downgrade():
    bind = op.get_bind()

    action_keys = [full_key for _, _, full_key, _, _, _ in ACTIONS]
    module_keys = [key for key, _, _ in MODULES]

    bind.execute(
        sa.text(
            """
            DELETE FROM permission_actions
            WHERE full_key IN :action_keys
            """
        ).bindparams(
            sa.bindparam("action_keys", expanding=True)
        ),
        {"action_keys": action_keys},
    )

    bind.execute(
        sa.text(
            """
            DELETE FROM permission_modules
            WHERE key IN :module_keys
            """
        ).bindparams(
            sa.bindparam("module_keys", expanding=True)
        ),
        {"module_keys": module_keys},
    )
