from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '8fda6e4996e8'
down_revision = 'a91dc3515ae9'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    user_columns = {column['name'] for column in inspector.get_columns('users')}
    if 'email' not in user_columns:
        return

    user_indexes = {index['name'] for index in inspector.get_indexes('users')}
    if 'ix_users_email' not in user_indexes:
        op.create_index('ix_users_email', 'users', ['email'], unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    user_indexes = {index['name'] for index in inspector.get_indexes('users')}
    if 'ix_users_email' in user_indexes:
        op.drop_index('ix_users_email', table_name='users')