import json
import logging
from types import SimpleNamespace
from unittest.mock import patch

from podcast_processor.chapter_fallback import (
    TOPIC_CHAPTER_CAP_WINDOW_SECONDS,
    TOPIC_CHAPTER_MAX_BLOCK_SECONDS,
    TOPIC_CHAPTER_MAX_CHARS_PER_BLOCK,
    TOPIC_CHAPTER_SHORT_EPISODE_CAP,
    TOPIC_CHAPTER_SHORT_EPISODE_SECONDS,
    TOPIC_CHAPTER_TARGET_BLOCK_COUNT,
    _build_topic_blocks,
    _build_topic_chapter_generation_prompt,
    _parse_topic_chapter_response,
    _topic_chapter_count_cap_for_duration,
    generate_chapters_from_transcript,
    generate_topic_chapters_from_transcript_with_llm,
    refine_description_chapters_with_word_refiner,
    refine_generated_chapter_titles_with_llm,
    resolve_llm_path_chapters,
)
from podcast_processor.chapter_reader import Chapter
from shared.test_utils import create_standard_test_config


def test_resolve_llm_path_chapters_prefers_embedded() -> None:
    embedded = [
        Chapter("chp0", "Intro", 0, 10_000),
        Chapter("chp1", "Topic", 10_000, 20_000),
    ]

    with (
        patch(
            "podcast_processor.chapter_fallback.read_chapters",
            return_value=embedded,
        ),
        patch(
            "podcast_processor.chapter_fallback.parse_chapters_from_description"
        ) as parse_mock,
        patch(
            "podcast_processor.chapter_fallback.generate_chapters_from_transcript"
        ) as gen_mock,
    ):
        chapters, source = resolve_llm_path_chapters(
            unprocessed_audio_path="/tmp/test.mp3",
            description="00:00 Intro\n00:10 Topic",
            transcript_segments=[],
        )

    assert chapters == embedded
    assert source == "embedded"
    parse_mock.assert_not_called()
    gen_mock.assert_not_called()


def test_resolve_llm_path_chapters_falls_back_to_description() -> None:
    parsed = [
        Chapter("desc0", "Intro", 0, 120_000),
        Chapter("desc1", "Topic", 120_000, 300_000),
    ]

    segments = [
        SimpleNamespace(start_time=0.0, end_time=10.0, text="Intro"),
        SimpleNamespace(start_time=299.0, end_time=300.0, text="Wrap"),
    ]

    with (
        patch("podcast_processor.chapter_fallback.read_chapters", return_value=[]),
        patch(
            "podcast_processor.chapter_fallback.parse_chapters_from_description",
            return_value=parsed,
        ) as parse_mock,
        patch(
            "podcast_processor.chapter_fallback.generate_chapters_from_transcript"
        ) as gen_mock,
    ):
        chapters, source = resolve_llm_path_chapters(
            unprocessed_audio_path="/tmp/test.mp3",
            description="ignored",
            transcript_segments=segments,
        )

    assert chapters == parsed
    assert source == "description"
    parse_mock.assert_called_once()
    gen_mock.assert_not_called()


def test_generate_chapters_from_transcript_splits_windows_and_titles() -> None:
    segments = [
        SimpleNamespace(start_time=0.0, end_time=20.0, text="Intro and setup"),
        SimpleNamespace(start_time=310.0, end_time=330.0, text="Main topic one"),
        SimpleNamespace(start_time=630.0, end_time=650.0, text="Main topic two"),
    ]

    chapters = generate_chapters_from_transcript(
        segments,
        total_duration_ms=900_000,
        target_chapter_seconds=300,
        min_remaining_seconds_for_split=0,
    )

    assert [c.start_time_ms for c in chapters] == [0, 310_000, 630_000]
    assert [c.end_time_ms for c in chapters] == [310_000, 630_000, 900_000]
    assert [c.title for c in chapters] == [
        "Intro and setup",
        "Main topic one",
        "Main topic two",
    ]


