---
trigger: always_on
---

## Data Retrofitting Rule (Backward Compatibility)

When adding new metadata or content that affects clients (RSS, descriptions, links, schemas), you MUST ensure it applies to historical data.

- Prefer render-time enrichment (e.g. RSS generation) so older records automatically benefit.
- If render-time enrichment is not possible, run a one-off backfill migration/script and document it.
- Add a stable marker to avoid duplication when appending content (e.g. `<!-- PODLY_TRIGGER_CTA -->`).
