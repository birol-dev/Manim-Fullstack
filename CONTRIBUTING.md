# Contributing to Manim Composer

Thanks for helping out! Bug reports, feature ideas, docs fixes, and code are all welcome.

## Setup

```bash
pip install -r backend/requirements.txt
pip install pytest pytest-asyncio pytest-cov pytest-timeout httpx pyflakes
cd frontend && npm install
```

Run the backend with reload and the Vite dev server (it proxies API calls to port 8000):

```bash
uvicorn backend.main:app --reload --reload-dir backend --port 8000
cd frontend && npm run dev        # http://localhost:5173
```

Watch only `backend/`: a plain `--reload` also watches `workspace/`, so every save or render restarts the server
and drops the render WebSocket. Without reload, `npm run backend -- --port 8100` (or `MANIM_HOST` / `MANIM_PORT`)
starts the API on another address; point Vite at it with `MANIM_BACKEND_URL=http://127.0.0.1:8100`.

## Before you open a pull request

```bash
python -m pyflakes backend tests run.py   # the same lint CI runs
npm test          # pytest + Vitest (with coverage thresholds)
npm run check     # ESLint, TypeScript, production build, backend import check
```

`tests/test_e2e_real_render.py` runs real renders when Manim is installed locally; CI skips it.

## Conventions

- **Python:** PEP 8, type hints where they help, docstrings on public functions. Keep route handlers thin and put
  logic in a module (`executor.py`, `scene_parser.py`, ...). Validate every path with `workspace_paths`.
- **TypeScript:** no `any`, no unused code (`noUnusedLocals`). Pure logic goes in `src/lib/` with unit tests; stateful
  logic in a hook; components stay presentational where possible.
- **Styling:** use the design tokens in `src/index.css` (`bg-surface`, `text-fg-muted`, `border-line`, `bg-accent`,
  `text-danger`, ...) rather than raw colors. Blue is reserved for primary actions, focus, and selection; green, gold,
  and red only for status.
- **Accessibility:** icon-only buttons need an `aria-label` (and usually a `Tooltip`); interactive rows are buttons,
  not clickable `div`s.
- **Tests:** new behavior gets a test. Frontend tests use the fakes in `src/test/` instead of mocking fetch by hand.

## Pull requests

1. Branch from `main`.
2. Keep each PR focused and describe what changed and why.
3. Make sure `npm test` and `npm run check` pass.

Please be kind and constructive in issues and reviews.
