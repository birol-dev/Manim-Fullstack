FROM python:3.11-slim

# Install system dependencies for Cairo, Pango, and FFmpeg (LaTeX omitted to save memory/space on cloud)
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    libcairo2-dev \
    libpango1.0-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the backend code and workspace template
COPY backend/ ./backend
COPY workspace/ ./workspace

EXPOSE 8000

# Start uvicorn on port 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
