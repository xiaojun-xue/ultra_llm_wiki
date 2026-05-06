"""PDF and Word document parser with semantic chunking."""

import re
import statistics
from typing import Any

from app.parsers.base import BaseParser, ParseResult, ParsedChunk


# ──────────────────────────────────────────────────────────────────────────────
# 标题识别正则
# ──────────────────────────────────────────────────────────────────────────────
HEADING_PATTERNS = [
    # 章节编号: 第一章, 第1章, 1.2.3, 1.2
    r"^(第[一二三四五六七八九十]+[章节篇])\s+(.+)$",
    r"^(第\d+[章节篇])\s+(.+)$",
    r"^(\d+(?:\.\d+)+)\s+(.+)$",
    r"^(\d+)\.\s+(\S.{0,50})$",  # 1. Section Title
    # 中文标题: 一、xxx, （一）xxx
    r"^([一二三四五六七八九十]+[、．]\s*)(.+)$",
    r"^[（(][一二三四五六七八九十]+[)）]\s*(.+)$",
    # 全大写简短文字
    r"^[A-Z\u4e00-\u9fff]{2,}[A-Z\u4e00-\u9fff\s]{0,30}$",
]

MAX_CHUNK_CHARS = 2000
MIN_CHUNK_CHARS = 300
SEMANTIC_BOOST = 1.5


# ──────────────────────────────────────────────────────────────────────────────
# PDF 解析器
# ──────────────────────────────────────────────────────────────────────────────

