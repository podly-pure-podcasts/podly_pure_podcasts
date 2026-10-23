"""Production CueDetector behavior plus optional scout extras/score."""

from podcast_processor.cue_detector import (
    CORE_ANALYZE_KEYS,
    CueDetector,
)


def test_default_analyze_keys_unchanged() -> None:
    detector = CueDetector()
    signals = detector.analyze("hello world")
    assert tuple(signals.keys()) == CORE_ANALYZE_KEYS
    assert not any(signals.values())
    assert not detector.include_scout_extras


def test_has_cue_ignores_transition_and_sponsor_extras() -> None:
    detector = CueDetector()
    assert detector.has_cue("visit example.com")
    assert not detector.has_cue("We'll be right back after the break.")
    assert not detector.has_cue("This episode is brought to you by Acme.")


def test_strong_cue_matches_adclassifier_neighbor_logic() -> None:
    detector = CueDetector()
    assert detector.has_strong_cue("use code SAVE20 at example.com")
    assert not detector.has_strong_cue("back to the show")
    assert not detector.has_strong_cue("my newsletter is out")


def test_score_weights_strong_cues_above_threshold() -> None:
    detector = CueDetector()
    score, signals = detector.score("Go to example.com and use code SAVE20")
    assert signals["url"]
    assert signals["cta"]
    assert signals["promo"]
    assert score >= 2.5


def test_scout_extras_detect_brought_to_you_by() -> None:
    production = CueDetector()
    scout = CueDetector(include_scout_extras=True)
    text = "This episode is brought to you by Squarespace."
    assert "sponsor" not in production.analyze(text)
    extras = scout.analyze(text)
    assert extras["sponsor"]
    score, _signals = scout.score(text)
    assert score >= 1.0
    highlighted = scout.highlight_cues(text)
    assert "***" in highlighted
    assert "brought to you by" in highlighted.lower()


def test_highlight_cues_url_unchanged_for_production() -> None:
    detector = CueDetector()
    text = "Check out example.com for more info."
    expected = "*** Check out *** *** example.com *** for more info."
    assert detector.highlight_cues(text) == expected
