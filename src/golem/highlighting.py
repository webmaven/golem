"""Provide server-side syntax highlighting and Fired Clay Pygments themes for Golem.

== Pygments Integration

Golem utilizes Pygments (`pygments>=2.18`) for rich, server-side syntax highlighting
of source code listings without requiring client-side JavaScript execution.

Custom styles aligning with Golem's Fired Clay / Workbench visual palette:
- `FiredClayStyle` (light mode): Warm terracotta, sage green, umber, and moss tokens.
- `FiredClayDarkStyle` (dark mode): Radiant ember, muted sage, ochre, and warm slate tokens.
"""

from __future__ import annotations

from collections.abc import Callable
import pygments  # type: ignore[import-untyped]
from pygments.formatters.html import HtmlFormatter  # type: ignore[import-untyped]
from pygments.lexers import get_lexer_by_name  # type: ignore[import-untyped]
from pygments.style import Style  # type: ignore[import-untyped]
from pygments.token import (  # type: ignore[import-untyped]
    Comment,
    Error,
    Generic,
    Keyword,
    Literal,
    Name,
    Number,
    Operator,
    Punctuation,
    String,
    Text,
)
from pygments.util import ClassNotFound  # type: ignore[import-untyped]


class FiredClayStyle(Style):
    """Light mode syntax highlighting style for Golem (Fired Clay palette)."""

    name = "firedclay"
    background_color = "#faf9f5"
    highlight_color = "#ede8df"

    styles = {
        Text: "#1e1a16",
        Comment: "italic #9a7a68",
        Comment.Preproc: "noitalic #9a7a68",
        Comment.Single: "italic #9a7a68",
        Comment.Multiline: "italic #9a7a68",
        Comment.Special: "bold italic #9a7a68",
        Keyword: "bold #6b2a08",
        Keyword.Constant: "bold #6b2a08",
        Keyword.Declaration: "bold #6b2a08",
        Keyword.Namespace: "bold #6b2a08",
        Keyword.Pseudo: "nobold #6b2a08",
        Keyword.Reserved: "bold #6b2a08",
        Keyword.Type: "nobold #6b2a08",
        Operator: "#6b2a08",
        Operator.Word: "bold #6b2a08",
        Punctuation: "#1e1a16",
        Name: "#1e1a16",
        Name.Builtin: "bold #3e2518",
        Name.Builtin.Pseudo: "bold #3e2518",
        Name.Function: "bold #8b3a12",
        Name.Class: "bold #8b3a12",
        Name.Namespace: "bold #8b3a12",
        Name.Exception: "bold #8b3a12",
        Name.Decorator: "#8b3a12",
        Name.Variable: "#1e1a16",
        Name.Constant: "bold #6b2a08",
        Name.Tag: "bold #6b2a08",
        Name.Attribute: "#8b3a12",
        String: "#2d6a5a",
        String.Doc: "italic #2d6a5a",
        String.Interpol: "#2d6a5a",
        String.Escape: "bold #2d6a5a",
        String.Regex: "#2d6a5a",
        String.Symbol: "#2d6a5a",
        Number: "#6e7818",
        Literal: "#6e7818",
        Literal.Number: "#6e7818",
        Generic.Heading: "bold #8b3a12",
        Generic.Subheading: "bold #8b3a12",
        Generic.Deleted: "#a31818 bg:#ffdddd",
        Generic.Inserted: "#2d6a5a bg:#ddffdd",
        Generic.Error: "#a31818",
        Generic.Emph: "italic",
        Generic.Strong: "bold",
        Generic.Prompt: "bold #9a7a68",
        Generic.Output: "#6b5d52",
        Error: "#a31818 bg:#ffdddd",
    }


class FiredClayDarkStyle(Style):
    """Dark mode syntax highlighting style for Golem (Fired Clay palette)."""

    name = "firedclay-dark"
    background_color = "#170f0b"
    highlight_color = "#2a1e17"

    styles = {
        Text: "#f0e4d8",
        Comment: "italic #7a5a48",
        Comment.Preproc: "noitalic #7a5a48",
        Comment.Single: "italic #7a5a48",
        Comment.Multiline: "italic #7a5a48",
        Comment.Special: "bold italic #7a5a48",
        Keyword: "bold #e07a3a",
        Keyword.Constant: "bold #e07a3a",
        Keyword.Declaration: "bold #e07a3a",
        Keyword.Namespace: "bold #e07a3a",
        Keyword.Pseudo: "nobold #e07a3a",
        Keyword.Reserved: "bold #e07a3a",
        Keyword.Type: "nobold #e07a3a",
        Operator: "#e07a3a",
        Operator.Word: "bold #e07a3a",
        Punctuation: "#f0e4d8",
        Name: "#f0e4d8",
        Name.Builtin: "bold #c8a882",
        Name.Builtin.Pseudo: "bold #c8a882",
        Name.Function: "bold #d4692a",
        Name.Class: "bold #d4692a",
        Name.Namespace: "bold #d4692a",
        Name.Exception: "bold #d4692a",
        Name.Decorator: "#d4692a",
        Name.Variable: "#f0e4d8",
        Name.Constant: "bold #e07a3a",
        Name.Tag: "bold #e07a3a",
        Name.Attribute: "#d4692a",
        String: "#4a9a8a",
        String.Doc: "italic #4a9a8a",
        String.Interpol: "#4a9a8a",
        String.Escape: "bold #4a9a8a",
        String.Regex: "#4a9a8a",
        String.Symbol: "#4a9a8a",
        Number: "#7aaa3a",
        Literal: "#7aaa3a",
        Literal.Number: "#7aaa3a",
        Generic.Heading: "bold #d4692a",
        Generic.Subheading: "bold #d4692a",
        Generic.Deleted: "#c04040 bg:#401010",
        Generic.Inserted: "#4a9a8a bg:#103020",
        Generic.Error: "#c04040",
        Generic.Emph: "italic",
        Generic.Strong: "bold",
        Generic.Prompt: "bold #7a5a48",
        Generic.Output: "#9a7a68",
        Error: "#c04040 bg:#401010",
    }


