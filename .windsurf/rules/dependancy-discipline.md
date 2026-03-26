---
trigger: always_on
---

## Dependency Discipline

- Ask before adding any new dependency.
- Prefer native platform APIs and existing project utilities first.
- If a dependency is required:
  - Justify it (why built-in or existing libs are insufficient)
  - Lock versions
  - Remove unused dependencies in the same change if discovered