def test_refine_description_chapters_with_word_refiner_adjusts_starts() -> None:
    config = create_standard_test_config()
    config.enable_word_level_boundary_refiner = True

    chapters = [
        Chapter("desc0", "First story", 5_000, 310_000),
        Chapter("desc1", "Second story", 310_000, 650_000),
    ]
    transcript_segments = [
        SimpleNamespace(sequence_num=0, start_time=0.0, end_time=4.0, text="Cold open"),
        SimpleNamespace(
            sequence_num=1,
            start_time=12.0,
            end_time=20.0,
            text="First story starts right now",
        ),
        SimpleNamespace(
            sequence_num=2,
            start_time=300.0,
            end_time=307.0,
            text="A quick transition",
        ),
        SimpleNamespace(
            sequence_num=3,
            start_time=318.0,
            end_time=328.0,
            text="Second story begins with an update",
        ),
    ]

    refined = refine_description_chapters_with_word_refiner(
        chapters,
        transcript_segments,
        config=config,
    )

    assert [ch.start_time_ms for ch in refined] == [12_000, 318_000]
    assert [ch.end_time_ms for ch in refined] == [318_000, 650_000]
    assert [ch.title for ch in refined] == ["First story", "Second story"]


def test_refine_generated_chapter_titles_with_llm_updates_titles() -> None:
    chapters = [
        Chapter("gen0", "Hello everybody and welcome...", 0, 300_000),
        Chapter("gen1", "You have to go find gold...", 300_000, 600_000),
    ]
    transcript_segments = [
        SimpleNamespace(start_time=0.0, end_time=20.0, text="Hello everybody"),
        SimpleNamespace(start_time=310.0, end_time=330.0, text="Gold challenge"),
    ]

    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=(
                        '{"titles":[{"index":0,"title":"Episode intro"},'
                        '{"index":1,"title":"Gold mission"}]}'
                    )
                )
            )
        ]
    )

    with patch(
        "podcast_processor.chapter_fallback.litellm.completion",
        return_value=response,
    ) as completion_mock:
        refined = refine_generated_chapter_titles_with_llm(
            chapters,
            transcript_segments,
            llm_model="test-model",
            llm_api_key="test-key",
            openai_base_url="https://llm.example.com/v1",
            openai_timeout_sec=30,
        )

    assert [c.title for c in refined] == ["Episode intro", "Gold mission"]
    assert [c.start_time_ms for c in refined] == [0, 300_000]
    assert completion_mock.call_args.kwargs["api_key"] == "test-key"
    assert completion_mock.call_args.kwargs["base_url"] == "https://llm.example.com/v1"


def test_generate_topic_chapters_from_transcript_with_llm_uses_llm_boundaries() -> None:
    transcript_segments = [
        SimpleNamespace(start_time=0.0, end_time=20.0, text="Host intro and recap"),
        SimpleNamespace(
            start_time=310.0,
            end_time=330.0,
            text="Castle challenge starts",
        ),
        SimpleNamespace(
            start_time=630.0,
            end_time=650.0,
            text="Roundtable and banishment",
        ),
    ]

    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=(
                        '{"chapters":['
                        '{"block_index":0,"title":"Opening recap"},'
                        '{"block_index":1,"title":"Challenge begins"},'
                        '{"block_index":2,"title":"Roundtable fallout"}'
                        "]}"
                    )
                )
            )
        ]
    )

    with patch(
        "podcast_processor.chapter_fallback.litellm.completion",
        return_value=response,
    ) as completion_mock:
        chapters = generate_topic_chapters_from_transcript_with_llm(
            transcript_segments,
            llm_model="test-model",
            llm_api_key="test-key",
            openai_base_url="https://llm.example.com/v1",
            total_duration_ms=900_000,
            openai_timeout_sec=30,
            min_chapter_seconds=0,
        )

    assert [c.start_time_ms for c in chapters] == [0, 310_000, 630_000]
    assert [c.end_time_ms for c in chapters] == [310_000, 630_000, 900_000]
    assert [c.title for c in chapters] == [
        "Opening recap",
        "Challenge begins",
        "Roundtable fallout",
    ]
    assert completion_mock.call_args.kwargs["api_key"] == "test-key"
    assert completion_mock.call_args.kwargs["base_url"] == "https://llm.example.com/v1"


