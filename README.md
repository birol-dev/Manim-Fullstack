# Manim Composer & Editor

An interactive, web-based IDE and live renderer for **Manim Community Edition** (Python animation engine). Designed for education, technical presentations, and mathematical animations, it combines code editing, live video previewing, and a browser-side LaTeX sandbox into a single monochromatic user interface.

## Core Features

- **Monochromatic B&W Interface**: Flat, high-contrast, minimalist design utilizing slate/zinc tones with zero gradients or colored indicators.
- **Auto-Config Diagnostics**: Automatically checks host system specifications (CPU cores, RAM capacity, GPU models) and builds optimization configurations to accelerate rendering.
- **Live Typing Auto-Render**: Debounced auto-render option that automatically compiles your active python scene 2 seconds after you stop typing.
- **Interactive File Management**: Double-click inline file renaming in the sidebar browser, uploads folder for asset libraries (SVGs, PNGs, MP3s), and creation of custom Python scripts.
- **LaTeX Math Sandbox**: Browser-side KaTeX sandbox containing common equation templates (Euler's identity, matrices, quadratic equations) to preview formulas instantly and insert them directly into Monaco as `MathTex(r"...")` blocks.
- **One-Click LaTeX Installer**: Detects missing local LaTeX dependencies and allows Windows users to silently install MiKTeX via `winget` directly from the web interface.
- **WebSocket Logs Streaming**: Captures rendering logs and outputs real-time compiler stdout/stderr streams and progress telemetry.

---

## Getting Started

### Prerequisites

1. **Python 3.9+**
2. **Node.js 18+** (including npm)
3. **Manim CE** (Python package `pip install manim`)
4. **FFmpeg** (installed and added to System PATH)
5. **LaTeX (Recommended)** (MiKTeX or TeX Live for compiling math equations)

---

## Installation & Running

### Option A: Local Run

#### 1. Launch FastAPI Backend
The backend manages file access, hardware diagnostics, and subprocess execution.

```bash
# Install backend requirements
pip install -r backend/requirements.txt

# Start backend server
python backend/main.py
```
*Backend runs locally on: [http://localhost:8000](http://localhost:8000)*

#### 2. Launch Vite Frontend
The frontend provides the Monaco editor, live viewer, and LaTeX sandbox.

```bash
# Navigate to the frontend directory
cd frontend

# Install Node dependencies
npm install

# Start local development server
npm run dev
```
*Frontend runs locally on: [http://localhost:5173](http://localhost:5173)*

### Option B: Running Backend with Docker

You can build and run the backend container, which bundles Cairo, Pango, and FFmpeg for rendering.

```bash
# Build the Docker image (run from the repository root)
docker build -t manim-composer-backend -f backend/Dockerfile .

# Run the container mapping port 8000
docker run -p 8000:8000 manim-composer-backend
```

---

## Directory Architecture

```text
├── backend/
│   ├── main.py          # FastAPI application server & REST/WebSocket routes
│   ├── diagnostics.py   # System hardware & software environment checker
│   ├── executor.py      # Subprocess execution and stream regex parser
│   └── Dockerfile       # Container setup for backend running on port 8000
├── frontend/
│   ├── src/
│   │   ├── App.tsx      # Main React dashboard component
│   │   ├── components/  # Radix UI and custom styled widgets
│   │   └── index.css    # Monochromatic theme overrides
│   ├── index.html       # KaTeX CDN links & application mount
│   ├── package.json     # Node scripts and react dependencies
│   └── tsconfig.json    # TypeScript compiler options
├── workspace/           # The active file system loaded in the editor
│   ├── media/           # Output directory for rendered videos (ignored)
│   ├── assets/          # Uploaded media assets (ignored)
│   └── example.py       # Default starter script
└── .gitignore           # Ignores system caches, node_modules, and media outputs
```

---

## License

This project is open-source and available under the [MIT License](LICENSE).
