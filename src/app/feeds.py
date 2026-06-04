import datetime
import html
import json
import logging
import re
import uuid
from collections.abc import Iterable
from email.utils import format_datetime, parsedate_to_datetime
from typing import Any, cast
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import feedparser
import PyRSS2Gen
from flask import current_app, g, request

from app.extensions import db
from app.models import Feed, Post, User, UserFeed
from app.runtime_config import config
from app.writer.client import writer_client
from podcast_processor.audio import get_audio_duration_ms
from podcast_processor.podcast_downloader import find_audio_link

logger = logging.getLogger("global_logger")

_FORWARDED_PROTO_RE = re.compile(
    r"(?:^|[;,])\s*proto=(\"?)(https?|[A-Za-z]+)\1", re.IGNORECASE
)
_FEED_TEXT_NORMALIZE_TABLE = str.maketrans(
    {
        "\u00a0": " ",
        "\u200b": "",
        "\u200c": "",
        "\u200d": "",
        "\u2060": "",
        "\ufeff": "",
    }
)


def _format_itunes_duration(duration_seconds: int) -> str:
    total_seconds = max(0, int(duration_seconds))
    hours, rem = divmod(total_seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _parse_duration_seconds(value: Any) -> int | None:
    if value is None:
        return None

    if isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value if value >= 0 else None

    if isinstance(value, float):
        return int(value) if value >= 0 else None

    raw_value = str(value).strip()
    if not raw_value:
        return None

    try:
        parsed = int(raw_value)
    except ValueError:
        parsed = None

    if parsed is not None:
        return parsed if parsed >= 0 else None

    parts = [part.strip() for part in raw_value.split(":")]
    if len(parts) not in {2, 3} or any(not part for part in parts):
        return None

    try:
        seconds = float(parts[-1])
        minutes = int(parts[-2])
        hours = int(parts[0]) if len(parts) == 3 else 0
    except ValueError:
        return None

    if hours < 0 or minutes < 0 or seconds < 0:
        return None

    return int((hours * 3600) + (minutes * 60) + seconds)


def _format_chapter_timestamp(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    hours, rem = divmod(total_seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _chapters_for_description(post: Post) -> list[tuple[float, str]]:
    raw_chapter_data = getattr(post, "chapter_data", None)
    if not raw_chapter_data:
        return []

    try:
        chapter_data = (
            json.loads(raw_chapter_data)
            if isinstance(raw_chapter_data, str)
            else raw_chapter_data
        )
    except Exception:  # noqa: BLE001
        return []

    if not isinstance(chapter_data, dict):
        return []

    chapters = chapter_data.get("chapters_for_output") or chapter_data.get(
        "chapters_kept"
    )
    if not isinstance(chapters, list):
        return []

    out: list[tuple[float, str]] = []
    for chapter in chapters:
        if not isinstance(chapter, dict):
            continue
        title = str(chapter.get("title") or "").strip()
        if not title:
            continue
        try:
            start_time = float(chapter.get("start_time", 0.0))
        except Exception:  # noqa: BLE001
            continue
        out.append((max(0.0, start_time), title))

    out.sort(key=lambda item: item[0])
    return out


def _render_podly_chapters_html(post: Post) -> str:
    chapters = _chapters_for_description(post)
    if not chapters:
        return ""

    items = "".join(
        (f"<li>{_format_chapter_timestamp(start_time)} {html.escape(title)}</li>")
        for start_time, title in chapters
    )
    return f"<p><strong>Podly Chapters</strong></p><ul>{items}</ul>"


def _normalize_feed_text(value: str | None) -> str:
    if not value:
        return ""
    return value.translate(_FEED_TEXT_NORMALIZE_TABLE)


def build_post_feed_description_html(post: Post) -> str:
    """Build the description shown in Podly-generated RSS items for a post."""
    description_parts: list[str] = []
    if post.description:
        description_parts.append(_normalize_feed_text(post.description))

    chapters_html = _render_podly_chapters_html(post)
    if chapters_html:
        description_parts.append(chapters_html)

    return "\n".join(description_parts)


def _write_cdata(handler: Any, value: str) -> None:
    if not value:
        return

    escaped_value = value.replace("]]>", "]]]]><![CDATA[>")
    writer = getattr(handler, "_write", None)
    if callable(writer):
        writer(f"<![CDATA[{escaped_value}]]>")
        return

    handler.characters(value)


def _publish_cdata_opt_element(handler: Any, name: str, value: str | None) -> None:
    if value is None:
        return

    handler.startElement(name, {})
    _write_cdata(handler, value)
    handler.endElement(name)


def is_feed_active_for_user(feed_id: int, user: User) -> bool:
    """Check if the feed is within the user's allowance based on subscription date."""
    if user.role == "admin":
        return True

    # Hack: Always treat Feed 1 as active
    if feed_id == 1:
        return True

    # Use manual allowance if set, otherwise fall back to plan allowance
    manual_allowance = user.manual_feed_allowance
    if manual_allowance is not None:
        allowance = int(manual_allowance)
    else:
        allowance = int(getattr(user, "feed_allowance", 0))

    # Sort user's feeds by creation date to determine priority
    user_feeds = sorted(
        cast(Iterable[UserFeed], user.user_feeds),
        key=lambda uf: uf.created_at or datetime.datetime(1970, 1, 1),
    )

    for i, uf in enumerate(user_feeds):
        if uf.feed_id == feed_id:
            return i < allowance

    return False


def _should_auto_whitelist_new_posts(feed: Feed, post: Post | None = None) -> bool:
    """Return True when new posts should default to whitelisted for this feed."""
    override = getattr(feed, "auto_whitelist_new_episodes_override", None)
    if override is not None:
        return bool(override)

    if not getattr(config, "automatically_whitelist_new_episodes", False):
        return False

    from app.auth import is_auth_enabled

    # If auth is disabled, we should auto-whitelist if the global setting is on.
    if not is_auth_enabled():
        return True

    memberships = getattr(feed, "user_feeds", None) or []
    if not memberships:
        # No memberships for this feed. If there are no users in the database at all,
        # still whitelist. This handles fresh installs where no account exists yet.
        if db.session.query(User.id).first() is None:
            return True
        return False

    # Check if at least one member has this feed in their "active" list (within allowance)
    for membership in memberships:
        user = membership.user
        if not user:
            continue

        if is_feed_active_for_user(feed.id, user):
            return True

    return False


def _get_base_url() -> str:
    try:

        def _normalize_proto(value: Any) -> str | None:
            if value is None:
                return None
            first = str(value).split(",")[0].strip().strip('"').lower()
            return first if first in {"http", "https"} else None

        # Check various ways HTTP/2 pseudo-headers might be available
        http2_scheme = (
            request.headers.get(":scheme")
            or request.headers.get("scheme")
            or request.environ.get("HTTP2_SCHEME")
        )
        http2_authority = (
            request.headers.get(":authority")
            or request.headers.get("authority")
            or request.environ.get("HTTP2_AUTHORITY")
        )
        host = request.headers.get("Host")

        if http2_scheme and http2_authority:
            return f"{http2_scheme}://{http2_authority}"

        # Fall back to Host header with scheme detection
        if host:
            forwarded_proto = None
            for header_name in (
                "X-Forwarded-Proto",
                "X-Forwarded-Protocol",
                "X-Forwarded-Scheme",
                "X-Url-Scheme",
            ):
                forwarded_proto = _normalize_proto(request.headers.get(header_name))
                if forwarded_proto:
                    break

            if not forwarded_proto:
                forwarded = request.headers.get("Forwarded")
                if forwarded:
                    match = _FORWARDED_PROTO_RE.search(forwarded)
                    if match:
                        forwarded_proto = _normalize_proto(match.group(2))

            if not forwarded_proto:
                cf_visitor = request.headers.get("CF-Visitor")
                if cf_visitor:
                    try:
                        forwarded_proto = _normalize_proto(
                            json.loads(cf_visitor).get("scheme")
                        )
                    except Exception:  # noqa: BLE001
                        forwarded_proto = None

            # Check multiple indicators for HTTPS
            is_https = forwarded_proto == "https" or (
                request.is_secure
                or request.headers.get("Strict-Transport-Security") is not None
                or request.headers.get("X-Forwarded-Ssl") == "on"
                or request.headers.get("Front-End-Https") == "on"
                or request.headers.get("X-Forwarded-Port") == "443"
                or request.environ.get("HTTPS") == "on"
                or request.scheme == "https"
            )
            scheme = forwarded_proto or ("https" if is_https else "http")
            return f"{scheme}://{host}"
    except RuntimeError:
        # Working outside of request context
        pass

    # Use localhost with main app port
    return "http://localhost:5001"


def fetch_feed(url: str) -> feedparser.FeedParserDict:
    logger.info(f"Fetching feed from URL: {url}")
    feed_data = feedparser.parse(url)
    for entry in feed_data.entries:
        entry.id = get_guid(entry)
    return feed_data


def refresh_feed(feed: Feed) -> None:
    logger.info(f"Refreshing feed with ID: {feed.id}")
    feed_data = fetch_feed(feed.rss_url)

    updates = {}
    image_info = feed_data.feed.get("image")
    if image_info and "href" in image_info:
        new_image_url = image_info["href"]
        if feed.image_url != new_image_url:
            updates["image_url"] = new_image_url

    existing_posts = {post.guid: post for post in feed.posts}  # type: ignore[attr-defined]
    existing_posts_by_url = {
        post.download_url: post
        for post in feed.posts  # type: ignore[attr-defined]
        if post.download_url
    }
    oldest_post = min(
        (post for post in feed.posts if post.release_date),  # type: ignore[attr-defined]
        key=lambda p: p.release_date,
        default=None,
    )

    new_posts = []
    existing_post_updates = []
    for entry in feed_data.entries:
        existing_post = existing_posts.get(entry.id)
        repaired_guid: str | None = None
        if existing_post is None:
            # GUID didn't match; try recovering by audio URL. This catches
            # posts whose stored guid was synthesized from the enclosure URL
            # by the legacy `get_guid` fallback. Without this lookup, the
            # corrected upstream guid would orphan the existing row and the
            # episode would re-appear to subscribers as new.
            audio_url = find_audio_link(entry)
            if audio_url:
                existing_post = existing_posts_by_url.get(audio_url)
                if existing_post is not None and existing_post.guid != entry.id:
                    repaired_guid = entry.id
        if existing_post is None:
            logger.debug("found new podcast: %s", entry.title)
            p = make_post(feed, entry)
            # do not allow automatic download of any backcatalog added to the feed
            if (
                oldest_post is not None
                and p.release_date
                and oldest_post.release_date
                and p.release_date.date() < oldest_post.release_date.date()
            ):
                p.whitelisted = False
                logger.debug(
                    f"skipping post from archive due to \
number_of_episodes_to_whitelist_from_archive_of_new_feed setting: {entry.title}"
                )
            else:
                p.whitelisted = _should_auto_whitelist_new_posts(feed, p)

            post_data = {
                "guid": p.guid,
                "title": p.title,
                "description": p.description,
                "download_url": p.download_url,
                "release_date": p.release_date.isoformat() if p.release_date else None,
                "duration": p.duration,
                "image_url": p.image_url,
                "whitelisted": p.whitelisted,
                "feed_id": feed.id,
            }
            new_posts.append(post_data)
            continue

        post_update: dict[str, Any] = {"post_id": existing_post.id}

        if repaired_guid is not None:
            post_update["guid"] = repaired_guid

        updated_title = str(getattr(entry, "title", "") or "").strip()
        if updated_title and existing_post.title != updated_title:
            post_update["title"] = updated_title

        updated_description = _extract_post_description(entry)
        if existing_post.description != updated_description:
            post_update["description"] = updated_description

        updated_image_url = _extract_episode_image_url(entry, feed)
        if existing_post.image_url != updated_image_url:
            post_update["image_url"] = updated_image_url

        parsed_duration = get_duration(entry)
        if (
            existing_post.processed_audio_path is None
            and parsed_duration is not None
            and existing_post.duration != parsed_duration
        ):
            post_update["duration"] = parsed_duration

        if len(post_update) > 1:
            existing_post_updates.append(post_update)

    if updates or new_posts or existing_post_updates:
        writer_client.action(
            "refresh_feed",
            {
                "feed_id": feed.id,
                "updates": updates,
                "new_posts": new_posts,
                "existing_post_updates": existing_post_updates,
            },
            wait=True,
        )
        # Refreshes are written through the separate writer service, so expire the
        # current request session before serializing the feed response.
        db.session.expire_all()

    logger.info(f"Feed with ID: {feed.id} refreshed")


def add_or_refresh_feed(url: str) -> Feed:
    feed_data = fetch_feed(url)
    if "title" not in feed_data.feed:
        logger.error("Invalid feed URL")
        raise ValueError(f"Invalid feed URL: {url}")

    feed = Feed.query.filter_by(rss_url=url).first()
    if feed:
        refresh_feed(feed)
    else:
        feed = add_feed(feed_data)
    return feed


def add_feed(feed_data: feedparser.FeedParserDict) -> Feed:
    logger.info(f"Storing feed: {feed_data.feed.title}")
    try:
        feed_dict = {
            "title": feed_data.feed.title,
            "description": feed_data.feed.get("description", ""),
            "author": feed_data.feed.get("author", ""),
            "rss_url": feed_data.href,
            "image_url": feed_data.feed.image.href,
        }

        # Create a temporary feed object to use make_post helper
        temp_feed = Feed(**feed_dict)
        temp_feed.id = 0  # Dummy ID

        posts_data = []
        num_posts_added = 0
        for entry in feed_data.entries:
            p = make_post(temp_feed, entry)
            if (
                config.number_of_episodes_to_whitelist_from_archive_of_new_feed
                is not None
                and num_posts_added
                >= config.number_of_episodes_to_whitelist_from_archive_of_new_feed
            ):
                p.whitelisted = False
            else:
                num_posts_added += 1
                p.whitelisted = config.automatically_whitelist_new_episodes

            post_data = {
                "guid": p.guid,
                "title": p.title,
                "description": p.description,
                "download_url": p.download_url,
                "release_date": p.release_date.isoformat() if p.release_date else None,
                "duration": p.duration,
                "image_url": p.image_url,
                "whitelisted": p.whitelisted,
            }
            posts_data.append(post_data)

        result = writer_client.action(
            "add_feed", {"feed": feed_dict, "posts": posts_data}, wait=True
        )

        if result is None or result.data is None:
            raise RuntimeError("Failed to get result from writer action")

        feed_id = result.data["feed_id"]
        logger.info(f"Feed stored with ID: {feed_id}")

        # Return the feed object
        feed = db.session.get(Feed, feed_id)
        if feed is None:
            raise RuntimeError(f"Feed {feed_id} not found after creation")
        return feed

    except Exception as e:
        logger.error(f"Failed to store feed: {e}")
        raise e


class ItunesRSSItem(PyRSS2Gen.RSSItem):
    def __init__(
        self,
        *,
        title: str,
        enclosure: PyRSS2Gen.Enclosure,
        description: str,
        guid: str,
        pubDate: str | None,
        image_url: str | None = None,
        duration_seconds: int | None = None,
        **kwargs: Any,
    ) -> None:
        self.image_url = image_url
        self.duration_seconds = duration_seconds
        super().__init__(
            title=title,
            enclosure=enclosure,
            description=description,
            guid=guid,
            pubDate=pubDate,
            **kwargs,
        )

    def publish_extensions(self, handler: Any) -> None:
        if self.image_url:
            handler.startElement("itunes:image", {"href": self.image_url})
            handler.endElement("itunes:image")
        if self.duration_seconds:
            handler.startElement("itunes:duration", {})
            handler.characters(_format_itunes_duration(self.duration_seconds))
            handler.endElement("itunes:duration")
        _publish_cdata_opt_element(handler, "content:encoded", self.description)
        super().publish_extensions(handler)

    def publish(self, handler: Any) -> None:
        # PyRSS2Gen escapes item descriptions with handler.characters(), which
        # flattens rich HTML from source feeds and the appended Podly chapters.
        handler.startElement("item", self.element_attrs)
        PyRSS2Gen._opt_element(handler, "title", self.title)
        PyRSS2Gen._opt_element(handler, "link", self.link)
        self.publish_extensions(handler)
        _publish_cdata_opt_element(handler, "description", self.description)
        PyRSS2Gen._opt_element(handler, "author", self.author)

        for item_category in self.categories:
            category = (
                PyRSS2Gen.Category(item_category)
                if isinstance(item_category, str)
                else item_category
            )
            category.publish(handler)

        PyRSS2Gen._opt_element(handler, "comments", self.comments)
        if self.enclosure is not None:
            self.enclosure.publish(handler)
        PyRSS2Gen._opt_element(handler, "guid", self.guid)

        pub_date = self.pubDate
        if isinstance(pub_date, datetime.datetime):
            pub_date = PyRSS2Gen.DateElement("pubDate", pub_date)
        PyRSS2Gen._opt_element(handler, "pubDate", pub_date)

        if self.source is not None:
            self.source.publish(handler)

        handler.endElement("item")


def _feed_item_duration_seconds(post: Post) -> int | None:
    processed_audio_path = getattr(post, "processed_audio_path", None)
    if processed_audio_path:
        duration_ms = get_audio_duration_ms(processed_audio_path)
        if duration_ms is not None and duration_ms > 0:
            return round(duration_ms / 1000.0)

    raw_duration = getattr(post, "duration", None)
    if raw_duration is None:
        return None

    duration_seconds = int(raw_duration)
    return duration_seconds if duration_seconds > 0 else None


def feed_item(post: Post, prepend_feed_title: bool = False) -> PyRSS2Gen.RSSItem:
    """
    Given a post, return the corresponding RSS item. Reference:
    https://github.com/Podcast-Standards-Project/PSP-1-Podcast-RSS-Specification?tab=readme-ov-file#required-item-elements
    """

    base_url = _get_base_url()

    # Podcast clients stream enclosure URLs directly, so use the inline MP3 route
    # rather than the attachment-style download endpoint.
    audio_url = _append_feed_token_params(f"{base_url}/post/{post.guid}.mp3")
    description = build_post_feed_description_html(post)

    title = post.title
    if prepend_feed_title and post.feed:
        title = f"[{post.feed.title}] {title}"

    duration_seconds = _feed_item_duration_seconds(post)

    item = ItunesRSSItem(
        title=title,
        enclosure=PyRSS2Gen.Enclosure(
            url=audio_url,
            type="audio/mpeg",
            length=post.audio_len_bytes(),
        ),
        description=description,
        guid=post.guid,
        pubDate=_format_pub_date(post.release_date),
        image_url=post.image_url,
        duration_seconds=duration_seconds,
    )

    return item


def generate_feed_xml(feed: Feed) -> Any:
    logger.info(f"Generating XML for feed with ID: {feed.id}")

    include_unprocessed = getattr(config, "autoprocess_on_download", True)

    if include_unprocessed:
        posts = list(cast(Iterable[Post], feed.posts))
    else:
        posts = (
            Post.query.filter(
                Post.feed_id == feed.id,
                Post.whitelisted.is_(True),
                Post.processed_audio_path.isnot(None),
            )
            .order_by(Post.release_date.desc().nullslast(), Post.id.desc())
            .all()
        )

    items = [feed_item(post) for post in posts]

    base_url = _get_base_url()
    link = _append_feed_token_params(f"{base_url}/feed/{feed.id}")

    last_build_date = format_datetime(datetime.datetime.now(datetime.UTC))

    rss_feed = PyRSS2Gen.RSS2(
        title="[podly] " + feed.title,
        link=link,
        description=_normalize_feed_text(feed.description),
        lastBuildDate=last_build_date,
        image=PyRSS2Gen.Image(url=feed.image_url, title=feed.title, link=link),
        items=items,
    )

    rss_feed.rss_attrs["xmlns:itunes"] = "http://www.itunes.com/dtds/podcast-1.0.dtd"
    rss_feed.rss_attrs["xmlns:content"] = "http://purl.org/rss/1.0/modules/content/"

    logger.info(f"XML generated for feed with ID: {feed.id}")
    return rss_feed.to_xml("utf-8")


def generate_aggregate_feed_xml(user: User | None) -> Any:
    """Generate RSS XML for a user's aggregate feed (last 3 processed posts per feed)."""
    username = user.username if user else "Public"
    user_id = user.id if user else 0
    logger.info(f"Generating aggregate feed XML for: {username}")

    posts = get_user_aggregate_posts(user_id)
    items = [feed_item(post, prepend_feed_title=True) for post in posts]

    base_url = _get_base_url()
    link = _append_feed_token_params(f"{base_url}/feed/user/{user_id}")

    last_build_date = format_datetime(datetime.datetime.now(datetime.UTC))

    if current_app.config.get("REQUIRE_AUTH") and user:
        feed_title = f"Podly Podcasts - {user.username}"
        feed_description = f"Aggregate feed for {user.username} - Last 3 processed episodes from each subscribed feed."
    else:
        feed_title = "Podly Podcasts"
        feed_description = (
            "Aggregate feed - Last 3 processed episodes from each subscribed feed."
        )

    rss_feed = PyRSS2Gen.RSS2(
        title=feed_title,
        link=link,
        description=feed_description,
        lastBuildDate=last_build_date,
        items=items,
        image=PyRSS2Gen.Image(
            url=f"{base_url}/static/images/logos/manifest-icon-512.maskable.png",
            title=feed_title,
            link=link,
        ),
    )

    rss_feed.rss_attrs["xmlns:itunes"] = "http://www.itunes.com/dtds/podcast-1.0.dtd"
    rss_feed.rss_attrs["xmlns:content"] = "http://purl.org/rss/1.0/modules/content/"

    logger.info(f"Aggregate XML generated for: {username}")
    return rss_feed.to_xml("utf-8")


def get_user_aggregate_posts(user_id: int, limit_per_feed: int = 3) -> list[Post]:
    """Fetch last N processed posts from each of the user's subscribed feeds."""
    if not current_app.config.get("REQUIRE_AUTH") or user_id == 0:
        feed_ids = [r[0] for r in Feed.query.with_entities(Feed.id).all()]
    else:
        user_feeds = UserFeed.query.filter_by(user_id=user_id).all()
        feed_ids = [uf.feed_id for uf in user_feeds]

    all_posts = []
    for feed_id in feed_ids:
        # Fetch last N processed posts for this feed
        posts = (
            Post.query.filter(
                Post.feed_id == feed_id,
                Post.whitelisted.is_(True),
                Post.processed_audio_path.isnot(None),
            )
            .order_by(Post.release_date.desc().nullslast(), Post.id.desc())
            .limit(limit_per_feed)
            .all()
        )
        all_posts.extend(posts)

    # Sort all posts by release date descending
    all_posts.sort(key=lambda p: p.release_date or datetime.datetime.min, reverse=True)

    return all_posts


def _append_feed_token_params(url: str) -> str:
    if not current_app.config.get("REQUIRE_AUTH"):
        return url

    try:
        token_result = getattr(g, "feed_token", None)
        token_id = request.args.get("feed_token")
        secret = request.args.get("feed_secret")
    except RuntimeError:
        return url

    if token_result is not None:
        token_id = token_id or token_result.token.token_id
        secret = secret or token_result.token.token_secret

    if not token_id or not secret:
        return url

    parsed = urlparse(url)
    query_params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query_params["feed_token"] = token_id
    query_params["feed_secret"] = secret
    new_query = urlencode(query_params)
    return urlunparse(parsed._replace(query=new_query))


def _extract_episode_image_url(
    entry: feedparser.FeedParserDict,
    feed: Feed,
) -> str | None:
    """Prefer episode-level artwork when the source feed exposes it."""
    episode_image_url = None

    # Try to get episode-specific image from various RSS fields
    if hasattr(entry, "image") and entry.image:
        if isinstance(entry.image, dict) and "href" in entry.image:
            episode_image_url = entry.image["href"]
        elif isinstance(entry.image, str):
            episode_image_url = entry.image

    # Try iTunes image tag
    if not episode_image_url and hasattr(entry, "itunes_image"):
        if isinstance(entry.itunes_image, dict) and "href" in entry.itunes_image:
            episode_image_url = entry.itunes_image["href"]
        elif isinstance(entry.itunes_image, str):
            episode_image_url = entry.itunes_image

    # Try media:thumbnail or media:content
    if not episode_image_url and hasattr(entry, "media_thumbnail"):
        if entry.media_thumbnail and len(entry.media_thumbnail) > 0:
            episode_image_url = entry.media_thumbnail[0].get("url")

    # Fallback to feed image if no episode-specific image found
    if not episode_image_url:
        episode_image_url = feed.image_url

    return episode_image_url


def _extract_post_description(entry: feedparser.FeedParserDict) -> str:
    """Prefer rich HTML payloads when a source feed exposes them."""
    content_items = getattr(entry, "content", None) or []
    for content in content_items:
        value = str(content.get("value", "") or "").strip()
        content_type = str(content.get("type", "") or "").strip().lower()
        if value and content_type in {"text/html", "application/xhtml+xml"}:
            return value

    for field in ("description", "summary"):
        value = str(entry.get(field, "") or "").strip()
        if value:
            return value

    for content in content_items:
        value = str(content.get("value", "") or "").strip()
        if value:
            return value

    return str(entry.get("subtitle", "") or "").strip()


def make_post(feed: Feed, entry: feedparser.FeedParserDict) -> Post:
    return Post(
        feed_id=feed.id,
        guid=get_guid(entry),
        download_url=find_audio_link(entry),
        title=entry.title,
        description=_extract_post_description(entry),
        release_date=_parse_release_date(entry),
        duration=get_duration(entry),
        image_url=_extract_episode_image_url(entry, feed),
    )


def _get_entry_field(
    entry: feedparser.FeedParserDict | dict[str, Any], field: str
) -> Any | None:
    value = getattr(entry, field, None)
    return value if value is not None else entry.get(field)


def _parse_datetime_string(value: str | None, field: str) -> datetime.datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        logger.debug("Failed to parse %s string for release date", field)
        return None


def _parse_struct_time(value: Any | None, field: str) -> datetime.datetime | None:
    if not value:
        return None
    try:
        dt = datetime.datetime(*value[:6])
    except (TypeError, ValueError):
        logger.debug("Failed to parse %s for release date", field)
        return None
    gmtoff = getattr(value, "tm_gmtoff", None)
    if gmtoff is not None:
        dt = dt.replace(tzinfo=datetime.timezone(datetime.timedelta(seconds=gmtoff)))
    return dt


def _normalize_to_utc(dt: datetime.datetime | None) -> datetime.datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.UTC)
    return dt.astimezone(datetime.UTC)


def _parse_release_date(
    entry: feedparser.FeedParserDict,
) -> datetime.datetime | None:
    """Parse a release datetime from a feed entry and normalize to UTC."""
    for field in ("published", "updated"):
        dt = _parse_datetime_string(_get_entry_field(entry, field), field)
        normalized = _normalize_to_utc(dt)
        if normalized:
            return normalized

    for field in ("published_parsed", "updated_parsed"):
        dt = _parse_struct_time(_get_entry_field(entry, field), field)
        normalized = _normalize_to_utc(dt)
        if normalized:
            return normalized

    return None


def _format_pub_date(release_date: datetime.datetime | None) -> str | None:
    if not release_date:
        return None

    normalized = release_date
    if normalized.tzinfo is None:
        normalized = normalized.replace(tzinfo=datetime.UTC)

    return format_datetime(normalized.astimezone(datetime.UTC))


def get_guid(entry: feedparser.FeedParserDict) -> str:
    """Return the post GUID, preferring the upstream `<guid>` verbatim.

    Real feeds rarely use UUIDs as their `<guid>`; URLs and `tag:` URIs are
    common. Hashing the enclosure URL as a substitute breaks subscriber
    libraries whenever the CDN path or tracking params change, so we only
    fall back to URL hashing when the upstream provides no usable id.
    """
    raw = getattr(entry, "id", None) or getattr(entry, "guid", None)
    if isinstance(raw, str):
        candidate = raw.strip()
        if candidate:
            return candidate
    dlurl = find_audio_link(entry)
    return str(uuid.uuid5(uuid.NAMESPACE_URL, dlurl))


def get_duration(entry: feedparser.FeedParserDict | dict[str, Any]) -> int | None:
    for field in ("itunes_duration", "duration"):
        parsed_duration = _parse_duration_seconds(_get_entry_field(entry, field))
        if parsed_duration is not None:
            return parsed_duration

    return None
