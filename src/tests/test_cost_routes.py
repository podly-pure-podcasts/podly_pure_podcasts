from datetime import datetime
from typing import Any

import pytest

from app.extensions import db
from app.model_call_token_backfill import backfill_model_call_token_usage
from app.models import (
    Feed,
    Identification,
    ModelCall,
    Post,
    ProcessingJob,
    TranscriptSegment,
    User,
    UserFeed,
)
from app.routes import cost_routes
from app.routes.cost_routes import _model_call_cost, costs_bp


def test_admin_costs_uses_persisted_llm_cost_and_configured_audio_rates(
    app: Any, monkeypatch: Any
) -> None:
    app.register_blueprint(costs_bp)
    monkeypatch.setattr(cost_routes, "require_admin", lambda _action: (None, None))
    monkeypatch.setattr(
        cost_routes,
        "read_combined",
        lambda: {
            "app": {
                "cost_rate_per_hour": 0.04,
                "whisper_cost_rate_per_hour": 0.04,
            }
        },
    )

    with app.app_context():
        feed = Feed(title="Cost Feed", rss_url="https://example.com/feed.xml")
        user_a = User(username="a", password_hash="x", role="user")
        user_b = User(username="b", password_hash="x", role="user")
        db.session.add_all([feed, user_a, user_b])
        db.session.flush()
        db.session.add_all(
            [
                UserFeed(feed_id=feed.id, user_id=user_a.id),
                UserFeed(feed_id=feed.id, user_id=user_b.id),
            ]
        )
        post = Post(
            feed_id=feed.id,
            guid="cost-guid",
            download_url="https://example.com/audio.mp3",
            title="Cost Episode",
            duration=3600,
        )
        db.session.add(post)
        db.session.flush()
        db.session.add(
            ProcessingJob(
                post_guid=post.guid,
                status="completed",
                completed_at=datetime(2026, 5, 15, 12, 0, 0),
            )
        )
        db.session.add_all(
            [
                ModelCall(
                    post_id=post.id,
                    first_segment_sequence_num=0,
                    last_segment_sequence_num=1,
                    model_name="gpt-4o-mini",
                    prompt="classify",
                    status="success",
                    prompt_tokens=1_000_000,
                    cached_prompt_tokens=500_000,
                    completion_tokens=250_000,
                    total_tokens=1_250_000,
                    estimated_cost_usd=0.2625,
                ),
                ModelCall(
                    post_id=post.id,
                    first_segment_sequence_num=0,
                    last_segment_sequence_num=-1,
                    model_name="whisper-large-v3-turbo",
                    prompt="Whisper transcription job",
                    status="success",
                ),
            ]
        )
        db.session.commit()

        response = app.test_client().get("/api/admin/costs?year=2026&month=5")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["total_llm_cost"] == 0.2625
    assert payload["total_whisper_cost"] == 0.04
    assert payload["total_cost"] == 0.3025
    assert payload["feeds"][0]["llm_cost"] == 0.2625
    assert payload["feeds"][0]["whisper_cost"] == 0.04
    assert payload["users"][0]["monthly_cost"] == 0.1512
    assert payload["users"][1]["monthly_cost"] == 0.1512


