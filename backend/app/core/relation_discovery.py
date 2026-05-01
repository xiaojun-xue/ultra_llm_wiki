"""
Automatic relation discovery between documents.

Strategies:
1. Code dependency: #include / import → depends_on
2. Document cross-reference: file mentions → references
3. Schematic-code linking: signal/component name matching → implements
4. Semantic similarity: embedding cosine distance → related_to
"""

import logging
import re

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentRelation

logger = logging.getLogger(__name__)


async def discover_relations(db: AsyncSession, doc: Document) -> int:
    """
    Run all relation discovery strategies for a newly ingested document.
    Returns the number of relations created.
    """
    count = 0
    count += await _discover_by_references(db, doc)
    count += await _discover_by_name_matching(db, doc)
    count += await _discover_by_semantic_similarity(db, doc)
    return count


async def _discover_by_references(db: AsyncSession, doc: Document) -> int:
    """
    Match explicit references found during parsing (e.g., #include "spi.h")
    to existing documents by filename.
    """
    refs = (doc.metadata_ or {}).get("references", [])
    if not refs:
        return 0

    count = 0
    for ref in refs:
        # Normalize the reference to a filename pattern
        ref_clean = ref.replace("\\", "/").split("/")[-1].lower()
        if not ref_clean:
            continue

        # Search for documents whose title or original_filename matches
        stmt = select(Document).where(
            Document.id != doc.id,
            Document.title.ilike(f"%{ref_clean}%"),
        )
        result = await db.execute(stmt)
        targets = result.scalars().all()

        for target in targets:
            relation_type = "depends_on" if doc.doc_type == "source_code" else "references"
            created = await _create_relation(
                db, doc.id, target.id, relation_type,
                description=f"'{doc.title}' references '{ref}'",
                confidence=0.9,
            )
            if created:
                count += 1

    return count


async def _discover_by_name_matching(db: AsyncSession, doc: Document) -> int:
    """
    Match schematic signals/components to code files by keyword overlap.
    E.g., schematic has SPI1_MOSI signal → code has spi_driver.c
    """
    if doc.doc_type not in ("schematic", "source_code"):
        return 0

    meta = doc.metadata_ or {}
    signals = meta.get("signals", [])
    components = meta.get("components", [])
    keywords = set()

    # Extract meaningful keywords from signals
    for sig in signals:
        # SPI1_MOSI → SPI, SPI1
        parts = re.split(r"[_\d]+", sig)
        for p in parts:
            if len(p) >= 3:
                keywords.add(p.lower())

    # Extract from component values
    for comp in components:
        if isinstance(comp, str) and len(comp) >= 3:
            keywords.add(comp.lower())

    if not keywords:
        return 0

    count = 0
    # Find source_code/schematic documents that contain these keywords
    other_type = "source_code" if doc.doc_type == "schematic" else "schematic"
    stmt = select(Document).where(
        Document.id != doc.id,
        Document.doc_type == other_type,
    )
    result = await db.execute(stmt)
    candidates = result.scalars().all()

    for candidate in candidates:
        content = (candidate.content or "").lower()
        title = (candidate.title or "").lower()
        matched_keywords = [kw for kw in keywords if kw in content or kw in title]

        if len(matched_keywords) >= 2:  # Require at least 2 keyword matches
            created = await _create_relation(
                db, doc.id, candidate.id, "implements",
                description=f"Matched keywords: {', '.join(matched_keywords[:5])}",
                confidence=min(0.5 + 0.1 * len(matched_keywords), 0.95),
            )
            if created:
                count += 1

    return count


async def _discover_by_semantic_similarity(db: AsyncSession, doc: Document) -> int:
    """
    Find semantically similar documents using embedding cosine distance.
    Creates 'related_to' relations for docs above similarity threshold.
    """
    # Get the average embedding of this document's chunks
    avg_embedding_sql = text("""
        SELECT AVG(embedding) as avg_emb
        FROM chunks
        WHERE document_id = :doc_id AND embedding IS NOT NULL
    """)
    result = await db.execute(avg_embedding_sql, {"doc_id": str(doc.id)})
    row = result.fetchone()

    if row is None or row.avg_emb is None:
        return 0

    avg_embedding = row.avg_emb

    # Find documents with similar average chunk embeddings
    similar_sql = text("""
        SELECT c.document_id, d.title, d.doc_type,
               AVG(c.embedding <=> :embedding) as avg_distance
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE c.document_id != :doc_id
          AND c.embedding IS NOT NULL
        GROUP BY c.document_id, d.title, d.doc_type
        HAVING AVG(c.embedding <=> :embedding) < :threshold
        ORDER BY avg_distance
        LIMIT 5
    """)
    result = await db.execute(similar_sql, {
        "embedding": str(avg_embedding),
        "doc_id": str(doc.id),
        "threshold": 0.3,  # cosine distance < 0.3 means similarity > 0.7
    })
    similar_docs = result.fetchall()

    count = 0
    for row in similar_docs:
        confidence = max(0.0, 1.0 - row.avg_distance)  # Convert distance to similarity
        created = await _create_relation(
            db, doc.id, row.document_id, "related_to",
            description=f"Semantic similarity: {confidence:.2f}",
            confidence=round(confidence, 3),
        )
        if created:
            count += 1

    return count


async def _create_relation(
    db: AsyncSession,
    source_id, target_id,
    relation_type: str,
    description: str = "",
    confidence: float = 1.0,
) -> bool:
    """Create a relation if it doesn't already exist. Returns True if created."""
    # Check for existing
    stmt = select(DocumentRelation).where(
        DocumentRelation.source_id == source_id,
        DocumentRelation.target_id == target_id,
        DocumentRelation.relation_type == relation_type,
    )
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        return False

    relation = DocumentRelation(
        source_id=source_id,
        target_id=target_id,
        relation_type=relation_type,
        description=description,
        confidence=confidence,
    )
    db.add(relation)
    await db.commit()
    logger.info(f"Created relation: {source_id} --{relation_type}--> {target_id}")
    return True
