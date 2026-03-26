---
trigger: always_on
---

## Modal Rule (New)

All modals in a section must be implemented as a single shared component.

- No duplicated modal implementations across pages.
- The shared modal must handle long content correctly:
  - `min-h-0` on flex parents
  - scroll container uses `overflow-y-auto` and is the only scroll region
- Any change to the modal must be verified using a known long-description episode (screenshot required).
