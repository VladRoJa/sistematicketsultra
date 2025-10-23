from alembic import op

# revision identifiers, used by Alembic.
revision = '8fda6e4996e8'
down_revision = 'a91dc3515ae9'
branch_labels = None
depends_on = None

def upgrade():
    # Solo recrear el índice normal (no unique) en users.email
    op.create_index('ix_users_email', 'users', ['email'], unique=False)

def downgrade():
    op.drop_index('ix_users_email', table_name='users')
