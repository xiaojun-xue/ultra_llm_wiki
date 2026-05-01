import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.base import get_db
from app.models.document import Document, DocumentRelation
from app.models.schemas import RelationCreate, RelationOut

router = APIRouter()


@router.get("/{doc_id}", response_model=list[RelationOut])
async def get_relations(
    doc_id: uuid.UUID,
    relation_type: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Get all relations for a document (both outgoing and incoming)."""
    # Outgoing
    stmt_out = (
        select(DocumentRelation)
        .where(DocumentRelation.source_id == doc_id)
        .options(selectinload(DocumentRelation.target))
    )
    if relation_type:
        stmt_out = stmt_out.where(DocumentRelation.relation_type == relation_type)

    # Incoming
    stmt_in = (
        select(DocumentRelation)
        .where(DocumentRelation.target_id == doc_id)
        .options(selectinload(DocumentRelation.source))
    )
    if relation_type:
        stmt_in = stmt_in.where(DocumentRelation.relation_type == relation_type)

    out_result = await db.execute(stmt_out)
    in_result = await db.execute(stmt_in)

    relations = []
    for r in out_result.scalars().all():
        relations.append(
            RelationOut(
                id=r.id,
                source_id=r.source_id,
                target_id=r.target_id,
                source_title=None,
                target_title=r.target.title if r.target else None,
                relation_type=r.relation_type,
                description=r.description,
                confidence=r.confidence,
                created_at=r.created_at,
            )
        )
    for r in in_result.scalars().all():
        relations.append(
            RelationOut(
                id=r.id,
                source_id=r.source_id,
                target_id=r.target_id,
                source_title=r.source.title if r.source else None,
                target_title=None,
                relation_type=r.relation_type,
                description=r.description,
                confidence=r.confidence,
                created_at=r.created_at,
            )
        )

    return relations


@router.post("/", response_model=RelationOut, status_code=201)
async def create_relation(body: RelationCreate, db: AsyncSession = Depends(get_db)):
    """Create a new relation between two documents."""
    # Verify both documents exist
    for doc_id in [body.source_id, body.target_id]:
        stmt = select(Document.id).where(Document.id == doc_id)
        result = await db.execute(stmt)
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")

    relation = DocumentRelation(
        source_id=body.source_id,
        target_id=body.target_id,
        relation_type=body.relation_type,
        description=body.description,
        confidence=body.confidence,
    )
    db.add(relation)
    await db.commit()
    await db.refresh(relation)

    return RelationOut(
        id=relation.id,
        source_id=relation.source_id,
        target_id=relation.target_id,
        relation_type=relation.relation_type,
        description=relation.description,
        confidence=relation.confidence,
        created_at=relation.created_at,
    )


@router.delete("/{relation_id}", status_code=204)
async def delete_relation(relation_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Delete a relation."""
    stmt = select(DocumentRelation).where(DocumentRelation.id == relation_id)
    result = await db.execute(stmt)
    relation = result.scalar_one_or_none()
    if not relation:
        raise HTTPException(status_code=404, detail="Relation not found")

    await db.delete(relation)
    await db.commit()
