export interface Feed {
  id: number;
  rss_url: string;
  title: string;
  description?: string;
  author?: string;
  image_url?: string;
  posts_count: number;
  latest_episode_release_date?: string | null;
  member_count?: number;
  is_member?: boolean;
  is_active_subscription?: boolean;
  ad_detection_strategy?: 'llm' | 'chapter' | 'chapter_insert';
  chapter_filter_strings?: string | null;
  enable_llm_chapter_fallback_tagging?: boolean | null;
  auto_whitelist_new_episodes_override?: boolean | null;
  language?: string | null;
}

export interface FeedSettingsUpdate {
  ad_detection_strategy?: 'llm' | 'chapter' | 'chapter_insert';
  chapter_filter_strings?: string | null;
  enable_llm_chapter_fallback_tagging?: boolean | null;
  auto_whitelist_new_episodes_override?: boolean | null;
  language?: string | null;
}

export interface Episode {
  id: number;
  guid: string;
  title: string;
  description: string;
  podly_description_html?: string | null;
  release_date: string | null;
  duration: number | null;
  whitelisted: boolean;
  has_processed_audio: boolean;
  processing_failed?: boolean;
  has_unprocessed_audio: boolean;
  download_url: string;
  image_url: string | null;
  download_count: number;
}

export interface PagedResult<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages?: number;
  whitelisted_total?: number;
}

export interface Job {
  job_id: string;
  post_guid: string;
  post_title: string | null;
  feed_title: string | null;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled' | 'skipped' | string;
  priority: number;
  step: number;
  step_name: string | null;
  total_steps: number;
  progress_percentage: number;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  // Service tier summary across this post's ModelCall rows. Present only
  // when at least one call was made at a non-default tier. `latest` is the
  // most recent call's tier; `mixed` is true when calls used multiple tiers
  // (e.g. Flex retried then fell back to standard).
  service_tier?: { label: string; latest: string; mixed: boolean };
}

export interface JobManagerRun {
  id: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | string;
  trigger: string;
  started_at: string | null;
  completed_at: string | null;
  updated_at: string | null;
  total_jobs: number;
  queued_jobs: number;
  running_jobs: number;
  completed_jobs: number;
  failed_jobs: number;
  skipped_jobs: number;
  context?: Record<string, unknown> | null;
  counters_reset_at: string | null;
  progress_percentage: number;
}

export interface JobManagerStatus {
  run: JobManagerRun | null;
}

export interface CleanupPreview {
  count: number;
  retention_days: number | null;
  cutoff_utc: string | null;
}

export interface CleanupRunResult {
  status: 'ok' | 'disabled' | 'error' | string;
  removed_posts?: number;
  remaining_candidates?: number;
  retention_days?: number | null;
  cutoff_utc?: string | null;
  message?: string;
}

// ----- Configuration Types -----

export interface LLMConfig {
  llm_api_key?: string | null;
  llm_api_key_preview?: string | null;
  llm_model: string;
  openai_base_url?: string | null;
  openai_timeout: number;
  openai_max_tokens: number;
  llm_max_concurrent_calls: number;
  llm_max_retry_attempts: number;
  llm_max_input_tokens_per_call?: number | null;
  llm_enable_token_rate_limiting: boolean;
  llm_max_input_tokens_per_minute?: number | null;
  enable_boundary_refinement: boolean;
  enable_word_level_boundary_refinder?: boolean;
  enable_llm_chapter_fallback_tagging?: boolean;
  llm_service_tier?: 'default' | 'flex' | 'priority' | 'auto';
}

export type WhisperConfig =
  | { whisper_type: 'local'; model: string }
  | {
    whisper_type: 'remote';
    model: string;
    api_key?: string | null;
    api_key_preview?: string | null;
    base_url?: string;
    language: string;
    timeout_sec: number;
    chunksize_mb: number;
  }
  | {
    whisper_type: 'groq';
    api_key?: string | null;
    api_key_preview?: string | null;
    model: string;
    language: string;
    max_retries: number;
  }
  | { whisper_type: 'test' };

export interface ProcessingConfigUI {
  num_segments_to_input_to_prompt: number;
}

export interface OutputConfigUI {
  fade_ms: number;
  // Note the intentional spelling to match backend
  min_ad_segement_separation_seconds: number;
  min_ad_segment_length_seconds: number;
  min_confidence: number;
}

