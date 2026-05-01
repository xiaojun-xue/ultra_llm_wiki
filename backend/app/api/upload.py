import logging

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ingest import ingest_document
from app.core.relation_discovery import discover_relations
from app.core.storage import storage_service
from app.db.base import get_db
from app.models.document import Document, Tag
from app.models.schemas import UploadResponse

logger = logging.getLogger(__name__)

router = APIRouter()

# Map file extensions to doc_type
_EXT_TO_TYPE = {
    # Source code
    ".c": "source_code", ".h": "source_code", ".cpp": "source_code", ".hpp": "source_code",
    ".java": "source_code", ".py": "source_code", ".js": "source_code", ".ts": "source_code",
    ".rs": "source_code", ".go": "source_code",
    # Documents
    ".md": "document", ".txt": "document", ".pdf": "document",
    ".doc": "document", ".docx": "document",
    ".ini": "document", ".cfg": "document", ".conf": "document",
    ".json": "document", ".yaml": "document", ".yml": "document",
    # Schematics
    ".sch": "schematic", ".schdoc": "schematic", ".kicad_sch": "schematic",
    ".brd": "schematic", ".pcbdoc": "schematic",
}


def _guess_doc_type(filename: str, content_type: str) -> str:
    """Guess document type from file extension."""
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return _EXT_TO_TYPE.get(ext, "document")


@router.post("/", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(None),
    tags: str = Form(""),  # comma-separated
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a file, store it in MinIO, create a document record.
    Parsing and embedding happen asynchronously (Phase 2).
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    data = await file.read()
    if len(data) > 100 * 1024 * 1024:  # 100MB limit
        raise HTTPException(status_code=413, detail="File too large (max 100MB)")

    doc_type = _guess_doc_type(file.filename, file.content_type or "")
    file_title = title or file.filename

    # Upload to MinIO
    storage_path = await storage_service.upload_file(
        data, file.filename, file.content_type or "application/octet-stream"
    )

    # Create document record
    doc = Document(
        title=file_title,
        doc_type=doc_type,
        file_path=storage_path,
        mime_type=file.content_type,
        metadata_={"original_filename": file.filename, "size_bytes": len(data)},
    )
    db.add(doc)
    await db.flush()

    # Handle tags
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    for tag_name in tag_list:
        stmt = select(Tag).where(Tag.name == tag_name)
        result = await db.execute(stmt)
        tag = result.scalar_one_or_none()
        if not tag:
            tag = Tag(name=tag_name)
            db.add(tag)
            await db.flush()
        # Use the association table directly instead of lazy-loaded relationship
        from app.models.document import DocumentTag
        db.add(DocumentTag(document_id=doc.id, tag_id=tag.id))
    await db.commit()
    await db.refresh(doc)

    # Parse, chunk, and embed the document
    chunks_count = 0
    try:
        chunks_count = await ingest_document(db, doc, data, file.filename)
    except Exception as e:
        logger.error(f"Ingest failed for {file.filename}: {e}")

    # Discover relations with existing documents
    relations_found = 0
    try:
        relations_found = await discover_relations(db, doc)
    except Exception as e:
        logger.error(f"Relation discovery failed for {file.filename}: {e}")

    return UploadResponse(
        document_id=doc.id,
        title=doc.title,
        doc_type=doc.doc_type,
        chunks_count=chunks_count,
        relations_found=relations_found,
    )
