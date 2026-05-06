# LLM Wiki 方案设计文档

## 1. 技术方案总览

### 1.1 核心技术选型

| 层级 | 技术 | 版本要求 | 说明 |
|------|------|---------|------|
| Web 框架 | FastAPI | ≥ 0.115 | 异步优先、自动 OpenAPI |
| ORM | SQLAlchemy | ≥ 2.0.30 | 类型提示、async 支持 |
| DB 驱动 | asyncpg | ≥ 0.29 | PostgreSQL 异步 |
| 向量引擎 | pgvector | ≥ 0.3 | PostgreSQL 内置 |
| 文件存储 | MinIO | latest | S3 协议兼容 |
| 前端框架 | Next.js | 14+ | App Router |
| Embedding | BGE-M3 | latest | Ollama 本地运行 |
| MCP | FastMCP | ≥ 1.20 | Claude Code 集成 |
| 缓存/队列 | Redis | 7+ | 任务状态 |

### 1.2 部署方案

```
开发环境: docker compose up
生产环境: K8s / Docker Swarm + NFS/云存储
```

---

## 2. 文档解析方案

### 2.1 解析器架构

```python
class BaseParser(ABC):
    @abstractmethod
    def supported_extensions(self) -> set[str]: ...

    @abstractmethod
    async def parse(self, data: bytes, filename: str) -> ParseResult: ...
```

每种文件类型实现自己的 Parser，统一返回 `ParseResult`。

### 2.2 切片策略

| 文件类型 | 切片方式 | 切片大小 |
|---------|---------|---------|
| Markdown | 按标题层级 | ~500 字/片 |
| 源代码 | 按函数/类 | ~200 行/片 |
| PDF | 按页/段落 | ~1000 字/片 |
| Word | 按段落 | ~1000 字/片 |
| 原理图 | 按元件/信号 | 整个文件 |

### 2.3 元数据提取

| 文件类型 | 提取的元数据 |
|---------|-------------|
| Markdown | heading_chain, references, links |
| 源代码 | language, function, calls, includes |
| PDF | pages, author, title |
| 原理图 | components, signals, netlist |

---

## 3. Embedding 方案

### 3.1 模型选择

| 模型 | 维度 | 语言支持 | 供应商 |
|------|------|---------|--------|
| BGE-M3 | 1024 | 中英为主 | Ollama (本地) |
| text-embedding-3-small | 1536 | 多语言 | OpenAI (可选) |

### 3.2 向量存储

```sql
-- PostgreSQL 内置 pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- chunks 表的向量列
embedding vector(1024);

-- IVFFlat 索引 (IVFFlat 比 HNSW 适合新增少的场景)
CREATE INDEX ix_chunks_embedding ON chunks
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
```

### 3.3 向量检索 SQL

```sql
SELECT c.document_id, c.content, d.title,
       c.embedding <=> :query_embedding AS distance
FROM chunks c
JOIN documents d ON d.id = c.document_id
WHERE d.doc_type = :doc_type
ORDER BY c.embedding <=> :query_embedding
LIMIT :limit;
```

`<=>` 是 cosine distance 操作符，距离越小相似度越高。

---

## 4. 搜索方案

### 4.1 混合检索架构

```
用户查询
    │
    ├──▶ 向量检索 (pgvector)
    │         cosine distance top-k
    │
    ├──▶ 全文检索 (PostgreSQL FTS)
    │         ts_rank top-k
    │
    ▼
RRF 融合
(score = Σ 1/(k+rank), k=60)
    │
    ▼
去重 + 排序
    │
    ▼
返回结果
```

### 4.2 RRF 算法

```python
def rrf_fusion(results_list: list[list[dict]], k: int = 60) -> list[dict]:
    """Reciprocal Rank Fusion"""
    scores = defaultdict(float)
    for results in results_list:
        for rank, item in enumerate(results, 1):
            doc_id = item['id']
            scores[doc_id] += 1 / (k + rank)

    return sorted(scores.items(), key=lambda x: -x[1])
```

### 4.3 中文分词

