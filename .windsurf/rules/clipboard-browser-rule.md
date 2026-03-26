---
trigger: model_decision
---

## Clipboard / Browser Capability Rule (New)

Anything “Copy …” must:

- Work in secure contexts and degrade gracefully outside them.
- Implement fallback: `document.execCommand("copy")` or manual select + “Press Ctrl/Cmd+C” UI.
- Must show the user the actual value being copied.
- Must log a clear non-secret error when copy fails (e.g. insecure context, missing permissions).
