"""Markdown and plain text parser: splits by headings, preserves heading chains."""

import re

from app.parsers.base import BaseParser, ParseResult, ParsedChunk


def _split_markdown_by_sections(text: str) -> list[ParsedChunk]:
    """Split markdown into chunks by headings, keeping heading hierarchy."""
    lines = text.split("\n")
    chunks = []
    current_content = []
    heading_chain: list[str] = []  # e.g., ["Chapter 1", "1.1 Overview"]
    current_level = 0

    for line in lines:
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)

        if heading_match:
            # Flush previous section
            if current_content:
                section_text = "\n".join(current_content).strip()
                if section_text:
                    # Prepend heading chain for context
                    context = " > ".join(heading_chain) if heading_chain else ""
                    full_content = f"[{context}]\n\n{section_text}" if context else section_text
                    chunks.append(ParsedChunk(
                        content=full_content,
                        metadata={
                            "type": "section",
                            "heading_chain": list(heading_chain),
                            "section": heading_chain[-1] if heading_chain else "",
                        },
                    ))
                current_content = []

            level = len(heading_match.group(1))
            heading_text = heading_match.group(2).strip()

            # Update heading chain based on level
            if level <= current_level:
                heading_chain = heading_chain[:level - 1]
            heading_chain.append(heading_text)
            current_level = level

            current_content.append(line)
        else:
            current_content.append(line)

    # Flush last section
    if current_content:
        section_text = "\n".join(current_content).strip()
        if section_text:
            context = " > ".join(heading_chain) if heading_chain else ""
            full_content = f"[{context}]\n\n{section_text}" if context else section_text
            chunks.append(ParsedChunk(
                content=full_content,
                metadata={
                    "type": "section",
                    "heading_chain": list(heading_chain),
                    "section": heading_chain[-1] if heading_chain else "",
                },
            ))

    # If no headings found, split by paragraphs
    if not chunks:
        chunks = _split_by_paragraphs(text)

    return chunks


def _split_by_paragraphs(text: str, max_chars: int = 2000) -> list[ParsedChunk]:
    """Split plain text by paragraphs, merging small ones."""
    paragraphs = re.split(r"\n\s*\n", text)
    chunks = []
    current = []
    current_len = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if current_len + len(para) > max_chars and current:
            chunks.append(ParsedChunk(
                content="\n\n".join(current),
                metadata={"type": "paragraph"},
            ))
            current = []
            current_len = 0

        current.append(para)
        current_len += len(para)

    if current:
        chunks.append(ParsedChunk(
            content="\n\n".join(current),
            metadata={"type": "paragraph"},
        ))

    return chunks


def _extract_references(text: str) -> list[str]:
    """Extract file references from markdown links and code mentions."""
    refs = []
    # Markdown links: [text](path)
    for m in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", text):
        refs.append(m.group(2))
    # Backtick code mentions that look like filenames
    for m in re.finditer(r"`([^`]+\.\w{1,5})`", text):
        refs.append(m.group(1))
    return refs


def _simple_md_to_html(text: str) -> str:
    """Very basic markdown to HTML conversion for storage."""
    from markdown_it import MarkdownIt

    md = MarkdownIt()
    return md.render(text)


class MarkdownParser(BaseParser):
    def supported_extensions(self) -> set[str]:
        return {".md", ".txt", ".rst"}

    async def parse(self, data: bytes, filename: str) -> ParseResult:
        text = data.decode("utf-8", errors="replace")
        is_markdown = filename.lower().endswith(".md")

        chunks = _split_markdown_by_sections(text) if is_markdown else _split_by_paragraphs(text)
        refs = _extract_references(text)

        content_html = None
        if is_markdown:
            try:
                content_html = _simple_md_to_html(text)
            except Exception:
                pass

        # Extract title from first heading or filename
        title = filename
        heading_match = re.match(r"^#\s+(.+)$", text, re.MULTILINE)
        if heading_match:
            title = heading_match.group(1).strip()

        return ParseResult(
            title=title,
            doc_type="document",
            content=text,
            content_html=content_html,
            chunks=chunks,
            metadata={"format": "markdown" if is_markdown else "plaintext"},
            references=refs,
        )


class ConfigParser(BaseParser):
    """Parser for INI/CFG/YAML/JSON config files."""

    def supported_extensions(self) -> set[str]:
        return {".ini", ".cfg", ".conf", ".json", ".yaml", ".yml"}

    async def parse(self, data: bytes, filename: str) -> ParseResult:
        text = data.decode("utf-8", errors="replace")

        # Config files are usually small enough to be a single chunk
        chunks = [ParsedChunk(
            content=f"# Configuration file: {filename}\n\n{text}",
            metadata={"type": "config", "file": filename},
        )]

        return ParseResult(
            title=filename,
            doc_type="document",
            content=text,
            chunks=chunks,
            metadata={"format": filename.rsplit(".", 1)[-1].lower()},
        )
