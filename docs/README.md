# LLM Wiki 设计文档索引

本文档目录包含 LLM Wiki 项目的完整设计文档。

---

## 文档总览

| 文档 | 说明 |
|------|------|
| [architecture.md](architecture.md) | 架构设计 - 整体架构、部署、核心技术选型 |
| [system-design.md](system-design.md) | 系统设计 - 功能模块、数据流、API 设计 |
| [solution-design.md](solution-design.md) | 方案设计 - 各项技术方案详细设计 |
| [requirements-analysis.md](requirements-analysis.md) | 需求分析 - 用户故事、功能清单、验收标准 |
| [module-design/](module-design/) | 模块设计说明书 |

---

## 模块设计文档

| 模块 | 文件 | 说明 |
|------|------|------|
| 解析器 | [module-design/parsers.md](module-design/parsers.md) | 多格式文件解析架构 |
| 搜索 | [module-design/search.md](module-design/search.md) | 混合检索、RRF 融合 |
| 摄取 | [module-design/ingest.md](module-design/ingest.md) | 文档处理流水线 |
| 关系发现 | [module-design/relation-discovery.md](module-design/relation-discovery.md) | 自动关联识别 |
| 数据库 | [module-design/database.md](module-design/database.md) | PostgreSQL + pgvector 存储设计 |
| 认证授权 | [module-design/auth.md](module-design/auth.md) | JWT + 角色权限 |
| MCP 服务 | [module-design/mcp-server.md](module-design/mcp-server.md) | Claude Code 集成 |
| 任务管理 | [module-design/task-manager.md](module-design/task-manager.md) | Redis 进度追踪 |

---

## 快速导航

### 架构设计
- [整体架构图](architecture.md#_2-整体架构图)
- [请求数据流](architecture.md#_4-请求数据流)
- [核心技术选型](architecture.md#_5-核心技术选型)

### 系统设计
- [功能模块划分](system-design.md#_2-功能模块划分)
- [数据库设计](system-design.md#_4-数据库设计)
- [API 路由](system-design.md#_5-api-设计)

### 方案设计
- [解析方案](solution-design.md#_2-文档解析方案)
- [Embedding 方案](solution-design.md#_3-embedding-方案)
- [RRF 融合算法](solution-design.md#_4-混合检索方案)

### 需求分析
- [用户角色](requirements-analysis.md#_2-用户角色分析)
- [功能清单](requirements-analysis.md#_3-功能需求清单)
- [验收标准](requirements-analysis.md#_6-验收标准)

---

*文档版本: v1.0*
*最后更新: 2026-05-02*
