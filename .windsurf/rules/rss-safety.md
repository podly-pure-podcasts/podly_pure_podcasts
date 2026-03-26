---
trigger: always_on
---

## RSS Client Safety Rule (No Side Effects on Fetch)

RSS clients probe aggressively. Therefore:

- Feed fetches (RSS XML) must be non-mutating.
- Enclosure requests must be non-mutating.
- Any action that triggers work must be explicit and isolated behind a dedicated “trigger” endpoint/page.
- Never rely on user-agent or Range heuristics as the primary gate for starting jobs.
