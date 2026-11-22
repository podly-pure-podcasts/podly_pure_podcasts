"""add call_type to model_call

Revision ID: c3d8e1f0a271
Revises: 9f14d34e725a
Create Date: 2026-11-22 17:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "c3d8e1f0a271"
down_revision = "9f14d34e725a"
branch_labels = None
depends_on = None

_LEGACY_KEY = [
    "post_id",
    "first_segment_sequence_num",
    "last_segment_sequence_num",
    "model_name",
]


def upgrade():
    with op.batch_alter_table("model_call", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "call_type",
                sa.String(),
                nullable=False,
                server_default="classification",
            )
        )

    # Existing rows get "classification" from the server default. Label the
    # rows whose purpose is certain from their key: Whisper rows carry a
    # language, and the chapter calls use fixed negative segment ranges
    # (podcast_processor/chapter_fallback.py). Older boundary-refinement rows
    # can't be told apart from classification rows by their columns and keep
    # "classification"; the next refinement of that ad block creates its own
    # row.
    op.execute(
        "UPDATE model_call SET call_type = 'transcription' WHERE language IS NOT NULL"
    )
    op.execute(
        "UPDATE model_call SET call_type = 'chapter_title' "
        "WHERE language IS NULL "
        "AND first_segment_sequence_num = -100 AND last_segment_sequence_num = -100"
    )
    op.execute(
        "UPDATE model_call SET call_type = 'topic_plan' "
        "WHERE language IS NULL "
        "AND first_segment_sequence_num IN (-200, -201) "
        "AND last_segment_sequence_num = first_segment_sequence_num"
    )

    with op.batch_alter_table("model_call", schema=None) as batch_op:
        batch_op.drop_index("ix_model_call_post_chunk_model")
        batch_op.create_index(
            "ix_model_call_post_chunk_model",
            [*_LEGACY_KEY, "call_type"],
            unique=True,
            sqlite_where=sa.text("language IS NULL"),
        )


def downgrade():
    # Without call_type, LLM rows that differ only by call type would collide
    # on the old unique index. Keep the classification row (identifications
    # point at it) and drop the other rows of the same key.
    op.execute(
        """
        DELETE FROM model_call
        WHERE language IS NULL
          AND call_type != 'classification'
          AND EXISTS (
            SELECT 1 FROM model_call AS keep
            WHERE keep.language IS NULL
              AND keep.call_type = 'classification'
              AND keep.post_id = model_call.post_id
              AND keep.first_segment_sequence_num = model_call.first_segment_sequence_num
              AND keep.last_segment_sequence_num = model_call.last_segment_sequence_num
              AND keep.model_name = model_call.model_name
          )
        """
    )
    # Any remaining duplicates are non-classification rows sharing a key (a
    # boundary and a word-boundary refinement of the same block). Keep the
    # newest.
    op.execute(
        """
        DELETE FROM model_call
        WHERE language IS NULL
          AND id NOT IN (
            SELECT MAX(id) FROM model_call
            WHERE language IS NULL
            GROUP BY post_id, first_segment_sequence_num,
                     last_segment_sequence_num, model_name
          )
        """
    )
    with op.batch_alter_table("model_call", schema=None) as batch_op:
        batch_op.drop_index("ix_model_call_post_chunk_model")
        batch_op.create_index(
            "ix_model_call_post_chunk_model",
            _LEGACY_KEY,
            unique=True,
            sqlite_where=sa.text("language IS NULL"),
        )
        batch_op.drop_column("call_type")
