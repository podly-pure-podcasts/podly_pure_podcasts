"""Quote-anchor classifier prompt: plain text, no per-segment timestamps."""

from __future__ import annotations

QUOTE_SYSTEM_PROMPT = """Your job is to identify advertisements in podcast transcript excerpts with high precision.

CRITICAL: self-promo, network/sister-show promos, first-party app plugs, and membership asks COUNT AS ADS anywhere in the episode (taxonomy may still be educational/self_promo). Distinguish those from technical discussion (company names as examples, not sales).

CONTENT-AWARE TAXONOMY:
- technical_discussion: Educational content or case studies. Not an ad.
- educational/self_promo: Host/network/membership/first-party plugs. These ARE ads.
- promotional_external: External sponsor ads with sales intent, URLs, promo codes, or offers.
- transition: Brief bumpers that are part of an ad block. Include them.

JSON CONTRACT (strict):
- Always respond with: {"ads": [...]}
- Each ads item: {"start_quote": "<first 5-8 words of the ad, exact phrasing from the transcript>", "end_quote": "<last 5-8 words of the ad, exact phrasing from the transcript>", "content_type": "<taxonomy>", "confidence": <0.0-1.0>}
- Quotes MUST be copied from the excerpt (punctuation optional). Do not invent wording.
- If there are no ads, respond with: {"ads":[]}
- Do not emit timestamps.

DECISION RULES:
1) Once an ad starts, follow it to its natural conclusion; include short transitions.
2) URLs, promo codes, and "brought to you by" are strong sponsor cues.
3) Self-promo / membership / sister shows are ads (do not omit them).
4) Prefer content unless there is a real ad block.

Example:
Excerpt: Good morning. This episode is sponsored by NetSuite. Get your free guide at netsuite.com/darknet. I just came back from Defcon.
Output: {"ads":[{"start_quote":"This episode is sponsored by NetSuite","end_quote":"free guide at netsuite.com/darknet","content_type":"promotional_external","confidence":0.95}]}
"""


QUOTE_SYSTEM_PROMPT_V2 = """Your job is to identify complete advertisement BLOCKS in podcast transcript excerpts.

CRITICAL: self-promo, network/sister-show promos, first-party app plugs, and membership asks COUNT AS ADS anywhere in the episode (taxonomy may still be educational/self_promo). Distinguish those from technical discussion (company names as examples, not sales).

CONTENT-AWARE TAXONOMY:
- technical_discussion: Educational content or case studies. Not an ad.
- educational/self_promo: Host/network/membership/first-party plugs. These ARE ads.
- promotional_external: External sponsor ads with sales intent, URLs, promo codes, or offers.
- transition: Brief bumpers that are part of an ad block. Include them.

JSON CONTRACT (strict):
- Always respond with: {"ads": [...]}
- Each ads item: {"start_quote": "<first 5-8 words>", "end_quote": "<last 5-8 words>", "content_type": "<taxonomy>", "confidence": <0.0-1.0>}
- Quotes MUST be copied from the excerpt (punctuation optional). Do not invent wording.
- If there are no ads, respond with: {"ads":[]}
- Do not emit timestamps.

QUOTE THE FULL AD BREAK, NOT JUST THE SPONSOR SENTENCE:
- start_quote = the first words of the transition INTO the ad. Prefer commercial bumpers whose job is to leave for ads: "support for this show comes from", "this episode is brought to you by", "this message comes from", "we'll be right back", "that's all coming after the break", "today's episode is sponsored by". A host recap or tease of upcoming episode topics is show content, not an ad start, even if it mentions continuing after the break — start at the first offer, CTA, plug, sponsor read, or sister/network promo. If the excerpt starts already inside the ad, use the first 5-8 words present.
- end_quote = the last words BEFORE the show resumes, including outro or CTA tail: URL, promo code, "back to the show", "and we're back", "thanks to our sponsor". Do not stop at the first CTA if more ad copy follows.
- Awards talk and thanking listeners with no offer, CTA, or plug are show content, not ads.

DECISION RULES:
1) Once an ad break starts, follow it to its natural conclusion; include short transitions on both sides.
2) URLs, promo codes, and "brought to you by" are strong sponsor cues.
3) Self-promo / membership / sister shows are ads (do not omit them).
4) Prefer content unless there is a real ad block.
5) Adjacent reads for the same break are one ad; a later separate break is another ad.

Example:
Excerpt: Good morning. Support for this show comes from NetSuite. Get your free guide at netsuite.com/darknet. And we're back. I just came back from Defcon.
Output: {"ads":[{"start_quote":"Support for this show comes from NetSuite","end_quote":"And we're back","content_type":"promotional_external","confidence":0.95}]}
"""


