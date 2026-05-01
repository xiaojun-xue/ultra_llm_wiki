"""
Ingest pipeline: file → parse → chunk → embed → store in DB.
This is the central orchestrator for document processing.
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embedding import embedding_service
from app.models.document import Chunk, Document, Tag
from app.parsers import get_parser, ParseResult

logger = logging.getLogger(__name__)


async def ingest_document(
    db: AsyncSession,
    doc: Document,
    file_data: bytes,
    filename: str,
) -> int:
    """
    Full ingest pipeline for a single document.

    1. Parse the file into text + chunks
    2. Update document record with parsed content
    3. Generate embeddings for each chunk
    4. Store chunks with embeddings in DB

    Returns the number of chunks created.
    """
    parser = get_parser(filename)
    if not parser:
        logger.warning(f"No parser found for: {filename}")
        return 0

    # Step 1: Parse
    logger.info(f"Parsing {filename} with {parser.__class__.__name__}")
    result: ParseResult = await parser.parse(file_data, filename)

    # Step 2: Update document with parsed content
    doc.content = result.content
    doc.content_html = result.content_html
    doc.title = result.title or doc.title
    # Merge metadata
    existing_meta = doc.metadata_ or {}
    existing_meta.update(result.metadata)
    if result.references:
        existing_meta["references"] = result.references
    doc.metadata_ = existing_meta

    if not result.chunks:
        logger.info(f"No chunks generated for {filename}")
        await db.commit()
        return 0

    # Step 3: Generate embeddings in batch
    chunk_texts = [c.content for c in result.chunks]
    logger.info(f"Generating embeddings for {len(chunk_texts)} chunks")

    try:
        embeddings = await embedding_service.embed(chunk_texts)
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        # Store chunks without embeddings — they can be embedded later
        embeddings = [None] * len(chunk_texts)

    # Step 4: Store chunks
    for i, (parsed_chunk, embedding) in enumerate(zip(result.chunks, embeddings)):
        chunk = Chunk(
            document_id=doc.id,
            chunk_index=i,
            content=parsed_chunk.content,
            embedding=embedding,
            metadata_=parsed_chunk.metadata,
            token_count=_estimate_tokens(parsed_chunk.content),
        )
        db.add(chunk)

    await db.commit()
    logger.info(f"Ingested {len(result.chunks)} chunks for {filename}")

    return len(result.chunks)


async def re_embed_document(db: AsyncSession, doc_id: uuid.UUID) -> int:
    """Re-generate embeddings for all chunks of a document (e.g., after model change)."""
    stmt = select(Chunk).where(Chunk.document_id == doc_id).order_by(Chunk.chunk_index)
    result = await db.execute(stmt)
    chunks = result.scalars().all()

    if not chunks:
        return 0

    texts = [c.content for c in chunks]
    embeddings = await embedding_service.embed(texts)

    for chunk, embedding in zip(chunks, embeddings):
        chunk.embedding = embedding

    await db.commit()
    return len(chunks)


def _estimate_tokens(text: str) -> int:
    """Rough token count estimate: ~0.75 tokens per character for mixed CJK/English."""
    ascii_chars = sum(1 for c in text if ord(c) < 128)
    cjk_chars = len(text) - ascii_chars
    return int(ascii_chars / 4 + cjk_chars * 1.5)
