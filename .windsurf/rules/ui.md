---
trigger: always_on
---

## UI Parity Rule (Non-Negotiable)


When adding or changing any view inside an existing section (e.g. Podcasts), you MUST:

1) **Reuse the existing layout tree** (same sidebar, same header, same routing parent) so navigation does not remount state or refetch lists.
2) **Reuse the same primitives** (cards, modals, buttons, filters) — no “similar” clones.
3) **Prove parity**:
   - Provide before/after screenshots OR a short screen recording
   - Confirm there is exactly one feed-list fetch on navigation (no duplicate queries)
   - Confirm filter placement matches the canonical view

If you cannot achieve parity by composition, STOP and refactor to enable reuse before shipping.

