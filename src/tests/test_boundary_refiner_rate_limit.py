"""Tests for BoundaryRefiner token-rate-limiter wiring.

Regression coverage for the Groq 429 incident (2026-09-24): the boundary
refiner fired LLM calls with no pacing right after the ad classifier had
filled the provider's per-minute token window, so the calls failed
permanently with RateLimitError. The refiner must now pace itself through the
classifier's shared token bucket.
"""

from unittest.mock import Mock, patch

from podcast_processor.ad_classifier import AdClassifier
from podcast_processor.boundary_refiner import BoundaryRefiner
from podcast_processor.token_rate_limiter import TokenRateLimiter
from podcast_processor.word_boundary_refiner import WordBoundaryRefiner

from .test_helpers import create_test_config


def _segments():
    return [
        {"start_time": 0.0, "end_time": 5.0, "text": "welcome to the show"},
        {"start_time": 5.0, "end_time": 10.0, "text": "brought to you by acme"},
        {"start_time": 10.0, "end_time": 15.0, "text": "acme makes great widgets"},
        {"start_time": 15.0, "end_time": 20.0, "text": "back to regular content"},
    ]


def _fake_response():
    resp = Mock()
    choice = Mock()
    choice.message.content = (
        '{"refined_start": 6.0, "refined_end": 14.0, '
        '"start_adjustment_reason": "ok", "end_adjustment_reason": "ok"}'
    )
    choice.text = ""
    resp.choices = [choice]
    return resp


class TestBoundaryRefinerTokenLimiter:
    def test_limiter_defaults_to_none(self):
        """Backward compatible: existing call sites keep working unpaced."""
        refiner = BoundaryRefiner(create_test_config())
        assert refiner.token_limiter is None

    def test_limiter_stored_when_provided(self):
        limiter = Mock(spec=TokenRateLimiter)
        refiner = BoundaryRefiner(create_test_config(), token_limiter=limiter)
        assert refiner.token_limiter is limiter

    def test_refine_waits_on_limiter_before_llm_call(self):
        """The limiter must gate the outgoing call, not run after it."""
        limiter = Mock(spec=TokenRateLimiter)
        calls = []
        limiter.wait_if_needed.side_effect = lambda *a, **k: calls.append(
            "wait_if_needed"
        )

        config = create_test_config()
        refiner = BoundaryRefiner(config, token_limiter=limiter)
        with (
            patch("podcast_processor.boundary_refiner.writer_client") as mock_writer,
            patch("litellm.completion") as mock_call,
        ):
            mock_writer.action.return_value = Mock(success=False)

            def _fake_llm(*args, **kwargs):
                calls.append("litellm")
                return _fake_response()

            mock_call.side_effect = _fake_llm
            result = refiner.refine(5.0, 15.0, 0.9, _segments())

        assert calls == ["wait_if_needed", "litellm"]
        (messages, model), _ = limiter.wait_if_needed.call_args
        assert model == config.llm_model
        assert isinstance(messages, list)
        assert messages[0]["role"] == "user"
        # The refinement itself still completes through the paced call.
        assert result.refined_start == 6.0
        assert result.refined_end == 14.0

    def test_refine_without_limiter_still_calls_llm(self):
        """No limiter -> straight-through call, as before."""
        refiner = BoundaryRefiner(create_test_config())
        with (
            patch("podcast_processor.boundary_refiner.writer_client") as mock_writer,
            patch("litellm.completion") as mock_call,
        ):
            mock_writer.action.return_value = Mock(success=False)
            mock_call.return_value = _fake_response()
            result = refiner.refine(5.0, 15.0, 0.9, _segments())

        mock_call.assert_called_once()
        assert result.refined_start == 6.0


class TestClassifierSharesLimiterWithRefiner:
    def test_classifier_passes_its_limiter_to_refiner(self):
        """The refiner must share the classifier's bucket (same quota)."""
        config = create_test_config(
            enable_boundary_refinement=True,
            enable_word_level_boundary_refinder=False,
        )
        with patch("podcast_processor.ad_classifier.db.session") as mock_session:
            classifier = AdClassifier(config=config, db_session=mock_session)

        assert classifier.rate_limiter is not None
        assert isinstance(classifier.boundary_refiner, BoundaryRefiner)
        assert classifier.boundary_refiner.token_limiter is classifier.rate_limiter


class TestWordRefinerSharesLimiter:
    def test_classifier_passes_its_limiter_to_word_refiner(self):
        config = create_test_config(
            enable_boundary_refinement=True,
            enable_word_level_boundary_refinder=True,
        )
        with patch("podcast_processor.ad_classifier.db.session") as mock_session:
            classifier = AdClassifier(config=config, db_session=mock_session)

        assert isinstance(classifier.boundary_refiner, WordBoundaryRefiner)
        assert classifier.boundary_refiner.token_limiter is classifier.rate_limiter


def test_unparseable_response_still_reports_usage_for_pricing():
    """A paid completion whose JSON can't be parsed must still be priced."""
    usage = {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110}
    response = _fake_response()
    response.choices[0].message.content = "not json"
    refiner = BoundaryRefiner(create_test_config())
    refiner._update_model_call = Mock()  # type: ignore[method-assign]

    with (
        patch("podcast_processor.boundary_refiner.writer_client") as mock_writer,
        patch("litellm.completion", return_value=response),
        patch(
            "podcast_processor.boundary_refiner.extract_litellm_usage",
            return_value=usage,
        ),
    ):
        mock_writer.action.return_value = Mock(success=False)
        refiner.refine(5.0, 15.0, 0.9, _segments())

    last = refiner._update_model_call.call_args_list[-1].kwargs
    assert last["status"] == "success_heuristic"
    assert last["usage"] == usage


def test_json_missing_required_fields_is_priced_as_a_heuristic_fallback():
    """Valid JSON without refined_end is still a paid reply, not a permanent failure."""
    usage = {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110}
    response = _fake_response()
    response.choices[0].message.content = '{"refined_start": 5}'
    refiner = BoundaryRefiner(create_test_config())
    refiner._update_model_call = Mock()  # type: ignore[method-assign]

    with (
        patch("podcast_processor.boundary_refiner.writer_client") as mock_writer,
        patch("litellm.completion", return_value=response),
        patch(
            "podcast_processor.boundary_refiner.extract_litellm_usage",
            return_value=usage,
        ),
    ):
        mock_writer.action.return_value = Mock(success=False)
        refiner.refine(5.0, 15.0, 0.9, _segments())

    last = refiner._update_model_call.call_args_list[-1].kwargs
    assert last["status"] == "success_heuristic"
    assert last["usage"] == usage
    assert "refined_end" in last["error_message"]
