"""add language to model_call

Revision ID: a7c1b9e2d4f5
Revises: 35adef5e4c3e
Create Date: 2026-05-19 14:30:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "a7c1b9e2d4f5"
down_revision = "35adef5e4c3e"
branch_labels = None
depends_on = None


def upgrade():
    # Nullable so existing rows keep NULL. The whisper cache lookup filters by
    # language, so legacy rows force a one-time re-transcription on next process.
    with op.batch_alter_table("model_call", schema=None) as batch_op:
        batch_op.add_column(sa.Column("language", sa.Text(), nullable=True))
        # Restrict the existing unique index to rows with NULL language (LLM /
        # legacy callers) so non-whisper uniqueness behaves exactly as before.
        batch_op.drop_index("ix_model_call_post_chunk_model")
        batch_op.create_index(
            "ix_model_call_post_chunk_model",
            [
                "post_id",
                "first_segment_sequence_num",
                "last_segment_sequence_num",
                "model_name",
            ],
            unique=True,
            sqlite_where=sa.text("language IS NULL"),
        )
        # Whisper rows are keyed by (post, model, language) — one row per
        # (post, model, language) regardless of segment count.
        batch_op.create_index(
            "ix_model_call_whisper_post_model_lang",
            ["post_id", "model_name", "language"],
            unique=True,
            sqlite_where=sa.text("language IS NOT NULL"),
        )


def downgrade():
    # Upgrade allowed multiple whisper ModelCall rows per (post, model) keyed
    # by language. The legacy unique index doesn't include language, so if two
    # rows share (post, first_seq, last_seq, model_name) but differ only in
    # language, recreating that index would collide. Collapse duplicates
    # first, keeping the most recently updated row.
    op.execute(
        """
        DELETE FROM model_call
        WHERE id NOT IN (
            SELECT MAX(id) FROM model_call
            GROUP BY post_id, first_segment_sequence_num,
                     last_segment_sequence_num, model_name
        )
        """
    )
    with op.batch_alter_table("model_call", schema=None) as batch_op:
        batch_op.drop_index("ix_model_call_whisper_post_model_lang")
        batch_op.drop_index("ix_model_call_post_chunk_model")
        batch_op.create_index(
            "ix_model_call_post_chunk_model",
            [
                "post_id",
                "first_segment_sequence_num",
                "last_segment_sequence_num",
                "model_name",
            ],
            unique=True,
        )
        batch_op.drop_column("language")
