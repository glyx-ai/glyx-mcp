FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    unzip \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Install uv for faster package management
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Copy project files
COPY pyproject.toml ./
COPY README.md ./
COPY src/ ./src/
COPY agents/ ./agents/

# Install Python dependencies
RUN uv pip install --system -e ".[dev]"

# Install OpenCode CLI
RUN curl -fsSL https://opencode.ai/install | bash
ENV PATH="/root/.opencode/bin:$PATH"

# Install Claude Code CLI
RUN npm install -g @anthropic-ai/claude-code

# Install Cursor Agent CLI (Linux x64)
# The install script creates symlink at ~/.local/bin/cursor-agent
RUN curl -fsSL https://cursor.com/install | bash && \
    # Also link to /usr/local/bin for guaranteed PATH availability
    ln -sf /root/.local/bin/cursor-agent /usr/local/bin/cursor-agent && \
    # Verify installation
    cursor-agent --version || echo "cursor-agent installed"

# Create directories for credentials
RUN mkdir -p /root/.claude /root/.cursor-agent

# Cloud Run uses PORT env var
ENV PORT=8080
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT}/api/healthz || exit 1

# Run HTTP server (Cloud Run compatible)
CMD ["glyx-mcp-http"]
