from collections.abc import Generator
from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask
from jinja2 import Template
from litellm.exceptions import InternalServerError
from litellm.types.utils import Choices

from app.extensions import db
from app.models import ModelCall, Post, TranscriptSegment
from podcast_processor.ad_classifier import (
    AdClassifier,
    ClassificationIncompleteError,
    InvalidModelOutputError,
)
from podcast_processor.model_output import (
    AdSegmentPrediction,
    AdSegmentPredictionList,
)
from shared.config import Config
from shared.test_utils import create_standard_test_config

VALID_RESPONSE = '{"ad_segments": [{"segment_offset": 1.0, "confidence": 0.9}]}'


@pytest.fixture
def app() -> Generator[Flask, None, None]:
    """Create and configure a Flask app for testing."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    with app.app_context():
        db.init_app(app)
        db.create_all()
        yield app


@pytest.fixture
def test_config() -> Config:
    return create_standard_test_config()


@pytest.fixture
def mock_db_session() -> MagicMock:
    """Create a mock database session"""
    mock_session = MagicMock()
    mock_session.add = MagicMock()
    mock_session.add_all = MagicMock()
    mock_session.commit = MagicMock()
    mock_session.rollback = MagicMock()
    return mock_session


@pytest.fixture
def test_classifier(test_config: Config) -> AdClassifier:
    """Create an AdClassifier with default dependencies"""
    return AdClassifier(config=test_config)


@pytest.fixture
def test_classifier_with_mocks(
    test_config: Config, mock_db_session: MagicMock
) -> AdClassifier:
    """Create an AdClassifier with mock dependencies"""
    mock_model_call_query = MagicMock()
    mock_identification_query = MagicMock()

    return AdClassifier(
        config=test_config,
        model_call_query=mock_model_call_query,
        identification_query=mock_identification_query,
        db_session=mock_db_session,
    )


def test_call_model(test_config: Config, app: Flask) -> None:
    """Test the _call_model method with mocked litellm"""
    with app.app_context():
        classifier = AdClassifier(config=test_config, db_session=db.session)

        # Create and persist a ModelCall row (writer_client local fallback updates by id)
        dummy_model_call = ModelCall(
            post_id=0,
            model_name=test_config.llm_model,
            prompt="test prompt",
            first_segment_sequence_num=0,
            last_segment_sequence_num=0,
            status="pending",
        )
        db.session.add(dummy_model_call)
        db.session.commit()

        # Create a mock message and choice directly
        mock_message = MagicMock()
        mock_message.content = VALID_RESPONSE

        mock_choice = MagicMock(spec=Choices)
        mock_choice.message = mock_message

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        # Patch the litellm.completion function for this test
        with patch("litellm.completion", return_value=mock_response):
            # Call the method
            response = classifier._call_model(
                model_call_obj=dummy_model_call,
                system_prompt="test system prompt",
            )

            # Verify response
            assert response == VALID_RESPONSE
            refreshed = db.session.get(ModelCall, dummy_model_call.id)
            assert refreshed is not None
            assert refreshed.status == "success"
            assert refreshed.response == VALID_RESPONSE


def test_call_model_retry_on_internal_error(test_config: Config, app: Flask) -> None:
    """Test that _call_model retries on InternalServerError"""
    with app.app_context():
        classifier = AdClassifier(config=test_config, db_session=db.session)

        dummy_model_call = ModelCall(
            post_id=0,
            model_name=test_config.llm_model,
            prompt="test prompt",
            first_segment_sequence_num=0,
            last_segment_sequence_num=0,
            status="pending",
        )
        db.session.add(dummy_model_call)
        db.session.commit()

        # Create a mock message and choice directly
        mock_message = MagicMock()
        mock_message.content = VALID_RESPONSE

        mock_choice = MagicMock(spec=Choices)
        mock_choice.message = mock_message

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        # First call fails, second succeeds
        mock_completion_side_effects = [
            InternalServerError(
                message="test error",
                llm_provider="test_provider",
                model="test_model",
            ),
            mock_response,
        ]

        # Patch time.sleep to avoid waiting during tests
        with (
            patch("time.sleep"),
            patch(
                "litellm.completion", side_effect=mock_completion_side_effects
            ) as mocked_completion,
        ):
            response = classifier._call_model(
                model_call_obj=dummy_model_call,
                system_prompt="test system prompt",
            )

            assert response == VALID_RESPONSE
            assert mocked_completion.call_count == 2
            refreshed = db.session.get(ModelCall, dummy_model_call.id)
            assert refreshed is not None
            assert refreshed.status == "success"
            assert refreshed.response == VALID_RESPONSE
            assert refreshed.retry_attempts == 2


def _persisted_model_call(test_config: Config) -> ModelCall:
    model_call = ModelCall(
        post_id=0,
        model_name=test_config.llm_model,
        prompt="test prompt",
        first_segment_sequence_num=0,
        last_segment_sequence_num=0,
        status="pending",
    )
    db.session.add(model_call)
    db.session.commit()
    return model_call


def _completion(content: str, finish_reason: str = "stop") -> MagicMock:
    mock_choice = MagicMock(spec=Choices)
    mock_choice.message = MagicMock()
    mock_choice.message.content = content
    mock_choice.finish_reason = finish_reason
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    return mock_response


def test_call_model_retries_truncated_response(test_config: Config, app: Flask) -> None:
    """A response cut off at max_tokens is retried instead of stored as success."""
    with app.app_context():
        classifier = AdClassifier(config=test_config, db_session=db.session)
        model_call = _persisted_model_call(test_config)
        # Parseable content: only finish_reason marks it as cut off.
        truncated = _completion('{"ad_segments": []}', "length")

        with (
            patch("time.sleep"),
            patch(
                "litellm.completion",
                side_effect=[truncated, _completion(VALID_RESPONSE)],
            ) as mocked_completion,
        ):
            response = classifier._call_model(
                model_call_obj=model_call, system_prompt="test system prompt"
            )

        assert response == VALID_RESPONSE
        assert mocked_completion.call_count == 2
        db.session.expire_all()
        refreshed = db.session.get(ModelCall, model_call.id)
        assert refreshed is not None
        assert refreshed.status == "success"
        assert refreshed.response == VALID_RESPONSE


@pytest.mark.parametrize(
    "content",
    ["no json here", '{"ad_segments": "invalid"}'],
    ids=["no_json", "schema_invalid"],
)
def test_call_model_unparseable_response_exhausts_retries(
    test_config: Config, app: Flask, content: str
) -> None:
    """Unparseable output never becomes a successful (empty) classification."""
    with app.app_context():
        classifier = AdClassifier(config=test_config, db_session=db.session)
        model_call = _persisted_model_call(test_config)

        with (
            patch("time.sleep"),
            patch(
                "litellm.completion", return_value=_completion(content)
            ) as mocked_completion,
            pytest.raises(InvalidModelOutputError),
        ):
            classifier._call_model(
                model_call_obj=model_call,
                system_prompt="test system prompt",
                max_retries=2,
            )

        assert mocked_completion.call_count == 2
        db.session.expire_all()
        refreshed = db.session.get(ModelCall, model_call.id)
        assert refreshed is not None
        assert refreshed.status == "failed_retries"
        assert refreshed.response is None


def test_call_model_retries_response_without_content(
    test_config: Config, app: Flask
) -> None:
    """A response without content is retried instead of failing permanently."""
    with app.app_context():
        classifier = AdClassifier(config=test_config, db_session=db.session)
        model_call = _persisted_model_call(test_config)
        empty = _completion(VALID_RESPONSE)
        empty.choices[0].message.content = None

        with (
            patch("time.sleep"),
            patch(
                "litellm.completion", side_effect=[empty, _completion(VALID_RESPONSE)]
            ) as mocked_completion,
        ):
            response = classifier._call_model(
                model_call_obj=model_call, system_prompt="test system prompt"
            )

        assert response == VALID_RESPONSE
        assert mocked_completion.call_count == 2


def _single_segment() -> list[TranscriptSegment]:
    return [
        TranscriptSegment(
            id=1,
            post_id=1,
            sequence_num=0,
            start_time=0.0,
            end_time=10.0,
            text="Test segment 1",
        )
    ]


@pytest.mark.parametrize(
    "model_call",
    [
        ModelCall(id=7, post_id=1, status="failed_retries"),
        # Stored as success before responses were validated
        ModelCall(id=7, post_id=1, status="success", response="no json here"),
        ModelCall(
            id=7, post_id=1, status="success", response='{"ad_segments": "invalid"}'
        ),
        ModelCall(id=7, post_id=1, status="success", response=""),
    ],
    ids=[
        "failed_call",
        "stored_unparseable_success",
        "stored_schema_invalid_success",
        "stored_empty_success",
    ],
)
def test_classify_fails_when_a_chunk_has_no_usable_response(
    test_config: Config, app: Flask, model_call: ModelCall
) -> None:
    """A chunk without a usable answer must fail classification, not pass as ad-free."""
    with app.app_context():
        classifier = AdClassifier(config=test_config, db_session=db.session)
        post = Post(id=1, title="Test Post")
        segments = _single_segment()

        with (
            patch.object(
                classifier, "_get_or_create_model_call", return_value=model_call
            ),
            patch.object(classifier, "_perform_llm_call"),
            pytest.raises(ClassificationIncompleteError, match=r"\[7\]"),
        ):
            classifier.classify(
                transcript_segments=segments,
                system_prompt="test system prompt",
                user_prompt_template=Template("{{ podcast_title }}"),
                post=post,
            )


def test_classify_reports_only_the_failed_chunk(app: Flask) -> None:
    """With one good and one failed chunk, only the failed one is reported."""
    config = create_standard_test_config(
        num_segments_to_input_to_prompt=1, max_overlap_segments=0
    )
    with app.app_context():
        classifier = AdClassifier(config=config, db_session=db.session)
        post = Post(id=1, title="Test Post")
        segments = [
            TranscriptSegment(
                id=seq + 1,
                post_id=1,
                sequence_num=seq,
                start_time=seq * 10.0,
                end_time=seq * 10.0 + 10.0,
                text=f"Test segment {seq}",
            )
            for seq in range(2)
        ]
        calls = {
            0: ModelCall(
                id=5, post_id=1, status="success", response='{"ad_segments": []}'
            ),
            1: ModelCall(id=6, post_id=1, status="failed_retries"),
        }

        def model_call_for(**kwargs: object) -> ModelCall:
            return calls[cast(int, kwargs["first_seq_num"])]

        with (
            patch.object(
                classifier, "_get_or_create_model_call", side_effect=model_call_for
            ),
            patch.object(classifier, "_perform_llm_call"),
            pytest.raises(ClassificationIncompleteError, match=r"1 chunk.*\[6\]"),
        ):
            classifier.classify(
                transcript_segments=segments,
                system_prompt="test system prompt",
                user_prompt_template=Template("{{ podcast_title }}"),
                post=post,
            )


def test_classify_accepts_valid_empty_result(test_config: Config, app: Flask) -> None:
    """A valid answer without ads is a successful classification, not a failure."""
    with app.app_context():
        classifier = AdClassifier(config=test_config, db_session=db.session)
        no_ads = ModelCall(
            id=5, post_id=1, status="success", response='{"ad_segments": []}'
        )

        with (
            patch.object(classifier, "_get_or_create_model_call", return_value=no_ads),
            patch.object(classifier, "_perform_llm_call"),
        ):
            # Must not raise ClassificationIncompleteError
            classifier.classify(
                transcript_segments=_single_segment(),
                system_prompt="test system prompt",
                user_prompt_template=Template("{{ podcast_title }}"),
                post=Post(id=1, title="Test Post"),
            )


def test_call_model_does_not_retry_filtered_response(
    test_config: Config, app: Flask
) -> None:
    """A content-filtered answer fails permanently instead of passing or retrying."""
    with app.app_context():
        classifier = AdClassifier(config=test_config, db_session=db.session)
        model_call = _persisted_model_call(test_config)

        with (
            patch("time.sleep"),
            patch(
                "litellm.completion",
                return_value=_completion('{"ad_segments": []}', "content_filter"),
            ) as mocked_completion,
            pytest.raises(RuntimeError, match="content_filter"),
        ):
            classifier._call_model(
                model_call_obj=model_call, system_prompt="test system prompt"
            )

        assert mocked_completion.call_count == 1
        db.session.expire_all()
        refreshed = db.session.get(ModelCall, model_call.id)
        assert refreshed is not None
        assert refreshed.status == "failed_permanent"


def test_invalid_output_quoting_429_uses_normal_backoff(
    test_config: Config, app: Flask
) -> None:
    """Model text in an invalid answer must not trigger the rate-limit backoff."""
    with app.app_context():
        classifier = AdClassifier(config=test_config, db_session=db.session)
        model_call = _persisted_model_call(test_config)

        with (
            patch("time.sleep") as mocked_sleep,
            patch(
                "litellm.completion",
                side_effect=[
                    _completion("error 429: rate limit"),
                    _completion(VALID_RESPONSE),
                ],
            ),
        ):
            classifier._call_model(
                model_call_obj=model_call, system_prompt="test system prompt"
            )

        mocked_sleep.assert_called_once_with(1)


def test_process_chunk(test_config: Config, app: Flask) -> None:
    """Test processing a chunk of transcript segments"""
    with app.app_context():
        # Create mocks
        mock_db_session = MagicMock()
        mock_model_call_query = MagicMock()

        # Create the classifier with our mocks
        classifier = AdClassifier(
            config=test_config,
            model_call_query=mock_model_call_query,
            db_session=mock_db_session,
        )

        # Create test data
        post = Post(id=1, title="Test Post")
        segments = [
            TranscriptSegment(
                id=1,
                post_id=1,
                sequence_num=0,
                start_time=0.0,
                end_time=10.0,
                text="Test segment 1",
            ),
            TranscriptSegment(
                id=2,
                post_id=1,
                sequence_num=1,
                start_time=10.0,
                end_time=20.0,
                text="Test segment 2",
            ),
        ]

        # Create a proper Jinja2 Template object
        user_template = Template("Test template: {{ podcast_title }}")

        user_prompt = classifier._generate_user_prompt(
            current_chunk_db_segments=segments,
            post=post,
            user_prompt_template=user_template,
            includes_start=True,
            includes_end=True,
        )

        # Create an actual ModelCall instance instead of a MagicMock
        model_call = ModelCall(
            post_id=1,
            model_name=test_config.llm_model,
            prompt="test prompt",
            first_segment_sequence_num=0,
            last_segment_sequence_num=1,
            status="success",
            response='{"ad_segments": []}',
        )

        # Use patch.multiple to mock multiple methods with a single context manager
        mock_get_model_call = MagicMock(return_value=model_call)
        mock_process_response = MagicMock(return_value=segments)

        with patch.multiple(
            classifier,
            _get_or_create_model_call=mock_get_model_call,
            _process_successful_response=mock_process_response,
        ):
            result = classifier._process_chunk(
                chunk_segments=segments,
                system_prompt="test system prompt",
                post=post,
                user_prompt_str=user_prompt,
            )

            mock_get_model_call.assert_called_once()
            mock_process_response.assert_called_once()
            assert result == segments


def test_compute_next_overlap_segments_includes_context(
    test_classifier_with_mocks: AdClassifier,
) -> None:
    classifier = test_classifier_with_mocks
    segments = [
        TranscriptSegment(
            id=i + 1,
            post_id=1,
            sequence_num=i,
            start_time=float(i),
            end_time=float(i + 1),
            text=f"Segment {i}",
        )
        for i in range(6)
    ]

    identified_segments = [segments[2], segments[3], segments[4]]

    result = classifier._compute_next_overlap_segments(
        chunk_segments=segments,
        identified_segments=identified_segments,
        max_overlap_segments=6,
    )

    assert [seg.sequence_num for seg in result] == [0, 1, 2, 3, 4, 5]


def test_compute_next_overlap_segments_respects_cap(
    test_classifier_with_mocks: AdClassifier,
) -> None:
    classifier = test_classifier_with_mocks
    segments = [
        TranscriptSegment(
            id=i + 1,
            post_id=1,
            sequence_num=i,
            start_time=float(i),
            end_time=float(i + 1),
            text=f"Segment {i}",
        )
        for i in range(6)
    ]
    identified_segments = [segments[2], segments[3], segments[4]]

    result = classifier._compute_next_overlap_segments(
        chunk_segments=segments,
        identified_segments=identified_segments,
        max_overlap_segments=2,
    )

    assert [seg.sequence_num for seg in result] == [4, 5]


def test_compute_next_overlap_segments_baseline_overlap_without_ads(
    test_classifier_with_mocks: AdClassifier,
) -> None:
    classifier = test_classifier_with_mocks
    segments = [
        TranscriptSegment(
            id=i + 1,
            post_id=1,
            sequence_num=i,
            start_time=float(i),
            end_time=float(i + 1),
            text=f"Segment {i}",
        )
        for i in range(8)
    ]

    result = classifier._compute_next_overlap_segments(
        chunk_segments=segments, identified_segments=[], max_overlap_segments=4
    )

    assert [seg.sequence_num for seg in result] == [4, 5, 6, 7]


def test_create_identifications_skips_existing_ad_label(
    test_classifier_with_mocks: AdClassifier,
) -> None:
    classifier = test_classifier_with_mocks
    mock_query = classifier.identification_query
    mock_query.filter_by.return_value.first.return_value = MagicMock()

    segment = TranscriptSegment(
        id=1,
        post_id=1,
        sequence_num=0,
        start_time=0.0,
        end_time=10.0,
        text="Test segment",
    )
    prediction_list = AdSegmentPredictionList(
        ad_segments=[AdSegmentPrediction(segment_offset=0.0, confidence=0.9)]
    )
    model_call = ModelCall(
        post_id=1,
        model_name=classifier.config.llm_model,
        prompt="prompt",
        first_segment_sequence_num=0,
        last_segment_sequence_num=0,
    )

    created_count, matched_segments = classifier._create_identifications(
        prediction_list=prediction_list,
        current_chunk_db_segments=[segment],
        model_call=model_call,
    )

    assert created_count == 0
    assert matched_segments == [segment]
    cast(MagicMock, classifier.db_session.add).assert_not_called()


def test_build_chunk_payload_trims_for_token_limit(
    test_classifier_with_mocks: AdClassifier,
) -> None:
    classifier = test_classifier_with_mocks
    classifier.config.processing.num_segments_to_input_to_prompt = 3
    classifier.config.processing.max_overlap_segments = 5
    classifier.config.llm_max_input_tokens_per_call = 1000

    overlap_segments = [
        TranscriptSegment(
            id=1,
            post_id=1,
            sequence_num=0,
            start_time=0.0,
            end_time=1.0,
            text="Overlap",
        )
    ]
    remaining_segments = [
        TranscriptSegment(
            id=i + 2,
            post_id=1,
            sequence_num=i + 1,
            start_time=float(i + 1),
            end_time=float(i + 2),
            text=f"Segment {i + 1}",
        )
        for i in range(3)
    ]

    system_prompt = "System"
    template = Template("{{ transcript }}")

    with patch.object(
        classifier,
        "_validate_token_limit",
        side_effect=[False, True],
    ) as mock_validator:
        chunk_segments, user_prompt, consumed, trimmed = (
            classifier._build_chunk_payload(
                overlap_segments=overlap_segments,
                remaining_segments=remaining_segments,
                total_segments=overlap_segments + remaining_segments,
                post=Post(id=1, title="Test"),
                system_prompt=system_prompt,
                user_prompt_template=template,
                max_new_segments=3,
            )
        )

    assert trimmed is True
    assert consumed == 2
    assert len(chunk_segments) >= consumed
    assert mock_validator.call_count == 2
    assert user_prompt
