---
name: unitechat-standards
description: Enforce UniteChat design and engineering standards. Use for any frontend UI/UX change or backend Python change. Prioritize extreme minimalism by default: keep one primary action, auto-apply after user selection, remove redundant UI operations, and avoid advanced entry points unless explicitly required. Keep frontend Claude-like and neutral; keep backend behavior explicit, typed, predictable, and safe.
---

# UniteChat Standards

Apply a single, calm language across frontend and backend changes.

## Workflow

1. Identify scope first:
- Frontend/UI work: load `references/frontend.md`.
- Backend/Python work: load `references/backend.md`.
- Full-stack work: load both reference files.

2. Apply minimalism defaults first:
- Keep one primary action per area.
- Run follow-up steps automatically after an explicit selection.
- Remove duplicate controls that lead to the same result.
- For data-source management, enforce strict single-root flow: pick one root folder, then auto-sync/import subfolders.
- Keep root path read-only in UI; allow root changes only via one picker button.
- Do not expose `Advanced` or manual source-creation entry points in data-source settings.

3. Preserve existing architecture:
- Do not rewrite structure unless the task requires it.
- Prefer local, reversible edits over broad refactors.

4. Validate before finishing:
- Frontend changes: run `npm run build` in `frontend/`.
- Backend changes: run targeted checks or tests relevant to touched files.

5. Report outcomes with file references:
- List what changed, why it changed, and what was validated.

## Guardrails

- Remove visual noise rather than adding decoration.
- Prefer direct, single-step flows over multi-control forms.
- Keep iconography as simple line icons; avoid emoji UI symbols.
- Keep spacing/type scales token-driven and consistent.
- Keep backend logic explicit, typed, and side-effect aware.
- Never mix unrelated style systems inside one change.

## Do Not

- Introduce one-off visual styles that ignore existing tokens.
- Add extra buttons for actions that can run automatically after selection.
- Reintroduce manual source-management controls when single-root flow is active (`Add Source`, `Advanced`, per-row `Rename`, status filler columns, editable per-row path).
- Add large abstractions for small local fixes.
- Return unvalidated frontend changes.
