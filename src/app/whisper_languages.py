VALID_WHISPER_LANGUAGES = frozenset(
    {
        "ar",
        "zh",
        "da",
        "nl",
        "en",
        "fi",
        "fr",
        "de",
        "it",
        "ja",
        "ko",
        "no",
        "pl",
        "pt",
        "ru",
        "es",
        "sv",
    }
)
VALID_WHISPER_LANGUAGES_STR = ", ".join(sorted(VALID_WHISPER_LANGUAGES))


def normalize_whisper_language(value: object) -> str | None:
    if value == "" or value is None:
        return None
    if not isinstance(value, str) or value not in VALID_WHISPER_LANGUAGES:
        raise ValueError("invalid whisper language")
    return value


def whisper_language_error(empty_label: str) -> str:
    return f"language must be one of: {VALID_WHISPER_LANGUAGES_STR}, or {empty_label}."