QUOTE_SYSTEM_PROMPT_V3 = """Your job is to identify complete advertisement BLOCKS in podcast transcript excerpts.

POLICY (this feed): these COUNT AS ADS anywhere in the episode, including the opening and the tail:
- paid sponsor reads ("support for the show comes from", "support for this show comes from", "this message comes from", URLs, promo codes)
- self-promo and membership asks (NPR Plus, donate, Patreon, subscribe)
- first-party newsletter / mailing-list CTAs
- follow / subscribe on YouTube, Spotify, or "wherever you get your podcasts"
- network / sister-show promos AND the teaser copy that leads into them (a seasonal movie guide, a news-package lead-in, "On Pop Culture Happy Hour", "This week on the Sunday Story", "Up First")
- "send it to a friend" / "please follow us" plugs packed against a paid read

Distinguish those from technical discussion (company names as examples, not sales).

CONTENT-AWARE TAXONOMY:
- technical_discussion: Educational content or case studies. Not an ad.
- educational/self_promo: Host/network/membership/first-party plugs. These ARE ads.
- promotional_external: External sponsor ads with sales intent, URLs, promo codes, or offers.
- transition: Brief bumpers that are part of an ad block. Include them.

JSON CONTRACT (strict):
- Always respond with: {"ads": [...]}
- Each ads item: {"start_quote": "<FULL first sentence of the ad break, copied from the excerpt>", "end_quote": "<FULL last sentence of the ad break, copied from the excerpt>", "content_type": "<taxonomy>", "confidence": <0.0-1.0>}
- Quotes MUST be complete sentences copied from the excerpt (punctuation optional). Do not invent wording. Do not use a 5-word stub if the sentence is longer.
- If there are no ads, respond with: {"ads":[]}
- Do not emit timestamps.

QUOTE THE FULL AD BREAK:
- start_quote = the first sentence of the transition INTO the ad (host handoff, "we'll be right back", "after the break", "support for the show comes from", a follow/newsletter plug, or sister-show teaser copy). If the excerpt starts already inside the ad, use the first full sentence present.
- end_quote = the last sentence BEFORE the show resumes (URL, promo code, "wherever you get your podcasts", "and we're back", sister-show listen-CTA).
- Do NOT stop at the first listen-CTA / "wherever you get your podcasts" if another teaser, listen-CTA, or sponsor read follows with only a short pause. That is still the same break until the host returns to episode content ("It's Indicators of the Week", "We're back with ProfG").
- A first-party newsletter or YouTube/follow plug immediately before "Support for the show comes from …" is part of that break. Include it. Do not start at the paid open and drop the plug.
- "Support for the show comes from" (with "the", not only "this") is a paid-read open. Quote from that sentence, not from a later body line or a URL-only tail.
- Adjacent reads for the same break are one ad; a later separate break is another ad.

DECISION RULES:
1) Once an ad break starts, follow it to its natural conclusion; include short transitions on both sides.
2) URLs, promo codes, and "brought to you by" / "support for the show comes from" are strong sponsor cues.
3) Self-promo / membership / sister shows / newsletter / follow-us plugs are ads (do not omit them).
4) Prefer content unless there is a real ad block.
5) Packed sister teasers after a listen-CTA are ads, even if the teaser does not name the sister show in the first sentence.

Example:
Excerpt: We'll be right back after the break. Please follow us on YouTube. Support for the show comes from BCX. Visit getbcx.com. We're back with ProfG Markets. Now the interview.
Output: {"ads":[{"start_quote":"We'll be right back after the break.","end_quote":"We're back with ProfG Markets.","content_type":"promotional_external","confidence":0.95}]}
"""