def test_admin_costs_skips_whisper_when_no_matching_model_calls(
    app: Any, monkeypatch: Any
) -> None:
    app.register_blueprint(costs_bp)
    monkeypatch.setattr(cost_routes, "require_admin", lambda _action: (None, None))
    monkeypatch.setattr(
        cost_routes,
        "read_combined",
        lambda: {
            "app": {
                "cost_rate_per_hour": 0.04,
                "whisper_cost_rate_per_hour": 0.04,
            }
        },
    )

    with app.app_context():
        feed = Feed(title="No Audio Feed", rss_url="https://example.com/feed.xml")
        user = User(username="solo", password_hash="x", role="user")
        db.session.add_all([feed, user])
        db.session.flush()
        db.session.add(UserFeed(feed_id=feed.id, user_id=user.id))
        post = Post(
            feed_id=feed.id,
            guid="no-audio-guid",
            download_url="https://example.com/audio.mp3",
            title="No Audio Episode",
            duration=3600,
        )
        db.session.add(post)
        db.session.flush()
        db.session.add(
            ProcessingJob(
                post_guid=post.guid,
                status="completed",
                completed_at=datetime(2026, 5, 15, 12, 0, 0),
            )
        )
        # Only an LLM call — no Whisper.
        db.session.add(
            ModelCall(
                post_id=post.id,
                first_segment_sequence_num=0,
                last_segment_sequence_num=1,
                model_name="gpt-4o-mini",
                prompt="classify",
                status="success",
                prompt_tokens=1_000_000,
                cached_prompt_tokens=500_000,
                completion_tokens=250_000,
                total_tokens=1_750_000,
            )
        )
        db.session.commit()

        response = app.test_client().get("/api/admin/costs?year=2026&month=5")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["total_whisper_cost"] == 0.0
    assert payload["feeds"][0]["whisper_cost"] == 0.0


def test_model_call_cost_prices_gemini_flex_at_half_base_rate(monkeypatch) -> None:
    import litellm

    # Pin the rate fixture: vendor pricing changes must not change this test
    # of the fallback discount and cached-token arithmetic.
    monkeypatch.setattr(
        litellm,
        "model_cost",
        {
            "gemini/gemini-3-flash-preview": {
                "input_cost_per_token": 0.50 / 1_000_000,
                "cache_read_input_token_cost": 0.05 / 1_000_000,
                "output_cost_per_token": 3.00 / 1_000_000,
            }
        },
    )
    call = ModelCall(
        model_name="gemini/gemini-3-flash-preview",
        service_tier="flex",
        prompt_tokens=1_000_000,
        cached_prompt_tokens=500_000,
        completion_tokens=250_000,
    )

    # With no explicit *_flex keys, apply the Flex 50% discount.
    assert _model_call_cost(call) == 0.5125


def test_model_call_cost_uses_openai_flex_rates_without_double_counting_cache(
    monkeypatch,
) -> None:
    import litellm

    monkeypatch.setattr(
        litellm,
        "model_cost",
        {
            "openai/gpt-5-mini": {
                "input_cost_per_token_flex": 0.125 / 1_000_000,
                "cache_read_input_token_cost_flex": 0.0125 / 1_000_000,
                "output_cost_per_token_flex": 1.0 / 1_000_000,
            }
        },
    )
    call = ModelCall(
        model_name="openai/gpt-5-mini",
        service_tier="flex",
        prompt_tokens=1_000_000,
        cached_prompt_tokens=500_000,
        completion_tokens=250_000,
    )

    # This fixture provides explicit Flex rates. OpenAI includes
    # cached tokens inside prompt_tokens, so only the uncached half gets the
    # regular Flex input rate.
    assert _model_call_cost(call) == 0.31875


def test_backfill_model_call_token_usage_dry_run_leaves_rows_unchanged(
    app: Any, monkeypatch: Any
) -> None:
    monkeypatch.setattr(
        "app.model_call_token_backfill._estimate_text_tokens",
        lambda _model_name, text: len(text.split()),
    )

    with app.app_context():
        feed = Feed(title="Backfill Feed", rss_url="https://example.com/feed.xml")
        db.session.add(feed)
        db.session.flush()
        post = Post(
            feed_id=feed.id,
            guid="backfill-dry-run",
            download_url="https://example.com/audio.mp3",
            title="Backfill Dry Run",
        )
        db.session.add(post)
        db.session.flush()
        model_call = ModelCall(
            post_id=post.id,
            first_segment_sequence_num=0,
            last_segment_sequence_num=1,
            model_name="gpt-4o-mini",
            prompt="one two three",
            response="four five",
            status="success",
        )
        db.session.add(model_call)
        db.session.commit()

        result = backfill_model_call_token_usage(apply=False)
        db.session.refresh(model_call)

    assert result["scanned"] == 1
    assert result["eligible"] == 1
    assert result["would_update"] == 1
    assert result["updated"] == 0
    assert model_call.prompt_tokens is None
    assert model_call.cached_prompt_tokens is None
    assert model_call.completion_tokens is None
    assert model_call.total_tokens is None


