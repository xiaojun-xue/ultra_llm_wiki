"""
Task progress manager using Redis.

Provides async task tracking for long-running operations like
document upload → parse → embed → relation discovery.

Task states flow:
  pending → parsing → embedding → discovering → done
           (or:       →         →          → failed)
"""

import asyncio
import json
import uuid
import logging
from datetime import datetime
from enum import Enum
from typing import Any

import redis.asyncio as redis

from app.config import settings

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    PARSING = "parsing"
    EMBEDDING = "embedding"
    DISCOVERING = "discovering"
    DONE = "done"
    FAILED = "failed"


class TaskManager:
    """
    Redis-backed task tracker.

    Each task is stored as a JSON hash:
      task:{task_id} = {
        "task_id": str,
        "status": str,
        "progress": int,        # 0-100
        "created_at": str,
        "updated_at": str,
        "error": str | null,
        "result": dict | null,  # final result when done
        "steps": [
          {"name": "文件上传", "status": "done", "progress": 100},
          {"name": "解析文件", "status": "done", "progress": 100},
          ...
        ]
      }
    """

    TASK_TTL_SECONDS = 3600 * 24  # 24 hours

    def __init__(self):
        self._pool: redis.ConnectionPool | None = None
        self._redis: redis.Redis | None = None

    async def _get_redis(self) -> redis.Redis:
        if self._redis is None:
            self._pool = redis.ConnectionPool.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            self._redis = redis.Redis(connection_pool=self._pool)
        return self._redis

    def _key(self, task_id: str) -> str:
        return f"task:{task_id}"

    # ─────────────────────────────────────────────────────────────────────────
    # Create & update tasks
    # ─────────────────────────────────────────────────────────────────────────

    async def create_task(
        self,
        steps: list[str] | None = None,
        metadata: dict | None = None,
    ) -> str:
        """
        Create a new task and return its ID.
        steps: human-readable step names, e.g. ["文件上传", "解析文件", "生成向量"]
        """
        r = await self._get_redis()
        task_id = str(uuid.uuid4())

        default_steps = [
            "文件上传",
            "解析文件",
            "生成向量",
            "发现关联",
        ]
        task_steps = steps or default_steps

        steps_state = [
            {"name": s, "status": "pending", "progress": 0}
            for s in task_steps
        ]

        now = datetime.utcnow().isoformat()
        payload = {
            "task_id": task_id,
            "status": TaskStatus.PENDING.value,
            "progress": 0,
            "created_at": now,
            "updated_at": now,
            "error": None,
            "result": None,
            "metadata": metadata or {},
            "steps": steps_state,
        }

        await r.set(self._key(task_id), json.dumps(payload), ex=self.TASK_TTL_SECONDS)
        return task_id

    async def update_step(
        self,
        task_id: str,
        step_index: int,
        *,
        status: str = "done",
        progress: int = 100,
    ) -> None:
        """Mark a specific step as completed."""
        r = await self._get_redis()
        data = await r.get(self._key(task_id))
        if not data:
            return
        task = json.loads(data)

        steps = task.get("steps", [])
        if 0 <= step_index < len(steps):
            steps[step_index] = {"name": steps[step_index]["name"], "status": status, "progress": progress}
            task["steps"] = steps

        task["updated_at"] = datetime.utcnow().isoformat()
        await r.set(self._key(task_id), json.dumps(task), ex=self.TASK_TTL_SECONDS)

    async def set_status(
        self,
        task_id: str,
        status: TaskStatus,
        *,
        progress: int | None = None,
        error: str | None = None,
        result: dict | None = None,
        step_index: int | None = None,
    ) -> None:
        """
        Update task status, optionally marking a step as done.
        If step_index is given, that step is marked as done automatically.
        """
        r = await self._get_redis()
        data = await r.get(self._key(task_id))
        if not data:
            return
        task = json.loads(data)

        task["status"] = status.value
        if progress is not None:
            task["progress"] = progress
        if error is not None:
            task["error"] = error
        if result is not None:
            task["result"] = result
        if step_index is not None:
            steps = task.get("steps", [])
            if 0 <= step_index < len(steps):
                steps[step_index] = {"name": steps[step_index]["name"], "status": "done", "progress": 100}
                task["steps"] = steps

        task["updated_at"] = datetime.utcnow().isoformat()
        await r.set(self._key(task_id), json.dumps(task), ex=self.TASK_TTL_SECONDS)

    async def set_progress(self, task_id: str, progress: int) -> None:
        """Update overall progress percentage (0-100)."""
        r = await self._get_redis()
        data = await r.get(self._key(task_id))
        if not data:
            return
        task = json.loads(data)
        task["progress"] = max(0, min(100, progress))
        task["updated_at"] = datetime.utcnow().isoformat()
        await r.set(self._key(task_id), json.dumps(task), ex=self.TASK_TTL_SECONDS)

    async def complete(
        self,
        task_id: str,
        result: dict,
        *,
        progress: int = 100,
    ) -> None:
        """Mark task as done with final result."""
        await self.set_status(task_id, TaskStatus.DONE, progress=progress, result=result)

    async def fail(self, task_id: str, error: str) -> None:
        """Mark task as failed with error message."""
        await self.set_status(task_id, TaskStatus.FAILED, error=error, progress=0)

    # ─────────────────────────────────────────────────────────────────────────
    # Read tasks
    # ─────────────────────────────────────────────────────────────────────────

    async def get_task(self, task_id: str) -> dict | None:
        """Return full task data or None if not found."""
        r = await self._get_redis()
        data = await r.get(self._key(task_id))
        if not data:
            return None
        return json.loads(data)

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None
        if self._pool:
            await self._pool.disconnect()
            self._pool = None


# Global singleton
task_manager = TaskManager()
