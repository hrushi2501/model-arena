---
name: frontend-ui
description: Build or change Model Arena's Next.js operator interface, visual system, controls, and interactions. Use for frontend features, dashboard pages, styling, responsive behavior, or UI review.
---

# Model Arena frontend UI

Use the existing Next.js App Router, TypeScript, Bun workspace, Biome, Tailwind styling, and installed UI primitives. Inspect the relevant page, component, CSS tokens, and API client before adding a pattern or dependency. The frontend is an operator console for live model releases: make system state, evidence, and consequences easy to see.

## Visual system

- The default theme is dark. Use true black (`#000`) for the page canvas and true white (`#fff`) for primary text and inverse surfaces. The light theme reverses these values.
- Do not use gray-filled backgrounds, gray cards, gray gradients, or gray-tinted page sections. Use black/white surfaces, spacing, typography, and fine low-opacity borders to establish hierarchy. Muted text may use opacity or a carefully selected accessible neutral text token; it must not become a gray-filled surface.
- Reserve saturated hues for small, meaningful signals such as success, warning, failure, or the selected action. Do not let accent color replace the monochrome foundation. Never signal rollout state by color alone; include text or an icon/shape.
- Provide a visible theme toggle. Start in dark mode regardless of the operating system preference; persist the operator's explicit light/dark choice. Avoid a hydration flash, and ensure the control is keyboard accessible and announces its state.
- Define theme colors as shared CSS variables/design tokens and consume them consistently. Keep charts legible in both themes and use the same semantic state mapping as the rest of the console.
- Build responsive layouts for the actual operator tasks: compare versions, inspect rollout stage and traffic share, read metric evidence, act on a rollout, and inspect audit history. Keep destructive controls distinct and require confirmation where an action is difficult to reverse.

## Interaction and motion

- Every animation needs a functional purpose: feedback, continuity, spatial relationship, or explanation. Skip decorative motion on frequently repeated actions.
- Make controls feel immediate. Prefer short, interruptible transitions for transform and opacity; avoid broad `transition: all`, sluggish entrances, and animations that block operator actions.
- Preserve layout stability as metrics or rollout states update. Reserve space for loading/error/empty states and avoid moving primary controls as data arrives.
- Respect `prefers-reduced-motion`. Do not animate critical status in a way that could look like an active state when it is not.
- Keep charts truthful: show units, time window, model/version, sample count, and missing-data state. Never fabricate sample data or make unavailable metrics look like zero.
- Use semantic HTML, labels, focus-visible states, keyboard-operable controls, and sufficient contrast in both themes. Make live changes understandable to assistive technology without announcing every metric tick.

## Data and app boundaries

- The browser must call Next.js same-origin routes. Server-side Next.js handlers proxy to FastAPI using `MODEL_ARENA_API_URL`; do not expose backend service URLs or secrets to browser code.
- Derive TypeScript response types from the current API contract or map them explicitly. Do not invent endpoint fields. Show loading, error, empty, stale, and success states.
- Rollout actions must reflect server-confirmed state and return a clear result. Disable or guard invalid transitions based on the state machine; never simulate a successful promote, pause, or rollback in the UI.
- Prefer existing components and installed dependencies. Keep page-specific composition readable and avoid abstraction layers that only wrap a single use.

## Source note

This project-specific adaptation draws on the animation and design-engineering guidance in [Emil Kowalski's `emil-design-eng` skill](https://github.com/emilkowalski/skills/tree/main/skills/emil-design-eng) (MIT). The original skill is broader; these instructions are tailored to Model Arena and its explicit monochrome theme.
