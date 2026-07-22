# Fine-Tune an Open Model for Podcast Ad Classification

**Status:** research / plan only — no implementation in this document’s scope  
**Target task:** Podly’s LLM ad-segment classifier (not Whisper, not boundary refinement as v1)

## Why this task

Podly’s core ML job is **structured ad-span labeling** over Whisper transcript chunks:

1. Input: podcast title + description + ~60 timed segments (`[59.8] text…`), with cue phrases optionally highlighted.
2. Output: strict JSON — `{"ad_segments":[{"segment_offset": float, "confidence": float}, ...], "content_type": "...", "confidence": float}` (or empty `ad_segments`).
3. Downstream: keep segments with `confidence >= min_confidence` (default **0.8**), merge ranges, optionally refine boundaries, cut audio with ffmpeg.

Today this runs via **LiteLLM** against a large hosted model (default `groq/openai/gpt-oss-120b`) with a long system prompt (`src/system_prompt.txt`). LLM cost is already small vs Whisper (~$0.001/episode vs ~$0.04/hr audio), so fine-tuning is mainly about:

- **Quality** on hard cases (host-read sponsors vs technical brand mentions vs self-promo)
- **Latency / offline / self-host** for Docker/local users
- **Shorter prompts** (bake taxonomy + format into weights; drop few-shot examples)
- **JSON reliability** on small local models (Podly already special-cases duplicate `ad_segments` keys)

## Problem framing for ML

This is closer to **token/segment multi-label span extraction** than free-form chat:

| Aspect | Implication |
|--------|-------------|
| Unit of prediction | Whisper segment offsets (not characters) |
| Class imbalance | Most segments are content; ads are sparse |
| Product priority | **High precision** — false positives delete real show content |
| Continuity | Ads are contiguous blocks with short transitions |
| Hard negatives | Brand names in educational context; host self-promo with CTAs |
| Schema | Must emit valid JSON matching `AdSegmentPredictionList` |

Two viable model families:

1. **Generative LLM (recommended path for Podly)** — keep the existing prompt/JSON contract; SFT/QLoRA so a small open model replaces the hosted LLM behind LiteLLM.
2. **Encoder classifier (alternative)** — per-segment binary/multiclass head (e.g. DeBERTa/ModernBERT) over local window context. Simpler eval, faster inference, but requires a new inference path (not drop-in LiteLLM).

**Recommendation:** start with (1) for drop-in compatibility with `AdClassifier` + LiteLLM/`openai_base_url`. Revisit (2) if a 4–8B gen model cannot hit precision targets on a held-out set.

Do **not** fine-tune Whisper for v1. Ad detection is text/semantic; audio AST approaches exist in the literature but are a separate project (different labels, different serving stack).

## What Podly already stores (training gold / silver)

| Source | Use | Caveat |
|--------|-----|--------|
| `TranscriptSegment` | Features + offsets | Deleted on full cleanup today (~5 day retention) unless files-only cleanup lands |
| `ModelCall.prompt` / `.response` | Near-ready SFT pairs | Teacher labels; include only `status=success` |
| `Identification` (`label=ad`, confidence) | Segment-level labels | Reflects teacher + thresholding; overlaps across chunks |
| `Post.refined_ad_boundaries` | Boundary supervision | Secondary task; skip for classifier v1 |
| Chapter strategy feeds | Weak span labels from ID3 titles | High precision, low recall; good for hard-negative mining elsewhere |
| CueDetector hits | Weak positives / hard negatives | Heuristic; use as features or filters, not sole labels |

**Blocking dependency for a real dataset:** processing metadata is purged with audio today. The [data retention improvement plan](./data_retention_improvement.md) (keep `ModelCall` / `TranscriptSegment` / `Identification`, delete files only) is effectively a prerequisite for accumulating production training data.

There is **no** user correction UI today — so no human preference pairs yet. Early training must use teacher distillation + curated review.

## External / literature context (brief)

Public podcast-ad datasets are scarce. Academic work (e.g. Hamburg thesis on multimodal ad ID; RadIA for radio; SponsorBlock-style YouTube weak labels; AST audio fine-tunes) consistently finds:

- Manual podcast labels are small but valuable (~100–200 episodes).
- Out-of-domain YouTube/SponsorBlock transfers poorly to host-read podcast sponsors.
- Multimodal helps in research setups; Podly’s product path is already transcript-first.

