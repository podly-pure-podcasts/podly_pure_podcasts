# [2.8.0](https://github.com/podly-pure-podcasts/podly_pure_podcasts/compare/v2.7.14...v2.8.0) (2026-10-23)


### Bug Fixes

* **ad-classifier:** retry bad LLM output, fail incomplete classification ([731b454](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/731b454e5a7d8e9b6dc3a551293e3525af590a7d))


### Features

* **processor:** publish without ad removal when ad detection is incomplete ([8e1c547](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/8e1c5471e4caaa028688e98f560f44be4a321d55))

## [2.7.14](https://github.com/podly-pure-podcasts/podly_pure_podcasts/compare/v2.7.13...v2.7.14) (2026-10-23)


### Bug Fixes

* **writer:** derive the reply wait from the busy timeout, with an env override ([c4a8a58](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/c4a8a5893ef2d5a60e63a22f9c92c9120f06129e))
* **writer:** wait for the writer's reply longer than SQLite's busy timeout ([9979ba6](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/9979ba6bfcc7695676b9bc6b7302ce0e52e495ca))

## [2.7.13](https://github.com/podly-pure-podcasts/podly_pure_podcasts/compare/v2.7.12...v2.7.13) (2026-10-23)


### Bug Fixes

* **deps:** bump certifi to 2026.10.19 (distrust emSign ECC Root CA - G3) ([9230c0a](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/9230c0a3078e1c569ae3c04ec879752ccfcf648f))

## [2.7.12](https://github.com/podly-pure-podcasts/podly_pure_podcasts/compare/v2.7.11...v2.7.12) (2026-10-20)


### Performance Improvements

* **feeds:** gzip feed XML for clients that accept it ([fee7e90](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/fee7e90661e2248f44f441e4d6441e8936f7dc3d))

## [2.7.11](https://github.com/podly-pure-podcasts/podly_pure_podcasts/compare/v2.7.10...v2.7.11) (2026-10-20)


### Bug Fixes

* **processing:** store the processed runtime for every strategy ([eb6eedd](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/eb6eedd3539bbc31f56372f988fbab79dc1521ba))


### Performance Improvements

* **feeds:** cache processed-audio durations instead of probing every request ([9baff93](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/9baff933d86fd56f058fb5d2a95357e1d276a07e))

## [2.7.10](https://github.com/podly-pure-podcasts/podly_pure_podcasts/compare/v2.7.9...v2.7.10) (2026-10-20)


### Bug Fixes

* **ci:** fail scripts/ci.sh when lint or tests fail ([2fe6644](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/2fe66443c625733daea20b3cf47be26beaf890aa))

## [2.7.9](https://github.com/podly-pure-podcasts/podly_pure_podcasts/compare/v2.7.8...v2.7.9) (2026-10-19)


### Performance Improvements

* **jobs:** reduce scheduling query allocations ([3f46d90](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/3f46d904d71d3523ac03971a616296d0f5166379))

## [2.7.8](https://github.com/podly-pure-podcasts/podly_pure_podcasts/compare/v2.7.7...v2.7.8) (2026-10-18)


### Performance Improvements

* **posts:** count whitelist state without loading episodes ([afa1d9b](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/afa1d9bf5408f8d67d88538a6bc6852ed1eb0764))
* **scheduler:** refresh feeds in separate ORM sessions ([d9e2b26](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/d9e2b26e0e3782a543276312c0ad39cab4ce42dd))
* **writer:** join feed titles and batch job lookups in audio cleanup ([36a25ab](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/36a25abefdd8fe82598b7a8e66eb9a26ea8b277a))

## [2.7.7](https://github.com/podly-pure-podcasts/podly_pure_podcasts/compare/v2.7.6...v2.7.7) (2026-10-14)


### Bug Fixes