class PDFParser(BaseParser):
    def supported_extensions(self) -> set[str]:
        return {".pdf"}

    async def parse(self, data: bytes, filename: str) -> ParseResult:
        import pymupdf

        doc = pymupdf.open(stream=data, filetype="pdf")
        page_count = len(doc)

        # 1. 提取带格式信息的文本块
        blocks_with_format = self._extract_blocks_with_formatting(doc)

        if not blocks_with_format:
            doc.close()
            return ParseResult(
                title=filename,
                doc_type="document",
                content="",
                chunks=[],
                metadata={"format": "pdf", "pages": page_count},
            )

        # 2. 合并为段落
        paragraphs = self._merge_to_paragraphs(blocks_with_format)

        # 3. 识别文档结构（标题检测）
        paragraphs = self._detect_structure(paragraphs)

        # 4. 语义切片
        chunks = self._build_semantic_chunks(paragraphs)

        # 5. 提取全文（用于 content 字段）
        full_text = "\n\n".join(p["text"] for p in paragraphs if p["text"].strip())

        # 6. 提取标题
        title = self._extract_title(paragraphs, filename)

        # 7. 提取引用
        refs = self._extract_references(full_text)

        doc.close()

        return ParseResult(
            title=title,
            doc_type="document",
            content=full_text,
            chunks=chunks,
            metadata={"format": "pdf", "pages": page_count},
            references=refs,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # 第一阶段：提取文本块（含字体信息）
    # ──────────────────────────────────────────────────────────────────────────

    def _extract_blocks_with_formatting(self, doc) -> list[dict[str, Any]]:
        """提取每个文本块及其格式信息（字号、字体、位置）"""
        all_blocks = []

        for page_num, page in enumerate(doc):
            # get_text("dict") 返回带详细信息的结构
            page_dict = page.get_text("dict")
            page_width = page.rect.width
            page_height = page.rect.height

            for block in page_dict.get("blocks", []):
                if block.get("type") != 0:  # 跳过图片等非文本块
                    continue

                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = span.get("text", "").strip()
                        if not text:
                            continue

                        font_size = span.get("size", 0)
                        font_name = span.get("font", "")
                        flags = span.get("flags", 0)

                        # 计算相对字号（用于识别标题）
                        # pymupdf 通常正文 9-12pt，标题 14-24pt
                        is_bold = bool(flags & 1)
                        is_italic = bool(flags & 2)

                        all_blocks.append({
                            "text": text,
                            "font_size": font_size,
                            "font_name": font_name,
                            "is_bold": is_bold,
                            "is_italic": is_italic,
                            "page": page_num + 1,
                            "x0": span.get("bbox", [0, 0, 0, 0])[0],
                            "y0": span.get("bbox", [0, 0, 0, 0])[1],
                            "width": page_width,
                            "height": page_height,
                        })

        return all_blocks

    # ──────────────────────────────────────────────────────────────────────────
    # 第二阶段：合并为段落
    # ──────────────────────────────────────────────────────────────────────────

    def _merge_to_paragraphs(self, blocks: list[dict]) -> list[dict]:
        """将细粒度文本块合并为连贯段落"""
        if not blocks:
            return []

        paragraphs = []
        current: dict[str, Any] | None = None

        for block in blocks:
            text = block["text"]
            if not text.strip():
                # 空行或纯空白 → 段落分隔
                if current and current["text"].strip():
                    paragraphs.append(self._finalize_paragraph(current))
                    current = None
                continue

            # 保存前一个块的位置快照（深拷贝基本类型）
            prev_y0 = current["y0"] if current else None
            prev_text = current["text"] if current else ""
            prev_avg_size = current["avg_font_size"] if current else 0

            # 检查是否与前一个块在同一段落（y坐标接近，x在文本后续位置）
            is_same_paragraph = False
            if prev_y0 is not None:
                is_same_paragraph = (
                    abs(block["y0"] - prev_y0) < 5 and
                    block["x0"] < block["avg_font_size"] * len(prev_text) * 0.7
                )

            if is_same_paragraph:
                # 同一段落的不同行，合并
                current["text"] += " " + text
                current["font_sizes"].append(block["font_size"])
                current["avg_font_size"] = sum(current["font_sizes"]) / len(current["font_sizes"])
                current["is_bold"] = current["is_bold"] or block["is_bold"]
                current["pages"].add(block["page"])
            else:
                # 新段落
                if current:
                    paragraphs.append(self._finalize_paragraph(current))
                current = {
                    "text": text,
                    "font_sizes": [block["font_size"]],
                    "avg_font_size": block["font_size"],
                    "y0": block["y0"],
                    "is_bold": block["is_bold"],
                    "pages": {block["page"]},
                    "is_heading": False,
                }

        # 处理最后一个段落
        if current and current["text"].strip():
            paragraphs.append(self._finalize_paragraph(current))

        return paragraphs

    def _finalize_paragraph(self, para: dict) -> dict:
        """完成段落构建"""
        return {
            "text": para["text"].strip(),
            "avg_font_size": para["avg_font_size"],
            "max_font_size": max(para["font_sizes"]),
            "is_bold": para["is_bold"],
            "pages": sorted(list(para["pages"])),
            "is_heading": False,
            "heading_chain": [],
        }

    # ──────────────────────────────────────────────────────────────────────────
    # 第三阶段：识别文档结构
    # ──────────────────────────────────────────────────────────────────────────

    def _detect_structure(self, paragraphs: list[dict]) -> list[dict]:
        """检测标题段落，构建标题层级链"""
        if not paragraphs:
            return paragraphs

        # 计算字号统计
        font_sizes = [p["avg_font_size"] for p in paragraphs if p["text"].strip()]
        if not font_sizes:
            return paragraphs

        # 用中位数作为基准，避免极端值干扰
        median_size = statistics.median(font_sizes)
        heading_threshold = median_size * 1.2  # 比中位数大 20% 视为可能标题

        heading_chain: list[tuple[str, float]] = []  # [(heading_text, font_size), ...]

        for para in paragraphs:
            text = para["text"].strip()
            if not text:
                continue

            # 检测是否为标题
            is_heading = self._is_heading(
                text, para["avg_font_size"], heading_threshold, para["is_bold"]
            )

            if is_heading:
                para["is_heading"] = True
                # 更新层级链
                heading_level = self._get_heading_level(text, para["avg_font_size"], median_size)
                # 裁剪到同级
                heading_chain = [h for h in heading_chain if h[1] >= heading_level]
                heading_chain.append((text, heading_level))
                para["heading_chain"] = [h[0] for h in heading_chain]
            else:
                para["heading_chain"] = [h[0] for h in heading_chain]

        return paragraphs

    def _is_heading(
        self, text: str, font_size: float, threshold: float, is_bold: bool
    ) -> bool:
        """判断段落是否为标题"""
        # 规则 1: 字号明显大于正文 + (粗体 或 符合标题模式)
        if font_size >= threshold and len(text) < 100:
            # 需要粗体 OR 符合标题编号格式才认定
            if is_bold or any(re.match(p, text) for p in HEADING_PATTERNS):
                return True

        # 规则 2: 明确匹配标题编号格式
        for pattern in HEADING_PATTERNS:
            if re.match(pattern, text):
                return True

        # 规则 3: 全大写 + 粗体 + 较短
        if is_bold and text.isupper() and 3 < len(text) < 80 and not text.isdigit():
            return True

        # 规则 4: 字号超过阈值 1.5 倍，无视粗体（超大标题如封面标题）
        if font_size >= threshold * 1.5 and len(text) < 60:
            return True

        return False

    def _get_heading_level(self, text: str, font_size: float, median: float) -> float:
        """根据字号估算标题层级（字号越大层级越高）"""
        ratio = font_size / median
        if ratio >= 2.0:
            return 1.0  # 一级标题（最大）
        elif ratio >= 1.6:
            return 2.0  # 二级标题
        elif ratio >= 1.3:
            return 3.0  # 三级标题
        else:
            # 按编号格式推断
            if re.match(r"^(第[一二三四五六七八九十]+[章节]|[0-9]+\.)", text):
                return 2.0
            return 4.0  # 其他小标题

    # ──────────────────────────────────────────────────────────────────────────
    # 第四阶段：语义切片
    # ──────────────────────────────────────────────────────────────────────────

    def _build_semantic_chunks(self, paragraphs: list[dict]) -> list[ParsedChunk]:
        """按语义边界（标题+段落）切分文档"""
        chunks = []
        current_content: list[dict] = []
        current_size = 0
        current_heading = ""
        # 孤儿标题：上一个标题是孤儿（无正文就遇到新标题），待确认
        pending_orphan: dict | None = None  # {text, para}

        def _make_orphan_chunk(orphan_text: str, orphan_para: dict) -> ParsedChunk:
            """为孤儿标题创建最小 chunk：使用标题文本作为内容"""
            pages = sorted(orphan_para["pages"])
            start_page = pages[0] if pages else 1
            end_page = pages[-1] if pages else start_page
            return ParsedChunk(
                content=orphan_text,
                metadata={
                    "type": "section",
                    "heading": orphan_text,
                    "start_page": start_page,
                    "end_page": end_page,
                },
            )

        for i, para in enumerate(paragraphs):
            text = para["text"]
            if not text.strip():
                continue

            para_size = len(text)

            # 遇到标题
            if para["is_heading"]:
                # 前一个孤儿标题遇到新标题 → 孤儿标题确认（无正文）
                if pending_orphan is not None:
                    orphan_chunk = _make_orphan_chunk(pending_orphan["text"], pending_orphan["para"])
                    chunks.append(orphan_chunk)
                    pending_orphan = None

                # 保存当前 accumulated 内容
                if current_content:
                    chunk = self._make_chunk(current_content, current_heading)
                    if chunk:
                        chunks.append(chunk)
                    current_content = []
                    current_size = 0

                # 当前标题标记为孤儿（等见到正文再取消）
                pending_orphan = {"text": text, "para": para}
                current_heading = text
                continue  # 标题不加入 content

            # 遇到正文：孤儿标题已确认有正文 → 不再是孤儿
            if pending_orphan is not None:
                pending_orphan = None

            # 非标题段落：检查是否需要切分
            if current_size + para_size > MAX_CHUNK_CHARS * SEMANTIC_BOOST:
                if current_size >= MIN_CHUNK_CHARS:
                    # 在段落边界切分
                    chunk = self._make_chunk(current_content, current_heading)
                    if chunk:
                        chunks.append(chunk)
                    current_content = []
                    current_size = 0
                    current_heading = ""

                # 如果单个段落就超过限制，按句子拆分
                if para_size > MAX_CHUNK_CHARS:
                    sub_chunks = self._split_paragraph(para, current_heading)
                    chunks.extend(sub_chunks)
                    continue

            current_content.append(para)
            current_size += para_size

        # 处理尾部孤儿标题
        if pending_orphan is not None:
            orphan_chunk = _make_orphan_chunk(pending_orphan["text"], pending_orphan["para"])
            chunks.append(orphan_chunk)
            pending_orphan = None

        # 处理最后一个 chunk
        if current_content:
            chunk = self._make_chunk(current_content, current_heading)
            if chunk:
                chunks.append(chunk)

        return chunks

        # 如果没有生成任何 chunk（比如文档全是短段落），把全文作为一个 chunk
        if not chunks and paragraphs:
            all_text = "\n\n".join(p["text"] for p in paragraphs if p["text"].strip())
            if all_text:
                chunks.append(ParsedChunk(
                    content=all_text,
                    metadata={"type": "full_document", "paragraphs_count": len(paragraphs)},
                ))

        return chunks

    def _make_chunk(self, paragraphs: list[dict], heading: str) -> ParsedChunk | None:
        """将段落列表合并为一个 chunk"""
        if not paragraphs:
            return None

        content_parts = []
        start_page = paragraphs[0]["pages"][0] if paragraphs[0]["pages"] else 1
        end_page = paragraphs[-1]["pages"][-1] if paragraphs[-1]["pages"] else start_page

        for idx, para in enumerate(paragraphs):
            para_text = para["text"]

            # 如果第一个段落的 heading_chain 已经包含当前 heading，说明该段落本身是 heading
            # 这种情况下不要重复 prepend
            if idx == 0 and para["heading_chain"]:
                last_heading = para["heading_chain"][-1] if para["heading_chain"] else ""
                if last_heading != heading:
                    # heading_chain 中的最后一项和 current_heading 不同，说明有子标题
                    chain_str = " > ".join(para["heading_chain"][-2:])
                    para_text = f"[{chain_str}]\n\n{para_text}"
                # else: heading_chain 最后一项 == current_heading，说明这个段落本身就是 heading，跳过
            elif idx == 0 and heading:
                # 第一个段落没有 heading_chain，使用 current_heading
                para_text = f"[{heading}]\n\n{para_text}"
            elif para["heading_chain"]:
                # 非首个段落有 heading_chain（说明有子标题层级）
                chain_str = " > ".join(para["heading_chain"][-2:])
                para_text = f"[{chain_str}]\n\n{para_text}"

            content_parts.append(para_text)

        content = "\n\n".join(content_parts)

        # 构建 heading 链元数据
        heading_chain = []
        if paragraphs[0]["heading_chain"]:
            heading_chain = paragraphs[0]["heading_chain"]
        elif heading:
            heading_chain = [heading]

        return ParsedChunk(
            content=content,
            metadata={
                "type": "section" if heading_chain else "paragraphs",
                "heading": heading_chain[-1] if heading_chain else None,
                "heading_chain": heading_chain,
                "start_page": start_page,
                "end_page": end_page,
                "paragraphs_count": len(paragraphs),
            },
        )

    def _split_paragraph(self, para: dict, current_heading: str) -> list[ParsedChunk]:
        """将过长的段落按句子拆分为多个 chunk"""
        text = para["text"]
        chunks = []

        # 按常见分隔符拆分句子
        # 优先按换行、句号、逗号分
        sentences = re.split(r"(?<=[。！？；\n])\s*", text)

        current_sentences = []
        current_size = 0

        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue

            if current_size + len(sent) > MAX_CHUNK_CHARS and current_sentences:
                # 保存当前 chunk
                content = "\n\n".join(current_sentences)
                if current_heading:
                    content = f"[{current_heading}]\n\n{content}"
                chunks.append(ParsedChunk(
                    content=content,
                    metadata={
                        "type": "section",
                        "heading": current_heading,
                        "start_page": para["pages"][0] if para["pages"] else 1,
                        "end_page": para["pages"][-1] if para["pages"] else 1,
                    },
                ))
                current_sentences = []
                current_size = 0

            current_sentences.append(sent)
            current_size += len(sent)

        # 处理剩余句子
        if current_sentences:
            content = "\n\n".join(current_sentences)
            if current_heading and not any(c.metadata.get("heading") == current_heading for c in chunks):
                content = f"[{current_heading}]\n\n{content}"
            chunks.append(ParsedChunk(
                content=content,
                metadata={
                    "type": "section",
                    "heading": current_heading,
                    "start_page": para["pages"][0] if para["pages"] else 1,
                    "end_page": para["pages"][-1] if para["pages"] else 1,
                },
            ))

        return chunks

    # ──────────────────────────────────────────────────────────────────────────
    # 辅助方法
    # ──────────────────────────────────────────────────────────────────────────

    def _extract_title(self, paragraphs: list[dict], filename: str) -> str:
        """从文档中提取标题（通常是第一个大字号段落）"""
        if not paragraphs:
            return filename

        # 优先找第一个被识别为标题的段落
        for para in paragraphs:
            if para["is_heading"] and len(para["text"]) < 100:
                return para["text"]

        # 否则用第一个粗体或大字号段落
        for para in paragraphs:
            text = para["text"].strip()
            if text and len(text) < 100:
                if para["is_bold"] or para["avg_font_size"] > 12:
                    return text

        return filename

    def _extract_references(self, text: str) -> list[str]:
        """从文本中提取文件名引用"""
        refs = []
        # 匹配常见代码/文档文件名
        for m in re.finditer(r"[\w/\\]+\.\w{1,10}", text):
            candidate = m.group(0)
            # 过滤掉 URL、邮箱等
            if any(candidate.startswith(x) for x in ["http://", "https://", "www.", "@"]):
                continue
            # 匹配常见的代码/文档扩展名
            if any(candidate.endswith(ext) for ext in [
                ".c", ".h", ".cpp", ".hpp", ".py", ".java", ".js", ".ts",
                ".md", ".txt", ".pdf", ".docx",
                ".sch", ".schdoc", ".kicad_sch",
            ]):
                refs.append(candidate)
        return list(set(refs))[:20]  # 限制数量


# ──────────────────────────────────────────────────────────────────────────────
# Word 解析器（保持原有实现，仅做代码整理）
# ──────────────────────────────────────────────────────────────────────────────

class WordParser(BaseParser):
    def supported_extensions(self) -> set[str]:
        return {".docx", ".doc"}

    async def parse(self, data: bytes, filename: str) -> ParseResult:
        from io import BytesIO

        from docx import Document as DocxDocument

        doc = DocxDocument(BytesIO(data))

        paragraphs = []
        chunks = []
        current_section = []
        current_heading = ""

        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                if current_section:
                    section_text = "\n\n".join(current_section)
                    if current_heading:
                        section_text = f"[{current_heading}]\n\n{section_text}"
                    chunks.append(ParsedChunk(
                        content=section_text,
                        metadata={"type": "section", "heading": current_heading},
                    ))
                    current_section = []
                continue

            paragraphs.append(text)

            # 检测是否为标题（样式名包含 Heading）
            is_heading = False
            if para.style and para.style.name:
                is_heading = para.style.name.startswith("Heading")

            if is_heading:
                if current_section:
                    section_text = "\n\n".join(current_section)
                    if current_heading:
                        section_text = f"[{current_heading}]\n\n{section_text}"
                    chunks.append(ParsedChunk(
                        content=section_text,
                        metadata={"type": "section", "heading": current_heading},
                    ))
                    current_section = []
                current_heading = text
                current_section.append(text)
            else:
                current_section.append(text)

        # 处理最后一个 section
        if current_section:
            section_text = "\n\n".join(current_section)
            if current_heading:
                section_text = f"[{current_heading}]\n\n{section_text}"
            chunks.append(ParsedChunk(
                content=section_text,
                metadata={"type": "section", "heading": current_heading},
            ))

        full_text = "\n\n".join(paragraphs)

        # 标题从第一个 Heading 样式获取
        title = filename
        for para in doc.paragraphs:
            if para.style and para.style.name and para.style.name.startswith("Heading"):
                title = para.text.strip()
                break

        refs = self._extract_references(full_text)

        return ParseResult(
            title=title,
            doc_type="document",
            content=full_text,
            chunks=chunks or [ParsedChunk(content=full_text, metadata={"type": "full"})],
            metadata={"format": "docx"},
            references=refs,
        )

    def _extract_references(self, text: str) -> list[str]:
        """从文本中提取文件名引用"""
        refs = []
        for m in re.finditer(r"[\w/\\]+\.\w{1,10}", text):
            candidate = m.group(0)
            if any(candidate.startswith(x) for x in ["http://", "https://", "www.", "@"]):
                continue
            if any(candidate.endswith(ext) for ext in [
                ".c", ".h", ".py", ".md", ".txt", ".pdf", ".docx",
            ]):
                refs.append(candidate)
        return list(set(refs))[:20]
