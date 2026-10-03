# Manim Composer — frontend

React 19 + TypeScript app built with Vite, Tailwind CSS v4, Radix UI primitives, and a trimmed, locally bundled
Monaco editor.

```bash
npm install
npm run dev            # http://localhost:5173, proxies /api, /media, /assets to :8000
npm test               # Vitest
npm run test:coverage  # with coverage thresholds
npm run lint
npm run build          # typecheck (including tests) + production bundle in dist/
```

Set `MANIM_BACKEND_URL` to proxy the dev server to a backend on another address, or `VITE_BACKEND_URL` at build time
to point a separately hosted frontend at a backend.

The structure, hooks, and design tokens are described in [PROJECT_REFERENCE.md](../PROJECT_REFERENCE.md#frontend-frontendsrc).
