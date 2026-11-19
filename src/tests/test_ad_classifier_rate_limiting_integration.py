"""
Tests for rate limiting integration in AdClassifier.
"""

from unittest.mock import Mock, patch

from podcast_processor.ad_classifier import AdClassifier
from podcast_processor.token_rate_limiter import TokenRateLimiter

from .test_helpers import create_test_config


class TestAdClassifierRateLimiting:
    """Test cases for rate limiting integration in AdClassifier."""

    def test_rate_limiter_initialization_enabled(self):
        """Test that rate limiter is properly initialized when enabled."""
        config = create_test_config()

        with patch("podcast_processor.ad_classifier.db.session") as mock_session:
            classifier = AdClassifier(config=config, db_session=mock_session)

            assert classifier.rate_limiter is not None
            assert isinstance(classifier.rate_limiter, TokenRateLimiter)
            assert (
                classifier.rate_limiter.tokens_per_minute == 30000
            )  # Anthropic default

    def test_rate_limiter_initialization_disabled(self):
        """Test that rate limiter is None when disabled."""
        config = create_test_config(llm_enable_token_rate_limiting=False)

        with patch("podcast_processor.ad_classifier.db.session") as mock_session:
            classifier = AdClassifier(config=config, db_session=mock_session)

            assert classifier.rate_limiter is None

    def test_rate_limiter_custom_limit(self):
        """Test rate limiter with custom token limit."""
        config = create_test_config(llm_max_input_tokens_per_minute=15000)

        with patch("podcast_processor.ad_classifier.db.session") as mock_session:
            classifier = AdClassifier(config=config, db_session=mock_session)

            assert classifier.rate_limiter is not None
            assert classifier.rate_limiter.tokens_per_minute == 15000

    def test_is_retryable_error_rate_limit_errors(self):
        """Test that rate limit errors are correctly identified as retryable."""
        config = create_test_config()

        with patch("podcast_processor.ad_classifier.db.session") as mock_session:
            classifier = AdClassifier(config=config, db_session=mock_session)

            # Test various rate limit error formats
            rate_limit_errors = [
                Exception("rate_limit_error: too many requests"),
                Exception("RateLimitError from API"),
                Exception("HTTP 429 rate limit exceeded"),
                Exception("rate limit reached"),
                Exception("Service temporarily unavailable (503)"),
            ]

            for error in rate_limit_errors:
                assert classifier._is_retryable_error(error) is True

    def test_is_retryable_error_non_retryable(self):
        """Test that non-retryable errors are correctly identified."""
        config = create_test_config()

        with patch("podcast_processor.ad_classifier.db.session") as mock_session:
            classifier = AdClassifier(config=config, db_session=mock_session)

            # Test non-retryable errors
            non_retryable_errors = [
                Exception("Invalid API key"),
                Exception("Bad request (400)"),
                ValueError("Invalid input"),
            ]

            for error in non_retryable_errors:
                assert classifier._is_retryable_error(error) is False

    @patch("litellm.completion")
    @patch("podcast_processor.ad_classifier.isinstance")
    def test_call_model_with_rate_limiter(self, mock_isinstance, mock_completion):
        """Test that _call_model uses rate limiter when available."""
        # Make isinstance return True for our mock objects
        mock_isinstance.return_value = True

        config = create_test_config()

        with patch("podcast_processor.ad_classifier.db.session") as mock_session:
            classifier = AdClassifier(config=config, db_session=mock_session)

            # Mock the rate limiter
            classifier.rate_limiter = Mock(spec=TokenRateLimiter)
            classifier.rate_limiter.wait_if_needed = Mock()
            classifier.rate_limiter.get_usage_stats = Mock(
                return_value={
                    "current_usage": 1000,
                    "limit": 30000,
                    "usage_percentage": 3.3,
                }
            )

            # Mock successful API response
            mock_response = Mock()
            mock_choice = Mock()
            mock_choice.message.content = '{"ad_segments": []}'
            mock_response.choices = [mock_choice]
            mock_completion.return_value = mock_response

            # Create a test ModelCall using actual ModelCall class
            from app.models import ModelCall

            model_call = ModelCall(
                id=1,
                model_name="anthropic/claude-3-5-sonnet-20240620",
                prompt="test prompt",
                status="pending",
            )

            # Call the model
            result = classifier._call_model(model_call, "test system prompt")

            # Verify rate limiter was used
            classifier.rate_limiter.wait_if_needed.assert_called_once()
            classifier.rate_limiter.get_usage_stats.assert_called_once()

            # Verify API was called with correct parameters
            mock_completion.assert_called_once()
            call_args = mock_completion.call_args
            assert call_args[1]["model"] == "anthropic/claude-3-5-sonnet-20240620"
            assert len(call_args[1]["messages"]) == 2
            assert call_args[1]["messages"][0]["role"] == "system"
            assert call_args[1]["messages"][1]["role"] == "user"

            assert result == '{"ad_segments": []}'

    @patch("time.sleep")
    def test_rate_limit_backoff_timing(self, mock_sleep):
        """Test that rate limit errors use longer backoff timing."""
        config = create_test_config()

        with patch("podcast_processor.ad_classifier.db.session") as mock_session:
            classifier = AdClassifier(config=config, db_session=mock_session)

            # Create a test ModelCall using actual ModelCall class
            from app.models import ModelCall

            model_call = ModelCall(id=1, error_message=None)

            error = Exception("rate_limit_error: too many requests")

            # Test first retry (attempt 0)
            classifier._handle_retryable_error(
                model_call_obj=model_call, error=error, attempt=0, current_attempt_num=1
            )
            mock_sleep.assert_called_with(30)  # 30 * (2^0) = 30 seconds

    def test_rate_limiter_model_specific_configs(self):
        """Test that different models get appropriate rate limits."""
        test_cases = [
            ("anthropic/claude-3-5-sonnet-20240620", 30000),
            ("gpt-4o", 150000),
            ("gpt-4o-mini", 200000),
            ("gemini/gemini-3-flash-preview", 60000),
            ("gemini/gemini-2.5-flash", 60000),
            ("unknown-model", 30000),  # Should use default
        ]

        for model_name, expected_limit in test_cases:
            # Clear singleton before each test case
            import podcast_processor.token_rate_limiter as trl_module

            trl_module._RATE_LIMITER = None

            config = create_test_config(llm_model=model_name)

            with patch("podcast_processor.ad_classifier.db.session") as mock_session:
                classifier = AdClassifier(config=config, db_session=mock_session)

                assert classifier.rate_limiter is not None
                assert classifier.rate_limiter.tokens_per_minute == expected_limit

    def test_retries_wait_for_the_token_budget_but_the_first_attempt_does_not(self):
        """The first request was already paced by _prepare_api_call; each later
        provider request (Flex retry, standard fallback) paces itself against the
        model the call actually uses."""
        config = create_test_config()

        with patch("podcast_processor.ad_classifier.db.session") as mock_session:
            classifier = AdClassifier(config=config, db_session=mock_session)
            classifier.rate_limiter = Mock(spec=TokenRateLimiter)
            args = {
                "model": "per-call/model",
                "messages": [{"role": "user", "content": "hi"}],
            }

            before_attempt = classifier._pace_retries(args)
            assert before_attempt is not None

            before_attempt()
            classifier.rate_limiter.wait_if_needed.assert_not_called()

            before_attempt()
            before_attempt()
            assert classifier.rate_limiter.wait_if_needed.call_count == 2
            classifier.rate_limiter.wait_if_needed.assert_called_with(
                args["messages"], "per-call/model"
            )

    def test_complete_passes_the_pacing_hook_to_the_tier_retry(self):
        config = create_test_config()

        with patch("podcast_processor.ad_classifier.db.session") as mock_session:
            classifier = AdClassifier(config=config, db_session=mock_session)

            with patch(
                "podcast_processor.ad_classifier.call_litellm_with_tier_retry"
            ) as tier_retry:
                classifier._complete({"messages": []}, model_call_id=7)

            assert callable(tier_retry.call_args.kwargs["before_attempt"])

    def test_no_pacing_hook_without_a_rate_limiter(self):
        config = create_test_config()

        with patch("podcast_processor.ad_classifier.db.session") as mock_session:
            classifier = AdClassifier(config=config, db_session=mock_session)
            classifier.rate_limiter = None

            assert classifier._pace_retries({"messages": []}) is None
