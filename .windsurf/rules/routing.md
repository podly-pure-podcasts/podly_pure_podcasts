---
trigger: always_on
---

## Routing and State Rule (Prevent Remount Bugs)

When adding new routes under an existing section:

- Use nested routing and a shared layout so the left sidebar and header do not remount.
- Do not duplicate “fetch feeds list” in child pages.
- Add a dev-only guard that warns if the same list endpoint is fetched multiple times due to remounting.
