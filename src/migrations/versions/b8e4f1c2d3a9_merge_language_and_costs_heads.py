"""merge language and costs heads

Revision ID: b8e4f1c2d3a9
Revises: 3e5eebc6b3b1, a7c1b9e2d4f5
Create Date: 2026-09-21 12:00:00.000000

"""

revision = "b8e4f1c2d3a9"
# The per-feed language branch (35adef5e4c3e -> a7c1b9e2d4f5) was based on
# 2e25a15d11de rather than the then-current tip, leaving two heads and breaking
# `flask db upgrade head`. The branches touch disjoint tables, so a no-op merge
# is safe for every database state, including installs that applied `heads`.
down_revision = ("3e5eebc6b3b1", "a7c1b9e2d4f5")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
