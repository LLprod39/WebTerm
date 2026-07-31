# WebTerm — Design System

User-selectable UI styles (Dashboard → **Настроить виджеты**, per-user localStorage):

| Id | Look |
| --- | --- |
| `catalog` | Editorial ops: ink, acid lime, Syne + IBM Plex Mono, hard offset shadows |
| `classic` | Previous console: teal, Inter + JetBrains Mono, soft elevation, violet AI |
| `pulse` | Violet night ops: orchid primary, cyan AI, Outfit + DM Sans, soft glass + aurora glow |
| `signal` | Brutal ops: carbon black, amber alarm, Space Grotesk + mono, zero radius, stamp shadows, tactical grid |
| `folio` | Folio **light**: warm cream paper, terracotta ink, Fraunces + Manrope |
| `folio-dark` | Folio **dark**: same editorial language, night paper surfaces |
| `flow` | AI-native SaaS **light**: off-white canvas, white cards, near-black CTAs, Inter + Manrope |
| `flow-dark` (**default**) | Flow at night: graphite cards, white CTAs, same language |
| `ashita` | **ASHITA // Sakura Rift** — dark Japanese atmospheric ops: navy hush, sakura primary, cyan AI, controlled glitch |

Tokens: `html[data-ui-style="…"]` in `src/index.css`. Provider: `src/lib/ui-style.tsx`. Switcher: `DashboardUiStyleSwitcher` inside widget edit mode. Default is `flow-dark` for every account without a saved preference. Light `color-scheme` skins: `folio`, `flow`.

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

### ASHITA palette (dark Japanese atmospheric ops)

| Role | Token / hex direction |
| --- | --- |
| Base night | `#080A10` / `--background` 225 33% 5% |
| Sakura primary | `#D66AB5` / `--primary` 318 57% 63% |
| Cyan AI / ring | `#49D4D1` / `--ai`, `--ring` 179 62% 56% |
| Glitch red | `#E14B5F` / `--destructive` only |
| Moon blue haze | soft radial in `--shell-glow` (upper right) |

**Rule of atmosphere:** 90% matte dark silence; 10% sakura, cyan, controlled digital glitch.

## 2. Typography

- **UI body:** `IBM Plex Mono` (`font-sans` / `font-mono`) — catalog default language
- **Display:** `Syne` (`font-display`) — titles, metrics, dialog titles
- **ASHITA:** UI `Manrope`, display `Space Grotesk`, mono `JetBrains Mono`
- **Scale utilities** (`index.css`):
  - `.type-display` — large metric / hero number
  - `.type-h1` / `.type-h2` / `.type-h3`
  - `.type-body` / `.type-body-sm`
  - `.type-label` — 2xs, uppercase, wide tracking
- **Floor:** never below `text-2xs` (11px)

## 3. Geometry & Elevation

- **Radius:** `0.25rem` (`rounded-sm`) — sharp catalog edges, not pill SaaS
- **ASHITA radius:** `0.625rem` — soft but not pill
- **Shadows:** hard offset — `--shadow-1/2/3` (`2px/4px/8px  … 0 black`) for catalog; ASHITA uses deep soft elevation with faint sakura/cyan edge, not neon halo
- **Borders:** solid `border` / `border-strong`, avoid heavy translucency stacks

## 4. Components

- **Buttons:** solid primary with hard shadow; outline = border only
- **ASHITA primary:** solid sakura, dark label, inset top light; hover = slight lift + 1px cyan/red chromatic split
- **Cards / panels:** `rounded-sm border border-border bg-card shadow-elev-1`
- **ASHITA panels:** matte surface gradient, thin top accent (primary → ai) on enterprise panels only
- **Dialogs / sheets / menus:** hard border, solid surface, `shadow-elev-3`, no heavy blur glass
- **Tabs:** active tab = primary fill
- **Inputs:** `bg-surface-0`, sharp corners, ring on focus; ASHITA focus ring is cyan with faint sakura inner edge
- **Badges:** uppercase 2xs mono labels
- **Sidebar:** acid left bar on active item; display wordmark
- **ASHITA sidebar:** near-black corridor; active row = surface-2 + sakura left bar + cyan icon

## 5. Motion

- **Ease:** `--ease-standard: cubic-bezier(0.16, 1, 0.3, 1)`
- Prefer opacity/transform over soft glows
- **ASHITA:** interactions 140–220ms; background petal drift 32–50s; disable drift + chromatic animation under `prefers-reduced-motion`
- **Controlled glitch only on:** primary CTA hover, active nav, selected rows, accent-gradient, one-shot dialog edge (~120ms)

## 6. Voice & Tone

- Professional, concise, ops-facing
- Russian primary, English secondary
- No marketing hype; standard IT labels

## 7. Anti-patterns

- Avoid teal→violet gradients and purple “AI SaaS” chrome
- Avoid large soft blur overlays on every panel
- Avoid Inter / generic rounded-xl card stacks as the default look
- Avoid mixing random English into Russian UI
- **ASHITA anti-patterns:** pink/blue cyberpunk wash; anime chrome; neon on every control; constant flicker; album-cover background; random kanji; glass on every card; glitch inside terminal

## 8. How restyles cascade

Tokens live in `src/index.css`. Most pages use `PageShell`, shadcn primitives, and semantic colors — they pick up this system automatically. One-off pages with hard-coded teal/violet classes may still need local cleanup.

New skins **only** add `html[data-ui-style="…"]` blocks — never rewrite other skins. ASHITA decorative layers live in `AshitaAtmosphere` (`aria-hidden`, `pointer-events: none`) and only mount when the active style is `ashita`.
