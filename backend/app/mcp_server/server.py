"""
MCP Server for LLM Wiki Knowledge Base.

Exposes wiki search, document retrieval, and relation browsing
as MCP tools that Claude Code can call directly.

Run standalone: python -m app.mcp_server.server
"""

import json
import uuid

from mcp.server.fastmcp import FastMCP

from app.config import settings

mcp = FastMCP("LLM Wiki", host="0.0.0.0", port=settings.mcp_port)


def _get_db_session():
    """Create a sync-compatible database session for MCP tools."""
    import asyncio
    from app.db.base import async_session

    return async_session()


@mcp.tool()
async def search_wiki(
    query: str,
    doc_type: str | None = None,
    tags: list[str] | None = None,
    limit: int = 5,
) -> str:
    """Search the knowledge base using hybrid search (vector + keyword).

    Args:
        query: Natural language search query
        doc_type: Filter by type: source_code, document, schematic, note
        tags: Filter by tags
        limit: Max results (default 5)

    Returns:
        Search results with document titles, types, and relevant content snippets.
    """
    from app.core.embedding import embedding_service
    from app.db.base import async_session
    from sqlalchemy import text

    embedding = await embedding_service.embed_query(query)

    async with async_session() as db:
        doc_type_filter = "AND d.doc_type = :doc_type" if doc_type else ""
        params: dict = {"embedding": str(embedding), "limit": limit}
        if doc_type:
            params["doc_type"] = doc_type

        sql = text(f"""
            SELECT c.document_id, c.content, c.metadata,
                   d.title, d.doc_type,
                   c.embedding <=> :embedding AS distance
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE 1=1 {doc_type_filter}
            ORDER BY c.embedding <=> :embedding
            LIMIT :limit
        """)
        result = await db.execute(sql, params)
        rows = result.fetchall()

    if not rows:
        return f"No results found for: {query}"

    output = []
    for i, row in enumerate(rows, 1):
        output.append(
            f"## [{i}] {row.title} ({row.doc_type})\n"
            f"ID: {row.document_id}\n"
            f"Distance: {row.distance:.4f}\n\n"
            f"{row.content[:1000]}\n"
        )
    return "\n---\n".join(output)


@mcp.tool()
async def get_document(doc_id: str) -> str:
    """Get the full content of a document by its ID.

    Args:
        doc_id: UUID of the document

    Returns:
        Document title, type, content, and metadata.
    """
    from app.db.base import async_session
    from app.models.document import Document
    from sqlalchemy import select

    async with async_session() as db:
        stmt = select(Document).where(Document.id == uuid.UUID(doc_id))
        result = await db.execute(stmt)
        doc = result.scalar_one_or_none()

    if not doc:
        return f"Document not found: {doc_id}"

    return (
        f"# {doc.title}\n\n"
        f"**Type:** {doc.doc_type}\n"
        f"**Created:** {doc.created_at}\n"
        f"**Metadata:** {json.dumps(doc.metadata_, ensure_ascii=False)}\n\n"
        f"---\n\n"
        f"{doc.content or '(No text content — file-based document)'}"
    )


@mcp.tool()
async def get_related(doc_id: str, relation_type: str | None = None) -> str:
    """Get all documents related to the given document.

    Args:
        doc_id: UUID of the document
        relation_type: Optional filter: references, implements, depends_on, related_to, derived_from

    Returns:
        List of related documents with relation details.
    """
    from app.db.base import async_session
    from app.models.document import Document, DocumentRelation
    from sqlalchemy import select, or_
    from sqlalchemy.orm import selectinload

    uid = uuid.UUID(doc_id)

    async with async_session() as db:
        stmt = select(DocumentRelation).where(
            or_(DocumentRelation.source_id == uid, DocumentRelation.target_id == uid)
        ).options(
            selectinload(DocumentRelation.source),
            selectinload(DocumentRelation.target),
        )
        if relation_type:
            stmt = stmt.where(DocumentRelation.relation_type == relation_type)

        result = await db.execute(stmt)
        relations = result.scalars().all()

    if not relations:
        return f"No relations found for document: {doc_id}"

    output = []
    for r in relations:
        is_outgoing = str(r.source_id) == doc_id
        other = r.target if is_outgoing else r.source
        direction = "→" if is_outgoing else "←"
        output.append(
            f"- {direction} **{other.title}** ({other.doc_type})\n"
            f"  Relation: {r.relation_type} | Confidence: {r.confidence:.2f}\n"
            f"  {r.description or ''}\n"
            f"  ID: {other.id}"
        )

    return "\n".join(output)


