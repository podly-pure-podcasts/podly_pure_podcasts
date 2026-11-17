import datetime
import time
from types import SimpleNamespace
from typing import Any
from unittest import mock

from app.episode_filters import (
    is_title_excluded,
    normalize_title_exclude_strings,
    parse_title_exclude_strings,
)
from app.extensions import db
from app.feeds import _should_whitelist_new_post, generate_feed_xml
from app.models import Feed, Post
from app.routes.feed_routes import feed_bp
from app.runtime_config import config as runtime_config
from app.writer.actions.feeds import whitelist_latest_post_for_feed_action


def _feed(exclude: str | None) -> SimpleNamespace:
    return SimpleNamespace(episode_title_exclude_strings=exclude)


def test_parse_title_exclude_strings_trims_and_drops_blanks():
    assert parse_title_exclude_strings(None) == []
    assert parse_title_exclude_strings("") == []
    assert parse_title_exclude_strings(" Spit Hit , ,BONUS ") == ["spit hit", "bonus"]


def test_normalize_title_exclude_strings_clears_blank_input():
    assert normalize_title_exclude_strings(None) is None
    assert normalize_title_exclude_strings(" , ") is None
    assert normalize_title_exclude_strings(" Spit Hit , Bonus ") == "Spit Hit,Bonus"


def test_is_title_excluded_matches_case_insensitive_substring():
    feed = _feed("spit hit,best of")
    assert is_title_excluded(feed, "SPIT HIT: Tuesday's highlights") is True
    assert is_title_excluded(feed, "The Best Of 2026") is True
    assert is_title_excluded(feed, "Episode 412 with a guest") is False
    assert is_title_excluded(feed, None) is False
    assert is_title_excluded(_feed(None), "Spit Hit") is False


def test_is_title_excluded_wildcards_match_the_whole_title():
    feed = _feed("spit hit*,*(rerun),*best*of*")
    # starts with
    assert is_title_excluded(feed, "Spit Hit: Tuesday") is True
    assert is_title_excluded(feed, "Episode 12 - spit hit") is False
    # ends with
    assert is_title_excluded(feed, "Episode 300 (Rerun)") is True
    assert is_title_excluded(feed, "(Rerun) Episode 300 extended") is False
    # ordered fragments
    assert is_title_excluded(feed, "The BEST moments OF 2026") is True
    assert is_title_excluded(feed, "Of course, the best") is False


def test_is_title_excluded_treats_only_star_as_special():
    feed = _feed("what?*,[bonus]*")
    assert is_title_excluded(feed, "What? A guest") is True
    assert is_title_excluded(feed, "Whats up") is False
    assert is_title_excluded(feed, "[BONUS] Live show") is True
    assert is_title_excluded(feed, "b Live show") is False


def test_is_title_excluded_bare_star_matches_everything():
    assert is_title_excluded(_feed("*"), "Anything at all") is True


def test_wildcard_matching_stays_fast_on_pathological_patterns():
    feed = _feed("*a*a*a*a*a*a*a*a*a*a*b")
    started = time.perf_counter()
    assert is_title_excluded(feed, "a" * 500) is False
    assert time.perf_counter() - started < 0.5


def test_should_whitelist_new_post_skips_excluded_titles():
    feed = Feed(
        title="Comedy",
        rss_url="https://example.com/comedy.xml",
        episode_title_exclude_strings="spit hit",
        auto_whitelist_new_episodes_override=True,
    )
    release = datetime.datetime(2026, 11, 1, tzinfo=datetime.UTC)
    excluded = Post(title="Spit Hit #12", release_date=release)
    regular = Post(title="Episode 500", release_date=release)

    assert _should_whitelist_new_post(feed, excluded, None) is False
    assert _should_whitelist_new_post(feed, regular, None) is True


