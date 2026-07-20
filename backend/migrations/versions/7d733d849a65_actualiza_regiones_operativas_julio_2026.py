"""actualiza regiones operativas julio 2026

Revision ID: 7d733d849a65
Revises: c2a4e8f91b7d
Create Date: 2026-07-20
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7d733d849a65"
down_revision = "c2a4e8f91b7d"
branch_labels = None
depends_on = None


def upgrade():
    # ---------------------------------------------------------
    # 1. Crear las nuevas regiones operativas.
    #
    # Las regiones anteriores se conservan activas porque deben
    # resolver correctamente el histórico hasta el 30 de junio
    # de 2026.
    # ---------------------------------------------------------
    op.execute(
        sa.text(
            """
            INSERT INTO suite_regions (
                region_key,
                region_label,
                is_active,
                created_at,
                updated_at
            )
            VALUES
                (
                    'MTY_SALT_SERR',
                    'Monterrey / Saltillo / Serranía',
                    true,
                    now(),
                    now()
                ),
                (
                    'CDMX_IXT_TLAL_CHIH',
                    'CDMX / Ixtapaluca / Tlalnepantla / Chihuahua',
                    true,
                    now(),
                    now()
                )
            ON CONFLICT (region_key) DO UPDATE
            SET
                region_label = EXCLUDED.region_label,
                is_active = true,
                updated_at = now();
            """
        )
    )

    # ---------------------------------------------------------
    # 2. Cerrar las asignaciones regionales anteriores.
    #
    # Las sucursales se resuelven por nombre porque sus IDs son
    # diferentes entre la base local y producción.
    #
    # Si Serranía no tiene asignación previa, como ocurre en
    # producción, el UPDATE simplemente no modifica una fila
    # para esa sucursal.
    # ---------------------------------------------------------
    op.execute(
        sa.text(
            """
            UPDATE suite_sucursal_region_assignments assignment
            SET
                is_current = false,
                valid_to = DATE '2026-06-30',
                updated_at = now()
            FROM sucursales sucursal
            WHERE sucursal.sucursal_id = assignment.sucursal_id
              AND UPPER(TRIM(sucursal.sucursal)) IN (
                    'SANTA CATARINA',
                    'SENDERO SALTILLO',
                    'SENDERO CHIHUAHUA',
                    'SALTILLO VILLALTA',
                    'SERRANIA',
                    'IXTAPALUCA',
                    'INSURGENTES',
                    'METEPEC',
                    'TLALNEPANTLA'
              )
              AND assignment.is_current = true;
            """
        )
    )

    # ---------------------------------------------------------
    # 3. Crear las nuevas asignaciones vigentes desde 2026-07-01.
    #
    # MTY / Saltillo / Serranía:
    # - Santa Catarina
    # - Sendero Saltillo
    # - Saltillo Villalta
    # - Serranía
    #
    # CDMX / Ixtapaluca / Tlalnepantla / Chihuahua:
    # - Sendero Chihuahua
    # - Ixtapaluca
    # - Insurgentes
    # - Metepec
    # - Tlalnepantla
    #
    # Si una sucursal no existe en un ambiente local, no se
    # genera ninguna asignación para ella.
    # ---------------------------------------------------------
    op.execute(
        sa.text(
            """
            INSERT INTO suite_sucursal_region_assignments (
                sucursal_id,
                region_id,
                is_current,
                valid_from,
                valid_to,
                created_at,
                updated_at
            )
            SELECT
                sucursal.sucursal_id,
                region.id,
                true,
                DATE '2026-07-01',
                NULL::date,
                now(),
                now()
            FROM (
                VALUES
                    ('SANTA CATARINA', 'MTY_SALT_SERR'),
                    ('SENDERO SALTILLO', 'MTY_SALT_SERR'),
                    ('SALTILLO VILLALTA', 'MTY_SALT_SERR'),
                    ('SERRANIA', 'MTY_SALT_SERR'),

                    ('SENDERO CHIHUAHUA', 'CDMX_IXT_TLAL_CHIH'),
                    ('IXTAPALUCA', 'CDMX_IXT_TLAL_CHIH'),
                    ('INSURGENTES', 'CDMX_IXT_TLAL_CHIH'),
                    ('METEPEC', 'CDMX_IXT_TLAL_CHIH'),
                    ('TLALNEPANTLA', 'CDMX_IXT_TLAL_CHIH')
            ) AS mapping(sucursal_name, region_key)
            JOIN sucursales sucursal
                ON UPPER(TRIM(sucursal.sucursal)) = mapping.sucursal_name
            JOIN suite_regions region
                ON region.region_key = mapping.region_key
            ON CONFLICT ON CONSTRAINT
                uq_suite_sucursal_region_assignment_period
            DO UPDATE
            SET
                is_current = true,
                valid_to = NULL,
                updated_at = now();
            """
        )
    )

    # ---------------------------------------------------------
    # 4. Registrar los responsables formales de las regiones.
    #
    # Los usuarios se resuelven por username porque sus IDs son
    # distintos entre local y producción.
    #
    # Si un usuario no existe en un ambiente local, el JOIN no
    # genera la relación. Antes del despliegue se validará que
    # los cinco usuarios existan en producción.
    # ---------------------------------------------------------
    op.execute(
        sa.text(
            """
            INSERT INTO suite_region_managers (
                region_id,
                user_id,
                is_active,
                created_at,
                updated_at
            )
            SELECT
                region.id,
                app_user.id,
                true,
                now(),
                now()
            FROM (
                VALUES
                    ('MXL_SL', 'EDMUNDO'),
                    ('TIJ_ROS_ENS', 'GEOVANNI'),
                    ('CLN_LP', 'ISAIRIS'),
                    ('MTY_SALT_SERR', 'OMAR'),
                    ('CDMX_IXT_TLAL_CHIH', 'ROBERTO')
            ) AS mapping(region_key, username)
            JOIN suite_regions region
                ON region.region_key = mapping.region_key
            JOIN users app_user
                ON UPPER(TRIM(app_user.username)) = mapping.username
            ON CONFLICT (
                region_id,
                user_id
            )
            DO UPDATE
            SET
                is_active = true,
                updated_at = now();
            """
        )
    )

    # ---------------------------------------------------------
    # 5. Reemplazar los pools efectivos de los regionales.
    #
    # usuario_sucursal es actualmente la fuente real utilizada
    # para autorizar el alcance de GERENTE_REGIONAL.
    #
    # Solo se modifican los regionales que existan en el
    # ambiente donde se ejecuta la migración.
    # ---------------------------------------------------------
    op.execute(
        sa.text(
            """
            DELETE FROM usuario_sucursal
            WHERE user_id IN (
                SELECT id
                FROM users
                WHERE UPPER(TRIM(username)) IN (
                    'EDMUNDO',
                    'GEOVANNI',
                    'ISAIRIS',
                    'OMAR',
                    'ROBERTO'
                )
            );
            """
        )
    )

    op.execute(
        sa.text(
            """
            INSERT INTO usuario_sucursal (
                user_id,
                sucursal_id
            )
            SELECT
                app_user.id,
                sucursal.sucursal_id
            FROM (
                VALUES
                    -- EDMUNDO: Mexicali / San Luis
                    ('EDMUNDO', 'VILLAS DEL REY'),
                    ('EDMUNDO', 'VILLA VERDE MEXICALI'),
                    ('EDMUNDO', 'INDEPENDENCIA'),
                    ('EDMUNDO', 'TEC MEXICALI'),
                    ('EDMUNDO', 'SENDERO MEXICALI'),
                    ('EDMUNDO', 'SAN LUIS'),

                    -- GEOVANNI: Tijuana / Rosarito / Ensenada
                    ('GEOVANNI', 'PABELLON ROSARITO'),
                    ('GEOVANNI', 'MISION ENSENADA'),
                    ('GEOVANNI', 'PASEO 2000'),
                    ('GEOVANNI', 'LOMA BONITA'),
                    ('GEOVANNI', 'SANTA FE'),
                    ('GEOVANNI', 'CARROUSEL TIJUANA'),
                    ('GEOVANNI', 'PAPALOTE TIJUANA'),

                    -- ISAIRIS: Culiacán / La Paz
                    ('ISAIRIS', 'SENDERO CULIACAN'),
                    ('ISAIRIS', 'SAN ISIDRO CULIACAN'),
                    ('ISAIRIS', 'AZAHARES CULIACAN'),
                    ('ISAIRIS', 'PASEO LA PAZ'),

                    -- OMAR: Monterrey / Saltillo / Serranía
                    ('OMAR', 'SANTA CATARINA'),
                    ('OMAR', 'SENDERO SALTILLO'),
                    ('OMAR', 'SALTILLO VILLALTA'),
                    ('OMAR', 'SERRANIA'),

                    -- ROBERTO: CDMX / Ixtapaluca /
                    -- Tlalnepantla / Chihuahua
                    ('ROBERTO', 'SENDERO CHIHUAHUA'),
                    ('ROBERTO', 'IXTAPALUCA'),
                    ('ROBERTO', 'INSURGENTES'),
                    ('ROBERTO', 'METEPEC'),
                    ('ROBERTO', 'TLALNEPANTLA')
            ) AS mapping(username, sucursal_name)
            JOIN users app_user
                ON UPPER(TRIM(app_user.username)) = mapping.username
            JOIN sucursales sucursal
                ON UPPER(TRIM(sucursal.sucursal)) = mapping.sucursal_name
            ON CONFLICT DO NOTHING;
            """
        )
    )


def downgrade():
    # ---------------------------------------------------------
    # 1. Retirar los pools definidos por esta migración.
    # ---------------------------------------------------------
    op.execute(
        sa.text(
            """
            DELETE FROM usuario_sucursal
            WHERE user_id IN (
                SELECT id
                FROM users
                WHERE UPPER(TRIM(username)) IN (
                    'EDMUNDO',
                    'GEOVANNI',
                    'ISAIRIS',
                    'OMAR',
                    'ROBERTO'
                )
            );
            """
        )
    )

    # ---------------------------------------------------------
    # 2. Restaurar los pools encontrados antes del cambio.
    #
    # OMAR no tenía pool asignado.
    # Saltillo Villalta no tenía regional.
    #
    # Nuevamente, usuarios y sucursales se resuelven por nombre.
    # ---------------------------------------------------------
    op.execute(
        sa.text(
            """
            INSERT INTO usuario_sucursal (
                user_id,
                sucursal_id
            )
            SELECT
                app_user.id,
                sucursal.sucursal_id
            FROM (
                VALUES
                    -- EDMUNDO
                    ('EDMUNDO', 'VILLAS DEL REY'),
                    ('EDMUNDO', 'VILLA VERDE MEXICALI'),
                    ('EDMUNDO', 'INDEPENDENCIA'),
                    ('EDMUNDO', 'TEC MEXICALI'),
                    ('EDMUNDO', 'SENDERO MEXICALI'),
                    ('EDMUNDO', 'SAN LUIS'),
                    ('EDMUNDO', 'IXTAPALUCA'),
                    ('EDMUNDO', 'INSURGENTES'),
                    ('EDMUNDO', 'METEPEC'),
                    ('EDMUNDO', 'TLALNEPANTLA'),

                    -- GEOVANNI
                    ('GEOVANNI', 'PABELLON ROSARITO'),
                    ('GEOVANNI', 'MISION ENSENADA'),
                    ('GEOVANNI', 'PASEO 2000'),
                    ('GEOVANNI', 'LOMA BONITA'),
                    ('GEOVANNI', 'SANTA FE'),
                    ('GEOVANNI', 'CARROUSEL TIJUANA'),
                    ('GEOVANNI', 'PAPALOTE TIJUANA'),

                    -- ISAIRIS
                    ('ISAIRIS', 'SENDERO CULIACAN'),
                    ('ISAIRIS', 'SAN ISIDRO CULIACAN'),
                    ('ISAIRIS', 'AZAHARES CULIACAN'),
                    ('ISAIRIS', 'SANTA CATARINA'),
                    ('ISAIRIS', 'SENDERO SALTILLO'),
                    ('ISAIRIS', 'SENDERO CHIHUAHUA'),
                    ('ISAIRIS', 'PASEO LA PAZ'),

                    -- ROBERTO
                    ('ROBERTO', 'IXTAPALUCA'),
                    ('ROBERTO', 'INSURGENTES'),
                    ('ROBERTO', 'METEPEC'),
                    ('ROBERTO', 'TLALNEPANTLA')
            ) AS mapping(username, sucursal_name)
            JOIN users app_user
                ON UPPER(TRIM(app_user.username)) = mapping.username
            JOIN sucursales sucursal
                ON UPPER(TRIM(sucursal.sucursal)) = mapping.sucursal_name
            ON CONFLICT DO NOTHING;
            """
        )
    )

    # ---------------------------------------------------------
    # 3. Eliminar las relaciones de responsables creadas por
    # esta migración.
    #
    # La revisión de producción confirmó que estas asignaciones
    # formales no existían antes del cambio.
    # ---------------------------------------------------------
    op.execute(
        sa.text(
            """
            DELETE FROM suite_region_managers
            WHERE (region_id, user_id) IN (
                SELECT
                    region.id,
                    app_user.id
                FROM (
                    VALUES
                        ('MXL_SL', 'EDMUNDO'),
                        ('TIJ_ROS_ENS', 'GEOVANNI'),
                        ('CLN_LP', 'ISAIRIS'),
                        ('MTY_SALT_SERR', 'OMAR'),
                        ('CDMX_IXT_TLAL_CHIH', 'ROBERTO')
                ) AS mapping(region_key, username)
                JOIN suite_regions region
                    ON region.region_key = mapping.region_key
                JOIN users app_user
                    ON UPPER(TRIM(app_user.username)) = mapping.username
            );
            """
        )
    )

    # ---------------------------------------------------------
    # 4. Eliminar las asignaciones regionales iniciadas el
    # 1 de julio de 2026.
    #
    # La condición por nombre evita afectar LA VIGA en local.
    # ---------------------------------------------------------
    op.execute(
        sa.text(
            """
            DELETE FROM suite_sucursal_region_assignments assignment
            USING sucursales sucursal, suite_regions region
            WHERE sucursal.sucursal_id = assignment.sucursal_id
              AND region.id = assignment.region_id
              AND assignment.valid_from = DATE '2026-07-01'
              AND region.region_key IN (
                    'MTY_SALT_SERR',
                    'CDMX_IXT_TLAL_CHIH'
              )
              AND UPPER(TRIM(sucursal.sucursal)) IN (
                    'SANTA CATARINA',
                    'SENDERO SALTILLO',
                    'SENDERO CHIHUAHUA',
                    'SALTILLO VILLALTA',
                    'SERRANIA',
                    'IXTAPALUCA',
                    'INSURGENTES',
                    'METEPEC',
                    'TLALNEPANTLA'
              );
            """
        )
    )

    # ---------------------------------------------------------
    # 5. Reabrir las asignaciones regionales anteriores.
    #
    # En local Serranía puede estar en NUEVAS.
    # En producción no tenía asignación; en ese caso no se
    # reabre ninguna fila para Serranía.
    # ---------------------------------------------------------
    op.execute(
        sa.text(
            """
            UPDATE suite_sucursal_region_assignments assignment
            SET
                is_current = true,
                valid_to = NULL,
                updated_at = now()
            FROM suite_regions region, sucursales sucursal
            WHERE assignment.region_id = region.id
              AND assignment.sucursal_id = sucursal.sucursal_id
              AND assignment.valid_to = DATE '2026-06-30'
              AND (
                    (
                        UPPER(TRIM(sucursal.sucursal)) IN (
                            'SANTA CATARINA',
                            'SENDERO SALTILLO',
                            'SENDERO CHIHUAHUA',
                            'SALTILLO VILLALTA'
                        )
                        AND region.region_key = 'MTY_SALT_CHIH'
                    )
                    OR
                    (
                        UPPER(TRIM(sucursal.sucursal)) IN (
                            'IXTAPALUCA',
                            'INSURGENTES',
                            'METEPEC',
                            'TLALNEPANTLA'
                        )
                        AND region.region_key = 'CDMX_IXT_TLAL'
                    )
                    OR
                    (
                        UPPER(TRIM(sucursal.sucursal)) = 'SERRANIA'
                        AND region.region_key = 'NUEVAS'
                    )
              );
            """
        )
    )

    # ---------------------------------------------------------
    # 6. Eliminar las regiones nuevas.
    #
    # Se ejecuta después de borrar responsables y asignaciones
    # para respetar las llaves foráneas.
    # ---------------------------------------------------------
    op.execute(
        sa.text(
            """
            DELETE FROM suite_regions
            WHERE region_key IN (
                'MTY_SALT_SERR',
                'CDMX_IXT_TLAL_CHIH'
            );
            """
        )
    )