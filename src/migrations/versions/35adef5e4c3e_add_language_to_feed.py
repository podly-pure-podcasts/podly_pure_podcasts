"""add language to feed

Revision ID: 35adef5e4c3e
Revises: 2e25a15d11de
Create Date: 2026-05-19 12:47:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "35adef5e4c3e"
down_revision = "2e25a15d11de"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("feed", schema=None) as batch_op:
        batch_op.add_column(sa.Column("language", sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table("feed", schema=None) as batch_op:
        batch_op.drop_column("language")
