#!/bin/bash
# Quick start script for LLM Wiki
set -e

echo "=== LLM Wiki Knowledge Base ==="
echo ""

# Copy .env if not exists
if [ ! -f .env ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo "  ⚠ Please edit .env to set secure passwords before production use."
    echo ""
fi

# Start all services
echo "Starting Docker services..."
docker compose up -d

# Wait for postgres to be healthy
echo "Waiting for PostgreSQL to be ready..."
until docker compose exec -T postgres pg_isready -U llm_wiki > /dev/null 2>&1; do
    sleep 2
done
echo "PostgreSQL is ready."

# Pull BGE-M3 model in Ollama
echo "Pulling BGE-M3 embedding model (this may take a few minutes on first run)..."
docker compose exec -T ollama ollama pull bge-m3

echo ""
echo "=== All services are running! ==="
echo ""
echo "  Web UI:      http://localhost"
echo "  API Docs:    http://localhost:8000/docs"
echo "  MCP Server:  http://localhost:8001 (SSE)"
echo "  MinIO UI:    http://localhost:9001"
echo ""
echo "To configure Claude Code, add this to .mcp.json:"
echo '  {'
echo '    "mcpServers": {'
echo '      "llm-wiki": {'
echo '        "type": "sse",'
echo '        "url": "http://your-server:8001/sse"'
echo '      }'
echo '    }'
echo '  }'
echo ""
echo "To import documents:"
echo "  python scripts/import_data.py /path/to/your/materials"
