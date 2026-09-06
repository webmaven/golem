"""
Compiler diagnostics and human-readable error formatting for Golem.

Provides structured Diagnostic objects with file, line, and column coordinates,
source snippet context windows, and visual caret indicators modeled after
modern compiler diagnostics.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

try:
    from asciidoctrine.exceptions import AsciiDocSyntaxError  # type: ignore[import-not-found,import-untyped]
except ImportError:
    try:
        from asciidoctrine import AsciiDocSyntaxError  # type: ignore[assignment]
    except ImportError:
        AsciiDocSyntaxError = None  # type: ignore[assignment,misc]


def format_diagnostic(error: Diagnostic | Exception, content_dir: Path | str | None = None) -> str:
    """Format clean AsciiDoc compiler diagnostics with source coordinates and context snippets.

    === Examples

    [source,python]
    ----
    >>> from golem.diagnostics import Diagnostic
    >>> err = Diagnostic(file="docs/02-architecture.adoc", line=14, column=5, message="Unclosed attribute list")
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
        exc = error.exception
        message = error.message or (getattr(exc, "message", str(exc)) if exc else "")
        file_path_raw = error.file or (
            getattr(exc, "filepath", None)
            if (getattr(exc, "filepath", None) and getattr(exc, "filepath", None) != "<root>")
            else (getattr(exc, "filename", getattr(exc, "file", None)) if exc else None)
        )
        line = error.line if error.line is not None else (getattr(exc, "lineno", getattr(exc, "line", None)) if exc else None)
        column = (
            error.column
            if error.column is not None
            else (getattr(exc, "offset", getattr(exc, "column", getattr(exc, "col_offset", None))) if exc else None)
        )
        severity = error.severity or "error"
        context_str = error.context or (getattr(exc, "context", None) if exc else None)

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


@dataclass(repr=False)
class Diagnostic:
    """Compiler diagnostic entry representing an error or warning."""

    file: str = ""
    line: int | None = None
    column: int | None = None
    message: str = ""
    severity: str = "error"
    error_type: str | None = None
    context: str | None = None
    exception: Exception | None = None

    def __post_init__(self) -> None:
        if self.file:
            self.file = str(self.file)
        else:
            self.file = ""
        if not self.severity:
            self.severity = "error"

    @classmethod
    def from_exception(
        cls,
        exc: Exception,
        file: str | Path | None = None,
        severity: str = "error",
    ) -> Diagnostic:
        """Construct a Diagnostic from an upstream syntax error or generic compilation exception."""
        exc_file = getattr(exc, "filepath", None)
        if exc_file == "<root>" or not exc_file:
            exc_file = getattr(exc, "filename", getattr(exc, "file", None))

        target_file = str(exc_file or file or "")
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
        warning: Any,
        file: str | Path | None = None,
        content: str | None = None,
    ) -> Diagnostic:
        """Construct a Diagnostic from an ASGResolver warning dictionary or object."""

        def _get_val(obj: Any, key: str, default: Any = None) -> Any:
            if hasattr(obj, "get") and callable(getattr(obj, "get", None)):
                try:
                    val = obj.get(key)
                    if val is not None:
                        return val
                except Exception:
                    pass
            return getattr(obj, key, default)

        line = _get_val(warning, "line")
        column = _get_val(warning, "column")
        target = _get_val(warning, "target")
        if (line is None or column is None) and content and target:
            for idx, line_str in enumerate(content.splitlines(), start=1):
                if target in line_str:
                    line = idx
                    col_idx = line_str.find(target)
                    column = col_idx + 1 if col_idx != -1 else 1
                    break

        warn_file = _get_val(warning, "file", "")
        target_file = str(file or warn_file or "")

        return cls(
            file=target_file,
            line=line,
            column=column,
            message=str(_get_val(warning, "message", "Resolver warning")),
            severity="warning",
            error_type=str(_get_val(warning, "type", "ResolverWarning")),
            context=_get_val(warning, "context"),
        )

    def __str__(self) -> str:
        return format_diagnostic(self)

    def __repr__(self) -> str:
        return (
            f"Diagnostic(file={self.file!r}, line={self.line!r}, column={self.column!r}, "
            f"severity={self.severity!r}, message={self.message!r})"
        )
