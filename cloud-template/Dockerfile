FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml server.py ./
RUN pip install --no-cache-dir fastmcp supabase
RUN mkdir -p /workspace
EXPOSE 8080
CMD ["fastmcp", "run", "server.py", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8080"]
