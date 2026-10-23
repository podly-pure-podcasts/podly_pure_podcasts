"""Production ad detection is spot-then-confirm, not the old chunk walk."""

from __future__ import annotations

import inspect

from podcast_processor.cue_detector import CORE_ANALYZE_KEYS, CueDetector
from podcast_processor.podcast_processor import PodcastProcessor
from shared import defaults as DEFAULTS
from shared.config import Config
from shared.test_utils import create_standard_test_config


def test_spot_then_confirm_has_no_feature_flags() -> None:
    assert "enable_bow_scout_gemini_confirm" not in Config.model_fields
    assert "enable_spot_then_confirm" not in Config.model_fields
    assert "enable_quote_anchor_boundaries" not in Config.model_fields
    config = create_standard_test_config()
    assert not hasattr(config, "enable_bow_scout_gemini_confirm")
    assert not hasattr(config, "enable_spot_then_confirm")
    assert DEFAULTS.ENABLE_DSP_BOUNDARY_SNAP is True
    assert config.enable_dsp_boundary_snap is True


def test_feed_ad_detection_default_remains_llm() -> None:
    assert DEFAULTS.AD_DETECTION_DEFAULT_STRATEGY == "llm"
    from app.models import Feed

    column = Feed.__table__.c.ad_detection_strategy
    assert column.default is not None
    assert column.default.arg == DEFAULTS.AD_DETECTION_DEFAULT_STRATEGY


def test_cue_detector_production_constructor_unchanged() -> None:
    detector = CueDetector()
    assert detector.include_scout_extras is False
    assert tuple(detector.analyze("hello").keys()) == CORE_ANALYZE_KEYS


def test_classify_uses_quote_anchor_only() -> None:
    source = inspect.getsource(PodcastProcessor._classify_ad_segments)
    assert "self.quote_anchor_classifier.classify" in source
    assert "self.ad_classifier.classify" not in source
    assert "bow_scout_gemini_confirm_enabled" not in source
