FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files
COPY pyproject.toml .python-version ./

# Install dependencies
RUN uv sync --no-dev --no-install-project

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Production: gunicorn with 3 workers x 4 threads per instance (3 instances = 36 handlers)
CMD ["uv", "run", "gunicorn", "--bind", "0.0.0.0:5000", "--workers", "3", "--threads", "4", "--timeout", "120", "--keep-alive", "5", "--worker-class", "gthread", "--access-logfile", "-", "run:app"]