LANGUAGE_ALIASES: dict[str, str] = {
    "py": "python",
    "python3": "python",
    "js": "javascript",
    "ts": "typescript",
    "sh": "bash",
    "shell": "bash",
    "zsh": "bash",
    "bash": "bash",
    "adoc": "asciidoc",
    "asciidoc": "asciidoc",
    "yml": "yaml",
    "yaml": "yaml",
    "toml": "toml",
    "html": "html",
    "htm": "html",
    "xml": "xml",
    "css": "css",
    "json": "json",
    "rust": "rust",
    "rs": "rust",
    "go": "go",
    "golang": "go",
    "c": "c",
    "cpp": "cpp",
    "c++": "cpp",
    "java": "java",
    "ruby": "ruby",
    "rb": "ruby",
    "sql": "sql",
    "dockerfile": "dockerfile",
    "docker": "dockerfile",
    "diff": "diff",
    "text": "text",
    "txt": "text",
    "plain": "text",
}


def make_highlighter(
    style: str | type[Style] | Style = FiredClayStyle,
) -> Callable[[str, str], str | None]:
    """Create a syntax highlighter callable compatible with asciidoctype's AsciiDoctypeRenderer.

    [parameters]
    `style` (str | type[Style] | Style, optional):: Pygments style class or name to format tokens. Defaults to `FiredClayStyle`.

    [returns]
    `Callable[[str, str], str | None]`:: A highlighter function accepting `(code, lang)` that returns
    highlighted HTML markup or `None` if the language is unknown or unsupported.
    """
    formatter = HtmlFormatter(nowrap=True, style=style)

    def highlighter(code: str, lang: str) -> str | None:
        if not code:
            return None
        raw_lang = (lang or "").strip().lower()
        if not raw_lang:
            return None

        lookup_lang = LANGUAGE_ALIASES.get(raw_lang, raw_lang)
        try:
            lexer = get_lexer_by_name(lookup_lang, stripall=False)
        except ClassNotFound:
            if lookup_lang != raw_lang:
                try:
                    lexer = get_lexer_by_name(raw_lang, stripall=False)
                except (ClassNotFound, Exception):
                    return None
            else:
                return None
        except Exception:
            return None

        try:
            tokens_html = pygments.highlight(code, lexer, formatter).rstrip("\n")
            return f'<pre class="highlight {raw_lang}"><code class="language-{raw_lang}">{tokens_html}</code></pre>'
        except Exception:
            return None

    return highlighter


def get_pygments_css(
    style: str | type[Style] | Style = FiredClayStyle,
    dark_style: str | type[Style] | Style = FiredClayDarkStyle,
    selector: str = ".highlight",
) -> str:
    """Generate combined Pygments CSS rules for light mode with dark mode media query overrides.

    [parameters]
    `style` (str | type[Style] | Style, optional):: Light mode Pygments style. Defaults to `FiredClayStyle`.
    `dark_style` (str | type[Style] | Style, optional):: Dark mode Pygments style. Defaults to `FiredClayDarkStyle`.
    `selector` (str, optional):: CSS selector prefix for generated rules. Defaults to `".highlight"`.

    [returns]
    `str`:: Combined CSS string ready for inline injection into HTML templates.
    """
    light_formatter = HtmlFormatter(style=style)
    dark_formatter = HtmlFormatter(style=dark_style)

    light_css = light_formatter.get_style_defs(selector)
    dark_css = dark_formatter.get_style_defs(selector)

    dark_rules = "\n".join(f"    {line}" if line.strip() else "" for line in dark_css.splitlines())

    return (
        f"/* Pygments Syntax Highlighting (Light) */\n"
        f"{light_css}\n\n"
        f"/* Pygments Syntax Highlighting (Dark) */\n"
        f"@media (prefers-color-scheme: dark) {{\n"
        f"{dark_rules}\n"
        f"}}"
    )


PYGMENTS_CSS: str = get_pygments_css()