Treat external data as **augmentation only**, not a substitute for Podly-in-distribution labels.

## Recommended approach: teacher → SFT (QLoRA) → optional preference tuning

### Phase 0 — Success criteria & baseline

Define offline metrics on a frozen eval set (episode-level splits, never segment-random):

- **Segment F1 / precision / recall** at confidence ≥ 0.8 (product threshold)
- **Ad-block IoU** or boundary error (±1–2s) after merger (what listeners hear)
- **Schema validity rate** (% parseable by `clean_and_parse_model_output`)
- **False-positive content seconds removed** (primary user-harm metric)

Record current hosted model as baseline on the same set before any fine-tune.

### Phase 1 — Dataset construction

**1a. Export pipeline (offline script, not product path)**

From DB (or snapshots):

```text
(system_prompt_version, user_prompt, teacher_response_json, post_id, chunk_range, model_name)
```

Filter:

- Successful `ModelCall`s only
- Deduplicate overlapping chunks (prefer highest-confidence / latest successful call)
- Cap per-feed share so one show doesn’t dominate
- Stratify: ad-heavy chunks, pure content, self-promo-like, technical brand mentions

**1b. Human gold subset (required)**

Aim for **~50–150 episodes** across genres (interview, tech, news, comedy, narrative), ~**2–5k labeled chunks** after chunking.

Review protocol:

- Annotate **ad vs not** at segment level using Podly’s taxonomy
- Especially review teacher disagreements on self-promo vs external sponsor
- Keep a sealed **test** set never used for training or prompt iteration

**1c. Weak / synthetic augmentation (optional)**

- Insert known sponsor-read templates into clean transcripts at realistic offsets
- Over-sample hard negatives (Shopify-as-example style cases already in the system prompt)
- Chapter-tagged ad windows as additional positives where strategy=`chapter`

**1d. Train format**

Chat/SFT JSONL matching the production messages API:

```json
{
  "messages": [
    {"role": "system", "content": "<compact or full system prompt>"},
    {"role": "user", "content": "<user_prompt.jinja rendered>"},
    {"role": "assistant", "content": "{\"ad_segments\":[...],\"content_type\":\"promotional_external\",\"confidence\":0.94}"}
  ]
}
```

Train mostly on **assistant completion**; keep temperature-0 eval.

Target sizes (order of magnitude):

| Split | Scale |
|-------|--------|
| Teacher silver | 5k–50k chunks (whatever retention allows) |
| Human gold train | 1k–5k chunks |
| Human gold val/test | 200–500 chunks each |

Small, clean gold often beats huge noisy silver for precision-critical tasks.

### Phase 2 — Base model selection

Prefer **Apache-2.0 / commercially permissive** instruct models that already do structured JSON well.

| Candidate | Why | Train (QLoRA) | Serve (approx.) |
|-----------|-----|---------------|-----------------|
| **Qwen3-4B-Instruct** | Strong structured/tooling for size; Apache-2.0; fits Colab/consumer GPU | ~1×16GB class | ~3–5GB Q4 |
| **Qwen3-8B-Instruct** | Better ceiling if 4B misses precision | 16–24GB | ~5–9GB |
| Llama 3.1/3.3 8B Instruct | Ecosystem familiarity; check license for distribution | similar to 8B | similar |
| Gemma 3 4B/12B | Competitive SLMs; verify license for SaaS redistribution | similar | similar |

**Default recommendation:** **Qwen3-4B-Instruct** for first experiment; promote to **8B** only if eval plateaus on hard negatives / schema compliance.

Avoid reasoning-heavy “thinking” modes for production inference (latency + token waste); if using Qwen3, prefer instruct / non-thinking settings for this classification task.

Audio/VLM fine-tunes (AST, Qwen2.5-VL ad-layout LoRAs) are **out of scope** for this text classifier.

### Phase 3 — Training recipe

**Method:** QLoRA / LoRA SFT (Unsloth or Axolotl/TRL). Full fine-tune is unnecessary for this schema-bound task.

Suggested starting knobs:

- LoRA rank 16–32, alpha ≈ 2×rank, dropout 0–0.05
- Target **all linear** layers (not only q/v)
- LR ~1e–4–2e–4, cosine, 1–3 epochs
- `max_seq_length` ≥ production chunk size (~2k–4k tokens; measure real prompts)
- Completion-only loss on assistant JSON
- Early stop on **val precision@0.8** and schema validity, not train loss alone

