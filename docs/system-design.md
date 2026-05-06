# LLM Wiki 系统设计文档

## 1. 系统概述

LLM Wiki 是一个基于知识图谱的语义检索系统，支持源代码、文档、原理图等多种格式的统一管理和智能搜索。

### 1.1 系统边界

```
输入:
├── 用户上传文件 (PDF/Word/Markdown/源代码/原理图)
├── Claude Code 查询请求
└── 其他 HTTP API 调用

输出:
├── Web UI (搜索结果/文档浏览/知识图谱)
├── MCP 工具响应 (Claude Code 可用)
└── REST API 响应 (JSON)
```

### 1.2 非功能性需求

| 指标 | 目标值 | 说明 |
|------|--------|------|
| API 响应时间 | < 500ms | 不含文件下载 |
| 向量检索延迟 | < 200ms | pgvector 查询 |
| 文件上传大小 | ≤ 100MB | Nginx 配置 |
| 支持并发用户 | 100+ | 水平扩展可支持更多 |
| 系统可用性 | 99% | 单节点部署 |
| 数据持久化 | 100% | PostgreSQL + MinIO |

---

## 2. 功能模块划分

| 模块 | 职责 | 核心文件 |
|------|------|---------|
| Auth | 用户认证/JWT/权限 | `api/auth.py`, `core/auth.py`, `middleware/auth.py` |
| Documents | 文档 CRUD | `api/documents.py` |
| Upload | 文件上传/异步处理 | `api/upload.py`, `core/ingest.py` |
| Parsers | 多格式解析 | `parsers/*.py` |
| Search | 混合检索 | `api/search.py`, `core/embedding.py` |
| Relations | 关系发现 | `core/relation_discovery.py` |
| MCP Server | Claude Code 工具 | `mcp_server/server.py` |
| Task Manager | 任务状态追踪 | `core/task_manager.py` |

---

## 3. 核心数据流

### 3.1 文档上传处理流水线

```
用户上传文件
      │
      ▼
┌─────────────┐
│ 文件验证    │ ← 大小/类型检查
└──────┬──────┘
       │ 合法
       ▼
┌─────────────┐
│ 存 MinIO   │ ← 生成唯一对象键
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 创建 Document │ ← 状态: pending
│ + Task 记录  │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 解析文件    │ ← Parser 选择 → 文本提取 + 切片
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 生成 Embedding│ ← Ollama BGE-M3
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 存储 Chunks │ ← PostgreSQL
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 关系发现    │ ← 引用/名称/语义
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 更新状态    │ ← Document: done
└─────────────┘
```

### 3.2 语义搜索流程

```
用户查询
   │
   ▼
┌─────────────┐
│ Query 解析  │ ← 提取关键词/意图
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 生成 Embedding│ ← Ollama embed_query()
└──────┬──────┘
       │
       ▼
┌─────────────┐     ┌─────────────┐
│ 向量检索    │────▶│ 全文检索    │  (并行)
│ pgvector    │     │ PostgreSQL  │
└──────┬──────┘     └──────┬──────┘
       │                   │
       ▼                   ▼
┌─────────────────────────────────────┐
│         RRF 融合 (Reciprocal Rank)  │
│    score = Σ 1/(k+rank_i)           │
└──────────────────┬──────────────────┘
                   │
                   ▼
            ┌─────────────┐
            │ 返回 Top-K  │
            └─────────────┘
```

---

## 4. 数据库设计

### 4.1 ER 关系

```
users ──────────────────────── documents ─────────────────────── chunks
(id,email,role)               (id,title,doc_type)              (id,doc_id,content,embedding)
                               │
                               ├─── document_tags ──── tags
                               │
                               └─── document_relations
                                     (source_id,target_id,relation_type)
```

### 4.2 核心表结构

#### documents

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| title | VARCHAR | 文档标题 |
| doc_type | VARCHAR | source_code/document/schematic |
| content | TEXT | 解析后文本 |
| content_html | TEXT | Markdown HTML |
| metadata | JSONB | 解析器元数据 |
| file_path | VARCHAR | MinIO 路径 |
| created_by | VARCHAR | 创建者邮箱 |

#### chunks

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| document_id | UUID | 外键 |
| chunk_index | INT | 切片序号 |
| content | TEXT | 切片内容 |
| embedding | VECTOR(1024) | BGE-M3 向量 |
| metadata | JSONB | 语言/函数/行号 |

**索引**：`ix_chunks_embedding` — IVFFlat + cosine_ops

---

## 5. API 设计

### 5.1 API 路由总览

| 前缀 | 模块 | 文件 |
|------|------|------|
| `/api/auth` | 认证 | `api/auth.py` |
| `/api/documents` | 文档 | `api/documents.py` |
| `/api/search` | 搜索 | `api/search.py` |
| `/api/upload` | 上传 | `api/upload.py` |
| `/api/relations` | 关系 | `api/relations.py` |
| `/api/tasks` | 任务 | `api/tasks.py` |

### 5.2 错误码

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 201 | 创建成功 |
| 400 | 参数错误 |
| 401 | 未认证 |
| 403 | 权限不足 |
| 404 | 不存在 |
| 500 | 服务器错误 |

---

## 6. MCP 工具规格

| 工具名 | 参数 | 返回格式 |
|--------|------|---------|
| `search_wiki` | query, doc_type?, tags?, limit?, auth_token? | Markdown |
| `get_document` | doc_id, auth_token? | Markdown |
| `get_related` | doc_id, relation_type?, auth_token? | Markdown |
| `list_documents` | doc_type?, tag?, limit?, auth_token? | Markdown |
| `get_code_context` | file_path, symbol?, auth_token? | Markdown |

所有返回 Markdown 文本，供 LLM 直接理解。

---

## 7. 缓存策略

| 数据 | 存储 | TTL |
|------|------|-----|
| 任务状态 | Redis Hash | 24h |
| Embedding 缓存 | Redis | 7d |
| FTS 配置 | Redis | 1h |

---

## 8. 前端页面

| 路径 | 页面 |
|------|------|
| `/` | 首页 |
| `/login` | 登录 |
| `/register` | 注册 |
| `/upload` | 上传 |
| `/search` | 搜索 |
| `/docs/[id]` | 文档详情 |
| `/graph` | 知识图谱 |

---

*文档版本: v1.0*
*最后更新: 2026-05-02*
