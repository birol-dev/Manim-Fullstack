FROM python:3.11-slim

# Install system dependencies for Cairo, Pango, FFmpeg, and LaTeX
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    libcairo2-dev \
    libpango1.0-dev \
    ffmpeg \
    texlive \
    texlive-latex-extra \
    dvisvgm \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the backend code and workspace template
COPY backend/ ./backend
COPY workspace/ ./workspace

EXPOSE 10000

# Start uvicorn on port 10000 (standard Render port)
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "10000"]
