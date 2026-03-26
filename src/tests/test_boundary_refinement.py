from __future__ import annotations

from unittest.mock import MagicMock, patch

from litellm.types.utils import Choices

from app.extensions import db
from app.models import Feed, Identification, ModelCall, Post, TranscriptSegment
from app.routes.post_routes import post_bp
from podcast_processor.ad_classifier import AdClassifier
from podcast_processor.audio_processor import AudioProcessor
from shared.test_utils import create_standard_test_config


def _mock_completion_response(content: str) -> MagicMock:
    message = MagicMock()
    message.content = content

    choice = MagicMock(spec=Choices)
    choice.message = message

    response = MagicMock()
    response.choices = [choice]
    return response


def test_audio_processor_prefers_refined_boundaries() -> None:
    processor = AudioProcessor(
        config=create_standard_test_config(enable_boundary_refinement=True),
        identification_query=MagicMock(),
        transcript_segment_query=MagicMock(),
        model_call_query=MagicMock(),
        db_session=MagicMock(),
    )
    post = Post(
        id=1,
        guid="episode-guid",
        title="Episode",
        refined_ad_boundaries=[
            {"refined_start": 12.5, "refined_end": 18.75},
            {"refined_start": 42.0, "refined_end": 48.0},
        ],
    )

    segments = processor.get_ad_segments(post)

    assert segments == [(12.5, 18.75), (42.0, 48.0)]


def test_ad_classifier_persists_refined_boundaries(app) -> None:
    with app.app_context():
        feed = Feed(title="Test Feed", rss_url="https://example.com/feed.xml")
        db.session.add(feed)
        db.session.commit()

        post = Post(
            feed_id=feed.id,
            guid="episode-1",
            download_url="https://example.com/audio.mp3",
            title="Episode 1",
        )
        db.session.add(post)
        db.session.commit()

        segments = [
            TranscriptSegment(
                post_id=post.id,
                sequence_num=0,
                start_time=0.0,
                end_time=5.0,
                text="Welcome back to the show.",
            ),
            TranscriptSegment(
                post_id=post.id,
                sequence_num=1,
                start_time=5.0,
                end_time=10.0,
                text="This episode is brought to you by Acme Cloud Hosting.",
            ),
            TranscriptSegment(
                post_id=post.id,
                sequence_num=2,
                start_time=10.0,
                end_time=15.0,
                text="Visit Acme dot com and use code podly today.",
            ),
            TranscriptSegment(
                post_id=post.id,
                sequence_num=3,
                start_time=15.0,
                end_time=20.0,
                text="Now back to the interview.",
            ),
        ]
        db.session.add_all(segments)
        db.session.commit()

        base_model_call = ModelCall(
            post_id=post.id,
            first_segment_sequence_num=1,
            last_segment_sequence_num=2,
            model_name="groq/openai/gpt-oss-120b",
            prompt="classify",
            response='{"ad_segments": []}',
            status="success",
        )
        db.session.add(base_model_call)
        db.session.commit()

        db.session.add_all(
            [
                Identification(
                    transcript_segment_id=segments[1].id,
                    model_call_id=base_model_call.id,
                    label="ad",
                    confidence=0.91,
                ),
                Identification(
                    transcript_segment_id=segments[2].id,
                    model_call_id=base_model_call.id,
                    label="ad",
                    confidence=0.88,
                ),
            ]
        )
        db.session.commit()

        classifier = AdClassifier(
            config=create_standard_test_config(
                enable_boundary_refinement=True,
                enable_word_level_boundary_refiner=True,
            )
        )

        boundary_response = _mock_completion_response("""{
              "refined_start": 5.0,
              "refined_end": 15.0,
              "start_adjustment_reason": "kept sponsor intro",
              "end_adjustment_reason": "kept sponsor wrap",
              "confidence_adjustment": 0.0
            }""")
        word_response = _mock_completion_response("""{
              "refined_start_segment_seq": 1,
              "refined_start_phrase": "this episode is brought",
              "refined_end_segment_seq": 2,
              "refined_end_phrase": "use code podly today",
              "start_adjustment_reason": "phrase matched",
              "end_adjustment_reason": "phrase matched"
            }""")

        with patch(
            "litellm.completion", side_effect=[boundary_response, word_response]
        ):
            classifier._refine_ad_boundaries(post, segments)

        db.session.refresh(post)
        assert post.refined_ad_boundaries is not None
        assert len(post.refined_ad_boundaries) == 1

        refined = post.refined_ad_boundaries[0]
        assert refined["orig_start"] == 5.0
        assert refined["orig_end"] == 15.0
        assert refined["refined_start"] == 5.0
        assert refined["refined_end"] > 13.0
        assert refined["refined_by"] == "word"

        refinement_calls = ModelCall.query.filter_by(
            model_name="groq/openai/gpt-oss-120b::boundary-refinement"
        ).all()
        assert len(refinement_calls) == 1
        word_calls = ModelCall.query.filter_by(
            model_name="groq/openai/gpt-oss-120b::word-boundary-refinement"
        ).all()
        assert len(word_calls) == 1


