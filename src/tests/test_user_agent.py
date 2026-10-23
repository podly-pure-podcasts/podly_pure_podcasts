"""Podly sends one non-spoofed User-Agent on every outbound request."""

from unittest import mock

import httpx
import pytest
from flask import Blueprint

from app.auth import discord_service
from app.feeds import fetch_feed
from app.models import Feed, Post
from app.routes.feed_routes import feed_bp
from podcast_processor.podcast_downloader import PodcastDownloader
from shared.user_agent import DEFAULT_USER_AGENT, get_user_agent, user_agent_headers


@pytest.fixture(autouse=True)
def _no_env_override(monkeypatch):
    monkeypatch.delenv("PODLY_USER_AGENT", raising=False)


def test_default_user_agent_identifies_podly():
    ua = get_user_agent()

    assert ua == DEFAULT_USER_AGENT
    assert ua.startswith("Podly/")
    assert "Mozilla" not in ua
    assert "AppleWebKit" not in ua


def test_env_var_overrides_user_agent(monkeypatch):
    monkeypatch.setenv("PODLY_USER_AGENT", "MyPodly (+https://pod.example.com)")

    assert get_user_agent() == "MyPodly (+https://pod.example.com)"


def test_blank_env_var_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("PODLY_USER_AGENT", "   ")

    assert get_user_agent() == DEFAULT_USER_AGENT


def test_user_agent_headers_merges_extras():
    headers = user_agent_headers(Referer="https://open.acast.com/")

    assert headers["User-Agent"] == DEFAULT_USER_AGENT
    assert headers["Referer"] == "https://open.acast.com/"
    assert "Referer" not in user_agent_headers(Referer=None)


@mock.patch("app.routes.feed_routes.requests.get")
def test_feed_search_sends_podly_user_agent(mock_get, app):
    response = mock.MagicMock()
    response.json.return_value = {"feeds": []}
    mock_get.return_value = response

    app.testing = True
    if "feed" not in app.blueprints:
        app.register_blueprint(feed_bp)
    client = app.test_client()

    result = client.get("/api/feeds/search?term=hello")

    assert result.status_code == 200
    assert mock_get.call_args.kwargs["headers"]["User-Agent"] == DEFAULT_USER_AGENT


@mock.patch("app.feeds.feedparser.parse")
def test_fetch_feed_uses_podly_user_agent(mock_parse):
    mock_parse.return_value = mock.MagicMock(entries=[])

    fetch_feed("https://example.com/feed.rss")

    assert mock_parse.call_args.kwargs["agent"] == DEFAULT_USER_AGENT


@mock.patch("podcast_processor.podcast_downloader.requests.get")
def test_episode_download_sends_podly_user_agent(mock_get, app, tmp_path):
    response = mock.MagicMock()
    response.status_code = 200
    response.iter_content.return_value = [b"podcast audio content"]
    response.__enter__.return_value = response
    response.__exit__.return_value = None
    mock_get.return_value = response

    with app.app_context():
        post = Post(
            feed_id=1,
            guid="ua-guid",
            download_url="https://audio.acast.com/episodes/ep.mp3",
            title="UA Episode",
        )
        post.feed = Feed(title="Test Feed", rss_url="https://example.com/feed.xml")

        downloader = PodcastDownloader(download_dir=str(tmp_path))
        dest = downloader.get_and_make_download_path(post.title)

        assert downloader.download_episode(post, dest_path=str(dest)) == str(dest)

    headers = mock_get.call_args.kwargs["headers"]
    assert headers["User-Agent"] == DEFAULT_USER_AGENT
    assert headers["Referer"] == "https://open.acast.com/"


def test_discord_requests_carry_podly_user_agent(monkeypatch):
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("User-Agent"))
        return httpx.Response(200, json={"id": "123", "username": "podly"})

    real_client = httpx.Client

    def client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(discord_service.httpx, "Client", client_factory)

    assert discord_service.get_discord_user("token").id == "123"
    assert seen == [DEFAULT_USER_AGENT]
