# Design system: Cyber-Botanical CRT Telemetry

The web project is a dark, botanical telemetry landing/dashboard surface built
with Vite, React, TypeScript, Tailwind, and custom CSS. Its current shipped
visuals are predominantly monochrome (white signal, zinc neutrals, void-black
background). Green and cyan may be used as semantic signal accents in future
components, but are not current global tokens; do not introduce them as if they
were already established brand colors.

## Design principles

- **Telemetry first:** labels, timestamps, thresholds, and status remain easy to
  scan at small sizes.
- **Botanical image, instrument treatment:** imagery supplies the organic
  subject; frames, data stamps, scan lines, and terminal panels supply the
  instrumentation.
- **Contrast before decoration:** overlays keep controls and body text legible.
- **Motion communicates state:** blinking and drift animations remain subtle
  and must not imply live data when a component is only a visual simulation.

## Color tokens

| Token | Value | Role |
|---|---|---|
| Void | `#040608` | Page canvas and deepest background |
| Ink | `#0a0a0f` | Secondary dark surface |
| Terminal | `#09090b` | Terminal/card surface |
| White | `#ffffff` | Primary text and active signal |
| Zinc 200 | `#e4e4e7` | Emphasized secondary text |
| Zinc 400 | `#a1a1aa` | Supporting text and labels |
| Zinc 500 | `#71717a` | Quiet labels |
| Zinc 600 | `#52525b` | Tertiary captions |
| Zinc 700 | `#3f3f46` | Inactive bars/borders |
| Phosphor green/cyan | Not currently tokenized | Optional future semantic signal colors; define accessible tokens before use |

Tailwind provides `void`, `ink`, and `terminal` color names. The config also
contains `crimson`, though the current interface styles emphasize white and
zinc. Prefer CSS variables and tokens over isolated color literals when adding
new elements.

## Type

- Display/body: Geist with Inter, system sans-serif fallback.
- Telemetry: JetBrains Mono, Geist Mono, Fira Code, then system monospace.
- Display headings use tight line-height and slight negative tracking.
- Micro-labels use uppercase monospace, generous tracking, and muted zinc.
- Keep long reading copy at comfortable sizes; the tiny type scale is for
  instrumentation labels, not paragraphs or controls.

`web/index.html` currently loads Inter and JetBrains Mono from Google Fonts;
Geist is preferred if available locally/system-side but is not fetched there.

## Surfaces and framing

- Use hairline borders with low-opacity white or zinc.
- Place terminal panels over near-black translucent surfaces; blur only where
  it improves separation from the background.
- Keep rounded corners restrained; controls are mostly squared instrument
  panels, while pills are reserved for status/category labels.
- Use radial vignettes and gradients around imagery to protect text contrast.
- The page currently uses a fixed full-viewport loop video with a left reading
  scrim; the framed flower also has radial vignette and scanline overlays.
  Keep a still fallback because the hero's ASCII clip is loaded from a remote
  asset host and may be unavailable offline.

## CRT and telemetry treatment

The flower frame and terminal panels use repeating linear-gradient scanline
layers, currently at approximately four-pixel spacing. The effect belongs on
image/terminal surfaces, not on all body content. Use `pointer-events: none`
for purely visual overlays and preserve a clean underlying text layer for
assistive technology and selection.

Oscilloscopic elements include the similarity bar chart, dashed threshold rule,
trip marker, live dot, timestamps, and terminal log. Label simulated/demo data
clearly. A threshold marker should expose its numeric value in accessible text,
not only through color or position.

## Media and motion rules

- Video must be decorative, muted, looped, and inline; use a poster/image
  fallback and respect `prefers-reduced-motion`.
- Never make successful rendering depend on autoplay. WebKit may block autoplay
  unless media is muted and inline; keep a static fallback available.
- Use `object-fit: cover`, a radial mask/vignette, and a gradient reading scrim
  when media sits behind text.
- Keep scanline/telemetry animation low-contrast and nonessential. Disable or
  reduce continuous movement for reduced-motion users.
- Do not place critical content only inside a video or canvas.

## Component map

| Component | Visual role |
|---|---|
| `HeroAsciiFlower` / `hero-flower-panel` | Botanical raster/canvas artwork with frame and stamps |
| `TerminalPreview` | Command/log/status display and similarity trip visualization |
| `telemetry-ticker` | Animated telemetry motif; label as decorative/demo |
| `button`, `badge`, `card` | Shared UI primitives |
| `styles.css` | Global tokens, layout, instrumentation, responsive rules |

When changing the identity, update CSS tokens, Tailwind config, component
states, and contrast/accessibility behavior together.
