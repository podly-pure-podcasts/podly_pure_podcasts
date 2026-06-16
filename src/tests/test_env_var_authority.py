"""Tests for environment variable authority over database configuration.

This module tests that environment variables take unconditional precedence over
database values, following the 12-factor app principle. Environment variables
are applied as runtime overlays only - they are never persisted to the database.
"""

from __future__ import annotations

from typing import Any

from app.extensions import db
from app.models import (
    AppSettings,
    LLMSettings,
    OutputSettings,
    ProcessingSettings,
    WhisperSettings,
)
from shared import defaults as DEFAULTS
from shared.config import GroqWhisperConfig, RemoteWhisperConfig


def _create_default_settings() -> None:
    """Create default settings rows for testing.

    The standard test fixture uses a basic Flask app without the 'writer' role,
    so ensure_defaults() won't create rows. We create them manually here.
    """
    db.session.add(
        LLMSettings(
            id=1,
            llm_model=DEFAULTS.LLM_DEFAULT_MODEL,
            openai_timeout=DEFAULTS.OPENAI_DEFAULT_TIMEOUT_SEC,
            openai_max_tokens=DEFAULTS.OPENAI_DEFAULT_MAX_TOKENS,
            llm_max_concurrent_calls=DEFAULTS.LLM_DEFAULT_MAX_CONCURRENT_CALLS,
            llm_max_retry_attempts=DEFAULTS.LLM_DEFAULT_MAX_RETRY_ATTEMPTS,
            llm_enable_token_rate_limiting=DEFAULTS.LLM_ENABLE_TOKEN_RATE_LIMITING,
            enable_boundary_refinement=DEFAULTS.ENABLE_BOUNDARY_REFINEMENT,
            enable_word_level_boundary_refinder=DEFAULTS.ENABLE_WORD_LEVEL_BOUNDARY_REFINDER,
        )
    )
    db.session.add(
        WhisperSettings(
            id=1,
            whisper_type=DEFAULTS.WHISPER_DEFAULT_TYPE,
            local_model=DEFAULTS.WHISPER_LOCAL_MODEL,
            remote_model=DEFAULTS.WHISPER_REMOTE_MODEL,
            remote_base_url=DEFAULTS.WHISPER_REMOTE_BASE_URL,
            remote_language=DEFAULTS.WHISPER_REMOTE_LANGUAGE,
            remote_timeout_sec=DEFAULTS.WHISPER_REMOTE_TIMEOUT_SEC,
            remote_chunksize_mb=DEFAULTS.WHISPER_REMOTE_CHUNKSIZE_MB,
            groq_model=DEFAULTS.WHISPER_GROQ_MODEL,
            groq_language=DEFAULTS.WHISPER_GROQ_LANGUAGE,
            groq_max_retries=DEFAULTS.WHISPER_GROQ_MAX_RETRIES,
        )
    )
    db.session.add(
        ProcessingSettings(
            id=1,
            num_segments_to_input_to_prompt=DEFAULTS.PROCESSING_NUM_SEGMENTS_TO_INPUT_TO_PROMPT,
        )
    )
    db.session.add(
        OutputSettings(
            id=1,
            fade_ms=DEFAULTS.OUTPUT_FADE_MS,
            min_ad_segement_separation_seconds=DEFAULTS.OUTPUT_MIN_AD_SEGMENT_SEPARATION_SECONDS,
            min_ad_segment_length_seconds=DEFAULTS.OUTPUT_MIN_AD_SEGMENT_LENGTH_SECONDS,
            min_confidence=DEFAULTS.OUTPUT_MIN_CONFIDENCE,
        )
    )
    db.session.add(
        AppSettings(
            id=1,
            background_update_interval_minute=DEFAULTS.APP_BACKGROUND_UPDATE_INTERVAL_MINUTE,
            automatically_whitelist_new_episodes=DEFAULTS.APP_AUTOMATICALLY_WHITELIST_NEW_EPISODES,
            post_cleanup_retention_days=DEFAULTS.APP_POST_CLEANUP_RETENTION_DAYS,
            number_of_episodes_to_whitelist_from_archive_of_new_feed=DEFAULTS.APP_NUM_EPISODES_TO_WHITELIST_FROM_ARCHIVE_OF_NEW_FEED,
            enable_public_landing_page=DEFAULTS.APP_ENABLE_PUBLIC_LANDING_PAGE,
            user_limit_total=DEFAULTS.APP_USER_LIMIT_TOTAL,
            autoprocess_on_download=DEFAULTS.APP_AUTOPROCESS_ON_DOWNLOAD,
        )
    )
    db.session.commit()


