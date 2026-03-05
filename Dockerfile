# ─────────────────────────────────────────────────────────────
# Nepal Chunab 2082 — Dockerfile for Render deployment
# ─────────────────────────────────────────────────────────────
FROM python:3.11-slim

# System deps required by Playwright/Chromium
# NOTE: python:3.11-slim uses Debian bookworm where libasound2 → libasound2t64
RUN apt-get update && apt-get install -y \
    wget curl gnupg ca-certificates \
    libglib2.0-0 libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libdbus-1-3 libxcb1 libxkbcommon0 libx11-6 \
    libxcomposite1 libxdamage1 libxext6 libxfixes3 libxrandr2 \
    libgbm1 libpango-1.0-0 libcairo2 libasound2t64 libatspi2.0-0 \
    fonts-liberation fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright + Chromium with all OS-level dependencies auto-handled
RUN playwright install --with-deps chromium

# Copy app files
COPY . .

# Render assigns a PORT env var — Flask must bind to it
ENV PORT=5000
EXPOSE 5000

# Use gunicorn for production (handles concurrent requests properly)
CMD gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120 server:app
