# 模块设计 - 数据库 (Database)

## 1. 数据库选型

### 1.1 为什么选择 PostgreSQL + pgvector

| 考量因素 | 方案 | 决策 |
|---------|------|------|
| 关系数据存储 | MySQL / PostgreSQL | **PostgreSQL** — JSONB 原生支持、丰富的索引类型 |
| 向量检索 | Pinecone / Milvus / pgvector | **pgvector** — 同库事务、运维简单 |
| 全文检索 | Elasticsearch / PostgreSQL FTS | **PostgreSQL FTS** — 不增加服务依赖 |
| 元数据存储 | MongoDB / PostgreSQL JSONB | **PostgreSQL JSONB** — 与主数据同库 |

**pgvector 优势**:
- 与 PostgreSQL 共用 ACID 事务，文档和向量操作原子性
- IVFFlat/HNSW 索引支持
- 备份和恢复与主库一致
- 不需要额外部署服务

### 1.2 备选方案对比

| 方案 | 优点 | 缺点 |
|------|------|------|
| PostgreSQL + pgvector | 运维简单、事务一致 | 向量规模受限（百万级） |
| Milvus + PostgreSQL | 向量性能强 | 双服务、运维复杂 |
| Pinecone (云) | 完全托管 | 数据出境、成本不确定 |
| Qdrant | 向量性能强 | 增加服务依赖 |

---

## 2. 数据实体

### 2.1 实体清单

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│    users    │     │ documents   │     │   chunks    │
├─────────────┤     ├─────────────┤     ├─────────────┤
│ id          │     │ id          │◀────│ document_id │
│ email       │     │ title       │     │ id          │
│ password_hash│     │ doc_type    │     │ chunk_index │
│ name        │     │ content     │     │ content     │
│ role        │     │ content_html │     │ embedding   │
│ is_active   │     │ metadata    │     │ metadata    │
│ created_at  │     │ file_path   │     │ token_count │
└─────────────┘     │ created_by   │     └─────────────┘
                    │ created_at   │
                    │ updated_at   │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────────┐
        │  tags    │ │doc_tags  │ │relations     │
        ├──────────┤ └──────────┘ ├──────────────┤
        │ id       │              │ source_id    │
        │ name     │              │ target_id    │
        │ category │              │ relation_type│
        └──────────┘              │ description  │
                                   │ confidence   │
                                   └──────────────┘
```

---

## 3. 表结构详解

### 3.1 users 用户表

```sql
CREATE TABLE users (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email       VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    name        VARCHAR(100) NOT NULL,
    role        VARCHAR(20) NOT NULL DEFAULT 'external',
                -- admin / internal / external
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    last_login_at TIMESTAMPTZ
);
```

**数据示例**:

| id | email | name | role | is_active |
|----|-------|------|------|-----------|
| b097ddde-... | admin@wiki.com | 管理员 | admin | true |
| a1234567-... | dev@team.com | 开发者 | internal | true |
| b789abcd-... | client@firm.com | 客户 | external | true |

**索引**:
```sql
CREATE UNIQUE INDEX ix_users_email ON users(email);
```

---

### 3.2 documents 文档表

```sql
CREATE TABLE documents (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title       VARCHAR NOT NULL,
    doc_type    VARCHAR NOT NULL,
                -- source_code / document / schematic / note
    content     TEXT,
    content_html TEXT,
    metadata    JSONB DEFAULT '{}',
                -- 解析器提取的元数据
                -- 代码: {language, lines, call_graph}
                -- 文档: {format, heading_chain}
                -- 原理图: {components, signals}
    file_path   VARCHAR,     -- MinIO 对象路径
    mime_type   VARCHAR,     -- 文件 MIME 类型
    created_by  VARCHAR,     -- 创建者邮箱 (User.email)
    owner_id    UUID REFERENCES users(id),
                -- 文档所有者 (可空，支持匿名上传)
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);
```

**元数据 JSONB 结构示例**:

```json
// 源代码
{
  "language": "c",
  "lines": 245,
  "call_graph": {
    "SPI_Init": ["GPIO_Init", "RCC_ClockCmd"],
    "SPI_Transfer": ["SPI_Init"]
  }
}

