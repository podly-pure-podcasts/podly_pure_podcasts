"""AdMerger must not span a long hole of non-ad show content."""

from app.models import Identification, TranscriptSegment
from podcast_processor.ad_merger import AdMerger
from shared import defaults as DEFAULTS


def _seg(seg_id: int, start: float, end: float, text: str) -> TranscriptSegment:
    return TranscriptSegment(
        id=seg_id,
        post_id=1,
        sequence_num=seg_id,
        start_time=start,
        end_time=end,
        text=text,
    )


def test_merger_does_not_span_49s_news_hole() -> None:
    first_a = _seg(1, 0.0, 20.8, "You can join the community at donate.npr.org")
    first_b = _seg(2, 20.8, 23.84, "and thank you.")
    second_a = _seg(
        3, 73.28, 90.0, "A free press is a critical protection for we the people."
    )
    second_b = _seg(4, 90.0, 99.12, "Give at donate.npr.org.")
    segs = [first_a, first_b, second_a, second_b]
    idents = [
        Identification(
            transcript_segment_id=seg.id,
            model_call_id=1,
            label="ad",
            confidence=0.85,
        )
        for seg in segs
    ]
    gap = float(DEFAULTS.OUTPUT_MIN_AD_CONTENT_GAP_SECONDS)
    groups = AdMerger().merge(
        segs,
        idents,
        max_gap=gap,
        min_content_gap=gap,
    )
    assert len(groups) == 2
    assert groups[0].start_time == 0.0
    assert groups[0].end_time == 23.84
    assert groups[1].start_time == 73.28
    assert groups[1].end_time == 99.12
