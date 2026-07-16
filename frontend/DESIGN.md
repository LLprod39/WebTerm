# WebTerm — Design System

User-selectable UI styles (Dashboard → **Настроить виджеты**, per-user localStorage):

| Id | Look |
| --- | --- |
| `catalog` | Editorial ops: ink, acid lime, Syne + IBM Plex Mono, hard offset shadows |
| `classic` | Previous console: teal, Inter + JetBrains Mono, soft elevation, violet AI |
| `pulse` | Violet night ops: orchid primary, cyan AI, Outfit + DM Sans, soft glass + aurora glow |
| `signal` | Brutal ops: carbon black, amber alarm, Space Grotesk + mono, zero radius, stamp shadows, tactical grid |
| `folio` | Folio **light**: warm cream paper, terracotta ink, Fraunces + Manrope |
| `folio-dark` (**default**) | Folio **dark**: same editorial language, night paper surfaces |

Tokens: `html[data-ui-style="…"]` in `src/index.css`. Provider: `src/lib/ui-style.tsx`. Switcher: `DashboardUiStyleSwitcher` inside widget edit mode. Default is `folio-dark` for every account without a saved preference. `folio` is the only light `color-scheme`.

## 1. Color System

- **Mode:** Dark-first (`hsl(var(--...))`)
- **Ink / bone**
  - `--background` — near-black ink `#09090b`
  - `--foreground` — bone `#f4f1ea`
- **Surfaces:** `--surface-0` … `--surface-3`, `--card`, `--popover`
- **Primary (acid lime `#c8f542`):** buttons, active nav, focus ring, kickers
- **AI accent (sky):** `--ai` — agents / AI panels only, not primary CTAs
- **Status:** success / warning / destructive / info
- **Contrast:** WCAG AA for text

## 2. Typography

- **UI body:** `IBM Plex Mono` (`font-sans` / `font-mono`)
- **Display:** `Syne` (`font-display`) — titles, metrics, dialog titles
- **Scale utilities** (`index.css`):
  - `.type-display` — large metric / hero number
  - `.type-h1` / `.type-h2` / `.type-h3`
  - `.type-body` / `.type-body-sm`
  - `.type-label` — 2xs, uppercase, wide tracking
- **Floor:** never below `text-2xs` (11px)

## 3. Geometry & Elevation

- **Radius:** `0.25rem` (`rounded-sm`) — sharp catalog edges, not pill SaaS
- **Shadows:** hard offset — `--shadow-1/2/3` (`2px/4px/8px  … 0 black`)
- **Borders:** solid `border` / `border-strong`, avoid heavy translucency stacks

## 4. Components

- **Buttons:** solid primary with hard shadow; outline = border only
- **Cards / panels:** `rounded-sm border border-border bg-card shadow-elev-1`
- **Dialogs / sheets / menus:** hard border, solid surface, `shadow-elev-3`, no heavy blur glass
- **Tabs:** active tab = primary fill
- **Inputs:** `bg-surface-0`, sharp corners, ring on focus
- **Badges:** uppercase 2xs mono labels
- **Sidebar:** acid left bar on active item; display wordmark

## 5. Motion

- **Ease:** `--ease-standard: cubic-bezier(0.16, 1, 0.3, 1)`
- Prefer opacity/transform over soft glows

## 6. Voice & Tone

- Professional, concise, ops-facing
- Russian primary, English secondary
- No marketing hype; standard IT labels

## 7. Anti-patterns

- Avoid teal→violet gradients and purple “AI SaaS” chrome
- Avoid large soft blur overlays on every panel
- Avoid Inter / generic rounded-xl card stacks as the default look
- Avoid mixing random English into Russian UI

## 8. How restyles cascade

Tokens live in `src/index.css`. Most pages use `PageShell`, shadcn primitives, and semantic colors — they pick up this system automatically. One-off pages with hard-coded teal/violet classes may still need local cleanup.
