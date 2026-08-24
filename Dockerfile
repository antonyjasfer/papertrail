# ==============================================================================
# Stage 1: Build & Dependencies
# ==============================================================================
FROM python:3.12-slim-bookworm AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-azure.txt ./

RUN pip install --no-cache-dir --user -r requirements.txt -r requirements-azure.txt && \
    find /root/.local -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true && \
    find /root/.local -type f -name '*.pyc' -delete 2>/dev/null || true && \
    find /root/.local -type f -name '*.pyo' -delete 2>/dev/null || true && \
    rm -rf /root/.cache

# ==============================================================================
# Stage 2: Production Lean Runtime
# ==============================================================================
FROM python:3.12-slim-bookworm AS runtime

# Security: Non-root user with UID/GID 10001
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/sh -M appuser

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /root/.local /home/appuser/.local
COPY app ./app

# Set ownership to appuser
RUN chown -R appuser:appgroup /app /home/appuser

ENV PATH=/home/appuser/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

USER appuser

EXPOSE 8080

# Default entrypoint (overridden in Container App definition for worker)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