def test_generate_topic_chapters_from_transcript_with_llm_retries_remaining_blocks() -> (
    None
):
    transcript_segments = [
        SimpleNamespace(start_time=0.0, end_time=20.0, text="Opening recap"),
        SimpleNamespace(start_time=600.0, end_time=620.0, text="Mission setup"),
        SimpleNamespace(start_time=1200.0, end_time=1220.0, text="Castle conflict"),
        SimpleNamespace(start_time=1800.0, end_time=1820.0, text="Roundtable vote"),
    ]

    prompts: list[str] = []

    def _mock_response(content: str, *, finish_reason: str) -> SimpleNamespace:
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=content),
                    finish_reason=finish_reason,
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=100,
                completion_tokens=100,
                total_tokens=200,
            ),
        )

    first_response = _mock_response(
        (
            '{"chapter_count":4,"chapters":['
            '{"block_index":0,"title":"Opening recap"},'
            '{"block_index":1,"title":"Mission setup"},'
            '{"block_index":'
        ),
        finish_reason="length",
    )
    second_response = _mock_response(
        (
            '{"chapter_count":3,"chapters":['
            '{"block_index":1,"title":"Different duplicate title"},'
            '{"block_index":2,"title":"Castle conflict"},'
            '{"block_index":3,"title":"Roundtable vote"}'
            "]}"
        ),
        finish_reason="stop",
    )

    def _completion_side_effect(**kwargs):
        prompts.append(kwargs["messages"][-1]["content"])
        if len(prompts) == 1:
            return first_response
        return second_response

    with patch(
        "podcast_processor.chapter_fallback.litellm.completion",
        side_effect=_completion_side_effect,
    ) as completion_mock:
        chapters = generate_topic_chapters_from_transcript_with_llm(
            transcript_segments,
            llm_model="test-model",
            total_duration_ms=2_400_000,
            openai_timeout_sec=30,
            min_chapter_seconds=0,
        )

    assert completion_mock.call_count == 2
    assert len(prompts) == 2
    assert "Return only chapters with block_index > 1" in prompts[1]
    assert "Do not repeat existing chapter block_index values: [0, 1]" in prompts[1]

    retry_payload = json.loads(prompts[1].split("Transcript blocks:\n", 1)[1])
    assert [block["block_index"] for block in retry_payload] == [1, 2, 3]

    assert [c.start_time_ms for c in chapters] == [0, 600_000, 1_200_000, 1_800_000]
    assert [c.end_time_ms for c in chapters] == [
        600_000,
        1_200_000,
        1_800_000,
        2_400_000,
    ]
    assert [c.title for c in chapters] == [
        "Opening recap",
        "Mission setup",
        "Castle conflict",
        "Roundtable vote",
    ]


def test_build_topic_blocks_reduces_prompt_payload_for_long_transcript() -> None:
    segments = [
        SimpleNamespace(
            start_time=float(i * 60),
            end_time=float(i * 60 + 20),
            text=("word " * 120).strip(),
        )
        for i in range(120)
    ]

    blocks = _build_topic_blocks(
        segments,
        total_duration_ms=7_200_000,  # 2h
    )

    assert 1 < len(blocks) <= TOPIC_CHAPTER_TARGET_BLOCK_COUNT
    for block in blocks:
        assert isinstance(block["text"], str)
        assert len(block["text"]) <= TOPIC_CHAPTER_MAX_CHARS_PER_BLOCK


