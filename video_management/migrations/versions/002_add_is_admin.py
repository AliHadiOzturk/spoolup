"""Add is_admin to users table."""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade():
    # Add is_admin column to users table
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column("is_admin", sa.Boolean(), nullable=True, server_default="0")
        )
    
    # Update existing users to have is_admin = False
    op.execute("UPDATE users SET is_admin = 0 WHERE is_admin IS NULL")
    
    # Make column non-nullable after setting defaults
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("is_admin", nullable=False)


def downgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("is_admin")