def test_backfill_model_call_token_usage_apply_updates_missing_tokens_only(
    app: Any, monkeypatch: Any
) -> None:
    monkeypatch.setattr(
        "app.model_call_token_backfill._estimate_text_tokens",
        lambda _model_name, text: len(text.split()),
    )

    with app.app_context():
        feed = Feed(title="Backfill Feed", rss_url="https://example.com/feed.xml")
        db.session.add(feed)
        db.session.flush()
        post = Post(
            feed_id=feed.id,
            guid="backfill-apply",
            download_url="https://example.com/audio.mp3",
            title="Backfill Apply",
        )
        db.session.add(post)
        db.session.flush()
        model_call = ModelCall(
            post_id=post.id,
            first_segment_sequence_num=0,
            last_segment_sequence_num=1,
            model_name="gpt-4o-mini",
            prompt="one two three",
            response="four five",
            status="success",
        )
        whisper_call = ModelCall(
            post_id=post.id,
            first_segment_sequence_num=0,
            last_segment_sequence_num=-1,
            model_name="whisper-large-v3-turbo",
            prompt="Whisper transcription job",
            response="transcript",
            status="success",
        )
        db.session.add_all([model_call, whisper_call])
        db.session.commit()

        result = backfill_model_call_token_usage(apply=True)
        db.session.refresh(model_call)
        db.session.refresh(whisper_call)

    assert result["scanned"] == 2
    assert result["eligible"] == 1
    assert result["would_update"] == 1
    assert result["updated"] == 1
    assert result["skipped_non_llm"] == 1
    assert model_call.prompt_tokens == 3
    assert model_call.cached_prompt_tokens is None
    assert model_call.completion_tokens == 2
    assert model_call.total_tokens == 5
    assert whisper_call.prompt_tokens is None


def test_backfill_token_usage_endpoint_validates_limit(
    app: Any, monkeypatch: Any
) -> None:
    app.register_blueprint(costs_bp)
    monkeypatch.setattr(cost_routes, "require_admin", lambda _action: (None, None))

    response = app.test_client().post(
        "/api/admin/costs/backfill-token-usage",
        json={"apply": False, "limit": 0},
    )

    assert response.status_code == 400


@pytest.mark.parametrize(
    ("duration", "ad_confidences"),
    [
        (3000, [0.95]),  # ads cut: processed length excludes them
        (3600, [0.2]),  # low-confidence ad was never cut
        (3000, [0.95, 0.9]),  # two model calls flagged the same segment
        (None, []),  # duration cleared after processing
    ],
)
def test_admin_costs_measure_original_length_from_transcript(
    app: Any, monkeypatch: Any, duration: int | None, ad_confidences: list[float]
) -> None:
    app.register_blueprint(costs_bp)
    monkeypatch.setattr(cost_routes, "require_admin", lambda _action: (None, None))
    monkeypatch.setattr(
        cost_routes,
        "read_combined",
        lambda: {"app": {"whisper_cost_rate_per_hour": 0.04}},
    )

    with app.app_context():
        feed = Feed(title="Cost Feed", rss_url="https://example.com/feed.xml")
        db.session.add(feed)
        db.session.flush()
        post = Post(
            feed_id=feed.id,
            guid="cost-guid",
            download_url="https://example.com/audio.mp3",
            title="Cost Episode",
            duration=duration,
        )
        db.session.add(post)
        db.session.flush()
        db.session.add(
            ProcessingJob(
                post_guid=post.guid,
                status="completed",
                completed_at=datetime(2026, 5, 15, 12, 0, 0),
            )
        )
        ad = TranscriptSegment(
            post_id=post.id, sequence_num=0, start_time=0, end_time=600, text="Ad"
        )
        content = TranscriptSegment(
            post_id=post.id, sequence_num=1, start_time=600, end_time=3600, text="Show"
        )
        whisper = ModelCall(
            post_id=post.id,
            first_segment_sequence_num=0,
            last_segment_sequence_num=-1,
            model_name="whisper-large-v3-turbo",
            prompt="Whisper transcription job",
            status="success",
        )
        db.session.add_all([ad, content, whisper])
        db.session.flush()
        for index, confidence in enumerate(ad_confidences):
            call = ModelCall(
                post_id=post.id,
                first_segment_sequence_num=0,
                last_segment_sequence_num=1,
                model_name=f"classifier-{index}",
                prompt="classify",
                status="success",
            )
            db.session.add(call)
            db.session.flush()
            db.session.add(
                Identification(
                    transcript_segment_id=ad.id,
                    model_call_id=call.id,
                    label="ad",
                    confidence=confidence,
                )
            )
        db.session.commit()

        response = app.test_client().get("/api/admin/costs?year=2026&month=5")

    payload = response.get_json()
    assert payload["total_audio_hours"] == 1.0
    assert payload["total_whisper_cost"] == 0.04


