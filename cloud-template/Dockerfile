FROM python:3.12-slim

# System deps + Node.js 20 for Claude Code CLI
RUN apt-get update && apt-get install -y --no-install-recommends curl git && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Claude Code CLI
RUN npm install -g @anthropic-ai/claude-code

# Pre-configure Claude Code (skip onboarding)
RUN mkdir -p /root/.claude && \
    echo '{"hasCompletedOnboarding": true}' > /root/.claude.json

WORKDIR /app

# Install Python deps + glyx-python-sdk
COPY pyproject.toml server.py ./
COPY glyx_python_sdk/ /app/glyx_python_sdk/
RUN pip install --no-cache-dir fastmcp supabase /app/glyx_python_sdk/

RUN mkdir -p /workspace
EXPOSE 8080
CMD ["python", "server.py"]
