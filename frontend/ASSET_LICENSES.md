# Frontend visual assets and release checks

Reviewed: 2026-08-21

This file records the visual dependencies used by the release-facing frontend. It is an engineering inventory, not legal advice.

## Fonts

The base document loads these families from Google Fonts with system fallbacks:

| Family | Product role | License source |
| --- | --- | --- |
| Inter | UI and body copy | [SIL Open Font License 1.1](https://github.com/rsms/inter/blob/master/LICENSE.txt) |
| Manrope | display headings and summary values | [SIL Open Font License 1.1](https://github.com/google/fonts/blob/main/ofl/manrope/OFL.txt) |
| JetBrains Mono | addresses, ports, metrics, technical values | [SIL Open Font License 1.1](https://github.com/JetBrains/JetBrainsMono/blob/master/OFL.txt) |

Current beta delivery uses the Google Fonts stylesheet linked in `index.html`; `font-display=swap` and native system fallbacks keep the UI usable if the font request fails.

Before an offline/on-prem commercial distribution, choose and document one of two policies:

1. self-host pinned WOFF2 files and ship their OFL texts; or
2. explicitly allow the Google Fonts domains in CSP and the deployment privacy/network policy.

Do not silently replace these fonts with files from an unverified download mirror.

## Interface icons

Interactive UI icons come from `lucide-react`, already declared in `package.json`. Lucide publishes the set under the [ISC License](https://github.com/lucide-icons/lucide/blob/main/LICENSE). Keep action icons from this one family unless a product-specific glyph is necessary.

Rules:

- use icons with visible text for primary actions;
- do not use a vendor logo as an action icon;
- keep a consistent optical size and stroke weight;
- every icon-only control requires an accessible name;
- decorative icons are `aria-hidden`.

## OS and infrastructure marks

The local files in `src/assets/os/` are used only to identify detected operating systems or infrastructure technologies. Their path data follows the Simple Icons collection style. A representative path comparison on 2026-08-21 confirmed exact matches for Ubuntu, Debian, Docker, and Kubernetes against the upstream files.

Simple Icons publishes its collection under [CC0 1.0](https://github.com/simple-icons/simple-icons/blob/develop/LICENSE.md), but that waiver does **not** grant trademark rights. The project's own [disclaimer](https://github.com/simple-icons/simple-icons/blob/develop/DISCLAIMER.md) requires users to consider the rights and brand guidelines of each represented company or project.

Commercial-release rules:

- marks are nominative labels for detected technology, never an endorsement or partnership claim;
- do not recolor, distort, animate, or combine a mark with the WebTerm logo;
- preserve the vendor's recognizable brand color where allowed;
- verify the current brand guidelines for every shipped mark before the commercial release gate;
- if a mark cannot be cleared, replace it with the neutral `unknown.svg` server glyph and retain the OS name as text.

The neutral `unknown.svg` is the fallback for unrecognized or uncleared technologies and does not imply a third-party brand.

## Images and illustrations

The Servers workspace intentionally contains no stock image, generated hero illustration, or remote decorative image. Operational density and truthful status communication are the visual priority. Any future image added to a product screen must have:

- a product reason beyond decoration;
- a local, versioned source asset;
- recorded author/source/license;
- meaningful alt text, or `aria-hidden` when purely decorative;
- verified rendering in both light and dark themes.
