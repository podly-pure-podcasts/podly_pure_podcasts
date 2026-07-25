from shared.processing_paths import (
    ProcessingPaths,
    get_in_root,
    get_job_unprocessed_path,
    get_srv_root,
    paths_from_unprocessed_path,
)


def test_filenames() -> None:
    """Test filename processing with sanitized characters."""
    work_paths = paths_from_unprocessed_path(
        "some/path/to/my/unprocessed.mp3", "foo buzz!! bang? a show?? about stuff."
    )
    # Expect sanitized directory name with special characters removed and spaces replaced with underscores
    assert work_paths == ProcessingPaths(
        post_processed_audio_path=get_srv_root()
        / "foo_buzz_bang_a_show_about_stuff"
        / "unprocessed.mp3",
    )


def test_job_unprocessed_path_encodes_guid_with_slashes() -> None:
    path = get_job_unprocessed_path(
        "tag:audioboom.com,2026-03-26:/posts/8879470",
        "job-1",
        "Episode Title!",
    )
    assert path == (
        get_in_root()
        / "jobs"
        / "tag%3Aaudioboom.com%2C2026-03-26%3A%2Fposts%2F8879470"
        / "job-1"
        / "Episode Title.mp3"
    )
    # Encoded GUID is a single path segment (no nested directories from '/').
    assert (
        path.parent.parent.name
        == "tag%3Aaudioboom.com%2C2026-03-26%3A%2Fposts%2F8879470"
    )
