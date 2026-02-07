# Frontend Standards (UniteChat)

## Design Direction

- Target: minimal, calm, readable, neutral "Claude-like" language.
- Prefer subtle contrast and 1px structure over heavy shadows.
- Favor consistency over novelty.
- Default to fewer controls and fewer decisions.

## Core Rules

- Use neutral palette variables from `frontend/src/index.css`.
- Keep one visual rhythm per area (header, sidebar, message body).
- Keep message layout in a shared column with slight role-based offset only.
- Avoid emoji as UI icons; use line SVG icons with consistent stroke.
- Keep one primary action per functional block.
- Remove duplicate actions when one can imply the other.

## Flow Minimalism

- For picker flows, auto-run the next step after user selection.
- Do not require extra "Run"/"Apply" clicks if selection is explicit.
- Keep destructive actions explicit and confirmed; keep non-destructive actions implicit.
- Keep labels short and operational (`Choose Folder`, `Save`, `Delete`).
- Prefer progressive disclosure over long always-visible forms.
- In settings pages, prefer single-root configuration over per-item path management.
- For single-root data-source UIs, enforce these hard rules.
- Keep root path read-only.
- Allow root changes only through one explicit picker button.
- Auto-import after root selection; no extra scan/apply button.
- Do not show `Add Source` or `Advanced` entry points.
- Do not show per-row `Rename` button when name is inline-editable.
- Do not show per-row path editing.
- Do not keep filler columns (for example status-only columns that do not change user decisions).

## Typography

- UI text: `var(--font-ui)`.
- Reading text: `var(--font-reading)`.
- Keep body line-height around 1.68-1.76 for long text.
- Avoid abrupt weight jumps (e.g., 400 -> 700) unless semantic priority is clear.

## Spacing + Shapes

- Use radius in a narrow band (8, 10, 12, 14, 16).
- Keep control paddings compact and consistent.
- Avoid mixing many spacing scales in one component.

## Icons

- Use inline SVG line icons.
- Typical sizes: 14/16/18 px.
- Typical stroke width: 1.2-1.6.
- Keep icon color tied to text hierarchy.

## Interaction

- Hover states should adjust background/border subtly.
- Avoid aggressive scale or bounce on utilitarian controls.
- On mobile, avoid hover-only affordances for essential actions.
- Keep transition timing short and smooth (roughly 120-220ms for utility UI).

## Review Checklist

- Are icons visually consistent and emoji-free?
- Are chat/user/assistant blocks aligned on a common grid?
- Is contrast readable without looking harsh?
- Does this component introduce style noise compared to neighbors?
- Can the same goal be completed with fewer visible controls?