def test_admin_costs_reports_service_tier_and_cost_by_tier(
    app: Any, monkeypatch: Any
) -> None:
    app.register_blueprint(costs_bp)
    monkeypatch.setattr(cost_routes, "require_admin", lambda _action: (None, None))
    monkeypatch.setattr(
        cost_routes,
        "read_combined",
        lambda: {"app": {"whisper_cost_rate_per_hour": 0.0}},
    )
    monkeypatch.setattr(cost_routes.runtime_config, "llm_service_tier", "flex")

    with app.app_context():
        feed = Feed(title="Tier Feed", rss_url="https://example.com/feed.xml")
        db.session.add(feed)
        db.session.flush()
        post = Post(
            feed_id=feed.id,
            guid="tier-guid",
            download_url="https://example.com/audio.mp3",
            title="Tier Episode",
            duration=3600,
        )
        db.session.add(post)
        db.session.flush()
        db.session.add(
            ProcessingJob(
                post_guid=post.guid,
                status="completed",
                completed_at=datetime(2026, 5, 15, 12, 0, 0),
            )
        )
        db.session.add_all(
            [
                ModelCall(
                    post_id=post.id,
                    first_segment_sequence_num=index,
                    last_segment_sequence_num=index,
                    model_name="gpt-4o-mini",
                    prompt="classify",
                    status="success",
                    service_tier=tier,
                    estimated_cost_usd=0.25,
                )
                for index, tier in enumerate(["flex", "flex", None])
            ]
        )
        db.session.commit()

        response = app.test_client().get("/api/admin/costs?year=2026&month=5")

    payload = response.get_json()
    assert payload["llm_service_tier"] == "flex"
    assert payload["llm_cost_by_tier"] == {"default": 0.25, "flex": 0.5}
    assert payload["total_llm_cost"] == 0.75


def _add_billable_call(post_id: int, **overrides: Any) -> ModelCall:
    fields: dict[str, Any] = {
        "post_id": post_id,
        "first_segment_sequence_num": 0,
        "last_segment_sequence_num": 1,
        "model_name": "gpt-4o-mini",
        "prompt": "classify",
        "status": "success",
    }
    fields.update(overrides)
    call = ModelCall(**fields)
    db.session.add(call)
    return call


def _seed_post(guid: str, duration: int = 3600) -> Post:
    feed = Feed(title=f"Feed {guid}", rss_url=f"https://example.com/{guid}.xml")
    db.session.add(feed)
    db.session.flush()
    post = Post(
        feed_id=feed.id,
        guid=guid,
        download_url=f"https://example.com/{guid}.mp3",
        title=guid,
        duration=duration,
    )
    db.session.add(post)
    db.session.flush()
    return post


