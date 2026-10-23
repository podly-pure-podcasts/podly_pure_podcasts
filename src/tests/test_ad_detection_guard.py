"""Confidence guard: do not publish a clean file on a silent 0-ad miss."""

from types import SimpleNamespace

from podcast_processor.ad_detection_guard import (
    ad_detection_confidence_failure,
    collect_opening_ad_cues,
)
from podcast_processor.cue_detector import CueDetector


def _seg(start: float, text: str, end: float | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        start_time=start,
        end_time=end if end is not None else start + 4.0,
        text=text,
    )


def test_opening_cues_catch_preroll_url_and_brought_to_you() -> None:
    segments = [
        _seg(0.0, "Okay, when I sell my business, I want the best tax advice."),
        _seg(26.3, "Find your advisor at idprivatewealth.com."),
        _seg(200.0, "This episode is brought to you by Squarespace."),  # outside window
    ]
    cues = collect_opening_ad_cues(segments, first_seconds=180.0)
    assert len(cues) == 1
    assert cues[0].signals["url"] is True
    assert "idprivatewealth.com" in cues[0].text


def test_opening_cues_catch_promo_code() -> None:
    cues = collect_opening_ad_cues([_seg(8.0, "Use promo code BOYLE20 at checkout.")])
    assert len(cues) == 1
    assert cues[0].signals["promo"] is True


def test_opening_cues_include_sponsor_extra_inside_window() -> None:
    segments = [_seg(12.0, "This episode is brought to you by Nespresso.")]
    cues = collect_opening_ad_cues(segments)
    assert len(cues) == 1
    assert cues[0].signals["sponsor"] is True


def test_production_cue_detector_default_still_excludes_sponsor_key() -> None:
    # Guard uses extras=True; production neighbor expansion must stay unchanged.
    production = CueDetector()
    assert "sponsor" not in production.analyze("brought to you by Acme")


def test_fail_when_opening_cues_and_zero_ads() -> None:
    cues = collect_opening_ad_cues(
        [_seg(26.3, "Find your advisor at idprivatewealth.com.")]
    )
    message = ad_detection_confidence_failure(
        n_ad_segments=0,
        opening_cues=cues,
        n_failed_classify_calls=0,
        n_success_classify_calls=6,
    )
    assert message is not None
    assert "0 ads" in message
    assert "idprivatewealth.com" in message


def test_fail_when_all_classify_calls_failed_even_without_cues() -> None:
    message = ad_detection_confidence_failure(
        n_ad_segments=0,
        opening_cues=[],
        n_failed_classify_calls=6,
        n_success_classify_calls=0,
    )
    assert message is not None
    assert "every LLM chunk" in message


def test_allow_true_ad_free_when_classify_succeeded_and_no_opening_cues() -> None:
    message = ad_detection_confidence_failure(
        n_ad_segments=0,
        opening_cues=[],
        n_failed_classify_calls=0,
        n_success_classify_calls=4,
    )
    assert message is None


def test_allow_when_ads_were_labeled() -> None:
    cues = collect_opening_ad_cues(
        [_seg(26.3, "Find your advisor at idprivatewealth.com.")]
    )
    message = ad_detection_confidence_failure(
        n_ad_segments=3,
        opening_cues=cues,
        n_failed_classify_calls=0,
        n_success_classify_calls=6,
    )
    assert message is None
