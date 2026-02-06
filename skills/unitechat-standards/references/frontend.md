# Frontend Standards (UniteChat)

## Design Direction

- Target: minimal, calm, readable, neutral "Claude-like" language.
- Prefer subtle contrast and 1px structure over heavy shadows.
- Favor consistency over novelty.

## Core Rules

- Use neutral palette variables from `frontend/src/index.css`.
- Keep one visual rhythm per area (header, sidebar, message body).
- Keep message layout in a shared column with slight role-based offset only.
- Avoid emoji as UI icons; use line SVG icons with consistent stroke.

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

## Review Checklist

- Are icons visually consistent and emoji-free?
- Are chat/user/assistant blocks aligned on a common grid?
- Is contrast readable without looking harsh?
- Does this component introduce style noise compared to neighbors?