def test_admin_costs_counts_success_heuristic_calls(app: Any, monkeypatch: Any) -> None:
    app.register_blueprint(costs_bp)
    monkeypatch.setattr(cost_routes, "require_admin", lambda _action: (None, None))
    monkeypatch.setattr(
        cost_routes,
        "read_combined",
        lambda: {"app": {"whisper_cost_rate_per_hour": 0.0}},
    )

    with app.app_context():
        post = _seed_post("heuristic-guid")
        db.session.add(
            ProcessingJob(
                post_guid=post.guid,
                status="completed",
                completed_at=datetime(2026, 5, 15, 12, 0, 0),
            )
        )
        _add_billable_call(post.id, status="success", estimated_cost_usd=0.1)
        _add_billable_call(
            post.id,
            status="success_heuristic",
            first_segment_sequence_num=2,
            estimated_cost_usd=0.05,
        )
        db.session.commit()

        response = app.test_client().get("/api/admin/costs?year=2026&month=5")

    assert response.get_json()["total_llm_cost"] == 0.15


def test_admin_costs_does_not_load_litellm_pricing(app: Any, monkeypatch: Any) -> None:
    app.register_blueprint(costs_bp)
    monkeypatch.setattr(cost_routes, "require_admin", lambda _action: (None, None))
    monkeypatch.setattr(
        cost_routes,
        "read_combined",
        lambda: {"app": {"whisper_cost_rate_per_hour": 0.0}},
    )

    def fail(_call: Any) -> float:
        raise AssertionError("dashboard must read the persisted cost")

    monkeypatch.setattr(cost_routes, "_model_call_cost", fail)

    with app.app_context():
        post = _seed_post("persisted-guid")
        db.session.add(
            ProcessingJob(
                post_guid=post.guid,
                status="completed",
                completed_at=datetime(2026, 5, 15, 12, 0, 0),
            )
        )
        _add_billable_call(post.id, estimated_cost_usd=0.2)
        _add_billable_call(post.id, first_segment_sequence_num=2)
        db.session.commit()

        response = app.test_client().get("/api/admin/costs?year=2026&month=5")

    assert response.get_json()["total_llm_cost"] == 0.2


def test_backfill_estimated_cost_applies_and_reports_updates(
    app: Any, monkeypatch: Any
) -> None:
    app.register_blueprint(costs_bp)
    monkeypatch.setattr(cost_routes, "require_admin", lambda _action: (None, None))
    monkeypatch.setattr(cost_routes, "_model_call_cost", lambda call: 0.5)
    updates: list[tuple[int, dict[str, Any], bool]] = []

    class _Result:
        success = True

    def fake_update(_model: str, row_id: int, data: dict[str, Any], wait: bool):
        updates.append((row_id, data, wait))
        return _Result()

    monkeypatch.setattr(cost_routes.writer_client, "update", fake_update)

    with app.app_context():
        post = _seed_post("backfill-cost-guid")
        priced = _add_billable_call(post.id, prompt_tokens=10, completion_tokens=5)
        _add_billable_call(
            post.id, first_segment_sequence_num=2
        )  # no token usage: stays NULL
        whisper = _add_billable_call(
            post.id,
            first_segment_sequence_num=3,
            model_name="whisper-1",
            prompt="Whisper transcription job",
        )
        db.session.commit()
        priced_id, whisper_id = priced.id, whisper.id

        response = app.test_client().post(
            "/api/admin/costs/backfill-estimated-cost", json={"apply": True}
        )

    payload = response.get_json()
    assert payload["eligible"] == 1
    assert payload["skipped_no_tokens"] == 1
    assert payload["skipped_non_billable"] == 1
    assert payload["updated"] == 2
    assert payload["failed_updates"] == 0
    assert {(row_id, data["estimated_cost_usd"]) for row_id, data, _ in updates} == {
        (priced_id, 0.5),
        (whisper_id, 0.0),
    }
    assert all(wait for _, _, wait in updates)


