# AgentDrift web interface

This directory contains the standalone Vite + React + TypeScript web experience
for AgentDrift. It presents the product's cyber-botanical telemetry identity,
architecture, install commands, and illustrative execution signals. The current
terminal preview/ticker is presentational demo UI; it does not automatically
connect to the FastAPI daemon.

## Development

Requirements: Node.js compatible with Vite 5 and npm.

```bash
npm ci
npm run dev
```

Create a static production bundle with `npm run build`; preview it with
`npm run preview`. Vite writes output to `web/dist/`. `npm audit --prefix web`
checks frontend dependencies.

## Stack and configuration

- React 18, TypeScript, Vite, Tailwind CSS, PostCSS, and Autoprefixer.
- `vite.config.ts` configures the React plugin and `@` alias to `src/`.
- `tailwind.config.js` scans `index.html` and `src/**/*.{ts,tsx}` and defines
  the font/color tokens.
- `src/styles.css` contains global tokens, layouts, CRT effects, responsive
  rules, and component styling.

## File map

| Path | Purpose |
|---|---|
| `src/App.tsx` | Page composition, sections, architecture/install UI |
| `src/TerminalPreview.tsx` | Terminal telemetry preview and signal chart |
| `src/HeroAsciiFlower.tsx` | Canvas-based ASCII image treatment |
| `src/components/hero-flower-panel.tsx` | Framed botanical/video stage and telemetry ticker |
| `src/components/telemetry-ticker.tsx` | Decorative animated signal ticker |
| `src/components/install-commands.tsx` | Install command data |
| `src/components/ui/` | Buttons, badges, cards, ASCII art primitives |
| `src/lib/utils.ts` | Shared class-name utility |
| `src/assets/`, `public/` | Botanical image and loop-video assets |
| `index.html` | Document metadata and font loading |

## Media and accessibility rules

Use video as decorative media only: muted, looping, and inline where rendered,
with a still-image fallback. Browser autoplay policies—especially WebKit—must
not block the page or hide information. Respect reduced-motion settings for
continuous animation. Place scanlines, vignettes, and reading scrims in
`aria-hidden`/pointer-transparent layers; keep meaningful telemetry in DOM text
with accessible labels. Keep colors and status text legible over the media.

See [`../docs/design_system.md`](../docs/design_system.md) for the visual
system and [`../docs/architecture.md`](../docs/architecture.md) for the backend.
