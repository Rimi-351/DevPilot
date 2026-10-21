# ── Stage 1: Build stage ──────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Install OS build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies cleanly into an isolated prefix
COPY pyproject.toml requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: Final runtime stage ──────────────────────────────────────
FROM python:3.11-slim AS runtime

# Install minimal runtime system utilities (e.g., curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root system user and group
RUN groupadd -g 1000 devpilot && \
    useradd -u 1000 -g devpilot -m -s /bin/bash devpilot

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

WORKDIR /app

# Create necessary directories for storage, artifacts, and benchmarks with non-root ownership
RUN mkdir -p /app/storage/uploads /app/artifacts /app/benchmarks && \
    chown -R devpilot:devpilot /app

# Copy application source code
COPY --chown=devpilot:devpilot . /app

# Switch to non-root user
USER devpilot

# Environment settings
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PORT=8000

# Expose HTTP port
EXPOSE 8000

# Health check verification
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Start FastAPI application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