def chunk_position_cue(start_seconds: float) -> str:
    mins = int(max(0.0, start_seconds) // 60)
    secs = int(max(0.0, start_seconds) % 60)
    cue = f"chunk starts at {mins}:{secs:02d}"
    if start_seconds < 90.0:
        cue += " / is the opening"
    return cue


def plain_transcript(texts: list[str]) -> str:
    lines = [str(t or "").strip() for t in texts]
    return "\n".join(line for line in lines if line)


def quote_user_prompt(
    *,
    title: str,
    start_seconds: float,
    texts: list[str],
    prompt_version: str = "v1",
) -> str:
    cue = chunk_position_cue(start_seconds)
    body = plain_transcript(texts)
    extra = ""
    if prompt_version == "v2":
        extra = (
            " Quote the commercial bumper into each ad break (not a host "
            "recap of upcoming topics) and the last words before the show "
            "resumes (outro/CTA tail). Awards/thanks with no offer or plug "
            "are show content.\n"
        )
    elif prompt_version == "v3":
        extra = (
            " Quote FULL SENTENCES: the first sentence of the break (including "
            "sister teasers, newsletter/follow/YouTube plugs, self-promo) and "
            "the last sentence before the show resumes. Do not stop at the "
            "first listen-CTA if more promo follows.\n"
        )
    return (
        f'You are analyzing "{title}". {cue}.{extra}\n'
        "Return only the JSON contract. Transcript excerpt (no timestamps):\n\n"
        f"{body}\n"
    )


def confirm_user_prompt(
    *,
    title: str,
    start_seconds: float,
    texts: list[str],
    prompt_version: str = "v2",
) -> str:
    """One-candidate confirm: smaller window, ads:[] if the region is not an ad."""
    cue = chunk_position_cue(start_seconds)
    body = plain_transcript(texts)
    extra = ""
    if prompt_version == "v2":
        extra = (
            " Quote the commercial bumper into each ad break (not a host "
            "recap of upcoming topics) and the last words before the show "
            "resumes (outro/CTA tail). Awards/thanks with no offer or plug "
            "are show content."
        )
    elif prompt_version == "v3":
        extra = (
            " Quote FULL SENTENCES for the start and end of the break. "
            "Sister-show teasers, newsletter/follow/YouTube plugs, self-promo "
            "and membership asks ARE ads. A follow/newsletter plug right "
            "before 'Support for the show comes from' belongs in the same "
            "break. Do not stop at the first listen-CTA if another teaser "
            "or sponsor read is packed after it."
        )
    no_ad = (
        "including no self-promo / sister-show / app / membership / "
        "newsletter / follow-us plug"
        if prompt_version == "v3"
        else "including no self-promo / sister-show / app / membership plug"
    )
    edge = (
        "quote the first/last full sentences that ARE present"
        if prompt_version == "v3"
        else "quote the first/last words that ARE present"
    )
    return (
        f'You are analyzing "{title}". {cue}. This excerpt is a CANDIDATE ad '
        "region plus padding — it may be show content. If there is no ad "
        f"({no_ad}), "
        f'return {{"ads":[]}}.{extra}\n'
        "If there is an ad break, quote the FULL break (not just the cue). "
        "If the ad continues past the start or end of this excerpt, still "
        f"{edge}.\n"
        "Return only the JSON contract. Transcript excerpt (no timestamps):\n\n"
        f"{body}\n"
    )


def system_prompt_for(version: str) -> str:
    if version == "v3":
        return QUOTE_SYSTEM_PROMPT_V3
    if version == "v2":
        return QUOTE_SYSTEM_PROMPT_V2
    return QUOTE_SYSTEM_PROMPT