def test_admin_costs_prices_legacy_and_stale_zero_rows_from_tokens(
    app: Any, monkeypatch: Any
) -> None:
    app.register_blueprint(costs_bp)
    monkeypatch.setattr(cost_routes, "require_admin", lambda _action: (None, None))
    monkeypatch.setattr(
        cost_routes,
        "read_combined",
        lambda: {"app": {"whisper_cost_rate_per_hour": 0.0}},
    )
    monkeypatch.setattr(cost_routes, "_model_call_cost", lambda call: 9.0)

    with app.app_context():
        post = _seed_post("legacy-dashboard-guid")
        db.session.add(
            ProcessingJob(
                post_guid=post.guid,
                status="completed",
                completed_at=datetime(2026, 5, 15, 12, 0, 0),
            )
        )
        _add_billable_call(post.id, prompt_tokens=10)  # NULL cost
        _add_billable_call(
            post.id,
            first_segment_sequence_num=2,
            prompt_tokens=10,
            estimated_cost_usd=0.0,
        )
        # A zero with no tokens is a genuine zero.
        _add_billable_call(
            post.id, first_segment_sequence_num=4, estimated_cost_usd=0.0
        )
        db.session.commit()

        response = app.test_client().get("/api/admin/costs?year=2026&month=5")

    assert response.get_json()["total_llm_cost"] == 18.0


def test_admin_costs_calls_prices_legacy_rows_from_tokens(
    app: Any, monkeypatch: Any
) -> None:
    app.register_blueprint(costs_bp)
    monkeypatch.setattr(cost_routes, "require_admin", lambda _action: (None, None))
    monkeypatch.setattr(cost_routes, "_model_call_cost", lambda call: 9.0)

    with app.app_context():
        post = _seed_post("calls-legacy-guid")
        stored = _add_billable_call(post.id, estimated_cost_usd=0.2)
        legacy_null = _add_billable_call(
            post.id, first_segment_sequence_num=2, prompt_tokens=10
        )
        stale_zero = _add_billable_call(
            post.id,
            first_segment_sequence_num=4,
            prompt_tokens=10,
            estimated_cost_usd=0.0,
        )
        genuine_zero = _add_billable_call(
            post.id, first_segment_sequence_num=6, estimated_cost_usd=0.0
        )
        db.session.commit()
        ids = (stored.id, legacy_null.id, stale_zero.id, genuine_zero.id)

        response = app.test_client().get("/api/admin/costs/calls?page=1&per_page=50")

    by_id = {c["id"]: c["estimated_cost"] for c in response.get_json()["calls"]}
    assert [by_id[i] for i in ids] == [0.2, 9.0, 9.0, 0.0]


def test_backfill_estimated_cost_limit_counts_rows_that_change(
    app: Any, monkeypatch: Any
) -> None:
    app.register_blueprint(costs_bp)
    monkeypatch.setattr(cost_routes, "require_admin", lambda _action: (None, None))
    monkeypatch.setattr(cost_routes, "_model_call_cost", lambda call: 0.5)
    updates: list[int] = []

    class _Result:
        success = True

    def fake_update(_model: str, row_id: int, data: dict[str, Any], wait: bool):
        updates.append(row_id)
        return _Result()

    monkeypatch.setattr(cost_routes.writer_client, "update", fake_update)

    with app.app_context():
        post = _seed_post("backfill-limit-guid")
        # Earlier unpriceable rows must not use up the limit.
        _add_billable_call(post.id, first_segment_sequence_num=0)
        _add_billable_call(post.id, first_segment_sequence_num=2)
        later = _add_billable_call(
            post.id, first_segment_sequence_num=4, prompt_tokens=10
        )
        _add_billable_call(post.id, first_segment_sequence_num=6, prompt_tokens=10)
        db.session.commit()
        later_id = later.id

        response = app.test_client().post(
            "/api/admin/costs/backfill-estimated-cost",
            json={"apply": True, "limit": 1},
        )

    assert response.get_json()["updated"] == 1
    assert updates == [later_id]