// Markdown 文档
{
  "format": "markdown",
  "references": ["uart.c", "gpio.h"]
}

// 原理图
{
  "components": ["U1:STM32F407", "R1:10K", "C1:100nF"],
  "signals": ["SPI1_MOSI", "SPI1_MISO", "SPI1_SCK"],
  "nets": [["U1.5", "R1.1"], ["U1.6", "C1.1"]]
}
```

**索引**:
```sql
CREATE INDEX ix_documents_doc_type ON documents(doc_type);
CREATE INDEX ix_documents_created_by ON documents(created_by);
CREATE INDEX ix_documents_updated_at ON documents(updated_at DESC);
CREATE INDEX ix_documents_metadata ON documents USING GIN(metadata);
```

---

### 3.3 chunks 切片表

```sql
CREATE TABLE chunks (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INT NOT NULL,
    content     TEXT NOT NULL,
    embedding   VECTOR(1024),
                -- BGE-M3 向量，1024 维
                -- 可为 NULL（Embedding 失败时）
    metadata    JSONB DEFAULT '{}',
                -- {type, language, function, start_line, end_line}
                -- 或 {section, heading_chain}
    token_count INT,

    CONSTRAINT fk_document FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);
```

**数据示例**:

| id | document_id | chunk_index | content | embedding | metadata |
|----|-------------|-------------|---------|-----------|----------|
| c001... | 550e... | 0 | `#include...` | [0.123,...] | {language: "c", function: "main"} |
| c002... | 550e... | 1 | `void SPI_Init...` | [0.456,...] | {language: "c", function: "SPI_Init"} |

**向量索引**:
```sql
-- IVFFlat 索引（适合新增少、查询多的场景）
CREATE INDEX ix_chunks_embedding ON chunks
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- 或 HNSW 索引（更快召回，但占用更多空间）
CREATE INDEX ix_chunks_embedding_hnsw ON chunks
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
```

---

### 3.4 tags 标签表

```sql
CREATE TABLE tags (
    id       SERIAL PRIMARY KEY,
    name     VARCHAR(100) UNIQUE NOT NULL,
    category VARCHAR(50)
             -- module / topic / version / status
);
```

**数据示例**:

| id | name | category |
|----|------|----------|
| 1 | spi | module |
| 2 | driver | topic |
| 3 | v2.0 | version |

---

### 3.5 document_tags 文档标签关联表 (M2M)

```sql
CREATE TABLE document_tags (
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    tag_id      INT REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (document_id, tag_id)
);
```

**数据示例**:

| document_id | tag_id |
|-------------|--------|
| 550e8400-... | 1 (spi) |
| 550e8400-... | 2 (driver) |
| 7de0784a-... | 1 (spi) |

---

### 3.6 document_relations 文档关系表

```sql
CREATE TABLE document_relations (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id      UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    target_id      UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    relation_type  VARCHAR(50) NOT NULL,
                  -- references / depends_on / implements / related_to
    description    TEXT,
    confidence     FLOAT DEFAULT 1.0,
                  -- 0.0 - 1.0，发现算法的置信度
    created_at     TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT uq_relation UNIQUE (source_id, target_id, relation_type)
);
```

**关系类型说明**:

| 关系类型 | 发现策略 | 置信度示例 |
|---------|---------|-----------|
| `references` | Markdown 链接/文件名引用 | 0.9 |
| `depends_on` | 代码 #include / import | 0.9 |
| `implements` | 原理图信号 ↔ 代码变量名 | 0.5-0.95 |
| `related_to` | 语义相似度 (cosine dist < 0.3) | 0.7-1.0 |

**数据示例**:

