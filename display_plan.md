# Frontend Design Unification Plan: "Claude-like" Aesthetic

## 1. Executive Summary

This plan outlines the steps to unify the UniteChat frontend design language. The goal is to elevate the entire application to the visual standard set by the new **Settings Modal**, which follows a "Claude/Apple" design philosophy: **warm neutrals, refined typography, subtle containment, and high-quality vector iconography**.

The current state suffers from "Design Fragmentation":
-   **Settings**: Modern, variable-based, clean.
-   **Sidebar**: Legacy inline styles, inconsistent hex colors, slightly "muddy" contrast.
-   **Chat View**: Mix of variables and hardcoded values, inconsistent header visuals.
-   **Icons**: Mix of high-quality SVGs (Sidebar) and low-fidelity Unicode characters (Thinking/WebSearch blocks).

## 2. Infrastructure & Design Tokens (`src/index.css`)

**Analysis:**
Currently, `SettingsModal.css` introduces several excellent local variables (implicitly) or follows strict hex codes that should be global standard. We need to lift these into the global scope to ensure "One Source of Truth".

**Action Plan:**
-   **Define Panel Colors**: Promote the specific "warm card" background used in Settings (`#FDFBF9`) to a global `--bg-panel`.
-   **Standardize Borders**: Define strict border hierarchies:
    -   `--border-soft`: `#E5E0DB` (Dividers, light inputs) - *Existing, enforce usage.*
    -   `--border-medium`: `#D8CBBE` (Active states, button borders).
-   **Typography**:
    -   Ensure headers use `--font-reading` (Serif) effectively, not just for body text.

## 3. Component Deep-Dive

### A. The Sidebar (`Sidebar.jsx`) - *Critical Priority*

**Analysis:**
-   **Current State**: Massive usage of **Inline Styles** (e.g., `style={{ background: '#F4F1EC' }}`). This makes it impossible to theme and inconsistent with global variables.
-   **Visual Gap**: The grey background (`#F4F1EC`) is slightly "cooler" or "dirtier" than the warm beige of the rest of the app (`#FDFBF9` or `--bg-base`).
-   **Interaction**: Hover states are managed via JS events (`onMouseEnter`) instead of CSS `:hover`, causing unnecessary re-renders and jitter.

**Refactor Plan:**
1.  **Extract CSS**: Create `frontend/src/components/Sidebar.css`.
2.  **Remove JS Styling**: Delete all `style={{...}}` props and JS-based hover logic.
3.  **Harmonize Colors**:
    -   Background: Change from `#F4F1EC` to `--bg-base` (or a specific sidebar opacity variant).
    -   Item Active State: mimic the "Settings Side Item" style (subtle darkening, strong text).
4.  **Layout**: Ensure the top bar height matches `ChatView` header pixel-perfectly (`64px` or `var(--topbar-h)`).

### B. Chat Area (`ChatView.jsx` / `.css`)

**Analysis:**
-   **Header**: Currently uses a hardcoded white/off-white background that disconnects it from the sidebar line. It should feel like a continuous "paper" sheet or have a very subtle separation.
-   **Typography**: The title font weight and spacing need slight tightening to match the "Settings" headers.
-   **Meta Tags**: The "Model" and "Reasoning" badges look a bit "engineering-heavy". They should be lighter, like small capsule pills with minimal borders.

**Refactor Plan:**
-   **Unified Header**: Use `--bg-panel` or transparency with a backdrop blur for the header to modernized it.
-   **Button Styles**: Update "Search" and "Exit" buttons to match the "Settings Button" styles (clean styling, no heavy shadows).

### C. Thought & Search Blocks (`ThinkingBlock`, `WebSearchBlock`)

**Analysis:**
-   **The "Unicode" Problem**: Using characters like `◷` (White Left-Pointing Index), `›`, `◉` makes the UI look cheap on high-DPI screens. They render differently on every OS (Windows/Mac/Android).
-   **Inconsistency**: Sidebar uses nice SVG stroke icons. These blocks use blocky generic fonts.

**Refactor Plan:**
-   **Vectorize**: Replace all unicode characters with inline SVG equivalents that share the `stroke-width` (approx 1.5px) and `stroke-linecap="round"` of the Sidebar icons.
-   **Animation**: The "Thinking" collapse animation in CSS is good, but the trigger button needs better hover feedback (opacity change vs background change).

### D. Message Bubbles (`MessageItem.css`)

**Analysis:**
-   **User Bubbles**: The background color `#f1eee7` is *okay*, but could be slightly warmer/lighter to reduce visual weight.
-   **Spacing**: Ensure padding inside bubbles matches the standard grid (multiples of 4px).

## 4. Execution Sequence

1.  **Global CSS Update**: Establish the variables.
2.  **Sidebar Refactor**: The biggest debt repayment. Move to CSS classes.
3.  **Icon Standardization**: Fix `Thinking` and `WebSearch` blocks.
4.  **Visual Polish**: Fine-tune margins, shadows, and hover states across the board.

## 5. Success Metric
The UI is considered "Unified" when:
-   No component uses inline styles for layout/color.
-   All borders use the same 1-2 hex codes (variables).
-   All icons share the same stroke weight style.
-   The transition from Settings to Sidebar to Chat feels seamless, like one continuous physical "paper-like" surface.
