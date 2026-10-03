# Build from the repository root:
#   docker build -t manim-composer -f backend/Dockerfile .
#   docker run -p 8000:8000 manim-composer

# --- 1. Frontend bundle --------------------------------------------------------
FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- 2. Python runtime with Manim ---------------------------------------------
FROM python:3.12-slim

# Cairo and Pango headers are needed to build Manim's native dependencies.
# FFmpeg is only used for audio (add_sound); LaTeX is omitted to keep the image small.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        pkg-config \
        libcairo2-dev \
        libpango1.0-dev \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY workspace/ workspace/
COPY --from=frontend /app/frontend/dist frontend/dist

# Selects the eco render profile and disables the package-installer endpoints.
ENV RUNNING_IN_DOCKER=true
EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
