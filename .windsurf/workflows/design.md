---
description: Open Design skills — create UI prototypes, design systems, decks, social cards, and more using the open-design skill catalog
---

# Open Design Skills

Skill catalog is installed at `C:\open-design\skills\`. Each skill is a folder with `SKILL.md` (workflow instructions) + optional `assets/` and `references/`.

## How to invoke a skill

When the user requests a skill by name or trigger phrase:

1. Read `C:\open-design\skills\<skill-name>\SKILL.md`
2. If the skill has `assets/` or `references/` subdirectories, read them too (they contain templates and checklists)
3. Follow the workflow instructions exactly as written in SKILL.md
4. Output goes to the current working directory unless the skill specifies otherwise

If the skill is a **catalog-only entry** (the SKILL.md just points to an upstream URL), explain this to the user and offer to proceed with Open Design's built-in `design-brief` guidance instead.

---

## Skill Catalog

### 🎨 Design Systems & Brief

| Skill | Trigger phrases |
|---|---|
| `design-brief` | "design brief", "create a design brief", "structured brief", "ilang brief" |
| `design-md` | "create DESIGN.md", "design tokens", "design system file" |
| `design-consultation` | "design from scratch", "design system kickoff", "brand workshop" |
| `design-review` | "review design", "design audit", "design feedback" |
| `color-expert` | "color theory", "palette generator", "oklch palette", "contrast check" |
| `frontend-design` | "frontend design", "ui design", "web design", "production ui" |
| `theme-factory` | "create theme", "theme tokens", "color scheme" |
| `apple-hig` | "apple design", "hig", "ios design guidelines" |
| `web-design-guidelines` | "web design guidelines", "design principles" |

### 🖥️ Web Prototypes & Pages

| Skill | Trigger phrases |
|---|---|
| `faq-page` | "faq", "frequently asked questions", "help center", "support page" |
| `release-notes-one-pager` | "release notes", "changelog", "what's new", "version update" |
| `login-flow` | "login page", "sign in", "auth flow" |
| `paywall-upgrade-cro` | "paywall", "upgrade page", "pricing cta" |
| `resume-modern` | "resume", "cv", "portfolio page" |
| `poster-hero` | "hero section", "poster design", "hero banner" |
| `article-magazine` | "magazine article", "editorial layout", "long-form article" |
| `data-report` | "data report", "analytics page", "metrics dashboard" |
| `artifacts-builder` | "html artifact", "react artifact", "multi-component artifact" |
| `web-artifacts-builder` | "web artifact", "interactive prototype" |
| `canvas-design` | "canvas ui", "whiteboard design" |
| `agent-browser` | "browser automation", "web scraping agent" |

### 📊 Decks & Presentations

| Skill | Trigger phrases |
|---|---|
| `deck-swiss-international` | "presentation deck", "slide deck", "swiss style slides" |
| `deck-open-slide-canvas` | "open slide canvas", "minimal deck" |
| `deck-guizang-editorial` | "editorial deck", "magazine deck", "guizang" |
| `pptx` | "powerpoint", "pptx", "export pptx" |
| `ppt-keynote` | "keynote", "apple keynote style" |
| `slides` | "simple slides", "html slides" |
| `frontend-slides` | "frontend slides", "reveal.js", "code slides" |
| `html-ppt-retro-quarterly-review` | "quarterly review", "retro deck", "q-review" |
| `pptx-html-fidelity-audit` | "pptx fidelity audit", "audit presentation" |
| `nanobanana-ppt` | "nanobanana", "minimal ppt" |

### 📱 Social & Marketing Cards

| Skill | Trigger phrases |
|---|---|
| `social-x-post-card` | "twitter card", "x post card", "tweet screenshot" |
| `social-reddit-card` | "reddit card", "reddit post screenshot" |
| `social-spotify-card` | "spotify card", "now playing card" |
| `card-twitter` | "twitter thread card", "social post" |
| `ad-creative` | "ad banner", "display ad", "ad creative" |
| `copywriting` | "copywriting", "landing copy", "ad copy", "homepage copy" |
| `screenshots-marketing` | "marketing screenshots", "app store screenshots" |
| `competitive-ads-extractor` | "ad analysis", "competitor ads" |

### 🎬 Video, Animation & Frames

| Skill | Trigger phrases |
|---|---|
| `8-bit-orbit-video-template` | "8-bit video", "orbit animation" |
| `after-hours-editorial-template` | "after hours template", "editorial video" |
| `frame-data-chart-nyt` | "nyt chart", "data visualization frame" |
| `frame-flowchart-sticky` | "flowchart", "sticky note diagram" |
| `frame-glitch-title` | "glitch title", "glitch effect" |
| `frame-light-leak-cinema` | "light leak", "cinematic frame" |
| `frame-liquid-bg-hero` | "liquid background", "fluid hero" |
| `frame-logo-outro` | "logo outro", "brand outro" |
| `frame-macos-notification` | "macos notification", "desktop notification mockup" |
| `vfx-text-cursor` | "vfx text", "cursor effect", "text animation" |
| `remotion` | "remotion", "react video", "programmatic video" |
| `video-hyperframes` | "hyperframes", "html to video" |
| `weread-year-in-review-video-template` | "year in review", "wrapped video" |
| `swiss-user-research-video-template` | "user research video", "ux video" |
| `swiss-creative-mode-template` | "swiss creative", "creative mode" |
| `gif-sticker-maker` | "gif sticker", "animated sticker" |

### 🖼️ Image Generation (fal.ai)

| Skill | Trigger phrases |
|---|---|
| `fal-generate` | "generate image", "fal image", "text to image" |
| `fal-image-edit` | "edit image", "fal edit", "image inpainting" |
| `fal-upscale` | "upscale image", "image enhancement" |
| `fal-3d` | "3d from image", "image to 3d" |
| `fal-kling-o3` | "kling video", "image to video" |
| `fal-tryon` | "virtual try-on", "clothing try-on" |
| `fal-vision` | "image analysis", "visual qa" |

### 🛠️ Code & Dev Tools

| Skill | Trigger phrases |
|---|---|
| `shadcn-ui` | "shadcn", "radix ui", "shadcn components" |
| `d3-visualization` | "d3 chart", "d3 visualization", "svg chart" |
| `gsap-core` | "gsap animation", "scroll animation" |
| `gsap-react` | "gsap react", "react animation" |
| `threejs` | "three.js", "3d scene", "webgl" |
| `shader-dev` | "glsl shader", "webgl shader" |
| `swiftui-design` | "swiftui", "ios app ui" |
| `flutter-animating-apps` | "flutter animation", "flutter ui" |
| `figma-generate-design` | "generate figma design", "figma design" |
| `figma-implement-design` | "implement figma", "figma to code" |
| `frontend-dev` | "frontend development", "build frontend" |
| `mockup-device-3d` | "device mockup", "3d phone mockup", "laptop mockup" |
| `full-page-screenshot` | "full page screenshot", "page capture" |

### 📄 Documents

| Skill | Trigger phrases |
|---|---|
| `doc` | "create document", "html document" |
| `doc-kami-parchment` | "parchment doc", "kami document style" |
| `docx` | "word document", "docx export" |
| `pdf` | "pdf document", "export pdf" |
| `hand-drawn-diagrams` | "hand drawn diagram", "sketch diagram" |
| `hatch-pet` | "hatch pet", "tamagotchi" |
| `brainstorming` | "brainstorm", "ideation", "concept exploration" |
| `enhance-prompt` | "improve prompt", "enhance prompt", "better prompt" |
| `design-brief` | "design brief", "ilang brief" |

### 📐 Special / Brand Templates

| Skill | Trigger phrases |
|---|---|
| `digits-fintech-swiss-template` | "fintech template", "finance ui" |
| `editorial-burgundy-principles-template` | "burgundy editorial", "principles page" |
| `field-notes-editorial-template` | "field notes", "editorial notes" |
| `after-hours-editorial-template` | "after hours", "dark editorial" |
| `brand-guidelines` | "brand guidelines", "brand kit", "style guide" |
| `marketing-psychology` | "marketing psychology", "persuasion copy" |
| `platform-design` | "platform design", "design system platform" |
| `taste-skill` | "taste", "aesthetic direction", "visual taste" |
| `creative-director` | "creative director", "art direction" |

---

## Usage examples

```
/design
→ list available skills and ask which one to use

/design design-brief
→ read C:\open-design\skills\design-brief\SKILL.md and follow the workflow

/design faq-page
→ read C:\open-design\skills\faq-page\SKILL.md and generate FAQ HTML

/design release-notes
→ maps to release-notes-one-pager skill

/design social-x-post-card
→ generate a tweet/X post card
```

## Notes

- Skills at `C:\open-design\skills\` — Apache-2.0 unless skill folder has its own LICENSE
- `design-brief`, `faq-page`, `release-notes-one-pager` are the richest standalone skills
- `fal-*` skills require a fal.ai API key
- `figma-*` skills require Figma MCP or API token
- When skill has `assets/template.html` — read it before generating output
- When skill has `references/` — read checklist.md and layouts.md first
