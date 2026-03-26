---
trigger: always_on
---

## Production Proof Rule (New, non-negotiable)

If a bug is reported in production (500s, broken links, wrong favicon, auth issues), you must:

- Capture the exact production error (traceback or structured error log) OR reproduce locally with the same code path.
- Fix the exact cause.
- Provide proof:
  - `curl -i` against the actual production URL shows correct status (not 500).
  - A corresponding log line shows the decision and no traceback.
No “might be undeployed” speculation is allowed as a conclusion.
