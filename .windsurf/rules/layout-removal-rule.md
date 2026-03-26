---
trigger: model_decision
---

## No Layout Remount Rule (New)

If you introduce nested routes inside a section:

- The sidebar + header must live in the parent layout route.
- Child routes must render only the right-hand content panel.
- Add a dev-only guard that warns if the feeds list is fetched more than once during in-section navigation.
