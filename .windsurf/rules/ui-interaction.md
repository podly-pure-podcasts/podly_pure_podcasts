---
trigger: always_on
---

## UI Interaction Reliability Rule (Clipboard, Links, and Public Pages)

UI actions must work in real browser security contexts.

- If using `navigator.clipboard`, you MUST implement a fallback:
  - Show the value in a readonly input
  - Provide a “Select all” affordance
  - Fallback copy via a temporary textarea (`document.execCommand('copy')`) if clipboard API fails
- Any “Open link” button must not depend on a fragile secondary API call to generate the link.
  - Prefer server-returned `trigger_url` / `enclosure_url` included in the primary response payload.
- Public trigger pages must be accessible without login by design and must not require app session cookies.
- If a button fails, show an error message that includes the failing step (e.g. “Failed to fetch trigger URL” vs “Failed to copy”).
