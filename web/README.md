# AgentDrift web

Standalone Vite + React + TypeScript landing page. It is isolated from the
FastAPI backend and builds static assets into `dist/` for Cloudflare Pages.

```sh
npm ci
npm run dev
```

For production output:

```sh
npm run build
npm run preview
```

`public/hero-flower.svg` is a self-contained vector fallback for the canvas
ASCII rasterizer. If the original reference image is available, save it as
`public/hero-flower.png`; `HeroAsciiFlower` will prefer that file automatically.
