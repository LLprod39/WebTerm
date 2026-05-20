---
name: open-design
description: Skill-driven design and implementation based on Open Design principles. Use when creating new applications, UI components, or design artifacts to ensure high fidelity and brand consistency through a structured Discovery Loop and DESIGN.md enforcement.
---

# Open Design

## Overview
This skill enables a "local-first" design workflow where AI agents act as designers and engineers following a structured protocol. It prioritizes design-system-first thinking and interactive discovery before implementation.

## The Discovery Loop
Before writing any code for a new feature or application, you MUST perform a "Discovery" phase. This prevents wasted tokens and ensures alignment with user expectations.

1. **Emit Discovery Form:** If the user request is broad, present a set of clarifying questions. Use `assets/DISCOVERY_FORM.md` as a guide.
2. **Wait for Clarification:** Do not proceed until the audience, tone, and scope are defined.
3. **Offer Visual Directions:** Propose 3-5 visual styles (e.g., "Modern Minimal", "Brutalist") if no brand is specified.

## Design Enforcement (`DESIGN.md`)
Always look for a `DESIGN.md` file in the project or relevant directory. If none exists, propose creating one using `references/DESIGN_TEMPLATE.md`.

- **Strict Adherence:** All CSS, Tailwind, or styled-components must use tokens (colors, typography, spacing) defined in `DESIGN.md`.
- **Tokenization:** Use semantic tokens (e.g., `brand-primary`) instead of hardcoded hex values.

## Artifact Generation
When generating UI, wrap the output in `<artifact>` tags if the environment supports it (or just use clear Markdown blocks with file paths).
- **Fidelity:** Aim for high-fidelity prototypes using modern CSS (OKLch, Container Queries).
- **Interactive Feedback:** Propose a "Pre-flight" check where you describe the design before implementation.

## Resources

### references/
- **[DESIGN_TEMPLATE.md](references/DESIGN_TEMPLATE.md)**: A comprehensive schema for brand identity (Color, Typography, Spacing, Layout, Components, Motion, Voice, Brand, Anti-patterns).

### assets/
- **[DISCOVERY_FORM.md](assets/DISCOVERY_FORM.md)**: Standard template for the initial brief.
