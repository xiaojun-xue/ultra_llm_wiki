# 模块设计 - 任务管理 (Task Manager)

## 1. 模块概述

任务管理模块使用 Redis 追踪异步文档处理任务的进度。

### 1.1 核心文件

```
core/task_manager.py   # Redis 状态存储 + 进度更新
api/tasks.py           # FastAPI 任务查询接口
```

---

## 2. Redis 数据结构

```
Key: task:{task_id}
Type: Hash
TTL: 24 小时
```

### 2.1 Hash 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| status | string | pending / parsing / embedding / discovering / done / failed |
| progress | int | 0-100 |
| steps | JSON | 步骤数组 |
| created_at | string | ISO 时间 |
| updated_at | string | ISO 时间 |
| error | string | 错误信息（失败时） |
| result | JSON | 最终结果对象 |

### 2.2 steps 格式

```json
[
    {"name": "saving", "status": "done", "progress": 100},
    {"name": "parsing", "status": "done", "progress": 100},
    {"name": "embedding", "status": "in_progress", "progress": 50},
    {"name": "discovering", "status": "pending", "progress": 0}
]
```

---

## 3. 核心 API

### 3.1 创建任务

```python
async def create_task(task_id: str) -> None:
    await redis.hset(f"task:{task_id}", mapping={
        "status": "pending",
        "progress": 0,
        "steps": json.dumps(DEFAULT_STEPS),
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    })
    await redis.expire(f"task:{task_id}", 86400)  # 24h TTL
```

### 3.2 更新进度

```python
async def update_task(task_id: str, step: str, status: str, progress: int) -> None:
    task_key = f"task:{task_id}"
    steps_json = await redis.hget(task_key, "steps")
    steps = json.loads(steps_json)

    # 更新指定步骤
    for s in steps:
        if s["name"] == step:
            s["status"] = status
            s["progress"] = progress
            break

    # 计算总体进度
    overall_progress = sum(s["progress"] for s in steps) // len(steps)

    await redis.hset(task_key, mapping={
        "status": _derive_status(steps),
        "progress": overall_progress,
        "steps": json.dumps(steps),
        "updated_at": datetime.utcnow().isoformat(),
    })

def _derive_status(steps: list[dict]) -> str:
    """根据步骤状态推导任务状态"""
    if all(s["status"] == "done" for s in steps):
        return "done"
    if any(s["status"] == "failed" for s in steps):
        return "failed"
    if any(s["status"] == "in_progress" for s in steps):
        return "in_progress"
    return "pending"
```

### 3.3 获取任务

```python
async def get_task(task_id: str) -> TaskStatus | None:
    data = await redis.hgetall(f"task:{task_id}")
    if not data:
        return None
    return TaskStatus(
        task_id=task_id,
        status=data["status"],
        progress=int(data["progress"]),
        steps=json.loads(data["steps"]),
        created_at=data["created_at"],
        updated_at=data["updated_at"],
        error=data.get("error"),
        result=json.loads(data["result"]) if data.get("result") else None,
    )
```

---

## 4. 前端轮询

```typescript
// web/lib/api.ts
export async function pollTask(
  taskId: string,
  onProgress?: (task: TaskStatus) => void
): Promise<TaskStatus> {
  return new Promise((resolve, reject) => {
    const interval = setInterval(async () => {
      try {
        const task = await getTask(taskId);
        onProgress?.(task);

        if (task.status === "done") {
          clearInterval(interval);
          resolve(task);
        } else if (task.status === "failed") {
          clearInterval(interval);
          reject(new Error(task.error || "Processing failed"));
        }
      } catch (err) {
        clearInterval(interval);
        reject(err);
      }
    }, 1000);  // 每秒轮询
  });
}
```

---

## 5. 任务流程

```
上传文件
    │
    ▼
创建 Task (status=pending)
    │
    ▼
update_task("saving", "done", 100)
    │
    ▼
update_task("parsing", "done", 100)  ──▶ ingest_document()
    │
    ▼
update_task("embedding", "done", 100) ──▶ embedding_service.embed()
    │
    ▼
update_task("discovering", "done", 100) ──▶ discover_relations()
    │
    ▼
status="done", progress=100
```

---

*文档版本: v1.0*