@mock.patch("app.feeds.feed_item")
@mock.patch("app.feeds.PyRSS2Gen.Image")
@mock.patch("app.feeds.PyRSS2Gen.RSS2")
def test_generate_feed_xml_hides_excluded_unwhitelisted_posts(
    mock_rss_2, mock_image, mock_feed_item, app
):
    with app.app_context():
        original_flag = getattr(runtime_config, "autoprocess_on_download", False)
        runtime_config.autoprocess_on_download = True
        try:
            feed = Feed(
                rss_url="http://example.com/comedy",
                title="Comedy",
                episode_title_exclude_strings="spit hit",
            )
            db.session.add(feed)
            db.session.commit()

            regular = Post(
                feed_id=feed.id,
                title="Episode 500",
                guid="regular",
                download_url="http://example.com/regular.mp3",
                whitelisted=False,
            )
            excluded = Post(
                feed_id=feed.id,
                title="Spit Hit #12",
                guid="excluded",
                download_url="http://example.com/excluded.mp3",
                whitelisted=False,
            )
            hand_whitelisted = Post(
                feed_id=feed.id,
                title="Spit Hit #13",
                guid="hand-whitelisted",
                download_url="http://example.com/hand.mp3",
                whitelisted=True,
            )
            db.session.add_all([regular, excluded, hand_whitelisted])
            db.session.commit()

            mock_feed_item.side_effect = lambda post, prepend_feed_title=False: (
                mock.MagicMock(post_guid=post.guid)
            )
            mock_rss_2.return_value.to_xml.return_value = "<rss></rss>"

            generate_feed_xml(feed)

            called = {call.args[0].guid for call in mock_feed_item.call_args_list}
            assert called == {"regular", "hand-whitelisted"}
        finally:
            runtime_config.autoprocess_on_download = original_flag


def test_whitelist_latest_post_skips_excluded_titles(app):
    with app.app_context():
        feed = Feed(
            rss_url="http://example.com/comedy-latest",
            title="Comedy",
            episode_title_exclude_strings="spit hit",
        )
        db.session.add(feed)
        db.session.commit()

        older = Post(
            feed_id=feed.id,
            title="Episode 500",
            guid="ep-500",
            download_url="http://example.com/500.mp3",
            release_date=datetime.datetime(2026, 11, 1),
            whitelisted=False,
        )
        newest = Post(
            feed_id=feed.id,
            title="Spit Hit #12",
            guid="spit-12",
            download_url="http://example.com/spit12.mp3",
            release_date=datetime.datetime(2026, 11, 2),
            whitelisted=False,
        )
        db.session.add_all([older, newest])
        db.session.commit()

        result = whitelist_latest_post_for_feed_action({"feed_id": feed.id})

        assert result == {"updated": True, "post_guid": "ep-500"}
        stored_older = db.session.get(Post, older.id)
        stored_newest = db.session.get(Post, newest.id)
        assert stored_older is not None and stored_older.whitelisted is True
        assert stored_newest is not None and stored_newest.whitelisted is False


def _settings_client(app) -> tuple[Any, int]:
    app.testing = True
    app.register_blueprint(feed_bp)
    with app.app_context():
        feed = Feed(title="Comedy", rss_url="https://example.com/settings.xml")
        db.session.add(feed)
        db.session.commit()
        feed_id = feed.id
    return app.test_client(), feed_id


def _apply_writer_update(
    model_name: str, model_id: int, updates: dict[str, Any], wait: bool = True
):
    Feed.query.filter_by(id=model_id).update(updates)
    db.session.commit()
    return SimpleNamespace(success=True)


def test_update_feed_settings_stores_normalized_title_exclusions(app):
    client, feed_id = _settings_client(app)

    with mock.patch("app.routes.feed_routes.writer_client") as mock_writer:
        mock_writer.update.side_effect = _apply_writer_update
        response = client.patch(
            f"/api/feeds/{feed_id}/settings",
            json={"episode_title_exclude_strings": " Spit Hit , ,Bonus "},
        )
        assert response.status_code == 200
        assert response.get_json()["episode_title_exclude_strings"] == "Spit Hit,Bonus"

        response = client.patch(
            f"/api/feeds/{feed_id}/settings",
            json={"episode_title_exclude_strings": ""},
        )
        assert response.status_code == 200
        assert response.get_json()["episode_title_exclude_strings"] is None


def test_update_feed_settings_rejects_non_string_title_exclusions(app):
    client, feed_id = _settings_client(app)

    with mock.patch("app.routes.feed_routes.writer_client") as mock_writer:
        response = client.patch(
            f"/api/feeds/{feed_id}/settings",
            json={"episode_title_exclude_strings": ["spit hit"]},
        )

    assert response.status_code == 400
    mock_writer.update.assert_not_called()
