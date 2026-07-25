"""Helpers for putting post GUIDs into URL paths safely.

After we began trusting upstream ``<guid>`` values verbatim, real-world feeds
often store URL- or ``tag:``-form ids that contain ``/``, ``:``, and other
reserved characters. Those must be percent-encoded when used as a single path
segment, and Flask routes must use the ``path`` converter so decoded slashes
still match.
"""

from urllib.parse import quote


def encode_guid_for_url(guid: str) -> str:
    """Percent-encode a post GUID for use as a single URL path segment."""
    return quote(guid, safe="")


def post_download_api_path(guid: str) -> str:
    return f"/api/posts/{encode_guid_for_url(guid)}/download"


def post_stream_path(guid: str) -> str:
    return f"/post/{encode_guid_for_url(guid)}.mp3"
