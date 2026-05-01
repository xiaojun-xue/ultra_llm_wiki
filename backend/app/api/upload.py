"""File upload API — returns task_id immediately, processes in background."""

import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import storage_service
from app.core.task_manager import task_manager, TaskStatus
from app.db.base import get_db
from app.models.document import Document, Tag

logger = logging.getLogger(__name__)

router = APIRouter()

_EXT_TO_TYPE = {
    ".c": "source_code", ".h": "source_code", ".cpp": "source_code", ".hpp": "source_code",
    ".java": "source_code", ".py": "source_code", ".js": "source_code", ".ts": "source_code",
    ".rs": "source_code", ".go": "source_code",
    ".md": "document", ".txt": "document", ".pdf": "document",
    ".doc": "document", ".docx": "document",
    ".ini": "document", ".cfg": "document", ".conf": "document",
    ".json": "document", ".yaml": "document", ".yml": "document",
    ".sch": "schematic", ".schdoc": "schematic", ".kicad_sch": "schematic",
    ".brd": "schematic", ".pcbdoc": "schematic",
}


def _guess_doc_type(filename: str, content_type: str) -> str:
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return _EXT_TO_TYPE.get(ext, "document")


# ─────────────────────────────────────────────────────────────────────────────
# Background processor
# ─────────────────────────────────────────────────────────────────────────────


async def _process_document(
    task_id: str,
    file_data: bytes,
    filename: str,
    file_title: str,
    doc_type: str,
    tag_list: list[str],
    original_size: int,
) -> None:
    """
    Background pipeline: parse → embed → discover relations.
    Updates Redis task state at each step.
    """
    from app.core.ingest import ingest_document
    from app.core.relation_discovery import discover_relations
    from app.db.base import async_session as async_session_maker
    from app.models.document import DocumentRelation
    from sqlalchemy import select

    async with async_session_maker() as db:
        try:
            # ── Step 1: Create document record ──────────────────────────────
            await task_manager.set_status(task_id, TaskStatus.PARSING, progress=15, step_index=1)
            doc = Document(
                title=file_title,
                doc_type=doc_type,
                file_path=None,
                mime_type=None,
                metadata_={"original_filename": filename, "size_bytes": original_size},
            )
            db.add(doc)
            await db.flush()

            for tag_name in tag_list:
                stmt = select(Tag).where(Tag.name == tag_name)
                result = await db.execute(stmt)
                tag = result.scalar_one_or_none()
                if not tag:
                    tag = Tag(name=tag_name)
                    db.add(tag)
                    await db.flush()
                from app.models.document import DocumentTag
                db.add(DocumentTag(document_id=doc.id, tag_id=tag.id))
            await db.commit()
            await db.refresh(doc)

            # ── Step 2: Parse + chunk + embed ──────────────────────────────
            await task_manager.set_status(task_id, TaskStatus.PARSING, progress=30, step_index=1)
            chunks_count = 0
            try:
                chunks_count = await ingest_document(db, doc, file_data, filename)
            except Exception as e:
                logger.error(f"Ingest failed for {filename}: {e}")
            await task_manager.set_status(task_id, TaskStatus.EMBEDDING, progress=60, step_index=2)

            # ── Step 3: Relation discovery ─────────────────────────────────
            await task_manager.set_status(task_id, TaskStatus.DISCOVERING, progress=80, step_index=3)
            relations_found = 0
            try:
                relations_found = await discover_relations(db, doc)
            except Exception as e:
                logger.error(f"Relation discovery failed for {filename}: {e}")

            # ── Step 4: Build result summary ────────────────────────────────
            from app.models.document import Chunk
            stmt = select(Chunk).where(Chunk.document_id == doc.id).order_by(Chunk.chunk_index)
            chunk_result = await db.execute(stmt)
            chunks = chunk_result.scalars().all()

            chunk_summary = []
            for c in chunks:
                preview = (c.content or "")[:80].replace("\n", " ").strip()
                if len(preview) == 80:
                    preview += "..."
                chunk_summary.append({
                    "index": c.chunk_index,
                    "preview": preview,
                    "tokens": c.token_count or 0,
                    "type": (c.metadata_ or {}).get("type", "text"),
                })

            # Build relations summary
            rel_stmt = select(DocumentRelation).where(
                (DocumentRelation.source_id == doc.id) | (DocumentRelation.target_id == doc.id)
            )
            rel_result = await db.execute(rel_stmt)
            relations = []
            for rel in rel_result.scalars():
                is_source = rel.source_id == doc.id
                other_id = rel.target_id if is_source else rel.source_id
                other_doc_result = await db.execute(select(Document).where(Document.id == other_id))
                other_doc = other_doc_result.scalar_one_or_none()
                relations.append({
                    "target_id": str(other_id),
                    "target_title": other_doc.title if other_doc else "Unknown",
                    "target_type": other_doc.doc_type if other_doc else "unknown",
                    "relation_type": rel.relation_type,
                    "confidence": rel.confidence,
                    "match_reason": rel.description or "",
                })

            relations.sort(key=lambda r: r["confidence"], reverse=True)

            await task_manager.complete(
                task_id,
                result={
                    "document_id": str(doc.id),
                    "title": doc.title,
                    "doc_type": doc.doc_type,
                    "file_size_bytes": original_size,
                    "chunks_count": chunks_count,
                    "chunk_summary": chunk_summary[:10],
                    "relations_count": relations_found,
                    "relations": relations,
                },
            )

        except Exception as e:
            logger.exception(f"Task {task_id} failed: {e}")
            await task_manager.fail(task_id, str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Upload endpoint
# ─────────────────────────────────────────────────────────────────────────────


class UploadTaskResponse(BaseModel):
    task_id: str
    message: str


@router.post("/", response_model=UploadTaskResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form(None),
    tags: str = Form(""),
):
    """
    Upload a file: store to MinIO, then process in background.
    Returns immediately with a task_id for progress polling.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    # Read file content synchronously (can't be done after response returns)
    data = await file.read()
    if len(data) > 100 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 100MB)")

    doc_type = _guess_doc_type(file.filename, file.content_type or "")
    file_title = title or file.filename
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    # Upload to MinIO synchronously first
    try:
        await storage_service.upload_file(
            data, file.filename, file.content_type or "application/octet-stream"
        )
    except Exception as e:
        logger.error(f"MinIO upload failed: {e}")
        raise HTTPException(status_code=500, detail="File storage failed")

    # Create task — returns task_id immediately
    task_id = await task_manager.create_task(
        steps=["文件上传", "解析与分块", "生成向量嵌入", "发现关联关系"],
        metadata={"filename": file.filename, "size_bytes": len(data)},
    )

    # Mark upload step done, start parsing in background
    await task_manager.set_status(task_id, TaskStatus.PARSING, progress=10, step_index=0)

    background_tasks.add_task(
        _process_document,
        task_id,
        data,
        file.filename,
        file_title,
        doc_type,
        tag_list,
        len(data),
    )

    return UploadTaskResponse(
        task_id=task_id,
        message="文件已上传，正在后台处理中",
    )
