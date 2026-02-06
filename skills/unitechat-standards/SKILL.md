---
name: unitechat-standards
description: Enforce UniteChat design and engineering standards. Use when implementing or reviewing UI/UX changes (especially chat layout, icons, spacing, typography, color hierarchy) or backend Python changes (API routes, parsing, normalization, search logic). Apply this skill to keep frontend style minimal and consistent (Claude-like neutral design language) and backend code predictable, typed, and safe.
---

# UniteChat Standards

Apply a single, coherent language across frontend and backend changes.

## Workflow

1. Identify scope first:
- Frontend/UI work: load `references/frontend.md`.
- Backend/Python work: load `references/backend.md`.
- Full-stack work: load both reference files.

2. Preserve existing architecture:
- Do not rewrite structure unless the task requires it.
- Prefer local, reversible edits over broad refactors.

3. Validate before finishing:
- Frontend changes: run `npm run build` in `frontend/`.
- Backend changes: run targeted checks or tests relevant to touched files.

4. Report outcomes with file references:
- List what changed, why it changed, and what was validated.

## Guardrails

- Remove visual noise rather than adding decoration.
- Keep iconography as simple line icons; avoid emoji UI symbols.
- Keep spacing/type scales token-driven and consistent.
- Keep backend logic explicit, typed, and side-effect aware.
- Never mix unrelated style systems inside one change.

## Do Not

- Introduce one-off visual styles that ignore existing tokens.
- Add large abstractions for small local fixes.
- Return unvalidated frontend changes.
