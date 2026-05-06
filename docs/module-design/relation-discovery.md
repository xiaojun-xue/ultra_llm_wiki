# 模块设计 - 关系发现 (Relation Discovery)

## 1. 模块概述

关系发现模块自动识别文档间的关联，形成知识图谱。

### 1.1 关系类型

| 关系类型 | 发现策略 | 置信度 |
|---------|---------|--------|
| `references` | 文档 A 引用/链接 B | 0.9 |
| `depends_on` | 代码 A #include/import B | 0.9 |
| `implements` | 原理图信号 ↔ 代码变量名匹配 | 0.5-0.95 |
| `related_to` | 语义 embedding 相似度 < 0.3 | 0.7-1.0 |

---

## 2. 核心函数

```python
async def discover_relations(db: AsyncSession, doc: Document) -> int:
    """运行所有发现策略，返回新增关系数"""
    count = 0
    count += await _discover_by_references(db, doc)
    count += await _discover_by_name_matching(db, doc)
    count += await _discover_by_semantic_similarity(db, doc)
    return count
```

---

## 3. 各策略详解

### 3.1 引用分析 (_discover_by_references)

```python
async def _discover_by_references(db, doc):
    refs = doc.metadata_.get("references", [])
    # refs = ["uart.h", "gpio.c"]

    for ref in refs:
        # 模糊匹配文档标题
        stmt = select(Document).where(
            Document.id != doc.id,
            Document.title.ilike(f"%{ref}%"),
        )
        targets = result.scalars().all()

        for target in targets:
            await _create_relation(
                db, doc.id, target.id,
                relation_type="depends_on" if doc.doc_type=="source_code" else "references",
                confidence=0.9,
            )
```

### 3.2 名称匹配 (_discover_by_name_matching)

原理图元件/信号名与代码变量名匹配：

```python
async def _discover_by_name_matching(db, doc):
    if doc.doc_type not in ("schematic", "source_code"):
        return 0

    signals = doc.metadata_.get("signals", [])  # ["SPI1_MOSI", "SPI1_MISO"]
    keywords = set()
    for sig in signals:
        # 拆分: SPI1_MOSI -> ["SPI", "MOSI"]
        parts = re.split(r"[_\d]+", sig)
        keywords.update(p for p in parts if len(p) >= 3)

    # 在其他文档中匹配关键词
    other_type = "source_code" if doc.doc_type == "schematic" else "schematic"
    candidates = await db.execute(
        select(Document).where(Document.doc_type == other_type)
    )

    for candidate in candidates:
        content = (candidate.content or "").lower()
        matched = [kw for kw in keywords if kw in content]
        if len(matched) >= 2:
            confidence = min(0.5 + 0.1 * len(matched), 0.95)
            await _create_relation(db, doc.id, candidate.id,
                "implements", matched_keywords=matched, confidence=confidence)
```

### 3.3 语义相似度 (_discover_by_semantic_similarity)

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
HAVING AVG(c.embedding <=> :avg_embedding) < 0.3;
```

---

## 4. 关系创建

```python
async def _create_relation(
    db,
    source_id, target_id,
    relation_type: str,
    description: str = "",
    confidence: float = 1.0,
) -> bool:
    """创建关系（如已存在则跳过）"""
    existing = await db.execute(
        select(DocumentRelation).where(
            DocumentRelation.source_id == source_id,
            DocumentRelation.target_id == target_id,
            DocumentRelation.relation_type == relation_type,
        )
    )
    if existing.scalar_one_or_none():
        return False  # 已存在

    db.add(DocumentRelation(...))
    await db.commit()
    return True
```

---

*文档版本: v1.0*
