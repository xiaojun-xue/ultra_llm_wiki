# 模块设计 - 解析器 (Parsers)

## 1. 模块概述

解析器模块负责将上传的原始文件转换为结构化文本和元数据，是文档处理流水线的第一步。

### 1.1 核心职责

- 识别文件类型，选择对应解析器
- 提取文本内容
- 按语义切分成 chunks
- 提取元数据（引用、函数名、信号等）

### 1.2 架构

```
parsers/
├── __init__.py          # get_parser() 工厂
├── base.py              # BaseParser + ParseResult
├── markdown_parser.py   # Markdown/纯文本
├── code_parser.py       # 源代码
├── pdf_parser.py        # PDF
└── schematic_parser.py  # 原理图
```

---

## 2. 接口定义

### 2.1 BaseParser

```python
class BaseParser(ABC):
    @abstractmethod
    def supported_extensions(self) -> set[str]: ...

    @abstractmethod
    async def parse(self, data: bytes, filename: str) -> ParseResult: ...

    def can_parse(self, filename: str) -> bool:
        ext = "." + filename.rsplit(".", 1)[-1].lower()
        return ext in self.supported_extensions()
```

### 2.2 ParseResult / ParsedChunk

```python
@dataclass
class ParseResult:
    title: str
    doc_type: str
    content: str
    content_html: str | None = None
    chunks: list[ParsedChunk] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    references: list[str] = field(default_factory=list)

@dataclass
class ParsedChunk:
    content: str
    metadata: dict = field(default_factory=dict)
```

---

## 3. 各解析器

### 3.1 MarkdownParser (.md .txt .rst)

- 按标题层级切分，heading 链作为上下文
- markdown-it 渲染 HTML
- 提取 `[link](path)` 和 `` `filename.c` `` 引用

### 3.2 CodeParser (.c .h .cpp .java .py .js .rs .go)

| 语言 | 切片方式 |
|------|---------|
| Python | ast.parse() 遍历，正确提取类方法 |
| C/C++ | 正则匹配函数 |
| 其他 | 正则或分块回退 |

- 提取 include/import 引用
- 调用 FunctionAnalyzer 提取 call graph

### 3.3 PdfParser (.pdf)

- pymupdf 提取每页文本
- 按段落切分

### 3.4 SchematicParser (.sch .schdoc .kicad_sch)

- ezdxf 读取 DXF
- 提取元件列表和网表

---

## 4. 工厂函数

```python
PARSERS = [MarkdownParser(), CodeParser(), PdfParser(), SchematicParser()]

def get_parser(filename: str) -> BaseParser | None:
    for parser in PARSERS:
        if parser.can_parse(filename):
            return parser
    return None
```

---

## 5. 扩展新解析器

```python
class MyParser(BaseParser):
    def supported_extensions(self) -> set[str]:
        return {".xyz"}
    async def parse(self, data: bytes, filename: str) -> ParseResult:
        return ParseResult(...)

PARSERS.append(MyParser())
```

---

*文档版本: v1.0*
