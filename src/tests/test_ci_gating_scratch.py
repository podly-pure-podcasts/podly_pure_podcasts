def test_deliberate_ci_gating_failure() -> None:
    """Scratch test to prove CI gating. Do not merge."""
    raise AssertionError("deliberate failure to prove CI gating")
