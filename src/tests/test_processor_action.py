"""Focused tests for replace_transcription_action's cache invalidation."""

from app.extensions import db
from app.models import Feed, ModelCall, Post
from app.writer.actions.processor import replace_transcription_action


def _make_post(app, *, guid="guid-1"):
    feed = Feed(title="T", rss_url=f"http://example.com/{guid}.rss")
    post = Post(
        feed=feed,
        guid=guid,
        download_url=f"http://example.com/{guid}.mp3",
        title=guid,
        unprocessed_audio_path=f"/tmp/{guid}.mp3",
    )
    db.session.add_all([feed, post])
    db.session.commit()
    return post


def test_replace_transcription_supersedes_sibling_whisper_calls(app):
    """A finished whisper run in one language marks prior-language whisper rows superseded."""
    with app.app_context():
        post = _make_post(app, guid="supersede")

        en_call = ModelCall(
            post_id=post.id,
            model_name="whisper-1",
            first_segment_sequence_num=0,
            last_segment_sequence_num=0,
            prompt="x",
            language="en",
            status="success",
        )
        de_call = ModelCall(
            post_id=post.id,
            model_name="whisper-1",
            first_segment_sequence_num=0,
            last_segment_sequence_num=-1,
            prompt="x",
            language="de",
            status="pending",
        )
        db.session.add_all([en_call, de_call])
        db.session.commit()

        replace_transcription_action(
            {
                "post_id": post.id,
                "segments": [
                    {
                        "sequence_num": 0,
                        "start_time": 0.0,
                        "end_time": 1.0,
                        "text": "Hallo",
                    }
                ],
                "model_call_id": de_call.id,
            }
        )
        db.session.commit()

        db.session.refresh(en_call)
        db.session.refresh(de_call)
        assert en_call.status == "superseded"
        assert de_call.status == "success"


def test_replace_transcription_deletes_llm_when_supersede_fires(app):
    """A real language change supersedes a sibling whisper row AND wipes LLM caches."""
    with app.app_context():
        post = _make_post(app, guid="llm-clear")

        prior_whisper = ModelCall(
            post_id=post.id,
            model_name="whisper-1",
            first_segment_sequence_num=0,
            last_segment_sequence_num=0,
            prompt="x",
            language="en",
            status="success",
        )
        llm_call = ModelCall(
            post_id=post.id,
            model_name="gpt-5-mini",
            first_segment_sequence_num=0,
            last_segment_sequence_num=29,
            prompt="ad classifier prompt built from English transcript",
            response="prior response",
            language=None,
            status="success",
        )
        new_whisper = ModelCall(
            post_id=post.id,
            model_name="whisper-1",
            first_segment_sequence_num=0,
            last_segment_sequence_num=-1,
            prompt="Whisper transcription job",
            language="de",
            status="pending",
        )
        db.session.add_all([prior_whisper, llm_call, new_whisper])
        db.session.commit()
        llm_id = llm_call.id

        replace_transcription_action(
            {
                "post_id": post.id,
                "segments": [
                    {
                        "sequence_num": 0,
                        "start_time": 0.0,
                        "end_time": 1.0,
                        "text": "neu",
                    }
                ],
                "model_call_id": new_whisper.id,
            }
        )
        db.session.commit()

        # Language actually changed: LLM cache is invalidated.
        assert db.session.get(ModelCall, llm_id) is None
        db.session.refresh(prior_whisper)
        assert prior_whisper.status == "superseded"


def test_replace_transcription_preserves_llm_when_no_sibling_to_supersede(app):
    """First post-migration transcription: legacy whisper row has language=NULL,
    so the supersede filter matches zero rows. We must NOT delete the LLM
    cache in this case — otherwise every previously-processed post pays an
    LLM re-classification cost on the first run after upgrade."""
    with app.app_context():
        post = _make_post(app, guid="legacy-llm")

        # Legacy whisper row from before the language column existed.
        legacy_whisper = ModelCall(
            post_id=post.id,
            model_name="whisper-1",
            first_segment_sequence_num=0,
            last_segment_sequence_num=0,
            prompt="x",
            language=None,
            status="success",
        )
        # Existing LLM ad-classifier cache — built against the legacy
        # transcript text but still useful for the current segments.
        llm_call = ModelCall(
            post_id=post.id,
            model_name="gpt-5-mini",
            first_segment_sequence_num=0,
            last_segment_sequence_num=29,
            prompt="ad classifier prompt",
            response="cached classification",
            language=None,
            status="success",
        )
        new_whisper = ModelCall(
            post_id=post.id,
            model_name="whisper-1",
            first_segment_sequence_num=0,
            last_segment_sequence_num=-1,
            prompt="Whisper transcription job",
            language="en",
            status="pending",
        )
        db.session.add_all([legacy_whisper, llm_call, new_whisper])
        db.session.commit()
        llm_id = llm_call.id

        replace_transcription_action(
            {
                "post_id": post.id,
                "segments": [
                    {
                        "sequence_num": 0,
                        "start_time": 0.0,
                        "end_time": 1.0,
                        "text": "hi",
                    }
                ],
                "model_call_id": new_whisper.id,
            }
        )
        db.session.commit()

        # Legacy NULL-language whisper isn't matched by the supersede filter
        # (which requires language IS NOT NULL), so the supersede count is 0
        # and the LLM cache survives untouched.
        assert db.session.get(ModelCall, llm_id) is not None
        db.session.refresh(llm_call)
        assert llm_call.status == "success"
