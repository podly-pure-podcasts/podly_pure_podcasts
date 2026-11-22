"""ModelCall rows are keyed by call type as well as segment range (#271)."""

import logging
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from app.extensions import db
from app.models import ModelCall
from app.writer.actions.processor import (
    upsert_model_call_action,
    upsert_whisper_model_call_action,
)
from podcast_processor.boundary_refiner import BoundaryRefiner
from podcast_processor.llm_model_call_utils import try_upsert_model_call
from shared import model_call_types
from shared.test_utils import create_standard_test_config

CLASSIFICATION_RESPONSE = (
    '{"ad_segments": [{"segment_offset": 10.0, "confidence": 0.9}]}'
)
REFINEMENT_RESPONSE = (
    '{"refined_start": 10.0, "refined_end": 20.0, "start_reason": "", "end_reason": ""}'
)


def _upsert(
    post_id: int, call_type: str | None, *, first: int = 3, last: int = 5
) -> int:
    params = {
        "post_id": post_id,
        "model_name": "test-model",
        "first_segment_sequence_num": first,
        "last_segment_sequence_num": last,
        "prompt": f"{call_type} prompt",
    }
    if call_type is not None:
        params["call_type"] = call_type
    return int(upsert_model_call_action(params)["model_call_id"])


def test_refinement_does_not_overwrite_classification_call(app: Flask) -> None:
    """The reproduction from #271: an ad block spanning exactly one chunk."""
    config = create_standard_test_config()
    with app.app_context():
        classification = ModelCall(
            post_id=1,
            model_name=config.llm_model,
            prompt="classification prompt",
            first_segment_sequence_num=3,
            last_segment_sequence_num=5,
            status="success",
            response=CLASSIFICATION_RESPONSE,
        )
        db.session.add(classification)
        db.session.commit()

        choice = MagicMock()
        choice.message.content = REFINEMENT_RESPONSE
        completion = MagicMock()
        completion.choices = [choice]
        segments = [
            {
                "sequence_num": n,
                "start_time": n * 5.0,
                "end_time": n * 5.0 + 5.0,
                "text": "x",
            }
            for n in range(8)
        ]

        with patch("litellm.completion", return_value=completion):
            BoundaryRefiner(config).refine(
                10.0, 30.0, 0.9, segments, post_id=1, first_seq_num=3, last_seq_num=5
            )

        db.session.expire_all()
        stored = db.session.get(ModelCall, classification.id)
        assert stored is not None
        assert stored.response == CLASSIFICATION_RESPONSE
        assert stored.status == "success"
        assert stored.call_type == model_call_types.CLASSIFICATION

        refinement = (
            db.session.query(ModelCall)
            .filter_by(post_id=1, call_type=model_call_types.BOUNDARY_REFINEMENT)
            .one()
        )
        assert refinement.id != classification.id
        assert (
            refinement.first_segment_sequence_num,
            refinement.last_segment_sequence_num,
        ) == (3, 5)
        assert refinement.response == REFINEMENT_RESPONSE


def test_each_call_type_gets_its_own_row_for_the_same_range(app: Flask) -> None:
    with app.app_context():
        ids = {
            call_type: _upsert(1, call_type)
            for call_type in sorted(model_call_types.LLM_CALL_TYPES)
        }
        db.session.commit()

        assert len(set(ids.values())) == len(model_call_types.LLM_CALL_TYPES)
        for call_type, model_call_id in ids.items():
            row = db.session.get(ModelCall, model_call_id)
            assert row is not None
            assert row.call_type == call_type


def test_same_call_type_reuses_its_row(app: Flask) -> None:
    with app.app_context():
        first = _upsert(1, model_call_types.WORD_BOUNDARY_REFINEMENT)
        db.session.commit()
        second = _upsert(1, model_call_types.WORD_BOUNDARY_REFINEMENT)
        db.session.commit()

        assert first == second
        assert db.session.query(ModelCall).count() == 1


def test_call_type_defaults_to_classification(app: Flask) -> None:
    with app.app_context():
        explicit = _upsert(1, model_call_types.CLASSIFICATION)
        db.session.commit()
        default = _upsert(1, None)
        db.session.commit()

        assert explicit == default


@pytest.mark.parametrize("call_type", ["", "bogus", model_call_types.TRANSCRIPTION])
def test_unsupported_call_type_is_rejected(app: Flask, call_type: str) -> None:
    with app.app_context():
        with pytest.raises(ValueError, match="call_type"):
            _upsert(1, call_type)


def test_whisper_rows_are_labelled_transcription(app: Flask) -> None:
    with app.app_context():
        result = upsert_whisper_model_call_action(
            {"post_id": 1, "model_name": "whisper-1", "language": "en"}
        )
        db.session.commit()

        row = db.session.get(ModelCall, int(result["model_call_id"]))
        assert row is not None
        assert row.call_type == model_call_types.TRANSCRIPTION


def test_try_upsert_model_call_sends_call_type() -> None:
    result = MagicMock(success=True, data={"model_call_id": 7})
    with patch(
        "podcast_processor.llm_model_call_utils.writer_client.action",
        return_value=result,
    ) as action:
        model_call_id = try_upsert_model_call(
            post_id=1,
            first_seq_num=3,
            last_seq_num=5,
            model_name="test-model",
            prompt="prompt",
            call_type=model_call_types.WORD_BOUNDARY_REFINEMENT,
            logger=logging.getLogger(__name__),
            log_prefix="test",
        )

    assert model_call_id == 7
    assert (
        action.call_args.args[1]["call_type"]
        == model_call_types.WORD_BOUNDARY_REFINEMENT
    )
