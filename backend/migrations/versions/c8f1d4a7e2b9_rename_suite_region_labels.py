"""rename suite region labels

Revision ID: c8f1d4a7e2b9
Revises: a6d9f2c4b781
Create Date: 2026-09-17
"""

from alembic import op
import sqlalchemy as sa


revision = "c8f1d4a7e2b9"
down_revision = "a6d9f2c4b781"
branch_labels = None
depends_on = None


NEW_LABELS = (
    ("MXL_SL", "Región Mexicali BC"),
    ("TIJ_ROS_ENS", "Región Costa BC"),
    ("CLN_LP", "Región Cln / La Paz"),
    ("MTY_SALT_CHIH", "Región Noreste"),
    ("MTY_SALT_SERR", "Región Noreste"),
    ("CDMX_IXT_TLAL", "Región Centro"),
    ("CDMX_IXT_TLAL_CHIH", "Región Centro"),
)

OLD_LABELS = (
    ("MXL_SL", "Mexicali / San Luis"),
    ("TIJ_ROS_ENS", "Tijuana / Rosarito / Ensenada"),
    ("CLN_LP", "Culiacán / La Paz"),
    ("MTY_SALT_CHIH", "Monterrey / Saltillo / Chihuahua"),
    ("MTY_SALT_SERR", "Monterrey / Saltillo / Serranía"),
    ("CDMX_IXT_TLAL", "CDMX / Ixtapaluca / Tlalnepantla"),
    ("CDMX_IXT_TLAL_CHIH", "CDMX / Ixtapaluca / Tlalnepantla / Chihuahua"),
)


def _apply_labels(labels):
    connection = op.get_bind()
    statement = sa.text(
        """
        UPDATE suite_regions
        SET
            region_label = :region_label,
            updated_at = now()
        WHERE region_key = :region_key
        """
    )

    for region_key, region_label in labels:
        connection.execute(
            statement,
            {
                "region_key": region_key,
                "region_label": region_label,
            },
        )


def upgrade():
    _apply_labels(NEW_LABELS)


def downgrade():
    _apply_labels(OLD_LABELS)