```sql
-- 启用中文分词 (pg_jieba 或 zhparser)
CREATE EXTENSION IF NOT EXISTS pg_jieba;

-- 全文检索配置
ALTER TABLE documents ADD COLUMN fts_vector tsvector
  GENERATED ALWAYS AS (to_tsvector('jieba', coalesce(title, '') || ' ' || coalesce(content, ''))) STORED;

-- 检索
SELECT * FROM documents
WHERE fts_vector @@ plainto_tsquery('jieba', :query)
ORDER BY ts_rank(fts_vector, plainto_tsquery('jieba', :query))
LIMIT 10;
```

---

## 5. 关系发现方案

### 5.1 关系类型

| 关系类型 | 发现策略 | 置信度 |
|---------|---------|--------|
| `references` | 文档 A 链接/引用 B | 0.9 |
| `depends_on` | 代码 A #include/import B | 0.9 |
| `implements` | 原理图信号 ↔ 代码变量名匹配 | 0.5-0.95 |
| `related_to` | 语义 embedding 相似度 < 0.3 | 0.7-1.0 |

### 5.2 引用分析

```python
# Markdown 中的引用
[link](file.md)
`code_filename.c`

# 代码中的引用
#include "header.h"
import module
```

### 5.3 名称匹配

```python
# 原理图信号: SPI1_MOSI
# 代码中匹配: spi, mosi, spi1

keywords = set()
for sig in signals:
    parts = re.split(r'[_\d]+', sig)
    keywords.update(p for p in parts if len(p) >= 3)

# 代码/文档中匹配关键词
matched = [kw for kw in keywords if kw in content.lower()]
if len(matched) >= 2:
    create_relation("implements", confidence=min(0.5 + 0.1*len(matched), 0.95))
```

### 5.4 语义相似度

```sql
-- 计算文档平均 embedding
SELECT AVG(embedding) as avg_emb
FROM chunks WHERE document_id = :doc_id;

-- 找相似文档 (cosine distance < 0.3)
SELECT c.document_id, d.title,
       AVG(c.embedding <=> :avg_embedding) as avg_distance
FROM chunks c
JOIN documents d ON d.id = c.document_id
WHERE c.document_id != :doc_id
GROUP BY c.document_id, d.title
HAVING AVG(c.embedding <=> :avg_embedding) < 0.3
ORDER BY avg_distance;
```

---

## 6. 认证授权方案

### 6.1 JWT 流程

```
登录 POST /api/auth/login
    │
    ▼
验证密码 → 查 User 表
    │
    ▼
生成 JWT: payload = {sub: user_id, role, email, exp, iat}
    │
    ▼
返回 {access_token, user: {...}}

后续请求:
Authorization: Bearer <token>
    │
    ▼
decode_token() → 验证签名/过期
    │
    ▼
get_current_user() → 查 User 表
    │
    ▼
返回 User 对象给 endpoint
```

### 6.2 权限控制

```python
def require_role(allowed_roles: list[str]):
    async def checker(user: User = Depends(get_current_user)):
        if user.role not in allowed_roles:
            raise HTTPException(403, "Insufficient permissions")
        return user
    return checker

# 使用
@router.delete("/{doc_id}")
async def delete_doc(
    doc_id: str,
    user: User = Depends(require_role(["admin", "internal"]))
):
    ...
```

### 6.3 角色权限矩阵

| 操作 | Admin | Internal | External |
|------|-------|----------|----------|
| 读所有文档 | ✅ | ✅ | ❌ |
| 读授权文档 | ✅ | ✅ | ✅ |
| 上传 | ✅ | ✅ | ❌ |
| 删除自己文档 | ✅ | ✅ | ❌ |
| 删除任意文档 | ✅ | ❌ | ❌ |
| 管理用户 | ✅ | ❌ | ❌ |

---

## 7. 任务队列方案

### 7.1 Redis 数据结构

```
Key: task:{task_id}
Type: Hash
Fields:
  - status: "pending" | "parsing" | "embedding" | "discovering" | "done" | "failed"
  - progress: 0-100
  - steps: JSON数组
  - created_at: ISO时间
  - updated_at: ISO时间
  - error: 错误信息
  - result: JSON结果对象

TTL: 24小时
```

### 7.2 任务步骤定义

