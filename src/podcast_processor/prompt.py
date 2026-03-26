<<<<<<< HEAD
from podcast_processor.cue_detector import CueDetector
=======
from typing import List

>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
from podcast_processor.model_output import AdSegmentPrediction, AdSegmentPredictionList
from podcast_processor.transcribe import Segment

DEFAULT_SYSTEM_PROMPT_PATH = "src/system_prompt.txt"
DEFAULT_USER_PROMPT_TEMPLATE_PATH = "src/user_prompt.jinja"

<<<<<<< HEAD
_cue_detector = CueDetector()


def transcript_excerpt_for_prompt(
    segments: list[Segment], includes_start: bool, includes_end: bool
) -> str:

    excerpts = [
        f"[{segment.start}] {_cue_detector.highlight_cues(segment.text)}"
        for segment in segments
    ]
=======

def transcript_excerpt_for_prompt(
    segments: List[Segment], includes_start: bool, includes_end: bool
) -> str:

    excerpts = [f"[{segment.start}] {segment.text}" for segment in segments]
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
    if includes_start:
        excerpts.insert(0, "[TRANSCRIPT START]")
    if includes_end:
        excerpts.append("[TRANSCRIPT END]")

    return "\n".join(excerpts)


def generate_system_prompt() -> str:
<<<<<<< HEAD
    valid_empty_example = AdSegmentPredictionList(ad_segments=[]).model_dump_json(
        exclude_none=True
    )

    output_for_one_shot_example = AdSegmentPredictionList(
        ad_segments=[
            AdSegmentPrediction(segment_offset=59.8, confidence=0.95),
            AdSegmentPrediction(segment_offset=64.8, confidence=0.9),
            AdSegmentPrediction(segment_offset=73.8, confidence=0.92),
            AdSegmentPrediction(segment_offset=77.8, confidence=0.98),
            AdSegmentPrediction(segment_offset=79.8, confidence=0.9),
        ],
        content_type="promotional_external",
        confidence=0.96,
    ).model_dump_json(exclude_none=True)

    example_output_for_prompt = output_for_one_shot_example.strip()
=======
    valid_non_empty_example = AdSegmentPredictionList(
        ad_segments=[
            AdSegmentPrediction(segment_offset=12.34, confidence=0.9),
            AdSegmentPrediction(segment_offset=56.78, confidence=0.8),
        ]
    ).model_dump_json()

    valid_empty_example = AdSegmentPredictionList(ad_segments=[]).model_dump_json()

    output_for_one_shot_example = AdSegmentPredictionList(
        ad_segments=[
            AdSegmentPrediction(segment_offset=59.8, confidence=0.9),
            AdSegmentPrediction(segment_offset=64.8, confidence=0.8),
            AdSegmentPrediction(segment_offset=73.8, confidence=0.9),
            AdSegmentPrediction(segment_offset=77.8, confidence=0.98),
            AdSegmentPrediction(segment_offset=79.8, confidence=0.88),
        ]
    ).model_dump_json()

    example_output_for_prompt = (
        output_for_one_shot_example[:-1]
        if output_for_one_shot_example.endswith("}")
        else output_for_one_shot_example
    )
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e

    one_shot_transcript_example = transcript_excerpt_for_prompt(
        [
            Segment(start=53.8, end=-1, text="That's all coming after the break."),
            Segment(
                start=59.8,
                end=-1,
                text="On this week's episode of Wildcard, actor Chris Pine tells "
                "us, it's okay not to be perfect.",
            ),
            Segment(
                start=64.8,
                end=-1,
                text="My film got absolutely decimated when it premiered, which "
                "brings up for me one of my primary triggers or whatever it was "
                "like, not being liked.",
            ),
            Segment(
                start=73.8,
                end=-1,
                text="I'm Rachel Martin, Chris Pine on How to Find Joy in Imperfection.",
            ),
            Segment(
                start=77.8,
                end=-1,
                text="That's on the new podcast, Wildcard.",
            ),
            Segment(
                start=79.8,
                end=-1,
                text="The Game Where Cards control the conversation.",
            ),
            Segment(
                start=83.8,
                end=-1,
                text="And welcome back to the show, today we're talking to Professor Hopkins",
            ),
        ],
        includes_start=False,
        includes_end=False,
    )

