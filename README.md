# LLM Wiki Knowledge Base

一个支持源代码、文档、原理图的知识库系统，提供 **Web Wiki** 和 **MCP Server** 双模式访问。

## 架构

```
浏览器 ──→ Nginx ──→ Next.js (Web UI)
                  ──→ FastAPI (REST API)
Claude Code ──→ MCP Server (SSE) ──→ Core Service
                                        ├── PostgreSQL + pgvector (数据 + 向量检索)
                                        ├── MinIO (文件存储)
                                        ├── Ollama/BGE-M3 (Embedding)
                                        └── Redis (缓存)
```

## 快速开始

```bash
# 1. 克隆项目
git clone <repo-url>
cd llm_wiki_claude

# 2. 启动所有服务
bash scripts/start.sh

# 3. 访问
#    Web UI:    http://localhost
#    API Docs:  http://localhost:8000/docs
#    MCP:       http://localhost:8001/sse
```

## 功能

### 支持的文件格式

| 类型 | 格式 |
|------|------|
| 源代码 | .c .h .cpp .hpp .java .py .js .ts .rs .go |
| 文档 | .md .txt .pdf .docx .ini .cfg .json .yaml |
| 原理图 | .sch .schdoc .kicad_sch .brd .pcbdoc |

### 智能解析

- **源代码**: 按函数/类分块，提取 include/import 依赖
- **文档**: 按章节分块，保留标题层级链
- **原理图**: 提取元件列表、信号名、网表连接

### 关系自动发现

- 代码依赖分析 (`#include` / `import`)
- 文档交叉引用 (链接、文件名提及)
- 原理图-代码关联 (信号名/元件名匹配)
- 语义相似度 (embedding 余弦距离)

### 混合搜索

- 向量相似度搜索 (pgvector)
- 全文关键词搜索 (支持中文分词)
- RRF 结果融合

## Claude Code 集成

将 `mcp.json.example` 复制为 `.mcp.json` 并修改服务器地址：

```json
{
  "mcpServers": {
    "llm-wiki": {
      "type": "sse",
      "url": "http://your-server:8001/sse"
    }
  }
}
```

可用的 MCP 工具：

| 工具 | 说明 |
|------|------|
| `search_wiki` | 搜索知识库 (支持按类型、标签过滤) |
| `get_document` | 获取文档完整内容 |
| `get_related` | 获取关联文档 (支持按关系类型过滤) |
| `list_documents` | 列出文档目录 |
| `get_code_context` | 获取代码上下文 + 关联的文档和原理图 |

## 批量导入

```bash
python scripts/import_data.py /path/to/your/materials --api-url http://localhost:8000
```

目录结构会自动转为标签。

## 开发

```bash
# 后端开发
cd backend
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000

# 前端开发
cd web
npm install
npm run dev

# 运行测试
cd backend
pytest tests/ -v
```

## 技术栈

- **后端**: FastAPI + SQLAlchemy + asyncpg
- **MCP**: FastMCP (Python SDK)
- **前端**: Next.js 14 + Tailwind CSS
- **数据库**: PostgreSQL 16 + pgvector
- **Embedding**: BGE-M3 (Ollama)
- **文件存储**: MinIO
- **缓存**: Redis
- **部署**: Docker Compose + Nginx
