# Build from the repository root:
#   docker build -t manim-composer -f backend/Dockerfile .
#   docker run -p 127.0.0.1:8000:8000 manim-composer
#
# Publish on 127.0.0.1 only. -p 8000:8000 exposes the API on every interface,
# and anyone who can reach it can run Python. There is no login.

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

# The process inside the container must listen on 0.0.0.0 so Docker can publish
# the port. It does not run as root. Bind the published port to 127.0.0.1 on the host.
RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin manim \
    && chown -R manim:manim /app
USER manim
ENV HOME=/home/manim

# Selects the eco render profile and disables the package-installer endpoints.
ENV RUNNING_IN_DOCKER=true
EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
