"""
Compiler diagnostics and human-readable error formatting for Golem.

Provides structured Diagnostic objects with file, line, and column coordinates,
source snippet context windows, and visual caret indicators modeled after
modern compiler diagnostics.
"""

from __future__ import annotations

import re
import sys
import types
from pathlib import Path
from typing import Any

# Ensure asciidoctrine.exceptions can be imported even if not exposed directly upstream
try:
    from asciidoctrine.exceptions import AsciiDocSyntaxError  # type: ignore[import-not-found,import-untyped]
except ImportError:
    try:
        from asciidoctrine import AsciiDocSyntaxError  # type: ignore[assignment]
    except ImportError:
        try:
            from asciidoctrine.lark_parser import AsciiDocSyntaxError  # type: ignore[assignment]
        except ImportError:
            AsciiDocSyntaxError = None  # type: ignore[assignment,misc]

if "asciidoctrine.exceptions" not in sys.modules and AsciiDocSyntaxError is not None:
    mod = types.ModuleType("asciidoctrine.exceptions")
    mod.AsciiDocSyntaxError = AsciiDocSyntaxError  # type: ignore[attr-defined]
    sys.modules["asciidoctrine.exceptions"] = mod


def format_diagnostic(error: dict[str, Any] | Exception, content_dir: Path | str | None = None) -> str:
    """Format clean AsciiDoc compiler diagnostics with source coordinates and context snippets.

    === Examples

    [source,python]
    ----
    >>> err = {"file": "docs/02-architecture.adoc", "line": 14, "column": 5, "message": "Unclosed attribute list"}
    >>> "Error in docs/02-architecture.adoc:14:5" in format_diagnostic(err)
    True

    ----
    """
    if isinstance(error, Exception):
        exc: Any = error
        message = getattr(exc, "message", str(exc))
        file_path_raw = getattr(exc, "filepath", None)
        if file_path_raw == "<root>" or not file_path_raw:
            file_path_raw = getattr(exc, "filename", getattr(exc, "file", None))
        line = getattr(exc, "lineno", getattr(exc, "line", None))
        column = getattr(exc, "offset", getattr(exc, "column", getattr(exc, "col_offset", None)))
        severity = getattr(exc, "severity", "error")
        context_str = getattr(exc, "context", None)
    else:
        exc = error.get("exception")
        message = str(error.get("message", ""))
        file_path_raw = error.get("file") or (
            getattr(exc, "filepath", None)
            if (getattr(exc, "filepath", None) and getattr(exc, "filepath", None) != "<root>")
            else (getattr(exc, "filename", getattr(exc, "file", None)) if exc else None)
        )
        line = error.get("line") or (getattr(exc, "lineno", getattr(exc, "line", None)) if exc else None)
        column = (
            error.get("column")
            or error.get("col")
            or (
                getattr(
                    exc,
                    "offset",
                    getattr(exc, "column", getattr(exc, "col_offset", None)),
                )
                if exc
                else None
            )
        )
        severity = error.get("severity", "error")
        context_str = error.get("context") or (getattr(exc, "context", None) if exc else None)

    # If line / column not found, parse coordinates from message if present
    if (line is None or column is None) and message:
        m_coord = re.search(r"(?:line\s*|:)(\d+)(?:,\s*col(?:umn)?\s*|:)(\d+)", message, re.IGNORECASE)
        if m_coord:
            if line is None:
                line = int(m_coord.group(1))
            if column is None:
                column = int(m_coord.group(2))
        else:
            m_line = re.search(r"(?:line\s*|:)(\d+)", message, re.IGNORECASE)
            if m_line and line is None:
                line = int(m_line.group(1))

    file_display = str(file_path_raw) if file_path_raw else "unknown"
    if file_path_raw:
        try:
            p = Path(file_path_raw)
            if p.is_absolute():
                try:
                    file_display = str(p.relative_to(Path.cwd()))
                except ValueError:
                    file_display = str(p)
            else:
                file_display = str(p)
        except Exception:
            file_display = str(file_path_raw)

    prefix = (severity or "error").capitalize()

    if line is not None and line > 0:
        if column is not None and column > 0:
            header = f"{prefix} in {file_display}:{line}:{column}"
        else:
            header = f"{prefix} in {file_display}:{line}"
    else:
        header = f"{prefix} in {file_display}: {message}"

    lines: list[str] = []
    if file_path_raw:
        target_path = Path(file_path_raw)
        if not target_path.exists() and content_dir:
            alt_path = Path(content_dir) / target_path
            if alt_path.exists():
                target_path = alt_path

        if target_path.exists() and target_path.is_file():
            try:
                with open(target_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.read().splitlines()
            except Exception:
                lines = []

    if lines and line is not None and 1 <= line <= len(lines):
        start_line = max(1, line - 2)
        end_line = line
        margin_width = len(str(end_line))

        out_lines = [header]
        for ln in range(start_line, end_line + 1):
            line_text = lines[ln - 1]
            ln_str = str(ln).rjust(margin_width)
            if line_text:
                out_lines.append(f"{ln_str} | {line_text}")
            else:
                out_lines.append(f"{ln_str} |")

        col = column if (column is not None and column > 0) else 1
        col_idx = max(0, col - 1)
        pointer_margin = " " * margin_width
        out_lines.append(f"{pointer_margin} | {' ' * col_idx}^-- {message}")
        return "\n".join(out_lines)

    if context_str:
        return f"{header}\n{context_str}\n  ^-- {message}"

    if line is not None and line > 0:
        return f"{header}\n  ^-- {message}"
    return header


class Diagnostic(dict[str, Any]):
    """Compiler diagnostic entry representing an error or warning.

    Maintains full dict compatibility while providing structured attribute access
    and compiler-grade string formatting.
    """

    def __init__(
        self,
        *args: Any,
        file: str | Path | None = None,
        line: int | None = None,
        column: int | None = None,
        message: str = "",
        severity: str = "error",
        error_type: str | None = None,
        context: str | None = None,
        exception: Exception | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        if file is not None:
            self["file"] = str(file)
        elif "file" not in self:
            self["file"] = ""
        if line is not None:
            self["line"] = line
        elif "line" not in self:
            self["line"] = None
        if column is not None:
            self["column"] = column
        elif "column" not in self:
            self["column"] = None
        if message:
            self["message"] = message
        elif "message" not in self:
            self["message"] = ""
        if severity:
            self["severity"] = severity
        elif "severity" not in self:
            self["severity"] = "error"
        if error_type is not None:
            self["error_type"] = error_type
        elif "error_type" not in self:
            self["error_type"] = None
        if context is not None:
            self["context"] = context
        elif "context" not in self:
            self["context"] = None
        if exception is not None:
            self["exception"] = exception
        elif "exception" not in self:
            self["exception"] = None

    @property
    def file(self) -> str:
        return self.get("file", "")

    @file.setter
    def file(self, val: str | Path | None) -> None:
        self["file"] = str(val) if val is not None else ""

    @property
    def line(self) -> int | None:
        return self.get("line")

    @line.setter
    def line(self, val: int | None) -> None:
        self["line"] = val

    @property
    def column(self) -> int | None:
        return self.get("column")

    @column.setter
    def column(self, val: int | None) -> None:
        self["column"] = val

    @property
    def message(self) -> str:
        return self.get("message", "")

    @message.setter
    def message(self, val: str) -> None:
        self["message"] = val

    @property
    def severity(self) -> str:
        return self.get("severity", "error")

    @severity.setter
    def severity(self, val: str) -> None:
        self["severity"] = val

    @property
    def error_type(self) -> str | None:
        return self.get("error_type")

    @error_type.setter
    def error_type(self, val: str | None) -> None:
        self["error_type"] = val

    @property
    def context(self) -> str | None:
        return self.get("context")

    @context.setter
    def context(self, val: str | None) -> None:
        self["context"] = val

    @property
    def exception(self) -> Exception | None:
        return self.get("exception")

    @exception.setter
    def exception(self, val: Exception | None) -> None:
        self["exception"] = val

    @classmethod
    def from_exception(
        cls,
        exc: Exception,
        file: str | Path | None = None,
        severity: str = "error",
    ) -> "Diagnostic":
        """Construct a Diagnostic from an upstream syntax error or generic compilation exception."""
        exc_file = getattr(exc, "filepath", None)
        if exc_file == "<root>" or not exc_file:
            exc_file = getattr(exc, "filename", getattr(exc, "file", None))

        target_file = exc_file or file or ""
        msg = getattr(exc, "message", str(exc))
        line = getattr(exc, "line", getattr(exc, "lineno", None))
        column = getattr(
            exc,
            "column",
            getattr(exc, "offset", getattr(exc, "col_offset", None)),
        )
        context = getattr(exc, "context", None)

        if (line is None or column is None) and msg:
            m_coord = re.search(r"(?:line\s*|:)(\d+)(?:,\s*col(?:umn)?\s*|:)(\d+)", str(exc), re.IGNORECASE)
            if m_coord:
                if line is None:
                    line = int(m_coord.group(1))
                if column is None:
                    column = int(m_coord.group(2))
            else:
                m_line = re.search(r"(?:line\s*|:)(\d+)", str(exc), re.IGNORECASE)
                if m_line and line is None:
                    line = int(m_line.group(1))

        return cls(
            file=target_file,
            line=line,
            column=column,
            message=str(msg),
            severity=severity,
            error_type=type(exc).__name__,
            context=context,
            exception=exc,
        )

    @classmethod
    def from_resolver_warning(
        cls,
        warning: dict[str, Any],
        file: str | Path | None = None,
        content: str | None = None,
    ) -> "Diagnostic":
        """Construct a Diagnostic from an ASGResolver warning dictionary."""
        line = warning.get("line")
        column = warning.get("column")
        target = warning.get("target")
        if (line is None or column is None) and content and target:
            for idx, line_str in enumerate(content.splitlines(), start=1):
                if target in line_str:
                    line = idx
                    col_idx = line_str.find(target)
                    column = col_idx + 1 if col_idx != -1 else 1
                    break

        return cls(
            file=file or warning.get("file", ""),
            line=line,
            column=column,
            message=warning.get("message", "Resolver warning"),
            severity="warning",
            error_type=warning.get("type", "ResolverWarning"),
            context=warning.get("context"),
        )

    def __str__(self) -> str:
        return format_diagnostic(self)

    def __repr__(self) -> str:
        return (
            f"Diagnostic(file={self.file!r}, line={self.line!r}, column={self.column!r}, "
            f"severity={self.severity!r}, message={self.message!r})"
        )