class TestEnvVarAuthority:
    """Test that env vars are authoritative and never persisted to DB."""

    def test_ensure_defaults_and_hydrate_does_not_persist_env_vars(
        self, app: Any, monkeypatch: Any
    ) -> None:
        """Verify that env vars are not written to DB during startup."""
        monkeypatch.setenv("GEMINI_API_KEY", "env-api-key-123")
        monkeypatch.setenv("LLM_MODEL", "env-model-override")

        with app.app_context():
            from app.config_store import hydrate_runtime_config_inplace

            _create_default_settings()

            # Hydrate runtime config (this applies env overlays)
            hydrate_runtime_config_inplace()

            # Check DB values - they should NOT have env values
            llm = LLMSettings.query.get(1)
            assert llm is not None
            # DB should have defaults, not env values
            assert llm.llm_api_key != "env-api-key-123"
            assert llm.llm_model != "env-model-override"
            # Default model should be the DEFAULTS value
            assert llm.llm_model == DEFAULTS.LLM_DEFAULT_MODEL

            # read_combined() returns DB values, while runtime_config
            # has env overlays applied by hydrate_runtime_config_inplace.
            # We already verified DB doesn't have env values above.

    def test_runtime_config_overlays_env_vars(self, app: Any, monkeypatch: Any) -> None:
        """Verify that runtime config has env var overlays applied."""
        monkeypatch.setenv("GEMINI_API_KEY", "runtime-env-key")
        monkeypatch.setenv("LLM_MODEL", "runtime-env-model")
        monkeypatch.setenv("OPENAI_TIMEOUT", "120")
        monkeypatch.setenv("OPENAI_MAX_TOKENS", "8192")
        monkeypatch.setenv("LLM_MAX_CONCURRENT_CALLS", "10")
        monkeypatch.setenv("LLM_MAX_RETRY_ATTEMPTS", "7")
        monkeypatch.setenv("LLM_ENABLE_TOKEN_RATE_LIMITING", "true")
        monkeypatch.setenv("LLM_MAX_INPUT_TOKENS_PER_CALL", "5000")
        monkeypatch.setenv("LLM_MAX_INPUT_TOKENS_PER_MINUTE", "50000")

        with app.app_context():
            from app.config_store import hydrate_runtime_config_inplace
            from app.runtime_config import config as runtime_config

            _create_default_settings()
            hydrate_runtime_config_inplace()

            # Runtime config should have env values
            assert runtime_config.llm_api_key == "runtime-env-key"
            assert runtime_config.llm_model == "runtime-env-model"
            assert runtime_config.openai_timeout == 120
            assert runtime_config.openai_max_tokens == 8192
            assert runtime_config.llm_max_concurrent_calls == 10
            assert runtime_config.llm_max_retry_attempts == 7
            assert runtime_config.llm_enable_token_rate_limiting is True
            assert runtime_config.llm_max_input_tokens_per_call == 5000
            assert runtime_config.llm_max_input_tokens_per_minute == 50000

    def test_hydrate_preserves_db_values_when_no_env_override(
        self, app: Any, monkeypatch: Any
    ) -> None:
        """Verify that DB values are used when no env var is set."""
        # Clear any LLM env vars
        for key in [
            "LLM_API_KEY",
            "OPENAI_API_KEY",
            "GROQ_API_KEY",
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "LLM_MODEL",
        ]:
            monkeypatch.delenv(key, raising=False)

        with app.app_context():
            from app.config_store import hydrate_runtime_config_inplace
            from app.runtime_config import config as runtime_config

            _create_default_settings()
            hydrate_runtime_config_inplace()

            # The runtime config model should be from DEFAULTS (since no env override)
            assert runtime_config.llm_model == DEFAULTS.LLM_DEFAULT_MODEL


