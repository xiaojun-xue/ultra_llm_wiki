# 模块设计 - MCP 服务 (MCP Server)

## 1. 模块概述

MCP Server 将 LLM Wiki 的能力以 Model Context Protocol 暴露给 Claude Code，使 AI 助手能直接查询知识库。

### 1.1 核心文件

```
mcp_server/
├── __init__.py
└── server.py    # FastMCP Server + 工具定义
```

### 1.2 架构

```
Claude Code
    │
    │ SSE (Server-Sent Events)
    ▼
Nginx /mcp/ ──▶ FastMCP Server (8001)
                      │
                      ├── @mcp.tool() 装饰的函数
                      │
                      └── 调用 core services
                              ├── embedding_service
                              ├── relation_discovery
                              └── PostgreSQL
```

---

## 2. MCP 工具清单

| 工具名 | 参数 | 说明 |
|--------|------|------|
| `search_wiki` | query, doc_type?, tags?, limit?, auth_token? | 语义搜索 |
| `get_document` | doc_id, auth_token? | 获取文档详情 |
| `get_related` | doc_id, relation_type?, auth_token? | 获取关联文档 |
| `list_documents` | doc_type?, tag?, limit?, auth_token? | 列出文档 |
| `get_code_context` | file_path, symbol?, auth_token? | 代码上下文 |

---

## 3. 工具实现

### 3.1 search_wiki

```python
@mcp.tool()
async def search_wiki(
    query: str,
    doc_type: str | None = None,
    tags: list[str] | None = None,
    limit: int = 5,
    auth_token: str | None = None,
) -> str:
    """搜索知识库"""
    # 1. 生成 embedding
    embedding = await embedding_service.embed_query(query)

    # 2. pgvector 检索
    sql = text("""
        SELECT c.document_id, c.content, d.title, d.doc_type,
               c.embedding <=> :embedding AS distance
        FROM chunks c JOIN documents d ON d.id = c.document_id
        WHERE 1=1 AND (:doc_type IS NULL OR d.doc_type = :doc_type)
        ORDER BY c.embedding <=> :embedding LIMIT :limit
    """)

    # 3. 格式化返回 Markdown
    output = []
    for row in rows:
        output.append(
            f"## [{i}] {row.title} ({row.doc_type})\n"
            f"Distance: {row.distance:.4f}\n\n"
            f"{row.content[:500]}\n"
        )
    return "\n---\n".join(output)
```

### 3.2 get_document

```python
@mcp.tool()
async def get_document(doc_id: str, auth_token: str | None = None) -> str:
    """获取文档完整内容"""
    doc = await db.get(Document, uuid.UUID(doc_id))
    return (
        f"# {doc.title}\n\n"
        f"**Type:** {doc.doc_type}\n"
        f"**Created:** {doc.created_at}\n\n"
        f"---\n\n"
        f"{doc.content or '(No content)'}"
    )
```

### 3.3 get_code_context

```python
@mcp.tool()
async def get_code_context(
    file_path: str,
    symbol: str | None = None,
    auth_token: str | None = None,
) -> str:
    """获取代码及其关联文档"""
    # 1. 查找源代码文档
    doc = await db.execute(
        select(Document).where(
            Document.doc_type == "source_code",
            Document.title.ilike(f"%{file_path}%")
        )
    )

    # 2. 获取关联文档
    relations = await get_relations(doc.id)

    # 3. 组装返回
    return f"# {doc.title}\n\n```\n{doc.content}\n```\n\n## Related\n{relations}"
```

---

## 4. 认证传递

```python
def _check_auth(request) -> tuple[str | None, str | None]:
    """从 SSE 请求中提取 JWT"""
    auth_header = getattr(request, "headers", {}).get("authorization", "")
    if not auth_header:
        return None, None

    payload = decode_token(auth_header.replace("Bearer ", ""))
    return payload.get("sub"), payload.get("role")
```

### 4.1 认证流程

```
Claude Code 连接 MCP 时:
1. Claude Code 发送 Authorization header
2. _check_auth() 提取并验证 JWT
3. 工具函数可使用 auth_token 参数
4. 工具内部可显示 "Authenticated as xxx"
```

---

## 5. 传输配置

```python
# Nginx 配置
location /mcp/ {
    proxy_pass http://backend:8001;
    proxy_buffering off;           # 禁用缓冲
    proxy_read_timeout 86400s;     # 长连接保活
    chunked_transfer_encoding off;  # SSE 需要
}
```

---

## 6. 返回格式

所有工具返回 **Markdown 格式文本**，便于 LLM 直接理解：

```markdown
## [1] SPI Driver (source_code)
ID: 550e8400-e29b-41d4-a716-446655440000
Distance: 0.1234

```c
void SPI_Init(void) {
    // SPI initialization code
}
```

---
## [2] SPI Protocol Document (document)
...
```

---

## 7. 扩展新工具

```python
@mcp.tool()
async def my_new_tool(
    param1: str,
    auth_token: str | None = None,
) -> str:
    """工具描述（会显示给 LLM）"""
    # 实现逻辑
    return "Markdown 格式的结果"
```

---

*文档版本: v1.0*
