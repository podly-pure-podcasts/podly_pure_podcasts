from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from podcast_processor.boundary_refiner import BoundaryRefiner
from shared.test_utils import create_standard_test_config

_SEGMENTS = [
    {
        "sequence_num": 1,
        "start_time": 10.0,
        "end_time": 12.0,
        "text": "This episode is brought to you by",
    }
]


def _response() -> MagicMock:
    choice = MagicMock()
    choice.message = MagicMock()
    choice.message.content = (
        '{"refined_start": 10.0, "refined_end": 12.0,'
        ' "start_adjustment_reason": "a", "end_adjustment_reason": "b"}'
    )
    response = MagicMock()
    response.choices = [choice]
    response.usage = SimpleNamespace(
        prompt_tokens=11,
        prompt_tokens_details=SimpleNamespace(cached_tokens=3),
        completion_tokens=7,
        total_tokens=18,
    )
    return response


def test_refine_persists_token_usage_and_cost_on_success() -> None:
    refiner = BoundaryRefiner(config=create_standard_test_config())

    with (
        patch("podcast_processor.boundary_refiner.writer_client") as writer,
        patch("litellm.completion", return_value=_response()),
        patch(
            "podcast_processor.llm_model_call_utils.compute_estimated_cost_usd",
            return_value=0.0123,
        ),
        patch("podcast_processor.llm_model_call_utils.writer_client") as util_writer,
    ):
        writer.action.return_value = SimpleNamespace(
            success=True, data={"model_call_id": 5}
        )
        refiner.refine(
            ad_start=10.0,
            ad_end=12.0,
            confidence=0.9,
            all_segments=_SEGMENTS,
            post_id=1,
            first_seq_num=1,
            last_seq_num=1,
        )

    payloads = [call.args[2] for call in util_writer.update.call_args_list]
    final = payloads[-1]
    assert final["status"] == "success"
    assert final["prompt_tokens"] == 11
    assert final["cached_prompt_tokens"] == 3
    assert final["completion_tokens"] == 7
    assert final["total_tokens"] == 18
    assert final["estimated_cost_usd"] == 0.0123
