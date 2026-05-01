"""
Function call graph analyzer.

Extracts function calls from source code using:
- Python:   ast module (stdlib, zero deps)
- C/C++/Java: Clang AST (libclang, high precision)
- Fallback: regex-based heuristic (always available)
"""

import ast
import re
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Data types
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class FunctionCalls:
    """Calls extracted from a single function or file."""

    function_name: str
    calls: list[str] = field(default_factory=list)
    # called_by: list[str] = field(default_factory=list)  # populated at file-level
    is_complete: bool = False  # True if from AST, False if from regex fallback


# ──────────────────────────────────────────────────────────────────────────────
# Python AST analyzer  (stdlib — always available)
# ──────────────────────────────────────────────────────────────────────────────


class PythonAstAnalyzer:
    """Extract function calls from Python source using the stdlib ast module."""

    @staticmethod
    def is_available() -> bool:
        return True  # ast is always in stdlib

    def analyze(self, source: str) -> list[FunctionCalls]:
        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            logger.warning("PythonAstAnalyzer: syntax error %s", e)
            return []

        results: list[FunctionCalls] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                calls = self._extract_calls(node)
                results.append(FunctionCalls(
                    function_name=node.name,
                    calls=calls,
                    is_complete=True,
                ))

        return results

    def _extract_calls(self, func_node: ast.FunctionDef) -> list[str]:
        """Walk the AST of a function body and collect all function call names."""
        calls: list[str] = []
        for node in ast.walk(func_node):
            if isinstance(node, ast.Call):
                # Direct name: foo()
                if isinstance(node.func, ast.Name):
                    calls.append(node.func.id)
                # Attribute access: self.foo(), obj.bar()
                elif isinstance(node.func, ast.Attribute):
                    # Don't include self/super as calls
                    if isinstance(node.func.value, ast.Name):
                        if node.func.value.id not in ("self", "cls", "super"):
                            calls.append(node.func.attr)
                    else:
                        calls.append(node.func.attr)
        return list(set(calls))  # deduplicate


# ──────────────────────────────────────────────────────────────────────────────
# Clang AST analyzer  (libclang — optional, high precision)
# ──────────────────────────────────────────────────────────────────────────────


class ClangAstAnalyzer:
    """Extract function calls from C/C++/Java source using libclang."""

    def __init__(self):
        self._index: Optional[object] = None
        self._available = self._check()

    def _check(self) -> bool:
        try:
            import clang
            self._index = clang.Index.create()
            return True
        except ImportError:
            logger.warning("ClangAstAnalyzer: clang package not installed")
            return False
        except Exception as e:
            logger.warning("ClangAstAnalyzer: failed to create index: %s", e)
            return False

    @staticmethod
    def is_available() -> bool:
        try:
            import clang
            return True
        except ImportError:
            return False

    def analyze(self, source: str, filename: str = "input.c") -> list[FunctionCalls]:
        if not self._available or self._index is None:
            return []

        try:
            # Parse source into a translation unit
            # -fsyntax-only: don't produce object file
            # -x c: force C language (regardless of extension)
            tu = self._index.parse(
                filename,
                args=["-fsyntax-only", "-x", self._lang_flag(filename), "-std=c11"],
            )
        except Exception as e:
            logger.warning("ClangAstAnalyzer: parse failed for %s: %s", filename, e)
            return []

        results: list[FunctionCalls] = []
        visitor = _ClangCallVisitor()
        tu.cursor.accept(visitor)
        for func_name, callees in visitor.results.items():
            results.append(FunctionCalls(
                function_name=func_name,
                calls=callees,
                is_complete=True,
            ))
        return results

    @staticmethod
    def _lang_flag(filename: str) -> str:
        ext = filename.rsplit(".", 1)[-1].lower()
        if ext in ("cpp", "cc", "cxx", "hpp", "cpp"):
            return "c++"
        return "c"


class _ClangCallVisitor:
    """Recursive visitor that collects (caller → callee) pairs from a Clang AST."""

    def __init__(self):
        self.results: dict[str, list[str]] = {}
        self._current_func: str | None = None

    def visit(self, cursor) -> bool:
        kind = cursor.kind

        # Enter a new function definition
        if kind in (
            clang.CursorKind.FUNCTION_DECL,
            clang.CursorKind.CXX_METHOD,
            clang.CursorKind.CONSTRUCTOR,
            clang.CursorKind.DESTRUCTOR,
        ):
            if cursor.spelling:
                self._current_func = cursor.spelling
                if self._current_func not in self.results:
                    self.results[self._current_func] = []

        # Function call expression
        if kind == clang.CursorKind.CALL_EXPR and cursor.spelling:
            if self._current_func is not None:
                callee = cursor.spelling
                if callee != self._current_func:  # no self-recursion
                    self.results[self._current_func].append(callee)

        return True  # continue visiting children


