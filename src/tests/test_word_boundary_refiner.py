from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock, patch

import pytest

from podcast_processor.word_boundary_refiner import WordBoundaryRefiner
from shared.test_utils import create_standard_test_config


def _build_response(
    *,
    content: str,
    finish_reason: str | None,
    prompt_tokens: int = 11,
    completion_tokens: int = 7,
    total_tokens: int = 18,
) -> MagicMock:
    choice = MagicMock()
    choice.message = MagicMock()
    choice.message.content = content
    choice.finish_reason = finish_reason

    response = MagicMock()
    response.choices = [choice]
    response.usage = SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
    )
    return response


@pytest.mark.parametrize(
    ("finish_reason", "expected"),
    [("length", "length"), ("stop", "format"), (None, "format")],
)
def test_parse_failure_reason_classification(
    finish_reason: str | None, expected: str
) -> None:
    assert WordBoundaryRefiner._parse_failure_reason(finish_reason) == expected


@pytest.mark.parametrize(
    ("finish_reason", "expected_error"),
    [("length", "parse_failed:length"), ("stop", "parse_failed:format")],
)
def test_refine_tags_parse_failures_with_finish_reason(
    finish_reason: str, expected_error: str, caplog: pytest.LogCaptureFixture
) -> None:
    refiner = WordBoundaryRefiner(config=create_standard_test_config())
    refiner._update_model_call = MagicMock()  # type: ignore[method-assign]

    response = _build_response(content="not valid json", finish_reason=finish_reason)
    all_segments = [
        {
            "sequence_num": 1,
            "start_time": 10.0,
            "end_time": 12.0,
            "text": "This episode is brought to you by",
        }
    ]

    with (
        patch(
            "podcast_processor.word_boundary_refiner.render_prompt_and_upsert_model_call",
            return_value=("prompt", 42),
        ),
        patch(
            "podcast_processor.word_boundary_refiner.litellm.completion",
            return_value=response,
        ),
        caplog.at_level("DEBUG"),
    ):
        result = refiner.refine(
            ad_start=10.0,
            ad_end=12.0,
            confidence=0.9,
            all_segments=all_segments,
            post_id=99,
            first_seq_num=1,
            last_seq_num=1,
        )

    assert result.start_adjustment_reason == "heuristic_fallback"
    assert result.end_adjustment_reason == "unchanged"

    update_calls = cast(MagicMock, refiner._update_model_call).call_args_list
    assert update_calls[0].kwargs["status"] == "received_response"
    assert update_calls[0].kwargs["error_message"] is None
    assert update_calls[1].kwargs["status"] == "success_heuristic"
    assert update_calls[1].kwargs["error_message"] == expected_error

    assert "Word boundary refine finish_reason=" in caplog.text
    assert f"no parseable JSON ({expected_error.split(':')[1]})" in caplog.text


def test_parse_json_recovers_truncated_fenced_payload() -> None:
    refiner = WordBoundaryRefiner(config=create_standard_test_config())

    truncated = """```json
{
  "refined_start_segment_seq": 2096,
  "refined_start_phrase": "if you're the purchasing",
  "refined_end_segment_seq": 2115,
  "refined_end_phrase": "thank you",
  "start_adjustment_reason": "start moved to sponsor lead in",
  "end_adjustment_reason": "end kept near return cue"
"""

    parsed = refiner._parse_json(truncated)

    assert parsed is not None
    assert parsed["refined_start_segment_seq"] == 2096
    assert parsed["refined_end_segment_seq"] == 2115
    assert parsed["refined_end_phrase"] == "thank you"


def test_parse_json_recovers_truncated_mid_key_prefix() -> None:
    refiner = WordBoundaryRefiner(config=create_standard_test_config())

    truncated = """{
  "refined_start_segment_seq": 288,
  "refined_start_phrase"""

    parsed = refiner._parse_json(truncated)

    assert parsed is not None
    assert parsed["refined_start_segment_seq"] == 288
    assert "refined_start_phrase" not in parsed


def test_context_by_seq_window_uses_contiguous_window_with_padding() -> None:
    refiner = WordBoundaryRefiner(config=create_standard_test_config())
    all_segments = [
        {
            "sequence_num": seq,
            "start_time": float(seq),
            "end_time": float(seq) + 1.0,
            "text": f"Segment {seq}",
        }
        for seq in range(100)
    ]

    selected = refiner._context_by_seq_window(
        all_segments,
        first_seq_num=20,
        last_seq_num=80,
    )
    selected_seqs = [int(seg["sequence_num"]) for seg in selected]

    assert selected_seqs == list(range(18, 83))
    assert 50 in selected_seqs


def test_refine_start_uses_segment_seq_without_phrase() -> None:
    refiner = WordBoundaryRefiner(config=create_standard_test_config())
    all_segments = [
        {
            "sequence_num": 288,
            "start_time": 100.0,
            "end_time": 101.0,
            "text": "Segment text",
        }
    ]

    refined_start, changed, _reason, err = refiner._refine_start(
        ad_start=110.0,
        all_segments=all_segments,
        context_segments=[],
        start_segment_seq=288,
        start_phrase=None,
        start_word=None,
        start_occurrence=None,
        start_word_index=None,
        start_reason="",
    )

    assert err is None
    assert changed is True
    assert refined_start == 100.0


def test_refine_end_uses_segment_seq_without_phrase() -> None:
    refiner = WordBoundaryRefiner(config=create_standard_test_config())
    all_segments = [
        {
            "sequence_num": 345,
            "start_time": 200.0,
            "end_time": 205.0,
            "text": "Segment text",
        }
    ]

    refined_end, changed, _reason, err = refiner._refine_end(
        ad_end=204.0,
        all_segments=all_segments,
        context_segments=[],
        end_segment_seq=345,
        end_phrase=None,
        end_reason="",
    )

    assert err is None
    assert changed is True
    assert refined_end == 205.0
