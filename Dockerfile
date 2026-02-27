# syntax=docker/dockerfile:1.4
# =============================================================================
# Glyx MCP Server - Multi-stage Docker build
# =============================================================================

# =============================================================================
# Development stage - includes dev dependencies and hot reload
# =============================================================================
FROM python:3.12-slim AS dev

WORKDIR /app

# Install system dependencies
RUN DEBIAN_FRONTEND=noninteractive apt-get update && \
    apt-get install -y --no-install-recommends \
    git \
    curl \
    unzip \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Copy uv binary from official image
COPY --from=ghcr.io/astral-sh/uv:0.9.24 /uv /uvx /bin/

# Copy project files
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Install dependencies with dev extras
RUN uv sync --all-extras || uv sync

# Install agent CLIs
RUN curl -fsSL https://opencode.ai/install | bash
ENV PATH="/root/.opencode/bin:$PATH"

RUN npm install -g @anthropic-ai/claude-code

RUN curl -fsSL https://cursor.com/install | bash && \
    ln -sf /root/.local/bin/cursor-agent /usr/local/bin/cursor-agent && \
    cursor-agent --version || echo "cursor-agent installed"

# Create directories
RUN mkdir -p /root/.claude /root/.cursor-agent

# Set environment
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT}/api/healthz || exit 1

# Development command with hot reload
CMD ["uv", "run", "uvicorn", "api.server:combined_app", "--host", "0.0.0.0", "--port", "8080", "--reload"]

# =============================================================================
# Production stage - optimized, minimal, secure
# =============================================================================
FROM python:3.12-slim AS production

# Create non-root user for security
RUN groupadd -r glyx && useradd -r -g glyx glyx

WORKDIR /app

# Install runtime dependencies only
RUN DEBIAN_FRONTEND=noninteractive apt-get update && \
    apt-get install -y --no-install-recommends \
    git \
    curl \
    unzip \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Copy uv binary from official image
COPY --from=ghcr.io/astral-sh/uv:0.9.24 /uv /uvx /bin/

# Copy project files
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Install production dependencies only (no dev extras)
RUN uv sync --no-dev || uv sync

# Install agent CLIs
RUN curl -fsSL https://opencode.ai/install | bash
ENV PATH="/root/.opencode/bin:$PATH"

RUN npm install -g @anthropic-ai/claude-code

RUN curl -fsSL https://cursor.com/install | bash && \
    ln -sf /root/.local/bin/cursor-agent /usr/local/bin/cursor-agent && \
    cursor-agent --version || echo "cursor-agent installed"

# Create necessary directories with proper permissions
RUN mkdir -p /app/logs /app/.data /home/glyx/.cache/uv /home/glyx/.claude /home/glyx/.cursor-agent && \
    chown -R glyx:glyx /app /home/glyx

# Set environment
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_CACHE_DIR=/home/glyx/.cache/uv \
    PORT=8080

EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT}/api/healthz || exit 1

# Switch to non-root user
USER glyx

# Production command - use --no-sync to skip re-syncing at runtime
CMD ["uv", "run", "--no-sync", "uvicorn", "api.server:combined_app", "--host", "0.0.0.0", "--port", "8080"]
