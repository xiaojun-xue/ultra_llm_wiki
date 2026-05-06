# 模块设计 - 文档摄取 (Ingest)

## 1. 模块概述

摄取模块是文档处理流水线的核心编排器，协调解析、Embedding、存储全过程。

### 1.1 核心职责

- 协调解析器处理文件
- 生成 Embedding 向量
- 存储 Chunks 到 PostgreSQL
- 管理任务状态（通过 Task Manager）

### 1.2 流程图

```
ingest_document()
    │
    ├──▶ get_parser(filename)     # 选择解析器
    │
    ├──▶ parser.parse()           # 解析文件
    │       │
    │       └──▶ ParseResult {chunks, content, metadata}
    │
    ├──▶ embedding_service.embed() # 生成向量
    │       │
    │       └──▶ list[embedding]
    │
    └──▶ 存储 Chunks 到 DB
            │
            └──▶ 每条 Chunk:
                - document_id
                - chunk_index
                - content
                - embedding
                - metadata
```

---

## 2. 核心函数

### 2.1 ingest_document

```python
async def ingest_document(
    db: AsyncSession,
    doc: Document,        # 已创建的 Document 记录
    file_data: bytes,
    filename: str,
) -> int:
    """完整摄取流程，返回 chunk 数量"""
    # 1. 解析
    parser = get_parser(filename)
    result = parser.parse(file_data, filename)

    # 2. 更新 Document
    doc.content = result.content
    doc.content_html = result.content_html
    doc.metadata_ = {**doc.metadata_, **result.metadata}

    # 3. 生成 Embedding
    embeddings = await embedding_service.embed(
        [c.content for c in result.chunks]
    )

    # 4. 存储 Chunks
    for i, (chunk, emb) in enumerate(zip(result.chunks, embeddings)):
        db.add(Chunk(
            document_id=doc.id,
            chunk_index=i,
            content=chunk.content,
            embedding=emb,
            metadata_=chunk.metadata,
            token_count=_estimate_tokens(chunk.content),
        ))

    await db.commit()
    return len(result.chunks)
```

### 2.2 re_embed_document

```python
async def re_embed_document(db: AsyncSession, doc_id: UUID) -> int:
    """重新生成文档所有 chunk 的 embedding（如模型更换）"""
    # 1. 获取所有 chunks
    # 2. 重新 embed
    # 3. 更新数据库
```

---

## 3. Token 估算

```python
def _estimate_tokens(text: str) -> int:
    """估算 token 数量"""
    ascii_chars = sum(1 for c in text if ord(c) < 128)
    cjk_chars = len(text) - ascii_chars
    # ASCII: ~4 chars/token, CJK: ~1.5 chars/token
    return int(ascii_chars / 4 + cjk_chars * 1.5)
```

---

## 4. 与 Task Manager 集成

```python
async def process_document(task_id: str, ...):
    """上传 API 调用的处理函数"""
    # 更新步骤: parsing
    await update_task(task_id, "parsing", "in_progress", 10)

    chunks_count = await ingest_document(...)

    # 更新步骤: embedding
    await update_task(task_id, "embedding", "done", 50)
```

---

*文档版本: v1.0*
