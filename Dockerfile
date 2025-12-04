# =============================================================================
# Builder stage - installs dependencies
# =============================================================================
FROM python:3.12-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for faster package management
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Copy dependency files first (for better caching)
COPY pyproject.toml README.md ./
COPY packages/ ./packages/

# Install Python dependencies (production only, no dev deps)
RUN uv pip install --system --no-cache .

# =============================================================================
# Development stage - includes dev dependencies and tools
# =============================================================================
FROM python:3.12-slim as dev

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    unzip \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Copy project files
COPY pyproject.toml README.md ./
COPY packages/ ./packages/
COPY src/ ./src/

# Install with dev dependencies
RUN uv pip install --system -e ".[dev]"

# Install agent CLIs
RUN curl -fsSL https://opencode.ai/install | bash
ENV PATH="/root/.opencode/bin:$PATH"

RUN npm install -g @anthropic-ai/claude-code

RUN curl -fsSL https://cursor.com/install | bash && \
    ln -sf /root/.local/bin/cursor-agent /usr/local/bin/cursor-agent && \
    cursor-agent --version || echo "cursor-agent installed"

# Create directories
RUN mkdir -p /root/.claude /root/.cursor-agent

# Port configuration
ENV PORT=8080
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT}/api/healthz || exit 1

# Run HTTP server (development mode)
CMD ["glyx-mcp-http"]

# =============================================================================
# Production stage - optimized, minimal, secure
# =============================================================================
FROM python:3.12-slim as production

# Create non-root user for security
RUN groupadd -r glyx && useradd -r -g glyx glyx

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y \
    git \
    curl \
    unzip \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Copy Python packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --chown=glyx:glyx pyproject.toml README.md ./
COPY --chown=glyx:glyx packages/ ./packages/
COPY --chown=glyx:glyx glyx/ ./glyx/

# Install agent CLIs
RUN curl -fsSL https://opencode.ai/install | bash
ENV PATH="/root/.opencode/bin:$PATH"

RUN npm install -g @anthropic-ai/claude-code

RUN curl -fsSL https://cursor.com/install | bash && \
    ln -sf /root/.local/bin/cursor-agent /usr/local/bin/cursor-agent && \
    cursor-agent --version || echo "cursor-agent installed"

# Create necessary directories
RUN mkdir -p /app/logs /app/.data /root/.claude /root/.cursor-agent && \
    chown -R glyx:glyx /app/logs /app/.data

# Port configuration
ENV PORT=8080
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT}/api/healthz || exit 1

# Switch to non-root user
USER glyx

# Run HTTP server (production mode)
CMD ["python", "-m", "uvicorn", "api.server:combined_app", "--host", "0.0.0.0", "--port", "8080"]
