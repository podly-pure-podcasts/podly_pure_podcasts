---
trigger: model_decision
---

## RSS Compatibility Rule (New)

Any UI feature that relies on podcast-app behaviour must be implemented across multiple RSS fields:

- Always populate:
  - `<link>` (for tap-through behaviour)
  - `<description>`
  - `<content:encoded>` (with `xmlns:content`)
- The content must apply to **all items** in the feed (historical + new), because podcast apps cache aggressively.
- Add one smoke script that:
  - fetches the combined feed
  - asserts that a known GUID includes the processing CTA in description/content:encoded
  - asserts `<link>` points to the trigger page
