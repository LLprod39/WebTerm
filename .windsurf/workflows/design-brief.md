---
description: Create a structured DESIGN.md design system file from a brief (natural language or I-Lang format) using the open-design design-brief skill
---

# Design Brief → DESIGN.md

Read and execute the full design-brief skill:

1. Read `C:\open-design\skills\design-brief\SKILL.md` — this contains the complete workflow
2. Follow all steps in the skill exactly:
   - Accept the user's brief (natural language or I-Lang format)
   - Convert natural language to I-Lang using the mapping table in the skill
   - Validate all 8 dimensions (palette, accent, typography, display, layout, mood, density, exclude)
   - Apply default resolution rules for unspecified dimensions
   - Generate `DESIGN.md` with all 9 sections using only the resolved token values
   - Generate `brief-preview.html` with color swatches, typography specimens, spacing ruler, and component preview
   - Report which dimensions were resolved from defaults and why

## Input formats

**Natural language:**
> "I need a landing page for a developer tool. Clean, minimal, dark mode. Inter font. No flashy animations."

**I-Lang structured:**
```
[PLAN:@DESIGN|type=saas_landing]
  |palette=navy_and_white|accent=coral
  |typography=inter|display=space_grotesk
  |mood=professional_minimal
  |density=spacious
```

## Output

- `DESIGN.md` — complete 9-section design system file
- `brief-preview.html` — visual token preview page