```python
DEFAULT_STEPS = [
    {"name": "saving", "status": "pending", "progress": 0},    # 保存到 MinIO
    {"name": "parsing", "status": "pending", "progress": 0},    # 解析文件
    {"name": "embedding", "status": "pending", "progress": 0}, # 生成向量
    {"name": "discovering", "status": "pending", "progress": 0}, # 发现关系
]
```

### 7.3 进度更新

```python
async def update_task(task_id: str, step: str, status: str, progress: int):
    await redis.hset(f"task:{task_id}", mapping={
        "steps": json.dumps(update_steps(steps, step, status, progress)),
        "updated_at": datetime.utcnow().isoformat(),
    })
```

---

## 8. MCP 集成方案

### 8.1 认证传递

```
Claude Code
    │
    ├── MCP 启动时携带 Authorization header
    │
    ▼
FastMCP server.py
    │
    ├── _check_auth(request) 提取 header
    │
    ▼
decode_token() 验证 JWT
    │
    ▼
工具函数接收 auth_token 参数
```

### 8.2 MCP 传输

```python
# SSE (Server-Sent Events) 传输
mcp.run(transport="sse")

# Nginx 配置
location /mcp/ {
    proxy_pass http://backend:8001;
    proxy_buffering off;
    proxy_read_timeout 86400s;  # 长连接保活
    proxy_http_version 1.1;
    chunked_transfer_encoding off;
}
```

---

## 9. 前端架构方案

### 9.1 Next.js App Router

```
app/
├── layout.tsx          # Root layout + Providers
├── page.tsx           # 首页
├── login/page.tsx     # 登录
├── register/page.tsx  # 注册
├── upload/page.tsx   # 上传
├── search/page.tsx   # 搜索
├── docs/[id]/page.tsx # 文档详情
└── graph/page.tsx    # 知识图谱
```

### 9.2 Auth Context

```typescript
// 全局认证状态
interface AuthContext {
  user: User | null;
  token: string | null;
  login: (email, password) => Promise<void>;
  register: (email, password, name) => Promise<void>;
  logout: () => void;
}

// Token 同步到 Cookie (供 middleware 读取)
setTokenCookie(token);
removeTokenCookie();
```

### 9.3 API Client

```typescript
// 所有请求自动附加 Authorization
async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const token = getToken();
  const headers = {
    "Content-Type": "application/json",
    ...(token ? { "Authorization": `Bearer ${token}` } : {}),
  };

  const res = await fetch(`${API_BASE}${path}`, { headers, ...options });

  if (res.status === 401) {
    // 清除本地状态 + 跳转登录
    localStorage.removeItem("llm_wiki_token");
    window.location.href = "/login";
  }

  return res.json();
}
```

### 9.4 Route Protection

```typescript
// middleware.ts
export function middleware(request: NextRequest) {
  const token = request.cookies.get("llm_wiki_token");

  if (PROTECTED_PREFIXES.some(p => pathname.startsWith(p)) && !token) {
    return NextResponse.redirect(new URL("/login", request.url));
  }
}
```

---

## 10. 存储方案

### 10.1 MinIO 对象键设计

```
wiki-files/
├── {year}/{month}/{day}/
│   └── {uuid}_{original_filename}
│
例: wiki-files/2026/05/02/550e8400-e29b_SPI_driver.c
```

### 10.2 目录自动创建

```python
async def ensure_bucket(self):
    if not await self.bucket_exists():
        await self.create_bucket()
        # 设置生命周期规则 (可选)
```

---

## 11. Call Graph 方案

### 11.1 Python AST

```python
import ast

class FunctionAnalyzer(ast.NodeVisitor):
    def visit_FunctionDef(self, node):
        # 提取函数调用
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                calls.add(child.func.id)
        self.generic_visit(node)
```

### 11.2 C/C++ Clang AST

```python
import clang.cindex

idx = clang.cindex.Index.create()
tu = idx.parse(source_file)
# 遍历 AST 提取函数调用
```

### 11.3 Regex Fallback

```python
# 始终可用的正则匹配
FUNCTION_PATTERN = {
    "c": r"^(?:\w[\w\s\*]+)\s+(\w+)\s*\([^)]*\)\s*\{",
    "python": r"^(?:async\s+)?def\s+(\w+)\s*\(",
}
```

---

*文档版本: v1.0*
*最后更新: 2026-05-02*
