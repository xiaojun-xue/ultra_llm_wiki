"""Task status API — poll for upload/processing progress."""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.task_manager import task_manager

logger = logging.getLogger(__name__)

router = APIRouter()


class TaskResponse(BaseModel):
    task_id: str
    status: str
    progress: int
    steps: list[dict]
    created_at: str
    updated_at: str
    error: str | None = None
    result: dict | None = None


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str):
    """Get current status of a task (upload/processing)."""
    task = await task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskResponse(**task)
