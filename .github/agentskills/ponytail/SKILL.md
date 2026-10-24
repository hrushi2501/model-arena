---
name: ponytail
description: Keep Model Arena coding work to the smallest complete, maintainable change. Use for implementation, bug fixing, refactoring, review, and dependency choices.
---

# Ponytail for Model Arena

Follow the required progress workflow in root `AGENTS.md`: read [progress.md](../../../progress.md) and [checklist.md](../../../checklist.md), respect lane ownership, and update task status and verification evidence in the same meaningful change. Check tasks only when their acceptance evidence exists; preserve other lanes' updates.

Prefer the smallest change that fully satisfies the request. Before editing, trace the affected code and its callers, configuration, contracts, and relevant checks. Reuse existing project patterns and installed tools; add a layer, dependency, option, or service only when it solves a concrete requirement.

Small must still mean complete: preserve validation at trust boundaries, error handling, accessibility, security, and every behavior the user asked for. For non-trivial new logic, add or update a focused check when the task allows it. Avoid unrelated cleanup and speculative extensibility. Keep comments for rationale that the code cannot express.

Do not use this skill to avoid necessary investigation or verification, and do not force response-format rules onto the user. Follow `AGENTS.md`, the relevant domain skill, and the user's current request when they provide more specific direction.

## Source note

Adapted for this repository from [Dietrich Gebert's Ponytail skill](https://github.com/DietrichGebert/ponytail/tree/main/skills/ponytail), distributed under the MIT License. This adaptation omits upstream session commands and response-format instructions that do not fit repository-level guidance.
