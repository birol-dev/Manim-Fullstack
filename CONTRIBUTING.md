# Contributing to Manim Composer

Thank you for your interest in contributing to Manim Composer! We welcome bug reports, feature requests, documentation improvements, and code contributions.

---

## Code of Conduct

Please be respectful and helpful to others when participating in this project. We aim to build a welcoming community for everyone.

---

## Local Development Setup

To make modifications to the codebase, we recommend running separate frontend and backend servers to take advantage of Hot Module Replacement (HMR) and automatic backend reloading.

### 1. Backend Setup (FastAPI)
1. Navigate to the repository root.
2. Install python dependencies:
   ```bash
   pip install -r backend/requirements.txt
   ```
3. Run the development server with reload enabled:
   ```bash
   uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
   ```

### 2. Frontend Setup (Vite + React)
1. Navigate to the `frontend/` directory.
2. Install npm dependencies:
   ```bash
   npm install
   ```
3. Run the Vite development server:
   ```bash
   npm run dev
   ```
4. Open your browser to the URL output by Vite (usually `http://localhost:5173`).

---

## Code Standards & Style

- **Python**: Follow PEP 8 guidelines. Write clear docstrings for public endpoints.
- **TypeScript**: Ensure the project compiles with no warnings (`npx tsc --noEmit`).
- **Styling**: Use Tailwind CSS variables. Keep the interface monochromatic and high-contrast.

---

## Submitting Pull Requests

1. **Fork** the repository and create your branch from `main`.
2. If you've added code that should be tested, add tests.
3. Ensure the test suite and type check passes.
4. Format your commit messages clearly.
5. Open a Pull Request, detailing what your changes accomplish.
