FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install uv for faster package management
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Copy project files
COPY glyx-mcp/pyproject.toml ./
COPY glyx-mcp/README.md ./
COPY glyx-mcp/src/ ./src/

# Copy local dependency and update path in pyproject.toml
COPY glyx-mcp-tasks /tmp/glyx-mcp-tasks
RUN sed -i 's|file:///home/parallels/glyx-mcp-tasks|file:///tmp/glyx-mcp-tasks|g' pyproject.toml

# Install Python dependencies
RUN uv pip install --system -e ".[dev]"

# Install Aider using the official installer
RUN python3 -m pip install --break-system-packages aider-install && \
    aider-install

# Install OpenCode CLI
RUN curl -fsSL https://opencode.ai/install | bash
ENV PATH="/root/.opencode/bin:$PATH"

# Expose MCP server port (if needed for stdio, this is optional)
# MCP typically uses stdio, but we expose for potential future HTTP transport
EXPOSE 8000

# Set entrypoint to run the MCP server
ENTRYPOINT ["glyx-mcp"]