@mcp.tool()
async def list_documents(
    doc_type: str | None = None, tag: str | None = None, limit: int = 20
) -> str:
    """List documents in the knowledge base.

    Args:
        doc_type: Filter by type: source_code, document, schematic, note
        tag: Filter by tag name
        limit: Max results (default 20)

    Returns:
        Document listing with IDs, titles, and types.
    """
    from app.db.base import async_session
    from app.models.document import Document, Tag
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    async with async_session() as db:
        stmt = select(Document).options(selectinload(Document.tags))
        if doc_type:
            stmt = stmt.where(Document.doc_type == doc_type)
        if tag:
            stmt = stmt.join(Document.tags).where(Tag.name == tag)
        stmt = stmt.order_by(Document.updated_at.desc()).limit(limit)

        result = await db.execute(stmt)
        docs = result.scalars().unique().all()

    if not docs:
        return "No documents found."

    output = []
    for d in docs:
        tags_str = ", ".join(t.name for t in d.tags) if d.tags else ""
        output.append(f"- [{d.doc_type}] **{d.title}** (ID: {d.id}){f' [{tags_str}]' if tags_str else ''}")

    return "\n".join(output)


@mcp.tool()
async def get_code_context(file_path: str, symbol: str | None = None) -> str:
    """Get source code context: the code itself, plus related docs and schematics.

    Args:
        file_path: Filename or path of the source code file (e.g., "spi_driver.c")
        symbol: Optional function/class name to focus on

    Returns:
        The code content, related documents, and schematic connections.
    """
    from app.db.base import async_session
    from app.models.document import Document, DocumentRelation
    from sqlalchemy import select, or_
    from sqlalchemy.orm import selectinload

    async with async_session() as db:
        # Find the document by title/filename match
        stmt = select(Document).where(
            Document.doc_type == "source_code",
            Document.title.ilike(f"%{file_path}%"),
        )
        result = await db.execute(stmt)
        doc = result.scalar_one_or_none()

        if not doc:
            return f"Source code not found: {file_path}"

        # Get related documents
        stmt_rel = select(DocumentRelation).where(
            or_(DocumentRelation.source_id == doc.id, DocumentRelation.target_id == doc.id)
        ).options(
            selectinload(DocumentRelation.source),
            selectinload(DocumentRelation.target),
        )
        result_rel = await db.execute(stmt_rel)
        relations = result_rel.scalars().all()

    # Build output
    output = f"# {doc.title}\n\n"

    if symbol:
        # Extract just the relevant function/class
        content = doc.content or ""
        # Simple search for the symbol in content
        lines = content.split("\n")
        found = False
        for i, line in enumerate(lines):
            if symbol in line:
                start = max(0, i - 2)
                end = min(len(lines), i + 50)
                output += f"```\n{''.join(lines[start:end])}\n```\n\n"
                found = True
                break
        if not found:
            output += f"Symbol '{symbol}' not found in file. Full content:\n\n"
            output += f"```\n{content[:3000]}\n```\n\n"
    else:
        output += f"```\n{(doc.content or '')[:5000]}\n```\n\n"

    # Add related context
    if relations:
        output += "## Related Materials\n\n"
        for r in relations:
            is_outgoing = r.source_id == doc.id
            other = r.target if is_outgoing else r.source
            output += (
                f"- **{other.title}** ({other.doc_type}) "
                f"[{r.relation_type}, confidence: {r.confidence:.2f}]\n"
                f"  ID: {other.id}\n"
            )

    return output


@mcp.resource("wiki://docs/{doc_id}")
async def document_resource(doc_id: str) -> str:
    """Access a document as an MCP resource."""
    return await get_document(doc_id)


if __name__ == "__main__":
    mcp.run(transport="sse")