**Optional Phase 3b — preference / DPO:**

Once humans can mark “over-cut” vs “under-cut” on the same chunk, build preference pairs (conservative vs aggressive labels) and run a light DPO/ORPO pass to bias toward precision.

**Prompt distillation:** after the model learns the contract, A/B a **short system prompt** (taxonomy + JSON only, no long few-shots) to cut tokens and latency.

### Phase 4 — Evaluation harness (must exist before shipping)

Add an offline eval (script under `scripts/`, not live CI GPU) that:

1. Loads frozen JSONL gold set
2. Calls candidate model via same LiteLLM path as production
3. Parses with `clean_and_parse_model_output`
4. Reports segment metrics + block IoU + schema fail rate + FP content seconds
5. Compares to teacher baseline

Gate for promotion: **precision ≥ baseline** and **FP content seconds ≤ baseline**, with recall within an agreed band (e.g. −5% absolute max).

### Phase 5 — Serving / Podly integration (later)

No product changes required until a model passes gates:

1. Serve merged or adapter model with **vLLM / llama.cpp / Ollama** OpenAI-compatible API
2. Point Podly `openai_base_url` + unprefixed `llm_model` at it (already supported)
3. Keep hosted Groq/OpenAI as fallback
4. Optionally ship a Docker profile (`compose.dev.nvidia.yml`-style) with the fine-tuned weights
5. Version the LoRA + prompt hash next to `ModelCall.model_name` for auditability

Boundary refinement and chapter-fallback LLMs stay on the general model until separately evaluated.

## Alternative: encoder sequence tagger

If generative SLMs underperform on latency/cost:

- Label each segment `ad` / `content` (+ optional taxonomy)
- Context window of ±K neighboring segments (mirrors continuity rules)
- Train ModernBERT/DeBERTa-v3 with class weights or focal loss
- Calibrate probabilities to map onto existing `min_confidence`
- New Python classifier implementing the same `Identification` write path

Higher engineering cost inside Podly; better if the goal is **CPU-only** edge inference.

## Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Teacher copies systematic errors | Human gold + hard-negative review; don’t train only on silver |
| Genre overfitting | Feed-stratified splits; genre quotas |
| Schema drift / duplicate keys | Constrained decoding / JSON schema where server supports it; keep repair parser |
| Retention deletes training data | Land files-only cleanup; export snapshots regularly |
| License / redistribution | Prefer Apache-2.0 (Qwen3); legal review before bundling weights |
| Users notice over-cutting | Precision-first gates; conservative confidence bias via DPO |
| Scope creep into Whisper/audio | Explicitly defer AST/multimodal |

## Suggested milestone order (technical, not calendar)

1. **Eval harness + 20–50 episode gold seed** (manual or semi-auto review of teacher labels)
2. **Export silver `ModelCall` dataset** (depends on retention / snapshots)
3. **QLoRA SFT on Qwen3-4B**; compare to hosted baseline
4. If close: scale gold, try 8B, shorten prompt, add DPO
5. If generative path fails latency/precision: spike encoder tagger
6. Only then: Docker/serve integration + config UI model preset

## Explicit non-goals (this plan)

- Implementing training code or shipping weights
- Fine-tuning Whisper or boundary-refiner prompts
- Replacing chapter-based strategies
- Building a public dataset release (privacy / ToS of podcast audio must be reviewed first)

## Key code touchpoints (for a future implementation)

| Concern | Path |
|---------|------|
| Classifier | `src/podcast_processor/ad_classifier.py` |
| Schema parse | `src/podcast_processor/model_output.py` |
| Prompts | `src/system_prompt.txt`, `src/user_prompt.jinja` |
| Config / LiteLLM | `src/shared/config.py`, `src/shared/defaults.py` |
| Labels in DB | `ModelCall`, `Identification`, `TranscriptSegment` in `src/app/models.py` |
| Cleanup / retention | `src/app/writer/actions/cleanup.py`, `docs/plans/data_retention_improvement.md` |

## Bottom line

Fine-tune a **small open instruct model (start Qwen3-4B, QLoRA SFT)** on **Podly’s existing prompt→JSON contract**, using **teacher `ModelCall` silver labels plus a human gold eval set**, with **precision and false-positive content seconds** as promotion gates. Serve it as a drop-in OpenAI-compatible endpoint behind LiteLLM. Treat encoder/audio approaches as fallbacks; fix **metadata retention** before expecting a large in-house corpus.
