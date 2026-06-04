"""feed last_changed_at

Revision ID: 8a4d0c2f3e91
Revises: 3e5eebc6b3b1
Create Date: 2026-04-28 00:45:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "8a4d0c2f3e91"
down_revision = "3e5eebc6b3b1"
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(sa.text(f"PRAGMA table_info({table_name})"))
    columns = [row[1] for row in result.fetchall()]
    return column_name in columns


def upgrade():
    if column_exists("feed", "last_changed_at"):
        return
    with op.batch_alter_table("feed", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "last_changed_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.current_timestamp(),
            )
        )


def downgrade():
    if column_exists("feed", "last_changed_at"):
        with op.batch_alter_table("feed", schema=None) as batch_op:
            batch_op.drop_column("last_changed_at")
