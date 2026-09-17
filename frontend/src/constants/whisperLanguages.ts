// Per-feed Whisper language vocabulary. Must stay in sync with the backend
// VALID_WHISPER_LANGUAGES set in src/app/whisper_languages.py.

export interface WhisperLanguageOption {
  code: string;
  name: string;
}

export const WHISPER_LANGUAGES: ReadonlyArray<WhisperLanguageOption> = [
  { code: 'ar', name: 'Arabic' },
  { code: 'zh', name: 'Chinese' },
  { code: 'da', name: 'Danish' },
  { code: 'nl', name: 'Dutch' },
  { code: 'en', name: 'English' },
  { code: 'fi', name: 'Finnish' },
  { code: 'fr', name: 'French' },
  { code: 'de', name: 'German' },
  { code: 'it', name: 'Italian' },
  { code: 'ja', name: 'Japanese' },
  { code: 'ko', name: 'Korean' },
  { code: 'no', name: 'Norwegian' },
  { code: 'pl', name: 'Polish' },
  { code: 'pt', name: 'Portuguese' },
  { code: 'ru', name: 'Russian' },
  { code: 'es', name: 'Spanish' },
  { code: 'sv', name: 'Swedish' },
];

export const WHISPER_LANGUAGE_NAMES: Readonly<Record<string, string>> =
  Object.fromEntries(WHISPER_LANGUAGES.map((l) => [l.code, l.name]));
