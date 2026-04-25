FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (better layer caching)
COPY pyproject.toml .
RUN pip install --no-cache-dir hatchling && \
    pip install --no-cache-dir -e . --no-build-isolation || true

# Now copy source and install properly
COPY src/ ./src/
RUN pip install --no-cache-dir -e .

# SSE transport so the server listens on $PORT
ENV MCP_TRANSPORT=sse

EXPOSE 8000

CMD ["moodle-mcp"]
