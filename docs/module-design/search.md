# 模块设计 - 搜索模块 (Search)

## 1. 模块概述

搜索模块是 LLM Wiki 的核心，提供语义检索能力，让用户用自然语言找到相关文档。

### 1.1 核心职责

- 向量语义检索（Embedding similarity）
- 全文关键词检索（PostgreSQL FTS）
- 混合检索（RRF 融合）
- 结果过滤与排序

### 1.2 架构图

```
search 模块
├── api/search.py          # FastAPI 路由
├── core/embedding.py     # Embedding 服务
└── parsers/              # 搜索结果格式化

查询流程:
用户查询 → 生成 Embedding → 向量检索 + 全文检索 → RRF 融合 → 返回结果
```

---

## 2. 向量检索

### 2.1 Embedding 服务

```python
# core/embedding.py
class EmbeddingService:
    def __init__(self):
        self.model = settings.embedding_model  # "bge-m3"
        self.dimension = settings.embedding_dim  # 1024

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """批量生成文本的 embedding 向量"""
        # 调用 Ollama API
        response = await httpx.AsyncClient().post(
            f"{settings.ollama_base_url}/api/embed",
            json={"model": self.model, "input": texts}
        )
        return response.json()["embeddings"]

    async def embed_query(self, query: str) -> list[float]:
        """单条查询的 embedding"""
        embeddings = await self.embed([query])
        return embeddings[0]
```

### 2.2 向量检索 SQL

```sql
SELECT c.document_id, c.content, c.metadata,
       d.title, d.doc_type,
       c.embedding <=> :query_embedding AS distance
FROM chunks c
JOIN documents d ON d.id = c.document_id
WHERE 1=1
  AND (:doc_type IS NULL OR d.doc_type = :doc_type)
ORDER BY c.embedding <=> :query_embedding
LIMIT :limit;
```

`<=>` 是 `vector_cosine_ops` 操作符，计算余弦距离（越小越相似）。

---

## 3. 全文检索

### 3.1 PostgreSQL FTS 配置

```sql
-- 启用 pg_jieba 中文分词 (可选)
CREATE EXTENSION IF NOT EXISTS pg_jieba;

-- 在 documents 表添加全文检索列
ALTER TABLE documents ADD COLUMN fts_vector tsvector
  GENERATED ALWAYS AS (
    to_tsvector('jieba', coalesce(title, '') || ' ' || coalesce(content, ''))
  ) STORED;

-- 创建索引
CREATE INDEX ix_documents_fts ON documents USING GIN(fts_vector);
```

### 3.2 全文检索 SQL

```sql
SELECT d.id, d.title, d.doc_type,
       ts_rank(d.fts_vector, plainto_tsquery('jieba', :query)) AS rank
FROM documents d
WHERE d.fts_vector @@ plainto_tsquery('jieba', :query)
ORDER BY rank DESC
LIMIT :limit;
```

---

## 4. 混合检索 (RRF)

### 4.1 RRF 算法

Reciprocal Rank Fusion (RRF) 是一种融合多路检索结果的算法：

```python
from collections import defaultdict

def rrf_fusion(results_list: list[list[dict]], k: int = 60) -> list[dict]:
    """
    融合多路检索结果

    Args:
        results_list: [[doc1, doc2, ...], [doc_a, doc_b, ...]]
                      每路检索的结果列表（已按相关性排序）
        k: 惩罚因子，默认 60

    Returns:
        融合后的结果列表（按综合得分排序）
    """
    scores = defaultdict(float)

    for results in results_list:
        for rank, item in enumerate(results, 1):
            doc_id = item['document_id']
            # RRF 公式: 1/(k + rank)
            scores[doc_id] += 1 / (k + rank)

    # 按得分降序排序
    sorted_docs = sorted(scores.items(), key=lambda x: -x[1])

    # 返回完整的文档信息
    return [get_doc_by_id(doc_id) for doc_id, _ in sorted_docs]
```

### 4.2 搜索流程

```python
async def hybrid_search(
    query: str,
    doc_type: str | None = None,
    limit: int = 10,
) -> list[SearchResult]:
    # 1. 生成 query embedding
    query_embedding = await embedding_service.embed_query(query)

    # 2. 向量检索
    vector_results = await vector_search(
        query_embedding,
        doc_type=doc_type,
        limit=limit * 2,  # 多取一些留给她融合
    )

    # 3. 全文检索
    fts_results = await fts_search(
        query,
        doc_type=doc_type,
        limit=limit * 2,
    )

    # 4. RRF 融合
    fused = rrf_fusion([vector_results, fts_results], k=60)

    return fused[:limit]
```

---

## 5. API 接口

### 5.1 搜索接口

```
POST /api/search/
Content-Type: application/json

{
    "query": "SPI 驱动如何配置",
    "doc_type": "source_code",   // 可选
    "tags": ["spi"],             // 可选
    "limit": 10                  // 默认 10
}
```

### 5.2 响应格式

```json
{
    "results": [
        {
            "document_id": "550e8400-...",
            "title": "spi_driver.c",
            "doc_type": "source_code",
            "chunk_content": "void SPI_Init(void) { ... }",
            "score": 0.85,
            "metadata": {"language": "c", "function": "SPI_Init"}
        }
    ],
    "total": 100,
    "query": "SPI 驱动如何配置"
}
```

---

## 6. 过滤与排序

### 6.1 支持的过滤条件

| 字段 | 类型 | 说明 |
|------|------|------|
| doc_type | string | source_code / document / schematic |
| tags | list[str] | 必须包含所有指定标签 |
| created_after | datetime | 创建时间之后 |
| created_before | datetime | 创建时间之前 |

### 6.2 排序选项

| 字段 | 说明 |
|------|------|
| relevance (默认) | RRF 融合得分 |
| created_at | 创建时间 |
| updated_at | 更新时间 |

---

## 7. 性能优化

### 7.1 向量索引

```sql
-- IVFFlat 索引（适合新增较少场景）
CREATE INDEX ix_chunks_embedding ON chunks
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- HNSW 索引（适合需要快速召回的场景）
CREATE INDEX ix_chunks_embedding_hnsw ON chunks
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
```

### 7.2 缓存

```python
# 热点 query 的 embedding 结果缓存到 Redis
async def embed_query_cached(query: str) -> list[float]:
    cache_key = f"embed:{hashlib.md5(query.encode()).hexdigest()}"

    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)

    embedding = await embed_query(query)
    await redis.setex(cache_key, 3600, json.dumps(embedding))  # 1小时 TTL
    return embedding
```

---

## 8. 扩展点

### 8.1 添加新的检索模型

```python
class EmbeddingService:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        if settings.embedding_model.startswith("bge"):
            return await self._embed_bge(texts)
        elif settings.embedding_model.startswith("openai"):
            return await self._embed_openai(texts)
        else:
            raise ValueError(f"Unknown embedding model: {settings.model}")
```

### 8.2 自定义 RRF 权重

```python
def rrf_fusion_weighted(
    results_list: list[list[dict]],
    weights: list[float],
    k: int = 60,
) -> list[dict]:
    """带权重的 RRF 融合"""
    scores = defaultdict(float)
    for results, weight in zip(results_list, weights):
        for rank, item in enumerate(results, 1):
            doc_id = item['document_id']
            scores[doc_id] += weight * (1 / (k + rank))
    ...
```

---

*文档版本: v1.0*
*最后更新: 2026-05-02*
