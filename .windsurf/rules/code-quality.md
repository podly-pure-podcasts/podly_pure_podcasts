---
trigger: always_on
---

## Code Quality

- Readability over brevity.
- Small functions with single responsibility.
- Clear, descriptive naming (no vague “data”, “thing”, “handler2”).
- No magic constants: extract to named constants with units in the name (e.g. `PROBE_MAX_BYTES`).
- Explicit error handling everywhere; failures must be visible and actionable.
- Keep side effects contained (I/O, DB writes, network calls) and easy to reason about.