def test_build_topic_blocks_caps_long_episode_window_at_two_minutes() -> None:
    segments = [
        SimpleNamespace(
            start_time=float(i * 60),
            end_time=float(i * 60 + 20),
            text=f"segment {i}",
        )
        for i in range(180)
    ]

    blocks = _build_topic_blocks(
        segments,
        total_duration_ms=10_800_000,  # 3h
    )

    assert len(blocks) > TOPIC_CHAPTER_TARGET_BLOCK_COUNT
    assert len(blocks) <= 10_800_000 // (TOPIC_CHAPTER_MAX_BLOCK_SECONDS * 1000) + 1
    assert blocks[0]["start_ms"] == 0
    assert blocks[1]["start_ms"] - blocks[0]["start_ms"] <= (
        TOPIC_CHAPTER_MAX_BLOCK_SECONDS * 1000
    )


def test_parse_topic_chapter_response_salvages_truncated_json(caplog) -> None:
    truncated = (
        '{"chapter_count":4,"chapters":[{"block_index":0,'
        '"title":"Intro and breakfast drama"},'
        '{"block_index":3,"title":"Mission and strategy breakdown"},'
        '{"block_index":7,"title":"Conflict at the round table"},'
        '{"block_index":'
    )

    test_logger = logging.getLogger("global_logger")
    original_level = test_logger.level
    test_logger.addHandler(caplog.handler)
    test_logger.setLevel(logging.WARNING)
    try:
        parsed = _parse_topic_chapter_response(truncated)
    finally:
        test_logger.removeHandler(caplog.handler)
        test_logger.setLevel(original_level)

    assert parsed == [
        (0, "Intro and breakfast drama"),
        (3, "Mission and strategy breakdown"),
        (7, "Conflict at the round table"),
    ]
    assert "Recovered partial topic chapter plan is incomplete" in caplog.text


def test_build_topic_chapter_generation_prompt_requests_minified_and_hard_cap() -> None:
    blocks = [
        {"block_index": 0, "timestamp": "00:00", "text": "intro block"},
        {"block_index": 1, "timestamp": "08:00", "text": "mission block"},
        {"block_index": 2, "timestamp": "16:00", "text": "roundtable block"},
    ]

    prompt = _build_topic_chapter_generation_prompt(
        blocks=blocks,
        total_duration_ms=2_160_000,  # 36 min
        target_chapter_seconds=8 * 60,
        min_chapter_seconds=2 * 60,
    )

    assert "Return minified JSON only on a single line" in prompt
    assert '{"chapter_count":2,"chapters":[' in prompt
    assert "Put chapter_count first in the JSON object" in prompt
    assert (
        f"Hard cap: at most {TOPIC_CHAPTER_SHORT_EPISODE_CAP} chapters total" in prompt
    )
    assert "ceiling, not a target" in prompt


def test_topic_chapter_count_cap_for_duration_matches_configured_policy() -> None:
    assert _topic_chapter_count_cap_for_duration(120 * 60) == (
        (120 * 60 + TOPIC_CHAPTER_CAP_WINDOW_SECONDS - 1)
        // TOPIC_CHAPTER_CAP_WINDOW_SECONDS
    )
    assert (
        _topic_chapter_count_cap_for_duration(36 * 60)
        == TOPIC_CHAPTER_SHORT_EPISODE_CAP
    )
    assert (
        _topic_chapter_count_cap_for_duration(59 * 60)
        == TOPIC_CHAPTER_SHORT_EPISODE_CAP
    )
    assert _topic_chapter_count_cap_for_duration(
        TOPIC_CHAPTER_SHORT_EPISODE_SECONDS
    ) == (
        (TOPIC_CHAPTER_SHORT_EPISODE_SECONDS + TOPIC_CHAPTER_CAP_WINDOW_SECONDS - 1)
        // TOPIC_CHAPTER_CAP_WINDOW_SECONDS
    )
