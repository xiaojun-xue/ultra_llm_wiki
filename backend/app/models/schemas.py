import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# ── Document ──────────────────────────────────────────────

class DocumentCreate(BaseModel):
    title: str
    doc_type: str = Field(pattern=r"^(source_code|document|schematic|note)$")
    content: str | None = None
    metadata: dict = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class DocumentUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    metadata: dict | None = None
    tags: list[str] | None = None


class DocumentSummary(BaseModel):
    id: uuid.UUID
    title: str
    doc_type: str
    mime_type: str | None
    tags: list[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentDetail(DocumentSummary):
    content: str | None
    content_html: str | None
    metadata: dict
    file_path: str | None
    created_by: str | None
    relations: list["RelationOut"]

    model_config = {"from_attributes": True}


# ── Relation ──────────────────────────────────────────────

class RelationCreate(BaseModel):
    source_id: uuid.UUID
    target_id: uuid.UUID
    relation_type: str = Field(
        pattern=r"^(references|implements|depends_on|related_to|derived_from)$"
    )
    description: str | None = None
    confidence: float = 1.0


class RelationOut(BaseModel):
    id: uuid.UUID
    source_id: uuid.UUID
    target_id: uuid.UUID
    source_title: str | None = None
    target_title: str | None = None
    relation_type: str
    description: str | None
    confidence: float
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Search ────────────────────────────────────────────────

class SearchQuery(BaseModel):
    query: str
    doc_type: str | None = None
    tags: list[str] = Field(default_factory=list)
    limit: int = Field(default=10, ge=1, le=50)


class SearchResult(BaseModel):
    document_id: uuid.UUID
    title: str
    doc_type: str
    chunk_content: str
    score: float
    metadata: dict


class SearchResponse(BaseModel):
    results: list[SearchResult]
    total: int
    query: str


# ── Tag ───────────────────────────────────────────────────

class TagOut(BaseModel):
    id: int
    name: str
    category: str | None

    model_config = {"from_attributes": True}


# ── Upload ────────────────────────────────────────────────

class UploadResponse(BaseModel):
    document_id: uuid.UUID
    title: str
    doc_type: str
    chunks_count: int
    relations_found: int