| source_id | target_id | relation_type | confidence |
|-----------|-----------|--------------|-------------|
| doc_a (spi_driver.c) | doc_b (spi.h) | depends_on | 0.9 |
| doc_c (原理图) | doc_a (spi_driver.c) | implements | 0.75 |
| doc_a (spi_driver.c) | doc_d (uart.c) | related_to | 0.65 |

**索引**:
```sql
CREATE INDEX ix_relations_source ON document_relations(source_id);
CREATE INDEX ix_relations_target ON document_relations(target_id);
CREATE INDEX ix_relations_type ON document_relations(relation_type);
```

---

## 4. 数据关系详解

### 4.1 用户-文档关系

```
users 1 ──── N documents
  │            │
  │            ├── owner_id (所有者，可选)
  │            │
  │            └── created_by (创建者邮箱，冗余字段)
```

- `owner_id`: 指向 users 表的外键，表示文档所有者
- `created_by`: 冗余存储创建者邮箱，便于快速查询
- External 用户只能访问 `document_access` 表中有权限的文档

### 4.2 文档-切片关系

```
documents 1 ──── N chunks
  │
  └── 每个 chunk 属于一个 document
  └── 删除文档时，CASCADE 删除所有 chunks
  └── chunk_index 标识切片顺序
```

- 文档是切片的容器
- 向量存储在 chunk 级别，检索返回的是 chunk
- 通过 `document_id` 关联回文档

### 4.3 文档-标签关系 (M2M)

```
documents N ──── M tags
         │
         └── document_tags (中间表)
```

- 一个文档可以有多个标签
- 一个标签可以关联多个文档
- 中间表实现多对多关系

### 4.4 文档-文档关系 (自关联)

```
document_relations
  │
  ├── source_id ──── documents (source)
  │
  └── target_id ──── documents (target)
```

- 同一张表存储有向关系
- `source_id → target_id` 表示关系方向
- 同一对文档可能有多种关系类型

---

## 5. 数据流转

### 5.1 上传时数据写入顺序

```
1. documents (新建记录，状态 pending)
       │
       ▼
2. MinIO (原始文件)
       │
       ▼
3. chunks (切片 + embedding)
       │
       ▼
4. document_relations (关系发现)
       │
       ▼
5. 更新 documents (状态 done)
```

### 5.2 搜索时数据读取

```
1. 用户查询
       │
       ▼
2. 生成 embedding (Ollama)
       │
       ▼
3. 向量检索 chunks 表
       │ JOIN documents 获取标题/类型
       │
       ▼
4. 返回相关 chunk 列表
       │ 携带 document_id / content / metadata
```

---

## 6. 完整 ER 图

```
┌──────────────────────────────────────────────────────────────────┐
│                           users                                   │
│  ┌────────┐  ┌─────────┐  ┌──────┐  ┌─────────┐  ┌──────────┐  │
│  │   id   │──│  email  │  │ name │  │   role  │  │ is_active│  │
│  └────────┘  └─────────┘  └──────┘  └─────────┘  └──────────┘  │
└──────────────────────────────────────────────────────────────────┘
                              │
                              │ 1:N (owner_id)
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                         documents                                 │
│  ┌────────┐  ┌───────┐  ┌──────────┐  ┌───────────┐  ┌──────┐ │
│  │   id   │  │ title │  │ doc_type │  │ metadata  │  │content│ │
│  └────────┘  └───────┘  └──────────┘  └───────────┘  └──────┘ │
│  ┌──────────┐  ┌───────────┐  ┌────────────┐  ┌─────────────┐ │
│  │file_path │  │ created_by│  │ created_at │  │ updated_at  │ │
│  └──────────┘  └───────────┘  └────────────┘  └─────────────┘ │
└──────────────────────────┬───────────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
          ▼                ▼                ▼
   ┌────────────┐    ┌────────────┐    ┌──────────────┐
   │   chunks   │    │ doc_tags  │    │ relations    │
   ├────────────┤    ├───────────┤    ├──────────────┤
   │ document_id│◀───│document_id│    │ source_id   │◀┐
   │ chunk_index│    └───────────┘    │ target_id   │  │
   │ content    │           │         │ relation_type│  │
   │ embedding  │           │         │ confidence  │  │
   │ metadata   │           │         └──────────────┘  │
   └────────────┘           │                ▲          │
                           ▼                │          │
                    ┌────────────┐         │          │
                    │    tags    │─────────┘          │
                    ├────────────┤                    │
                    │     id     │────────────────────┘
                    │    name    │
                    └────────────┘
```

