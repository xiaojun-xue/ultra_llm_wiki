import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.base import get_db
from app.models.document import Document, DocumentRelation, Tag, DocumentTag
from app.models.schemas import (
    DocumentCreate,
    DocumentDetail,
    DocumentSummary,
    DocumentUpdate,
    RelationOut,
)

router = APIRouter()


@router.get("/", response_model=list[DocumentSummary])
async def list_documents(
    doc_type: str | None = None,
    tag: str | None = None,
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """List documents with optional filtering."""
    stmt = select(Document).options(selectinload(Document.tags))

    if doc_type:
        stmt = stmt.where(Document.doc_type == doc_type)
    if tag:
        stmt = stmt.join(Document.tags).where(Tag.name == tag)

    stmt = stmt.order_by(Document.updated_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    docs = result.scalars().unique().all()

    return [
        DocumentSummary(
            id=d.id,
            title=d.title,
            doc_type=d.doc_type,
            mime_type=d.mime_type,
            tags=[t.name for t in d.tags],
            created_at=d.created_at,
            updated_at=d.updated_at,
        )
        for d in docs
    ]


@router.get("/{doc_id}", response_model=DocumentDetail)
async def get_document(doc_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get a document by ID with full details and relations."""
    stmt = (
        select(Document)
        .where(Document.id == doc_id)
        .options(
            selectinload(Document.tags),
            selectinload(Document.outgoing_relations).selectinload(DocumentRelation.target),
            selectinload(Document.incoming_relations).selectinload(DocumentRelation.source),
        )
    )
    result = await db.execute(stmt)
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    relations = []
    for r in doc.outgoing_relations:
        relations.append(
            RelationOut(
                id=r.id,
                source_id=r.source_id,
                target_id=r.target_id,
                source_title=doc.title,
                target_title=r.target.title if r.target else None,
                relation_type=r.relation_type,
                description=r.description,
                confidence=r.confidence,
                created_at=r.created_at,
            )
        )
    for r in doc.incoming_relations:
        relations.append(
            RelationOut(
                id=r.id,
                source_id=r.source_id,
                target_id=r.target_id,
                source_title=r.source.title if r.source else None,
                target_title=doc.title,
                relation_type=r.relation_type,
                description=r.description,
                confidence=r.confidence,
                created_at=r.created_at,
            )
        )

    return DocumentDetail(
        id=doc.id,
        title=doc.title,
        doc_type=doc.doc_type,
        content=doc.content,
        content_html=doc.content_html,
        metadata=doc.metadata_,
        file_path=doc.file_path,
        mime_type=doc.mime_type,
        tags=[t.name for t in doc.tags],
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        created_by=doc.created_by,
        relations=relations,
    )


@router.post("/", response_model=DocumentSummary, status_code=201)
async def create_document(body: DocumentCreate, db: AsyncSession = Depends(get_db)):
    """Create a new document (text-based, no file upload)."""
    doc = Document(
        title=body.title,
        doc_type=body.doc_type,
        content=body.content,
        metadata_=body.metadata,
    )

    # Handle tags
    for tag_name in body.tags:
        stmt = select(Tag).where(Tag.name == tag_name)
        result = await db.execute(stmt)
        tag = result.scalar_one_or_none()
        if not tag:
            tag = Tag(name=tag_name)
            db.add(tag)
        doc.tags.append(tag)

    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    return DocumentSummary(
        id=doc.id,
        title=doc.title,
        doc_type=doc.doc_type,
        mime_type=doc.mime_type,
        tags=[t.name for t in doc.tags],
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


@router.patch("/{doc_id}", response_model=DocumentSummary)
async def update_document(
    doc_id: uuid.UUID, body: DocumentUpdate, db: AsyncSession = Depends(get_db)
):
    """Update document fields."""
    stmt = select(Document).where(Document.id == doc_id).options(selectinload(Document.tags))
    result = await db.execute(stmt)
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if body.title is not None:
        doc.title = body.title
    if body.content is not None:
        doc.content = body.content
    if body.metadata is not None:
        doc.metadata_ = body.metadata

    if body.tags is not None:
        doc.tags.clear()
        for tag_name in body.tags:
            stmt_tag = select(Tag).where(Tag.name == tag_name)
            result_tag = await db.execute(stmt_tag)
            tag = result_tag.scalar_one_or_none()
            if not tag:
                tag = Tag(name=tag_name)
                db.add(tag)
            doc.tags.append(tag)

    await db.commit()
    await db.refresh(doc)

    return DocumentSummary(
        id=doc.id,
        title=doc.title,
        doc_type=doc.doc_type,
        mime_type=doc.mime_type,
        tags=[t.name for t in doc.tags],
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


@router.delete("/{doc_id}", status_code=204)
async def delete_document(doc_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Delete a document and its chunks/relations (cascades)."""
    stmt = select(Document).where(Document.id == doc_id)
    result = await db.execute(stmt)
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Delete file from MinIO if exists
    if doc.file_path:
        from app.core.storage import storage_service
        try:
            await storage_service.delete_file(doc.file_path)
        except Exception:
            pass  # File may already be gone

    await db.delete(doc)
    await db.commit()