# ──────────────────────────────────────────────────────────────────────────────
# Regex fallback  (always available, moderate precision)
# ──────────────────────────────────────────────────────────────────────────────


class RegexAnalyzer:
    """
    Regex-based call extractor for any language.
    Less precise (may capture strings/comments) but always works.
    """

    # Match function-call-like patterns:  word(...)
    _CALL_PAT = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]{1,64})\s*\(", re.MULTILINE)

    # Common builtin/library names to exclude (noise)
    _SKIP = frozenset({
        "if", "while", "for", "switch", "return", "sizeof", "defined",
        "include", "define", "undef", "error", "pragma", "line",
        "printf", "print", "puts", "scanf", "sprintf",  # stdio
        "malloc", "calloc", "realloc", "free", "memcpy", "memset", "memmove",  # memory
        "strlen", "strcpy", "strncpy", "strcat", "strcmp", "strncmp",  # string
        "true", "false", "nullptr", "NULL",
    })

    def is_available(self) -> bool:
        return True

    def analyze(self, source: str) -> list[FunctionCalls]:
        # Find top-level function definitions
        func_patterns = [
            re.compile(r"^(?:(?:static|inline|extern|const)\s+)*"
                        r"(?:[\w\*\s&]+)\s+(\w+)\s*\([^)]*\)\s*\{",
                        re.MULTILINE),  # C/C++/Java style
            re.compile(r"^(?:async\s+)?def\s+(\w+)\s*\(",
                        re.MULTILINE),  # Python style
            re.compile(r"^function\s+(\w+)\s*\(",
                        re.MULTILINE),  # JavaScript/shell style
        ]

        func_starts: list[tuple[int, str]] = []
        for pat in func_patterns:
            for m in pat.finditer(source):
                func_starts.append((m.start(), m.group(1)))
        func_starts.sort()

        results: list[FunctionCalls] = []

        for i, (start, func_name) in enumerate(func_starts):
            end = func_starts[i + 1][0] if i + 1 < len(func_starts) else len(source)
            body = source[start:end]

            # Find all calls in this function's body
            raw_calls = set()
            for m in self._CALL_PAT.finditer(body):
                name = m.group(1)
                if name not in self._SKIP and name != func_name:
                    raw_calls.add(name)

            if raw_calls:
                results.append(FunctionCalls(
                    function_name=func_name,
                    calls=sorted(raw_calls),
                    is_complete=False,
                ))

        return results


# ──────────────────────────────────────────────────────────────────────────────
# Main dispatcher
# ──────────────────────────────────────────────────────────────────────────────


class FunctionAnalyzer:
    """
    Unified interface for function call extraction.

    Strategy (in priority order):
      Python (.py)   → PythonAstAnalyzer  (ast, always available)
      C/C++/Java     → ClangAstAnalyzer  (libclang, if installed)
                       → RegexAnalyzer   (fallback)
      Other          → RegexAnalyzer
    """

    _PYTHON_EXTS = {".py"}
    _CLANG_EXTS  = {".c", ".h", ".cpp", ".hpp", ".cc", ".cxx", ".java", ".js", ".ts"}

    def __init__(self):
        self._py_analyzer   = PythonAstAnalyzer()
        self._clang_analyzer = ClangAstAnalyzer()
        self._regex_analyzer = RegexAnalyzer()

    def analyze(self, source: str, filename: str) -> list[FunctionCalls]:
        ext = "." + filename.rsplit(".", 1)[-1].lower()

        if ext in self._PYTHON_EXTS:
            return self._py_analyzer.analyze(source)

        if ext in self._CLANG_EXTS:
            if self._clang_analyzer.is_available():
                results = self._clang_analyzer.analyze(source, filename)
                if results:
                    return results
                logger.debug("Clang failed for %s, falling back to regex", filename)
            return self._regex_analyzer.analyze(source)

        return self._regex_analyzer.analyze(source)

    def extract_calls_for_function(
        self, source: str, filename: str, function_name: str
    ) -> list[str]:
        """
        Extract calls made within a specific named function.
        Returns an empty list if the function is not found.
        """
        all_funcs = self.analyze(source, filename)
        for fc in all_funcs:
            if fc.function_name == function_name:
                return fc.calls
        return []
