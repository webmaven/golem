"""Provide AsciiDoc document metadata parsing, title extraction, and URL normalization.

== Document Header Metadata Extraction

Golem inspects leading header sections of AsciiDoc source files to extract metadata
attributes before complete AST/ASG compilation:
- Title (`= ...` or `:title:`)
- Navigation title (`:nav_title:`, `:navtitle:`)
- Navigation sort order (`:nav_order:`, `:nav-order:`, `:navorder:`)
- Table of contents directives (`:toc:`, `:!toc:`, `:toc!:`, etc.)
- Layout CSS classes (`:page_class:`, `:body_class:`, `:content_class:`)

== URL and Filename Normalization

Utility functions provide consistent URL path resolution for index files and automatic
derivation of human-readable display titles from filenames and directory names.
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

__all__ = [
    "clean_index_url",
    "dir_has_adoc_content",
    "extract_metadata_from_doc",
    "extract_title_from_doc",
    "title_from_filename",
]


def title_from_filename(name: str) -> str:
    """Derive a human-readable display title from a filename or directory name.

    Strips numeric sorting prefixes (such as `01-`, `10_`), removes file extensions,
    replaces hyphens and underscores with whitespace, and applies title capitalization.

    [parameters]
    `name` (str):: Filename or directory path segment to parse.

    [returns]
    `str`:: Cleaned, capitalized display title.

    === Examples

    [source,python]
    ----
    >>> from golem.metadata import title_from_filename
    >>> title_from_filename("01-getting-started.adoc")
    'Getting Started'
    >>> title_from_filename("api_reference")
    'Api Reference'
    ----
    """
    stem = Path(name).stem if "." in name else name
    cleaned = re.sub(r"^\d+[-_.]\s*", "", stem)
    if not cleaned:
        cleaned = stem
    cleaned = cleaned.replace("-", " ").replace("_", " ")
    return " ".join(word.capitalize() for word in cleaned.split())


def clean_index_url(url: str) -> str:
    """Normalize index.html URLs to clean directory paths.

    Converts URLs ending in `/index.html` to the parent directory form (ending with `/`)
    and maps `index.html` to `./`. This ensures generated navigation and pagination links
    use the same canonical URL form as hand-authored AsciiDoc `link:` macros, preventing
    search crawlers from treating them as distinct resources.

    [parameters]
    `url` (str):: Relative or absolute URL string to normalize.

    [returns]
    `str`:: Normalized clean URL path string.

    === Examples

    [source,python]
    ----
    >>> from golem.metadata import clean_index_url
    >>> clean_index_url("docs/guide/index.html")
    'docs/guide/'
    >>> clean_index_url("index.html")
    './'
    >>> clean_index_url("docs/guide/about.html")
    'docs/guide/about.html'
    ----
    """
    if url == "index.html":
        return "./"
    if url.endswith("/index.html"):
        return url[: -len("index.html")]
    return url


def extract_metadata_from_doc(path: Path) -> dict[str, Any]:
    """Extract document metadata attributes from an AsciiDoc file header.

    Reads the leading header section of an AsciiDoc file up to the first section break
    or block delimiter. Parses document title (`= ...`), `:nav_title:`, `:nav_order:`,
    `:body_class:`, `:page_class:`, `:content_class:`, and `:toc:` attributes.
    Falls back to filename-derived titles if no header title is present.

    [parameters]
    `path` (Path):: Path to the target `.adoc` file on disk.

    [returns]
    `dict[str, Any]`:: Dictionary containing `"title"`, `"nav_title"`, `"nav_order"`, `"has_toc"`, `"page_class"`, `"body_class"`, and `"content_class"` keys.

    === Examples

    [source,python]
    ----
    >>> from pathlib import Path
    >>> import tempfile
    >>> from golem.metadata import extract_metadata_from_doc
    >>> with tempfile.NamedTemporaryFile("w", suffix=".adoc", delete=False) as f:
    ...     _ = f.write("= Hello World\\n:nav_title: Custom Nav\\n:toc:\\n")
    ...     f_path = Path(f.name)
    >>> meta = extract_metadata_from_doc(f_path)
    >>> meta["title"]
    'Hello World'
    >>> meta["nav_title"]
    'Custom Nav'
    >>> meta["has_toc"]
    True
    >>> f_path.unlink()
    ----
    """
    title = None
    nav_title = None
    nav_order: int | None = None
    has_toc = False
    page_class: str | None = None
    body_class: str | None = None
    content_class: str | None = None
    page_role: str | None = None
    if path.exists() and path.is_file():
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line_s = line.strip()
                    if (
                        line_s.startswith("==")
                        or line_s.startswith("----")
                        or line_s.startswith("....")
                        or line_s.startswith("++++")
                        or line_s.startswith("****")
                    ):
                        break
                    if line_s.startswith("= ") and not line_s.startswith("== ") and title is None:
                        t = line_s[2:].strip()
                        if t:
                            title = t
                    elif (line_s.startswith(":nav_title:") or line_s.startswith(":navtitle:")) and nav_title is None:
                        val = line_s.split(":", 2)[2].strip()
                        if val:
                            nav_title = val
                    elif (
                        line_s.startswith(":nav_order:") or line_s.startswith(":nav-order:") or line_s.startswith(":navorder:")
                    ) and nav_order is None:
                        val = line_s.split(":", 2)[2].strip()
                        try:
                            nav_order = int(val)
                        except ValueError:
                            pass
                    elif (
                        line_s.startswith(":page_class:")
                        or line_s.startswith(":page-class:")
                        or line_s.startswith(":pageclass:")
                    ) and page_class is None:
                        val = line_s.split(":", 2)[2].strip()
                        if val:
                            page_class = val
                    elif (
                        line_s.startswith(":body_class:")
                        or line_s.startswith(":body-class:")
                        or line_s.startswith(":bodyclass:")
                    ) and body_class is None:
                        val = line_s.split(":", 2)[2].strip()
                        if val:
                            body_class = val
                    elif (
                        line_s.startswith(":content_class:")
                        or line_s.startswith(":content-class:")
                        or line_s.startswith(":contentclass:")
                    ) and content_class is None:
                        val = line_s.split(":", 2)[2].strip()
                        if val:
                            content_class = val
                    elif (
                        line_s.startswith(":page_role:") or line_s.startswith(":page-role:") or line_s.startswith(":role:")
                    ) and page_role is None:
                        val = line_s.split(":", 2)[2].strip()
                        if val:
                            page_role = val.lower()
                    elif line_s.startswith(":title:") and title is None:
                        val = line_s.split(":", 2)[2].strip()
                        if val:
                            title = val
                    elif line_s == ":toc:" or line_s.startswith(":toc:") or line_s.startswith(":toc: "):
                        if line_s in (":!toc:", ":toc!:", ":toc: none", ":toc: false"):
                            has_toc = False
                        else:
                            has_toc = True
                    elif line_s in (":!toc:", ":toc!:"):
                        has_toc = False
        except Exception:
            pass
    if not title:
        title = title_from_filename(path.name)
    if not nav_title:
        nav_title = title
    resolved_body_class = (body_class or page_class or "").strip()
    resolved_page_class = (page_class or body_class or "").strip()
    resolved_content_class = (content_class or "").strip()
    return {
        "title": title,
        "nav_title": nav_title,
        "nav_order": nav_order,
        "has_toc": has_toc,
        "page_class": resolved_page_class,
        "body_class": resolved_body_class,
        "content_class": resolved_content_class,
        "page_role": page_role,
    }


def extract_title_from_doc(path: Path) -> str:
    """Extract the top-level document title from an AsciiDoc file.

    Retrieves the document title by inspecting the file header via `extract_metadata_from_doc()`,
    falling back to a formatted title derived from the filename.

    [parameters]
    `path` (Path):: Path to the target `.adoc` file.

    [returns]
    `str`:: Extracted or derived document title.

    === Examples

    [source,python]
    ----
    >>> from pathlib import Path
    >>> import tempfile
    >>> from golem.metadata import extract_title_from_doc
    >>> with tempfile.NamedTemporaryFile("w", suffix=".adoc", delete=False) as f:
    ...     _ = f.write("= My Document Title\\n\\nSome body content.")
    ...     f_path = Path(f.name)
    >>> extract_title_from_doc(f_path)
    'My Document Title'
    >>> f_path.unlink()
    ----
    """
    return str(extract_metadata_from_doc(path)["title"])


def dir_has_adoc_content(dir_path: Path) -> bool:
    """Check whether a directory contains any publishable AsciiDoc content files.

    Recursively inspects `dir_path` for `.adoc` files, ignoring hidden files
    (starting with `.`) and partial content files (starting with `_`).

    [parameters]
    `dir_path` (Path):: Directory path to inspect.

    [returns]
    `bool`:: `True` if at least one publishable `.adoc` document exists in the directory tree, `False` otherwise.

    === Examples

    [source,python]
    ----
    >>> from pathlib import Path
    >>> import tempfile
    >>> from golem.metadata import dir_has_adoc_content
    >>> with tempfile.TemporaryDirectory() as tmp_dir:
    ...     p = Path(tmp_dir)
    ...     dir_has_adoc_content(p)
    ...     _ = (p / "doc.adoc").write_text("= Title")
    ...     dir_has_adoc_content(p)
    False
    True
    ----
    """
    if not dir_path.exists() or not dir_path.is_dir():
        return False
    try:
        for p in dir_path.rglob("*.adoc"):
            if p.is_file() and not any(part.startswith(".") or part.startswith("_") for part in p.relative_to(dir_path).parts):
                return True
    except Exception:
        pass
    return False
