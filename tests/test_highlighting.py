"""Tests for golem.highlighting module."""

from golem.highlighting import (
    FiredClayStyle,
    FiredClayDarkStyle,
    make_highlighter,
    get_pygments_css,
    PYGMENTS_CSS,
)


def test_fired_clay_styles():
    """Verify FiredClayStyle and FiredClayDarkStyle are valid Pygments styles with expected colors."""
    assert FiredClayStyle is not None
    assert FiredClayDarkStyle is not None

    # Verify light style properties
    light_css = get_pygments_css(style=FiredClayStyle).lower()
    assert "#6b2a08" in light_css  # Keyword / Operator
    assert "#2d6a5a" in light_css  # String
    assert "#9a7a68" in light_css  # Comment
    assert "#6e7818" in light_css  # Number
    assert "#3e2518" in light_css  # Name.Builtin
    assert "#8b3a12" in light_css  # Name.Function / Class

    # Verify dark style in media query
    assert "@media (prefers-color-scheme: dark)" in light_css
    assert "#e07a3a" in light_css  # Keyword / Operator
    assert "#4a9a8a" in light_css  # String
    assert "#7a5a48" in light_css  # Comment
    assert "#7aaa3a" in light_css  # Number
    assert "#c8a882" in light_css  # Name.Builtin
    assert "#d4692a" in light_css  # Name.Function / Class


def test_make_highlighter_python():
    """Verify make_highlighter highlights Python code into tokenized spans."""
    highlighter = make_highlighter()
    code = 'def greet(name: str) -> str:\n    return f"Hello, {name}!"\n'
    result = highlighter(code, "python")
    assert result is not None
    assert '<pre class="highlight python"><code class="language-python">' in result
    assert "</code></pre>" in result
    assert 'class="k"' in result or 'class="kn"' in result or 'class="nf"' in result
    assert "greet" in result


def test_make_highlighter_aliases():
    """Verify language aliases work properly."""
    highlighter = make_highlighter()

    # 'py' alias for python
    py_result = highlighter('x = 42\nprint("hi")', "py")
    assert py_result is not None
    assert '<pre class="highlight py"><code class="language-py">' in py_result
    assert 'class="mi"' in py_result or 'class="m"' in py_result or 'class="nb"' in py_result

    # 'sh' / 'bash'
    sh_result = highlighter('echo "test"', "sh")
    assert sh_result is not None
    assert '<pre class="highlight sh"><code class="language-sh">' in sh_result

    # 'toml'
    toml_result = highlighter('[project]\nname = "golem"', "toml")
    assert toml_result is not None
    assert '<pre class="highlight toml"><code class="language-toml">' in toml_result


def test_make_highlighter_unknown_language():
    """Verify make_highlighter returns None for unknown languages without raising."""
    highlighter = make_highlighter()
    result = highlighter("some text", "nonexistent_unknown_lang_xyz")
    assert result is None


def test_make_highlighter_empty_inputs():
    """Verify make_highlighter returns None for empty code or language."""
    highlighter = make_highlighter()
    assert highlighter("", "python") is None
    assert highlighter("print(1)", "") is None


def test_get_pygments_css():
    """Verify get_pygments_css generates complete CSS with light and dark mode rules."""
    css = get_pygments_css()
    assert ".highlight" in css
    assert "@media (prefers-color-scheme: dark)" in css
    assert "/* Pygments Syntax Highlighting (Light) */" in css
    assert "/* Pygments Syntax Highlighting (Dark) */" in css


def test_pygments_css_constant():
    """Verify PYGMENTS_CSS constant is populated and matches get_pygments_css()."""
    assert isinstance(PYGMENTS_CSS, str)
    assert len(PYGMENTS_CSS) > 100
    assert ".highlight" in PYGMENTS_CSS


def test_make_highlighter_alias_fallback(monkeypatch):
    """Test alias fallback when aliased lexer name fails."""
    import golem.highlighting

    monkeypatch.setitem(golem.highlighting.LANGUAGE_ALIASES, "alias_fails", "nonexistent_lexer_xyz")
    highlighter = make_highlighter()
    # lookup_lang != raw_lang and raw_lang is also nonexistent
    assert highlighter("code", "alias_fails") is None


def test_make_highlighter_highlight_exception(monkeypatch):
    """Test graceful handling when pygments.highlight or get_lexer_by_name raises unexpected Exception."""
    import pygments  # type: ignore[import-untyped]

    highlighter = make_highlighter()

    def fake_highlight(*args, **kwargs):
        raise RuntimeError("Pygments internal error")

    monkeypatch.setattr(pygments, "highlight", fake_highlight)
    assert highlighter("x = 1", "python") is None
