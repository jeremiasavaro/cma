# Multi-stage Dockerfile for the API.
# - builder: installs dependencies with uv
# - development: includes dev tools, hot reload
# - production: minimal runtime image


# =============================================================================
# Builder Stage - Install dependencies
# =============================================================================
FROM python:3.12-slim AS builder

WORKDIR /app

# System dependencies for building packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv (fast Python package manager)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files
COPY pyproject.toml uv.lock* ./

# Install dependencies (cached layer if pyproject.toml unchanged)
RUN uv sync --frozen --no-dev


# =============================================================================
# Development Stage - Hot reload, dev tools
# =============================================================================
FROM python:3.12-slim AS development

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy installed packages from builder
COPY --from=builder /app/.venv /app/.venv

# Ensure venv is in PATH
ENV PATH="/app/.venv/bin:$PATH"

# Non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Run with hot reload (code mounted via docker-compose volume)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]


# =============================================================================
# Production Stage - Minimal runtime
# =============================================================================
FROM python:3.12-slim AS production

WORKDIR /app

# Runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH"

# Copy application code
COPY --chown=appuser:appuser app ./app
COPY --chown=appuser:appuser alembic ./alembic
COPY --chown=appuser:appuser alembic.ini ./

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]