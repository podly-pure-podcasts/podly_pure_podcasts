"""What a ModelCall row was made for.

The value is part of the key that the ``upsert_model_call`` writer action uses
to find an LLM row, and part of the ``ix_model_call_post_chunk_model`` unique
index. Calls made for different purposes over the same segment range (an ad
classification chunk and a boundary refinement of an ad block that covers
exactly that chunk, for example) therefore get separate rows instead of
overwriting each other (#271).
"""

CLASSIFICATION = "classification"
BOUNDARY_REFINEMENT = "boundary_refinement"
WORD_BOUNDARY_REFINEMENT = "word_boundary_refinement"
CHAPTER_TITLE = "chapter_title"
TOPIC_PLAN = "topic_plan"
TRANSCRIPTION = "transcription"

# Types the LLM upsert accepts. Transcription rows have their own writer
# action and are keyed by language instead.
LLM_CALL_TYPES = frozenset(
    {
        CLASSIFICATION,
        BOUNDARY_REFINEMENT,
        WORD_BOUNDARY_REFINEMENT,
        CHAPTER_TITLE,
        TOPIC_PLAN,
    }
)