class TestEnvOverrideMetadata:
    """Test that API returns correct read_only metadata for env-set fields."""

    def test_env_override_metadata_includes_read_only(
        self, app: Any, monkeypatch: Any
    ) -> None:
        """Verify that env-overridden fields have read_only=True in metadata."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")

        with app.app_context():
            from app.routes.config_routes import _build_env_override_metadata

            # Mock data structure
            data = {
                "llm": {"llm_api_key": "test-key"},
                "whisper": {"whisper_type": "groq"},
            }

            metadata = _build_env_override_metadata(data)

            # LLM API key should be marked as read_only
            assert "llm.llm_api_key" in metadata
            assert metadata["llm.llm_api_key"]["read_only"] is True
            assert metadata["llm.llm_api_key"]["env_var"] in [
                "LLM_API_KEY",
                "OPENAI_API_KEY",
                "GROQ_API_KEY",
                "GEMINI_API_KEY",
                "GOOGLE_API_KEY",
            ]

    def test_env_override_metadata_for_all_llm_fields(
        self, app: Any, monkeypatch: Any
    ) -> None:
        """Verify that all LLM env vars produce read_only metadata."""
        monkeypatch.setenv("OPENAI_TIMEOUT", "120")
        monkeypatch.setenv("OPENAI_MAX_TOKENS", "8192")
        monkeypatch.setenv("LLM_MAX_CONCURRENT_CALLS", "10")
        monkeypatch.setenv("LLM_MAX_RETRY_ATTEMPTS", "7")
        monkeypatch.setenv("LLM_ENABLE_TOKEN_RATE_LIMITING", "true")
        monkeypatch.setenv("LLM_MAX_INPUT_TOKENS_PER_CALL", "5000")
        monkeypatch.setenv("LLM_MAX_INPUT_TOKENS_PER_MINUTE", "50000")

        with app.app_context():
            from app.routes.config_routes import _build_env_override_metadata

            data = {
                "llm": {},
                "whisper": {"whisper_type": "groq"},
            }

            metadata = _build_env_override_metadata(data)

            for field_path in [
                "llm.openai_timeout",
                "llm.openai_max_tokens",
                "llm.llm_max_concurrent_calls",
                "llm.llm_max_retry_attempts",
                "llm.llm_enable_token_rate_limiting",
                "llm.llm_max_input_tokens_per_call",
                "llm.llm_max_input_tokens_per_minute",
            ]:
                assert field_path in metadata, f"{field_path} missing from metadata"
                assert metadata[field_path]["read_only"] is True


class TestEnvOverriddenFieldStripping:
    """Test that PUT /api/config strips env-overridden fields."""

    def test_strip_env_overridden_fields(self, monkeypatch: Any) -> None:
        """Verify that env-overridden fields are removed from update payload."""
        monkeypatch.setenv("GEMINI_API_KEY", "env-key")
        monkeypatch.setenv("LLM_MODEL", "env-model")
        monkeypatch.setenv("OPENAI_TIMEOUT", "120")

        from app.routes.config_routes import _strip_env_overridden_fields

        payload = {
            "llm": {
                "llm_api_key": "user-submitted-key",  # Should be stripped
                "llm_model": "user-model",  # Should be stripped
                "openai_timeout": 300,  # Should be stripped (env override set)
                "openai_max_tokens": 4096,  # Should be kept (no env override)
            },
            "whisper": {
                "whisper_type": "groq",
            },
        }

        cleaned, stripped = _strip_env_overridden_fields(payload)

        # Verify stripped fields
        assert "llm.llm_api_key" in stripped
        assert "llm.llm_model" in stripped
        assert "llm.openai_timeout" in stripped
        assert "llm_api_key" not in cleaned["llm"]
        assert "llm_model" not in cleaned["llm"]
        assert "openai_timeout" not in cleaned["llm"]

        # Verify kept fields
        assert cleaned["llm"]["openai_max_tokens"] == 4096

    def test_strip_whisper_env_overridden_fields(self, monkeypatch: Any) -> None:
        """Verify that whisper env-overridden fields are stripped."""
        monkeypatch.setenv("WHISPER_REMOTE_TIMEOUT_SEC", "120")
        monkeypatch.setenv("WHISPER_REMOTE_CHUNKSIZE_MB", "48")

        from app.routes.config_routes import _strip_env_overridden_fields

        payload = {
            "whisper": {
                "whisper_type": "remote",
                "timeout_sec": 600,  # Should be stripped
                "chunksize_mb": 24,  # Should be stripped
                "model": "whisper-1",  # Should be kept
            },
        }

        cleaned, stripped = _strip_env_overridden_fields(payload)

        assert "whisper.timeout_sec" in stripped
        assert "whisper.chunksize_mb" in stripped
        assert "timeout_sec" not in cleaned["whisper"]
        assert "chunksize_mb" not in cleaned["whisper"]
        assert cleaned["whisper"]["model"] == "whisper-1"

    def test_no_stripping_when_no_env_vars(self, monkeypatch: Any) -> None:
        """Verify that fields are kept when no env vars are set."""
        for key in [
            "LLM_API_KEY",
            "OPENAI_API_KEY",
            "GROQ_API_KEY",
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "LLM_MODEL",
        ]:
            monkeypatch.delenv(key, raising=False)

        from app.routes.config_routes import _strip_env_overridden_fields

        payload = {
            "llm": {
                "llm_api_key": "user-key",
                "llm_model": "user-model",
            },
        }

        cleaned, stripped = _strip_env_overridden_fields(payload)

        # Nothing should be stripped
        assert len(stripped) == 0
        assert cleaned["llm"]["llm_api_key"] == "user-key"
        assert cleaned["llm"]["llm_model"] == "user-model"


class TestParseHelpers:
    """Test _parse_int and _parse_bool edge cases."""

    def test_parse_int_valid(self) -> None:
        from app.config_store import _parse_int

        assert _parse_int("42") == 42
        assert _parse_int("0") == 0
        assert _parse_int("-1") == -1

    def test_parse_int_invalid_returns_none(self) -> None:
        from app.config_store import _parse_int

        assert _parse_int("abc", env_name="TEST") is None
        assert _parse_int("3.5", env_name="TEST") is None
        assert _parse_int("", env_name="TEST") is None
        assert _parse_int(None) is None

    def test_parse_bool_valid(self) -> None:
        from app.config_store import _parse_bool

        for val in ("1", "true", "True", "TRUE", "yes", "on"):
            assert _parse_bool(val) is True, f"Expected True for {val!r}"
        for val in ("0", "false", "False", "FALSE", "no", "off"):
            assert _parse_bool(val) is False, f"Expected False for {val!r}"

    def test_parse_bool_invalid_returns_none(self) -> None:
        from app.config_store import _parse_bool

        assert _parse_bool("maybe", env_name="TEST") is None
        assert _parse_bool("", env_name="TEST") is None
        assert _parse_bool(None) is None

    def test_parse_bool_false_through_runtime_overlay(
        self, app: Any, monkeypatch: Any
    ) -> None:
        """Verify that LLM_ENABLE_TOKEN_RATE_LIMITING=false actively overrides to False."""
        monkeypatch.setenv("LLM_ENABLE_TOKEN_RATE_LIMITING", "false")

        with app.app_context():
            from app.config_store import hydrate_runtime_config_inplace
            from app.runtime_config import config as runtime_config

            _create_default_settings()
            hydrate_runtime_config_inplace()

            assert runtime_config.llm_enable_token_rate_limiting is False


class TestWhisperRuntimeOverlay:
    """Test that whisper env vars are applied to runtime config."""

    def test_remote_whisper_env_overlay(self, app: Any, monkeypatch: Any) -> None:
        """Verify remote whisper env vars are overlaid on runtime config."""
        monkeypatch.setenv("WHISPER_TYPE", "remote")
        monkeypatch.setenv("WHISPER_REMOTE_API_KEY", "env-remote-key")
        monkeypatch.setenv("WHISPER_REMOTE_TIMEOUT_SEC", "120")
        monkeypatch.setenv("WHISPER_REMOTE_CHUNKSIZE_MB", "48")

        with app.app_context():
            from app.config_store import hydrate_runtime_config_inplace
            from app.runtime_config import config as runtime_config

            original_whisper = runtime_config.whisper
            try:
                _create_default_settings()
                hydrate_runtime_config_inplace()

                assert isinstance(runtime_config.whisper, RemoteWhisperConfig)
                assert runtime_config.whisper.whisper_type == "remote"
                assert runtime_config.whisper.api_key == "env-remote-key"
                assert runtime_config.whisper.timeout_sec == 120
                assert runtime_config.whisper.chunksize_mb == 48
            finally:
                runtime_config.whisper = original_whisper

    def test_groq_whisper_env_overlay(self, app: Any, monkeypatch: Any) -> None:
        """Verify groq whisper env vars are overlaid on runtime config."""
        monkeypatch.setenv("WHISPER_TYPE", "groq")
        monkeypatch.setenv("GROQ_API_KEY", "env-groq-key")
        monkeypatch.setenv("GROQ_WHISPER_MODEL", "custom-model")
        monkeypatch.setenv("GROQ_MAX_RETRIES", "5")

        with app.app_context():
            from app.config_store import hydrate_runtime_config_inplace
            from app.runtime_config import config as runtime_config

            original_whisper = runtime_config.whisper
            try:
                _create_default_settings()
                hydrate_runtime_config_inplace()

                assert isinstance(runtime_config.whisper, GroqWhisperConfig)
                assert runtime_config.whisper.whisper_type == "groq"
                assert runtime_config.whisper.api_key == "env-groq-key"
                assert runtime_config.whisper.model == "custom-model"
                assert runtime_config.whisper.max_retries == 5
            finally:
                runtime_config.whisper = original_whisper