def test_post_stats_marks_mixed_segments_when_refined_window_splits_segment(
    app,
) -> None:
    app.register_blueprint(post_bp)

    with app.app_context():
        feed = Feed(title="Stats Feed", rss_url="https://example.com/stats.xml")
        db.session.add(feed)
        db.session.commit()

        post = Post(
            feed_id=feed.id,
            guid="episode-stats",
            download_url="https://example.com/stats.mp3",
            title="Episode Stats",
            refined_ad_boundaries=[
                {
                    "orig_start": 5.0,
                    "orig_end": 15.0,
                    "refined_start": 6.5,
                    "refined_end": 14.0,
                    "first_seq_num": 1,
                    "last_seq_num": 2,
                    "confidence": 0.9,
                    "start_adjustment_reason": "trimmed intro",
                    "end_adjustment_reason": "trimmed outro",
                    "refined_by": "word",
                }
            ],
        )
        db.session.add(post)
        db.session.commit()

        segments = [
            TranscriptSegment(
                post_id=post.id,
                sequence_num=0,
                start_time=0.0,
                end_time=5.0,
                text="Show intro.",
            ),
            TranscriptSegment(
                post_id=post.id,
                sequence_num=1,
                start_time=5.0,
                end_time=10.0,
                text="Sponsored by Acme.",
            ),
            TranscriptSegment(
                post_id=post.id,
                sequence_num=2,
                start_time=10.0,
                end_time=15.0,
                text="Use code PODLY today.",
            ),
        ]
        db.session.add_all(segments)
        db.session.commit()

        model_call = ModelCall(
            post_id=post.id,
            first_segment_sequence_num=1,
            last_segment_sequence_num=2,
            model_name="groq/openai/gpt-oss-120b",
            prompt="classify",
            response='{"ad_segments": []}',
            status="success",
        )
        db.session.add(model_call)
        db.session.commit()

        db.session.add_all(
            [
                Identification(
                    transcript_segment_id=segments[1].id,
                    model_call_id=model_call.id,
                    label="ad",
                    confidence=0.91,
                ),
                Identification(
                    transcript_segment_id=segments[2].id,
                    model_call_id=model_call.id,
                    label="ad",
                    confidence=0.88,
                ),
            ]
        )
        db.session.commit()

    client = app.test_client()
    response = client.get("/api/posts/episode-stats/stats")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["processing_stats"]["boundary_refinement_count"] == 1

    transcript_by_seq = {
        item["sequence_num"]: item for item in payload["transcript_segments"]
    }
    assert transcript_by_seq[1]["mixed"] is True
    assert transcript_by_seq[2]["mixed"] is True

    mixed_identifications = [
        item for item in payload["identifications"] if item["label"] == "ad"
    ]
    assert mixed_identifications
    assert all(item["mixed"] is True for item in mixed_identifications)