export interface AppConfigUI {
  background_update_interval_minute: number | null;
  automatically_whitelist_new_episodes: boolean;
  post_cleanup_retention_days: number | null;
  number_of_episodes_to_whitelist_from_archive_of_new_feed: number;
  enable_public_landing_page: boolean;
  user_limit_total: number | null;
  autoprocess_on_download: boolean;
  cost_rate_per_hour: number;
  whisper_cost_rate_per_hour: number;
}

export interface CombinedConfig {
  llm: LLMConfig;
  whisper: WhisperConfig;
  processing: ProcessingConfigUI;
  output: OutputConfigUI;
  app: AppConfigUI;
}

export interface EnvOverrideEntry {
  env_var: string;
  value?: string;
  value_preview?: string | null;
  is_secret?: boolean;
  read_only?: boolean;
}

export type EnvOverrideMap = Record<string, EnvOverrideEntry>;

export interface ConfigResponse {
  config: CombinedConfig;
  env_overrides?: EnvOverrideMap;
}

export interface PodcastSearchResult {
  title: string;
  author: string;
  feedUrl: string;
  artworkUrl: string;
  description: string;
  genres: string[];
}

export interface AuthUser {
  id: number;
  username: string;
  role: 'admin' | 'user' | string;
  feed_allowance?: number;
  feed_subscription_status?: string;
  manual_feed_allowance?: number | null;
}

export interface ManagedUser extends AuthUser {
  created_at: string;
  updated_at: string;
  last_active?: string | null;
}

export interface DiscordStatus {
  enabled: boolean;
}

export interface BillingSummary {
  feed_allowance: number;
  feeds_in_use: number;
  remaining: number;
  current_amount?: number;
  min_amount_cents?: number;
  subscription_status: string;
  stripe_subscription_id?: string | null;
  stripe_customer_id?: string | null;
  product_id?: string | null;
  message?: string;
}

export interface LandingStatus {
  require_auth: boolean;
  landing_page_enabled: boolean;
  user_count: number;
  user_limit_total: number | null;
  slots_remaining: number | null;
}

export interface FeedSubscriber {
  user_id: number;
  username: string;
  role: string;
  subscription_status: string;
  joined_at: string | null;
}

export interface FeedSubscribersResponse {
  feed_id: number;
  subscribers: FeedSubscriber[];
}

export interface CostUser {
  id: number;
  username: string;
  role: string;
  feed_count: number;
  subscription_status: string;
  stripe_subscription_id: string | null;
  subscription_amount_cents: number | null;
  monthly_cost: number;
}

export interface CostFeed {
  id: number;
  title: string;
  subscriber_count: number;
  episodes_this_month: number;
  monthly_cost: number;
  llm_cost: number;
  whisper_cost: number;
}

export interface CostSummary {
  year: number;
  month: number;
  total_cost: number;
  cost_rate_per_hour: number;
  whisper_cost_rate_per_hour: number;
  total_llm_cost: number;
  llm_service_tier: string;
  llm_cost_by_tier: Record<string, number>;
  total_whisper_cost: number;
  total_audio_hours: number;
  users: CostUser[];
  feeds: CostFeed[];
}

export interface CallLogEntry {
  id: number;
  post_id: number;
  model_name: string;
  status: string;
  timestamp: string | null;
  retry_attempts: number;
  service_tier?: string | null;
  prompt_tokens?: number | null;
  cached_prompt_tokens?: number | null;
  completion_tokens?: number | null;
  total_tokens?: number | null;
  estimated_cost?: number;
}

export interface CallLog {
  calls: CallLogEntry[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export interface TokenBackfillModelSummary {
  would_update: number;
  updated: number;
  tokenizer_errors: number;
}

export interface EstimatedCostBackfillResult {
  applied: boolean;
  scanned: number;
  eligible: number;
  skipped_non_billable: number;
  skipped_no_tokens: number;
  updated: number;
  failed_updates: number;
}

export interface TokenBackfillResult {
  apply: boolean;
  scanned: number;
  eligible: number;
  would_update: number;
  updated: number;
  skipped_existing: number;
  skipped_non_llm: number;
  skipped_missing_text: number;
  skipped_tokenizer_error: number;
  failed_updates: number;
  models: Record<string, TokenBackfillModelSummary>;
  errors: Array<{
    model_call_id: number;
    model_name: string;
    error: string;
  }>;
}
