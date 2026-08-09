# syntax=docker/dockerfile:1

# --- Builder: install dependencies with uv, then discard this stage ---
FROM ghcr.io/astral-sh/uv:python3.13-trixie-slim AS builder

# Copy deps into the venv instead of hard-linking from the uv cache,
# so the venv is self-contained when copied to the runtime stage
ENV UV_LINK_MODE=copy

WORKDIR /app

# Dependencies first — this layer only rebuilds when pyproject/uv.lock change
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# Then the application code (reuses the cached dependency layer)
COPY . .

# --- Runtime: minimal Python image, just the venv + code ---
FROM python:3.13-slim-trixie

WORKDIR /app

COPY --from=builder /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

# The SQLite database lives here and persists across restarts
VOLUME ["/app/data"]

CMD ["python", "main.py"]
