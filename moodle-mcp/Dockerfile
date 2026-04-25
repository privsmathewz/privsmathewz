FROM python:3.12-slim

WORKDIR /app

# Copy metadata files hatchling needs before running pip install
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir -e .

# SSE transport so the server listens on $PORT
ENV MCP_TRANSPORT=sse

EXPOSE 8000

CMD ["moodle-mcp"]