* **docker:** install torch 2.13 ROCm wheel from the rocm7.1 index ([2ce9f0d](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/2ce9f0d05fea4621201bf1622b44e6f02310b914)), closes [#250](https://github.com/podly-pure-podcasts/podly_pure_podcasts/issues/250)
* **docker:** install variant torch wheels with --no-deps ([5077d7d](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/5077d7d18682949c00dde9e46c2403bc17a86ca1))

## [2.7.6](https://github.com/podly-pure-podcasts/podly_pure_podcasts/compare/v2.7.5...v2.7.6) (2026-10-14)


### Bug Fixes

* **deps:** bump vulnerable Python and frontend packages ([ab715d9](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/ab715d9d1dcff990dc23b11fbf84da3024fa96bc))
* **docker:** drop leftover CUDA 13 libs from the CPU image ([495aaa9](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/495aaa9a127b7d8952ecaae3ffac19fbf76555be))
* **docker:** install CPU torch 2.13 wheel in the full image ([dd97585](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/dd9758500faab3552bb8585d94e7b078482a5622))
* **docker:** uv pip uninstall does not accept -y ([aa06fce](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/aa06fce36dbb6c6d64bc98ebf9a2f6b13b5f6c0e))

## [2.7.5](https://github.com/podly-pure-podcasts/podly_pure_podcasts/compare/v2.7.4...v2.7.5) (2026-10-13)


### Bug Fixes

* **web:** trust HTTPS scheme from a configured proxy peer ([7061c50](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/7061c50a76e5dd6017c22a31233324956ab652a0))

## [2.7.4](https://github.com/podly-pure-podcasts/podly_pure_podcasts/compare/v2.7.3...v2.7.4) (2026-10-13)


### Bug Fixes

* **auth:** isolate feed-token backoff and bound limiter storage ([12c526c](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/12c526c32b6492802012527d1f424869af29ed28))

## [2.7.3](https://github.com/podly-pure-podcasts/podly_pure_podcasts/compare/v2.7.2...v2.7.3) (2026-10-11)


### Bug Fixes

* remux AAC/M4A podcasts without transcoding ([424c05d](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/424c05d220ecab14d10f80262353307773342d0d))
* remux AAC/M4A podcasts without transcoding ([#247](https://github.com/podly-pure-podcasts/podly_pure_podcasts/issues/247)) ([38e53ec](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/38e53ecd81bd60103f80a001bc45d068a4d689a6))

## [2.7.2](https://github.com/podly-pure-podcasts/podly_pure_podcasts/compare/v2.7.1...v2.7.2) (2026-10-11)


### Bug Fixes

* **feeds:** encode GUIDs with slashes in feed and API paths ([5e54b8a](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/5e54b8a1e35d19832a1f89306708d2dad1e3c0f2)), closes [#216](https://github.com/podly-pure-podcasts/podly_pure_podcasts/issues/216)
* **feeds:** match existing posts by derived guid on refresh ([0b904a1](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/0b904a1db8101733f7d421b3473ae96ea26f66b2)), closes [#231](https://github.com/podly-pure-podcasts/podly_pure_podcasts/issues/231)
* **feeds:** reconcile GUID lookup with upstream-guid + URL self-heal ([fa91947](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/fa919477856922b635a036ce0746bf9ab0bce78b))
* **feeds:** trust upstream <guid> verbatim and self-heal legacy rows ([6597837](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/65978373e1de7350c43925fd16edd3c16a6e52a3))
* **feeds:** trust upstream GUIDs, encode slashes, per-feed uniqueness ([#246](https://github.com/podly-pure-podcasts/podly_pure_podcasts/issues/246)) ([78b7107](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/78b7107de21674ef8f52b0beb2674feff2590a3e))
* **migrations:** parent guid uniqueness revision on last_changed_at head ([d3b477c](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/d3b477cacabca65d98b604f7c179f65df61d8f1d))
* scope post guid and download_url uniqueness per feed ([34374fd](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/34374fd60f026c0e4bfa2c181359fd49aa6aa418)), closes [#186](https://github.com/podly-pure-podcasts/podly_pure_podcasts/issues/186) [#192](https://github.com/podly-pure-podcasts/podly_pure_podcasts/issues/192)

## [2.7.1](https://github.com/podly-pure-podcasts/podly_pure_podcasts/compare/v2.7.0...v2.7.1) (2026-10-11)


### Performance Improvements

* **feed:** short-circuit unchanged feeds with ETag/Last-Modified 304s ([19982b1](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/19982b19c5c975bb672c2c1e464ac762fbdd0201)), closes [#240](https://github.com/podly-pure-podcasts/podly_pure_podcasts/issues/240)
* **feed:** short-circuit unchanged feeds with ETag/Last-Modified 304s ([#217](https://github.com/podly-pure-podcasts/podly_pure_podcasts/issues/217)) ([318ec4c](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/318ec4cf5f0b81c0b595b3d528b54e450f2ccd76))

# [2.7.0](https://github.com/podly-pure-podcasts/podly_pure_podcasts/compare/v2.6.1...v2.7.0) (2026-10-11)


### Features

* prevent auto-whitelisting back-catalog episodes on feed refresh ([77d4f7d](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/77d4f7d1c6dcf8079a57124723fb5532ae9b60b7))
* prevent auto-whitelisting back-catalog episodes on feed refresh ([#212](https://github.com/podly-pure-podcasts/podly_pure_podcasts/issues/212)) ([f5ffa3c](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/f5ffa3c97edb13973986700d1c314b1be38f8782))

## [2.6.1](https://github.com/podly-pure-podcasts/podly_pure_podcasts/compare/v2.6.0...v2.6.1) (2026-10-11)


### Bug Fixes

* **config:** keep env overrides after saving settings ([bcf53df](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/bcf53dfa8520778f773fd3771de46f9b307fdb35))
* **config:** keep env overrides after saving settings ([#241](https://github.com/podly-pure-podcasts/podly_pure_podcasts/issues/241)) ([0123a41](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/0123a41faad9104774b350f61015ab147fb0d978))
* **migrations:** merge duplicate alembic heads ([b386d02](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/b386d027be24d89131496e36968f797ab22d6587)), closes [podly-pure-podcasts/podly_pure_podcasts#234](https://github.com/podly-pure-podcasts/podly_pure_podcasts/issues/234)
* **migrations:** merge duplicate alembic heads ([#240](https://github.com/podly-pure-podcasts/podly_pure_podcasts/issues/240)) ([638e297](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/638e297ce4fe473efa4ddf13e59072a6d7d2f456))

# [2.6.0](https://github.com/podly-pure-podcasts/podly_pure_podcasts/compare/v2.5.0...v2.6.0) (2026-07-25)


### Features

* add per-feed Whisper language override ([bf6e58c](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/bf6e58c40f2777781ddd193cf8d248d2e8731220))

# [2.4.0](https://github.com/podly-pure-podcasts/podly_pure_podcasts/compare/v2.3.0...v2.4.0) (2026-06-04)


### Bug Fixes

* add 100vh fallback for older browsers ([93b884a](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/93b884a36c736df6126fb5c5df53eb40c8d1ae70))
* address PR review findings — logging, tests, DRY, docs ([9931407](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/993140794ec1fa54138e88ff670182340373dea4))
* **ci:** add source path to mypy install-types and restore mypy cache ([0ae6b65](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/0ae6b6582079fc6057a889b0c76aee7996e0d5be))
* **ci:** collapse redundant mypy steps into one ([f71dfdf](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/f71dfdf780f5d0d9f08898ef28d198c954cefbd8))
* **ci:** remove --install-types from mypy invocations ([b6e97da](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/b6e97da8f9cf85074485199bfd704cd5ee58cfba))
* **ci:** restore optional integration check flag ([1dbfb5a](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/1dbfb5aea96c72d3ae772e5400cfcc4c49ac5fb6))
* clear SQLAlchemy identity map after each writer command ([2e5a957](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/2e5a957c2a27b75ef873e6ad6def070cf154bb85)), closes [#199](https://github.com/podly-pure-podcasts/podly_pure_podcasts/issues/199)
* cover all env var fields in read-only UI, API stripping, and runtime overlay ([00ae8a6](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/00ae8a63c144e0397381eb0787fc6f81a9d7dfce)), closes [#196](https://github.com/podly-pure-podcasts/podly_pure_podcasts/issues/196)
* dark mode contrast and readability tweaks ([fa8fa68](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/fa8fa68a0661485a5be4a21ac1db8cef578056c3))
* **docker:** avoid undocumented --project file path in uv sync ([7281803](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/728180359a9803e5c97c9f6590a9075b55487cfb))
* **docker:** install deps via uv export requirements ([a2aba0e](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/a2aba0e3f32af09817ad9dcab671b8a96893cbfd))
* **docker:** pin uv version and remove dead pip env vars ([58135fb](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/58135fb5e61ffc23722bef7711a593abef7a1ed4))
* **docker:** restore diagnostic echo lines in dependency install ([c531dd1](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/c531dd1461d1cc5e56536f578edc148835a39827))
* **docker:** use uv sync and uv run in container ([e1a752d](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/e1a752db6959dfe8ae7ce43a20c9988e0c68742d))
* don't strip out rich html from podcast feeds. ([bdf5f87](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/bdf5f878215b6af58e610624640c391a3dec6784))
* double casting ([191612f](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/191612f3580eb8c562f6683cbc4ee474d6e2cab8))
* enhance word boundary refiner with improved JSON output handling. Output was geting truncated resulting in wasted LLM calls. ([c66f139](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/c66f1392c90649149eb5bc8351eb922f1abf8578))
* fix issues with dark mode text input coloring and sub-settings selector ([2358644](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/2358644b04ccaa0f20f6645ef932b4b788581222))
* fix podcast feed spacing on mobile so buttons shapes behave correctly on mobile layouts ([6ba9bf3](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/6ba9bf3c279ff54111b4a0ee9056abb2cb1c394b))
* fix refresh button being hard coded as black, and transparent borders not being transparent in dark mode ([fdb8b94](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/fdb8b9431225a8f95edc2ba3822c1c7f2711d15b))
* Implement auto-whitelist check for first member in feed ([c052e93](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/c052e93752a6301b33d13e270aa46b4e53b4bf7b))
* Implement auto-whitelist check for first member in feed so ([38d320a](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/38d320a2332257f8e2252a55e4f730ab5f0326b1))
* Implement auto-whitelist check for first member in feed so ([ad3fe13](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/ad3fe13b90db423a9bac00f0da1354803faf559d))
* **jobs:** skip job creation for whitelisted posts with existing processed audio ([1172f02](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/1172f0243a2a3e6b9383ab7a7ec5fe9073111cbc))
* Make the first click both reveal the in-page player and actually start playback, instead of needing a second click. ([85e3c25](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/85e3c2502af59ff3d758b6a0b19f8e60f5e8a4b1))
* merge duplicate ad_segments JSON keys from local LLMs ([5d19488](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/5d194881aee7760e4268f5fc62951676c173e0ab)), closes [#185](https://github.com/podly-pure-podcasts/podly_pure_podcasts/issues/185)
* only re-queue failed jobs on cleanup and set step_name on cancel ([2f296c1](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/2f296c1f539c52e07f013c9fc8d79c6a1389c82d))
* preserve rich feed HTML while normalizing problematic whitespace, and generate share/feed URLs with the correct HTTPS scheme behind forwarded proxy headers. ([4585ed0](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/4585ed0bde15968aa48160a2ca218a6a132f7a04))
* re-add response_format to ad classification LLM calls ([aa59013](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/aa59013af4bbfebc156009607aca67366e7af632)), closes [#184](https://github.com/podly-pure-podcasts/podly_pure_podcasts/issues/184)
* resolve NameError and linting issues ([0113a2d](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/0113a2da8affc0014a76fbada419b4bcb2a9ea99))
* revert cleanup re-queue change, keep cancel step_name fixes ([ddf299f](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/ddf299f2ac176b68aba9168beb46e807ecd99ada))
* **scripts:** restore --install-types --non-interactive to ci.sh mypy ([c6a9853](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/c6a9853729faa64ea104fb98d00f25ddbfa15f2d))
* **tests:** stabilize flaky post cleanup tests with explicit file mtimes ([56b0eaf](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/56b0eaf0c83937ba91c718c662b954bb03a9b55e))
* use dvh units to prevent bottom cutoff on Android Chrome ([118c2d6](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/118c2d653f610b35bcb819988a041c863d4f40ca))
* use expunge_all() not expire_all() — actually frees identity map ([e2b89d1](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/e2b89d1ad84a93e1bb6642f43ea68e0030649517))
* use original episode duration for ad percentage and timeline stats ([984f9c7](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/984f9c7ff751c93ca061288ccca0af21cc5c293e))
* use original episode duration for processing cost calculation ([bf9a532](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/bf9a5329724fc8663cc7d2a6c313c70877d0c7ca))


### Features

* add advertisement removal summary and processing stats to the UI ([046d112](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/046d112b08fafea629472f536e3a2ea378c3b234))
* Add advertisement removal summary and timeline visualization to LLMProcessingStats component that was accidently removed in a previous refactoring  PR ([63682d9](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/63682d9ad21f63435d6635a3fd07f8a5e746b0de))
* add build options for AMD64 and ARM64 images in Docker workflow ([af5eb48](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/af5eb484ded7ac5c95f9f677bf2281fe113841ae))
* add debug information for post stats including audio paths and processing details ([6fcc0bc](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/6fcc0bc2089d8dc5221c9cf122045f515ca5a930))
* Add feed detail route and handle feed selection in HomePage component ([a4d8d7e](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/a4d8d7eb616f186a93de9d74a4429f9a11a2c2e9))
* Add feed detail route and handle feed selection in HomePage component ([8a81f5c](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/8a81f5c767416967342610405887288b3b41ffa5))
* add function to refine transcript chapter boundaries and enhance processing logic to ensure blocks are too large in long episodes ([2df470c](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/2df470c085108c21518a73e2bb0818295ba8217c))
* add functionality to cancel all queued jobs with API integration and UI support ([0387ec9](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/0387ec92b82822d1a0e04a1882b9f14fceb03dfc))
* add LLM chapter fallback tagging configuration and related tests ([aa45d06](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/aa45d06050aa43069fd37d35f4cd82f44c067a74))
* add manual workflow inputs for Docker image builds and update conditions for job execution ([6d448d1](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/6d448d112d6a866a452d78dc26eac93277221768))
* Add Sorting Behavior to the podcast feed ([a0b6119](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/a0b6119a11f59550ba98e568c7d845ac5ec06506))
* add support for manual workflow dispatch in Docker publish process ([40abc03](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/40abc03bad25234fdf97c58b7978e66349dbbd09))
* enhance audio processing and duration handling across routes and models ([e2f754b](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/e2f754b83819153c693dd5e3eba60532ce527721))
* Enhance episode description handling with expandable view and HTML decoding ([5fa0c77](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/5fa0c7752590f6f84204c1ee4f872814222470be))
* enhance feed settings handling with chapter fallback logic and validation ([f481d00](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/f481d009fb7dc4b4aa38fb97dc8d1e46a064b6cf))
* **frontend:** add persisted dark mode toggle and contrast fixes ([0cda964](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/0cda964943e36eb704e4daef55eb03eaa5bb0b88))
* Implement admin cost dashboard and feed subscriber view with new job management actions. ([e3afea6](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/e3afea6e7023948b33c71eacc2b2695fb0e2005c))
* Implement advanced episode description parsing and rendering ([0736bfe](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/0736bfeabe7c645df0bafe5460ec02ae3b64414a))
* implement audio path resolution in JobManager and add unit tests for validation logic ([6318fd1](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/6318fd1026a4f7c0f0c5eef91f10aa2c8de39bd4))
* implement find_existing_processed_audio_path utility and refactor audio path handling in jobs manager and cleanup actions ([c96f183](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/c96f183c007d7d2730dea5f21609d47fc33f7c54))
* introduce configurable cost rate per hour setting in app configuration. ([72c7f39](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/72c7f39cd251606c0f5484df15468a737b63341e))
* make env vars authoritative over database config ([9a97c51](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/9a97c51bd78a9888368b0d7367591fc15f65ef67)), closes [#190](https://github.com/podly-pure-podcasts/podly_pure_podcasts/issues/190)
* retain more info on cleanup and integration check ([80069fc](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/80069fcf0f1119e4201417b9f372c6a2730ca62d))
* retain most recent post after cleanup ([add27e1](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/add27e143519942c548221d378dc49c99c0b7472))
* simplify conditional checks for Docker build jobs and add variant selection logic ([c66a2ec](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/c66a2eccd286b8a4f92bf10f4c7e6760f8d775e0))


### Performance Improvements

* **feed:** drop synchronous refresh_feed from GET /feed/<id> ([bef20fd](https://github.com/podly-pure-podcasts/podly_pure_podcasts/commit/bef20fd03bfff9597f3defe4ca4deb068b4b9ef9))