---

## 7. 向量设计

### 7.1 Embedding 模型

| 模型 | 维度 | 说明 |
|------|------|------|
| BGE-M3 | 1024 | Ollama 本地运行，支持中英 |

### 7.2 向量存储策略

```sql
-- chunks.embedding 列
embedding VECTOR(1024)

-- 典型 embedding 值
[0.0123, -0.0456, 0.0789, ...]  -- 1024 维浮点数数组
```

### 7.3 向量检索

```sql
-- 找最相似的 5 个 chunk
SELECT c.*, d.title,
       c.embedding <=> :query_embedding AS distance
FROM chunks c
JOIN documents d ON d.id = c.document_id
WHERE c.embedding IS NOT NULL
ORDER BY c.embedding <=> :query_embedding
LIMIT 5;

-- <=> 是 cosine distance，距离越小越相似
```

---

## 8. 索引汇总

| 表 | 索引 | 类型 | 用途 |
|----|------|------|------|
| users | ix_users_email | B-tree | 登录查询 |
| documents | ix_documents_doc_type | B-tree | 类型过滤 |
| documents | ix_documents_updated_at | B-tree | 列表排序 |
| documents | ix_documents_metadata | GIN | JSONB 查询 |
| chunks | ix_chunks_embedding | IVFFlat/HNSW | 向量检索 |
| document_relations | ix_relations_source | B-tree | 关系查询 |
| document_relations | ix_relations_target | B-tree | 关系查询 |
| document_relations | ix_relations_type | B-tree | 关系类型过滤 |

---

## 9. 性能考量

### 9.1 向量规模

pgvector 适合 **百万级向量**以内：

| 向量数量 | 索引类型 | 内存占用 | 检索延迟 |
|---------|---------|---------|---------|
| 10K | IVFFlat | ~50MB | ~5ms |
| 100K | IVFFlat | ~500MB | ~20ms |
| 1M | HNSW | ~5GB | ~30ms |

当前系统单文档平均 20 chunks，1000 文档约 20K 向量，完全在 pgvector 舒适区。

### 9.2 JSONB 使用建议

- `metadata` 字段用于存储灵活元数据
- GIN 索引支持 `@>`、`?` 等 JSONB 操作符
- 避免在 JSONB 列上做大事务

### 9.3 分片策略 (未来)

如需扩展到千万级向量：

```sql
-- 按时间分片
CREATE TABLE chunks_2026 (
    CHECK (created_at >= '2026-01-01' AND created_at < '2027-01-01')
) INHERITS (chunks_base);
```

---

## 10. 迁移脚本

```sql
-- 初始化数据库
-- 见 scripts/init_db.sql

-- 主要步骤:
-- 1. CREATE EXTENSION vector;          -- 启用 pgvector
-- 2. CREATE TABLE users (...);          -- 用户表
-- 3. CREATE TABLE documents (...);     -- 文档表
-- 4. CREATE TABLE chunks (...);         -- 切片表
-- 5. CREATE TABLE tags (...);           -- 标签表
-- 6. CREATE TABLE document_tags (...);  -- 关联表
-- 7. CREATE TABLE document_relations;   -- 关系表
-- 8. CREATE INDEX ... ON chunks ...;    -- 向量索引
```

---

*文档版本: v1.0*
*最后更新: 2026-05-03*