<<<<<<< HEAD
    technical_example = transcript_excerpt_for_prompt(
        [
            Segment(
                start=4762.7,
                end=-1,
                text="Our brains are configured differently.",
            ),
            Segment(
                start=4765.6,
                end=-1,
                text="My brain is configured perfectly for Ruby, perfectly for a dynamically typed language.",
            ),
            Segment(
                start=4831.3,
                end=-1,
                text="Shopify exists at a scale most programmers never touch, and it still runs on Rails.",
            ),
            Segment(start=4933.2, end=-1, text="Shopify.com has supported this show."),
        ],
        includes_start=False,
        includes_end=False,
    )

    return f"""Your job is to identify advertisements in podcast transcript excerpts with high precision, continuity awareness, and content-context sensitivity.

CRITICAL: distinguish external sponsor ads from technical discussion and self-promotion.

CONTENT-AWARE TAXONOMY:
- technical_discussion: Educational content, case studies, implementation details. Company names may appear as examples; do not mark as ads.
- educational/self_promo: Host discussing their own products, newsletters, funds, or courses (may include CTAs but are first-party).
- promotional_external: True sponsor ads for external companies with sales intent, URLs, promo codes, or explicit offers.
- transition: Brief bumpers that connect to or from ads; include if they are part of an ad block.

JSON CONTRACT (strict):
- Always respond with: {{"ad_segments": [...], "content_type": "<taxonomy>", "confidence": <0.0-1.0>}}
- Each ad_segments item must be: {{"segment_offset": <seconds.float>, "confidence": <0.0-1.0>}}
- If there are no ads, respond with: {valid_empty_example} (no extra keys).

DURATION AND CUE GUIDANCE:
- Ads are typically 15–120 seconds and contain CTAs, URLs/domains, promo/discount codes, phone numbers, or phrases like "brought to you by".
- Integrated ads can be longer but maintain sales intent; continuous mention of the same sponsor for >3 minutes without CTAs is likely educational/self_promo.
- Pre-roll/mid-roll/post-roll intros ("a word from our sponsor") and quick outros ("back to the show") belong to the ad block.

DECISION RULES:
1) Continuous ads: once an ad starts, follow it to its natural conclusion; include 1–5 second transitions.
2) Strong cues: treat URLs/domains, promo/discount language, and phone numbers as strong sponsor indicators.
3) Self-promotion guardrail: host promoting their own products/platforms → classify as educational/self_promo with lower confidence unless explicit external sponsorship language is present.
4) Boundary bias: if later segments clearly form an ad for a sponsor, pull in the prior two intro/transition lines as ad content.
5) Prefer labeling as content unless multiple strong ad cues appear with clear external branding.

This transcript excerpt is broken into segments starting with a timestamp [X] (seconds). Output every segment that is advertisement content.

Example (external sponsor with CTA):
{one_shot_transcript_example}
Output: {example_output_for_prompt}

Example (technical mention, not an ad):
{technical_example}
Output: {{"ad_segments": [{{"segment_offset": 4933.2, "confidence": 0.75}}], "content_type": "technical_discussion", "confidence": 0.45}}
\n\n"""
=======
    # pylint: disable=line-too-long
    return f"""Your job is to identify ads in excerpts of podcast transcripts. Ads are for other network podcasts and products or services.

There may be a pre-roll ad before the intro, as well as mid-roll and an end-roll ad after the outro.

Ad breaks are between 15 seconds and 120 seconds long.

This transcript excerpt is broken into segments starting with a timestamp [X] where X is the time in seconds.

Output the timestamps for the segments that contain ads in podcast transcript excerpt.

Include a confidence score out of 1 for the the classification, with 1 being the most confident and 0 being the least confident.

Respond with valid JSON: {valid_non_empty_example}.

If there are no ads respond: {valid_empty_example}. Do not respond with anything else.

For example, given the transcript excerpt:

{one_shot_transcript_example}

Output: {example_output_for_prompt}.\n\n"""
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
