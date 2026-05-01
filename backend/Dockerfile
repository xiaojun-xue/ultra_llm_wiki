FROM python:3.12-slim-bookworm

WORKDIR /app

# Use USTC mirror for faster apt downloads in China
RUN sed -i 's|deb.debian.org|mirrors.ustc.edu.cn|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null; \
    sed -i 's|deb.debian.org|mirrors.ustc.edu.cn|g' /etc/apt/sources.list 2>/dev/null; \
    true

# Install system deps for document parsing + Clang AST for C/C++ call graph
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libclang-dev \
    clang \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Use Tsinghua PyPI mirror for faster pip downloads
ENV UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

# Copy all source first, then install
COPY . .
RUN uv pip install --system ".[dev]"

# FastAPI on 8000, MCP Server on 8001
EXPOSE 8000 8001

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000 & python -m app.mcp_server"]
