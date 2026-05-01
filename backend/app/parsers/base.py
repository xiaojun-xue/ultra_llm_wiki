"""Base parser interface for all document types."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ParsedChunk:
    """A single chunk of parsed content."""

    content: str
    metadata: dict = field(default_factory=dict)
    # metadata examples:
    #   code: {"language": "c", "function": "SPI_Init", "file": "spi.c", "start_line": 10}
    #   doc:  {"section": "3.2 SPI Communication", "heading_chain": ["Ch3", "3.2"]}
    #   sch:  {"component": "U3", "module": "SPI", "designator": "STM32F407"}


@dataclass
class ParseResult:
    """Result of parsing a document."""

    title: str
    doc_type: str
    content: str  # Full text content
    content_html: str | None = None
    chunks: list[ParsedChunk] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    # Hints for relation discovery
    references: list[str] = field(default_factory=list)  # filenames/symbols referenced


class BaseParser(ABC):
    """Abstract base class for document parsers."""

    @abstractmethod
    def supported_extensions(self) -> set[str]:
        """Return set of file extensions this parser handles (e.g., {'.c', '.h'})."""

    @abstractmethod
    async def parse(self, data: bytes, filename: str) -> ParseResult:
        """Parse raw file bytes into structured content + chunks."""

    def can_parse(self, filename: str) -> bool:
        ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        return ext in self.supported_extensions()
