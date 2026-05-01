"""Allow running MCP server via: python -m app.mcp_server"""
from app.mcp_server.server import mcp

mcp.run(transport="sse")
