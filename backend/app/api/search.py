import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embedding import embedding_service
from app.db.base import get_db
from app.models.schemas import SearchQuery, SearchResponse, SearchResult

logger = logging.getLogger(__name__)
router = APIRouter()

# Will be detected at startup
_fts_config = "simple"


async def _detect_fts_config(db: AsyncSession) -> str:
    """Detect if Chinese FTS config is available."""
    global _fts_config
    for config in ("chinese_jieba", "chinese_zh"):
        try:
            await db.execute(text(f"SELECT to_tsvector('{config}', 'test')"))
            _fts_config = config
            logger.info(f"Using FTS config: {config}")
            return config
        except Exception:
            await db.rollback()
    logger.info("Using default FTS config: simple")
    return "simple"


@router.post("/", response_model=SearchResponse)
async def search_documents(body: SearchQuery, db: AsyncSession = Depends(get_db)):
    """
    Hybrid search: vector similarity + full-text keyword search.
    Results are fused using Reciprocal Rank Fusion (RRF).
    """
    query_embedding = await embedding_service.embed_query(body.query)
    limit = body.limit

    # ── Vector search ─────────────────────────────────────
    doc_type_filter = "AND d.doc_type = :doc_type" if body.doc_type else ""
    params: dict = {"embedding": str(query_embedding), "limit": limit * 2}
    if body.doc_type:
        params["doc_type"] = body.doc_type

    vector_sql = text(f"""
        SELECT c.document_id, c.content, c.metadata,
               d.title, d.doc_type,
               c.embedding <=> :embedding AS distance
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE 1=1 {doc_type_filter}
        ORDER BY c.embedding <=> :embedding
        LIMIT :limit
    """)
    vector_result = await db.execute(vector_sql, params)
    vector_rows = vector_result.fetchall()

    # ── Full-text search (auto-detect Chinese config) ────
    fts_params: dict = {"query": body.query, "limit": limit * 2}
    if body.doc_type:
        fts_params["doc_type"] = body.doc_type

    fts_sql = text(f"""
        SELECT d.id AS document_id, d.title, d.doc_type,
               ts_rank(
                   to_tsvector('{_fts_config}', coalesce(d.title, '') || ' ' || coalesce(d.content, '')),
                   plainto_tsquery('{_fts_config}', :query)
               ) AS rank
        FROM documents d
        WHERE to_tsvector('{_fts_config}', coalesce(d.title, '') || ' ' || coalesce(d.content, ''))
              @@ plainto_tsquery('{_fts_config}', :query)
              {doc_type_filter}
        ORDER BY rank DESC
        LIMIT :limit
    """)
    fts_result = await db.execute(fts_sql, fts_params)
    fts_rows = fts_result.fetchall()

    # ── Reciprocal Rank Fusion ────────────────────────────
    k = 60  # RRF constant
    scores: dict[str, dict] = {}

    for rank, row in enumerate(vector_rows):
        doc_key = str(row.document_id)
        if doc_key not in scores:
            scores[doc_key] = {
                "document_id": row.document_id,
                "title": row.title,
                "doc_type": row.doc_type,
                "chunk_content": row.content,
                "metadata": row.metadata or {},
                "rrf_score": 0.0,
            }
        scores[doc_key]["rrf_score"] += 1.0 / (k + rank + 1)

    for rank, row in enumerate(fts_rows):
        doc_key = str(row.document_id)
        if doc_key not in scores:
            scores[doc_key] = {
                "document_id": row.document_id,
                "title": row.title,
                "doc_type": row.doc_type,
                "chunk_content": "",
                "metadata": {},
                "rrf_score": 0.0,
            }
        scores[doc_key]["rrf_score"] += 1.0 / (k + rank + 1)

    # Sort by fused score, take top results
    ranked = sorted(scores.values(), key=lambda x: x["rrf_score"], reverse=True)[:limit]

    results = [
        SearchResult(
            document_id=r["document_id"],
            title=r["title"],
            doc_type=r["doc_type"],
            chunk_content=r["chunk_content"],
            score=r["rrf_score"],
            metadata=r["metadata"],
        )
        for r in ranked
    ]

    return SearchResponse(results=results, total=len(results), query=body.query)
