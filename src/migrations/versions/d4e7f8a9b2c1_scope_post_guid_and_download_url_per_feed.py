"""scope post guid and download_url unique constraints per feed

Revision ID: d4e7f8a9b2c1
Revises: 3e5eebc6b3b1
Create Date: 2026-04-13 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = "d4e7f8a9b2c1"
down_revision = "3e5eebc6b3b1"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = inspector.get_columns("post")
    fks = inspector.get_foreign_keys("post")
    pk = inspector.get_pk_constraint("post")

    col_defs = []
    for col in columns:
        col_type = col["type"]
        parts = [f'"{col["name"]}"', str(col_type)]
        if col["name"] in (pk.get("constrained_columns") or []):
            parts.append("PRIMARY KEY")
        if not col.get("nullable", True):
            parts.append("NOT NULL")
        if col.get("default") is not None:
            parts.append(f"DEFAULT {col['default']}")
        col_defs.append(" ".join(parts))

    for fk in fks:
        ref_table = fk["referred_table"]
        ref_cols = ", ".join(fk["referred_columns"])
        local_cols = ", ".join(fk["constrained_columns"])
        col_defs.append(
            f"FOREIGN KEY({local_cols}) REFERENCES {ref_table} ({ref_cols})"
        )

    col_defs.append('CONSTRAINT "uq_post_feed_id_guid" UNIQUE (feed_id, guid)')
    col_defs.append(
        'CONSTRAINT "uq_post_feed_id_download_url" UNIQUE (feed_id, download_url)'
    )

    create_sql = f'CREATE TABLE "_post_new" ({", ".join(col_defs)})'
    col_names = ", ".join(f'"{c["name"]}"' for c in columns)

    conn.execute(sa.text(create_sql))
    conn.execute(
        sa.text(f'INSERT INTO "_post_new" ({col_names}) SELECT {col_names} FROM "post"')
    )
    conn.execute(sa.text('DROP TABLE "post"'))
    conn.execute(sa.text('ALTER TABLE "_post_new" RENAME TO "post"'))


def downgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = inspector.get_columns("post")
    fks = inspector.get_foreign_keys("post")
    pk = inspector.get_pk_constraint("post")

    col_defs = []
    for col in columns:
        col_type = col["type"]
        parts = [f'"{col["name"]}"', str(col_type)]
        if col["name"] in (pk.get("constrained_columns") or []):
            parts.append("PRIMARY KEY")
        if not col.get("nullable", True):
            parts.append("NOT NULL")
        if col["name"] == "guid":
            parts.append("UNIQUE")
        if col["name"] == "download_url":
            parts.append("UNIQUE")
        if col.get("default") is not None:
            parts.append(f"DEFAULT {col['default']}")
        col_defs.append(" ".join(parts))

    for fk in fks:
        ref_table = fk["referred_table"]
        ref_cols = ", ".join(fk["referred_columns"])
        local_cols = ", ".join(fk["constrained_columns"])
        col_defs.append(
            f"FOREIGN KEY({local_cols}) REFERENCES {ref_table} ({ref_cols})"
        )

    create_sql = f'CREATE TABLE "_post_new" ({", ".join(col_defs)})'
    col_names = ", ".join(f'"{c["name"]}"' for c in columns)

    conn.execute(sa.text(create_sql))
    conn.execute(
        sa.text(f'INSERT INTO "_post_new" ({col_names}) SELECT {col_names} FROM "post"')
    )
    conn.execute(sa.text('DROP TABLE "post"'))
    conn.execute(sa.text('ALTER TABLE "_post_new" RENAME TO "post"'))
