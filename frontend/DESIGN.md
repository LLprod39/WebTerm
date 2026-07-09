# WEU AI Platform — Design System

## 1. Color System

- **Mode:** Dark-first (CSS custom properties via `hsl(var(--...))`)
- **Semantic Tokens (shadcn/ui):**
  - `--background` / `--foreground` — base surfaces and text
  - `--card` — elevated card surfaces
  - `--primary` — brand accent (buttons, active states)
  - `--secondary` — subtle fills, hover states
  - `--muted` / `--muted-foreground` — subdued text, labels
  - `--border` — dividers, card borders
  - `--destructive` — error, danger actions
- **Status Colors:**
  - `emerald-500` — success / healthy / allowed
  - `amber-500` — warning / attention
  - `red-500` — critical / error / denied
  - `blue-400` — info / active
  - `violet-500` — groups / secondary accent
- **Contrast:** WCAG AA minimum for all text

## 2. Typography

- **Font Stack:** `Inter` (`font-sans`), `JetBrains Mono` (`font-mono`)
- **Scale utilities** (defined in `index.css @layer utilities`; adopt these instead of ad-hoc sizes):
  - `.type-display` — 28/34, semibold, tracking-tight (hero numbers, marketing)
  - `.type-h1` — 22/28, semibold, tracking-tight (page title)
  - `.type-h2` — 18/24, semibold (section title)
  - `.type-h3` — 15/20, semibold (card title)
  - `.type-body` — 13/20 (default body)
  - `.type-body-sm` — 12/20 (secondary body)
  - `.type-label` — `text-2xs` (11px), semibold, uppercase, tracking-wide, muted (labels/kickers)
- **Floor:** never go below `text-2xs` (11px). No `text-[10px]`/`text-[9px]`. The only exception is
  non-textual preview glyphs inside scaled swatches (e.g. terminal font-size preview).
- **Weights:** `font-medium` (body), `font-semibold` (headings), `font-bold` (emphasis)

## 3. Spacing & Grid

- **Base Unit:** 4px
- **Container:** max-width `7xl` (`max-w-7xl mx-auto`)
- **Section Gap:** `space-y-6`
- **Card Padding:** `px-5 py-4` (header), `p-5` (body)
- **Grid System:** 12-column CSS grid with responsive breakpoints

## 4. Components

- **Cards:** `rounded-xl border border-border bg-card shadow-sm`
- **Section Cards (SettingsSectionCard):**
  - Header: icon (8×8 rounded-lg `bg-primary/10`), title, description, optional actions
  - Body: `p-5`
- **Buttons:** shadcn/ui `Button` — variants: default, outline, ghost, destructive
- **Inputs:** shadcn/ui `Input` — height `h-9`, border-border
- **Select:** shadcn/ui `Select` or native `<select>` with `h-9 rounded-lg border`
- **Switch:** shadcn/ui `Switch`
- **Badge:** shadcn/ui `Badge` — default, secondary, outline
- **StatusBadge:** custom — dot + text, tones: info, success, warning, danger, neutral
- **Avatar:** initials in colored circle, `h-10 w-10 rounded-full`

## 5. Motion

- **Transitions:** `transition-all duration-200`
- **Hover:** `hover:bg-secondary/20`, `hover:border-border`
- **Focus:** `focus:border-primary/40 focus:ring-1 focus:ring-primary/30`
- **Animations:** Framer Motion for layout shifts, accordion expand/collapse

## 6. Voice & Tone

- **Principles:** Professional, concise, corporate B2B
- **Language:** Russian primary, English secondary
- **Rules:**
  - No marketing hype or AI-generated buzzwords
  - No sci-fi terminology ("Fleet Health", "Control Center", "System Overview")
  - Use standard IT terminology ("Серверы", "Панель администратора", "Настройки")
  - Labels: short, dry, descriptive
  - Descriptions: one line, factual
  - Use "вы" form, not "ты"

## 7. Layout Patterns

- **Settings Pages:**
  - Header: icon + title + description (one line)
  - Stats bar: horizontal metrics in `rounded-xl border bg-card/secondary`
  - Two-column: content (left) + sidebar (right, sticky)
  - Cards list: vertical stack of expandable cards
- **Forms:**
  - Labels above inputs
  - Grid layout for multi-field forms
  - Actions at bottom: primary Save + ghost Cancel

## 8. Anti-patterns

- **Avoid:** Flashy colored backgrounds on cards (`bg-emerald-950/10`)
- **Avoid:** `bg-white/[0.03]` and `bg-white/[0.06]` — use design tokens instead
- **Avoid:** Hardcoded `ring-white/[0.06]` — use `border-border` tokens
- **Avoid:** Inconsistent select styling (native vs shadcn mixed)
- **Avoid:** Oversized headers (`text-2xl font-bold`) on sub-pages
- **Avoid:** Random English words mixed into Russian UI ("staff", "override")
