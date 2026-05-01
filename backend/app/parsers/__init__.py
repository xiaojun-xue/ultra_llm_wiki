"""Parser registry: maps file extensions to parser instances."""

from app.parsers.base import BaseParser, ParseResult, ParsedChunk
from app.parsers.code_parser import CodeParser
from app.parsers.markdown_parser import MarkdownParser, ConfigParser
from app.parsers.pdf_parser import PDFParser, WordParser
from app.parsers.schematic_parser import SchematicParser

_PARSERS: list[BaseParser] = [
    CodeParser(),
    MarkdownParser(),
    ConfigParser(),
    PDFParser(),
    WordParser(),
    SchematicParser(),
]


def get_parser(filename: str) -> BaseParser | None:
    """Find a parser that can handle the given filename."""
    for parser in _PARSERS:
        if parser.can_parse(filename):
            return parser
    return None


__all__ = ["get_parser", "BaseParser", "ParseResult", "ParsedChunk"]