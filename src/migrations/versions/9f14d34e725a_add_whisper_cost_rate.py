"""add whisper cost rate

Revision ID: 9f14d34e725a
Revises: a5e9a6d6d505
Create Date: 2026-05-27 21:49:58.438945

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "9f14d34e725a"
down_revision = "a5e9a6d6d505"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("app_settings", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "whisper_cost_rate_per_hour",
                sa.Float(),
                nullable=False,
                server_default="0.04",
            )
        )


def downgrade():
    with op.batch_alter_table("app_settings", schema=None) as batch_op:
        batch_op.drop_column("whisper_cost_rate_per_hour")
