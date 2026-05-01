"""Source code parser: extracts functions, classes, includes, and splits by structure."""

import re

from app.parsers.base import BaseParser, ParseResult, ParsedChunk

# Language-specific patterns for splitting code into logical chunks
_PATTERNS = {
    "c": {
        "function": re.compile(
            r"^(?:\w[\w\s\*]+)\s+(\w+)\s*\([^)]*\)\s*\{", re.MULTILINE
        ),
        "include": re.compile(r'#include\s*[<"]([^>"]+)[>"]'),
        "struct": re.compile(r"^(?:typedef\s+)?struct\s+(\w+)", re.MULTILINE),
    },
    "cpp": {
        "function": re.compile(
            r"^(?:\w[\w\s\*:&<>]+)\s+(\w+(?:::\w+)?)\s*\([^)]*\)\s*(?:const\s*)?\{",
            re.MULTILINE,
        ),
        "include": re.compile(r'#include\s*[<"]([^>"]+)[>"]'),
        "class": re.compile(r"^class\s+(\w+)", re.MULTILINE),
    },
    "java": {
        "function": re.compile(
            r"^\s*(?:public|private|protected)?\s*(?:static\s+)?(?:\w+(?:<[^>]+>)?)\s+(\w+)\s*\(",
            re.MULTILINE,
        ),
        "import": re.compile(r"^import\s+([\w.]+);", re.MULTILINE),
        "class": re.compile(r"^(?:public\s+)?class\s+(\w+)", re.MULTILINE),
    },
    "python": {
        "function": re.compile(r"^(?:async\s+)?def\s+(\w+)\s*\(", re.MULTILINE),
        "import": re.compile(r"^(?:from\s+([\w.]+)\s+)?import\s+([\w.,\s]+)", re.MULTILINE),
        "class": re.compile(r"^class\s+(\w+)", re.MULTILINE),
    },
}

_EXT_TO_LANG = {
    ".c": "c", ".h": "c",
    ".cpp": "cpp", ".hpp": "cpp", ".cc": "cpp", ".cxx": "cpp",
    ".java": "java",
    ".py": "python",
    ".js": "c", ".ts": "c",  # Use C-style patterns as fallback
    ".rs": "c", ".go": "c",
}


def _get_language(filename: str) -> str:
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return _EXT_TO_LANG.get(ext, "c")


def _extract_references(text: str, lang: str) -> list[str]:
    """Extract file/module references from includes/imports."""
    patterns = _PATTERNS.get(lang, {})
    refs = []
    for key in ("include", "import"):
        pat = patterns.get(key)
        if pat:
            for m in pat.finditer(text):
                refs.append(m.group(1))
    return refs


def _split_by_functions(text: str, lang: str, filename: str) -> list[ParsedChunk]:
    """Split source code into chunks by function/class boundaries."""
    patterns = _PATTERNS.get(lang, {})
    func_pat = patterns.get("function")

    if not func_pat:
        # Fallback: split by blank-line-separated blocks
        return _split_by_blocks(text, filename, lang)

    # Find all function start positions
    matches = list(func_pat.finditer(text))
    if not matches:
        return _split_by_blocks(text, filename, lang)

    lines = text.split("\n")
    chunks = []

    # Header chunk: everything before the first function (includes, defines, etc.)
    first_func_line = text[:matches[0].start()].count("\n")
    if first_func_line > 2:
        header = "\n".join(lines[:first_func_line]).strip()
        if header:
            chunks.append(ParsedChunk(
                content=header,
                metadata={"type": "header", "language": lang, "file": filename},
            ))

    # Extract includes for context prefix
    include_lines = [l for l in lines[:first_func_line] if re.match(r"#include|^import|^from .+ import", l)]
    context_prefix = "\n".join(include_lines[:10])

    # Each function as a chunk
    for i, match in enumerate(matches):
        func_name = match.group(1)
        start_line = text[:match.start()].count("\n")

        # Find the end: next function start or EOF
        if i + 1 < len(matches):
            end_line = text[:matches[i + 1].start()].count("\n")
        else:
            end_line = len(lines)

        func_text = "\n".join(lines[start_line:end_line]).rstrip()

        # Prepend context (includes) for better embedding
        chunk_content = f"// File: {filename}\n{context_prefix}\n\n{func_text}" if context_prefix else func_text

        chunks.append(ParsedChunk(
            content=chunk_content,
            metadata={
                "type": "function",
                "language": lang,
                "file": filename,
                "function": func_name,
                "start_line": start_line + 1,
                "end_line": end_line,
            },
        ))

    return chunks


def _split_by_blocks(text: str, filename: str, lang: str) -> list[ParsedChunk]:
    """Fallback: split by double-newline separated blocks, max ~80 lines each."""
    lines = text.split("\n")
    chunks = []
    current_lines = []

    for line in lines:
        current_lines.append(line)
        if len(current_lines) >= 80 and line.strip() == "":
            chunk_text = "\n".join(current_lines).strip()
            if chunk_text:
                chunks.append(ParsedChunk(
                    content=chunk_text,
                    metadata={"type": "block", "language": lang, "file": filename},
                ))
            current_lines = []

    if current_lines:
        chunk_text = "\n".join(current_lines).strip()
        if chunk_text:
            chunks.append(ParsedChunk(
                content=chunk_text,
                metadata={"type": "block", "language": lang, "file": filename},
            ))

    return chunks


class CodeParser(BaseParser):
    def supported_extensions(self) -> set[str]:
        return {".c", ".h", ".cpp", ".hpp", ".cc", ".cxx", ".java", ".py", ".js", ".ts", ".rs", ".go"}

    async def parse(self, data: bytes, filename: str) -> ParseResult:
        text = data.decode("utf-8", errors="replace")
        lang = _get_language(filename)

        refs = _extract_references(text, lang)
        chunks = _split_by_functions(text, lang, filename)

        return ParseResult(
            title=filename,
            doc_type="source_code",
            content=text,
            chunks=chunks,
            metadata={"language": lang, "lines": text.count("\n") + 1},
            references=refs,
        )
