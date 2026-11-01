---
name: context-handoff
description: Orchestrator writes CONTEXT.md once with the goal, requirements, decisions, relevant files, and acceptance criteria. Other agents read it first and never re-ask.
---

The orchestrator writes `CONTEXT.md` once (project root, or `.agents/context.md`). Include the goal, requirements, decisions already made, relevant files, and acceptance criteria.

Every other agent reads that file first. Do not ask again for anything already written there.
