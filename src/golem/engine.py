"""Orchestrate incremental Directed Acyclic Graph (DAG) compilation, caching, and static site generation for Golem.

== DAG Compilation Architecture

Golem models documentation projects as a Directed Acyclic Graph (DAG) where nodes represent
source documents (`.adoc`), partials (`_*.adoc`), and layout templates, while directed edges
represent file inclusions (`include::...[]`) and structural dependencies.

== Cache Invalidation Strategies

Incremental rebuilds track content digests and filesystem timestamps to avoid redundant compilations:

Direct Invalidation:: If a file's SHA-256 digest on disk differs from its cached hash, the document
is flagged as directly modified.
Reverse Dependency Propagation:: When an included partial or child document changes, the engine
traverses the reverse dependency graph to mark all ancestor documents as outdated.
Template & Configuration Invalidation:: Modifications to global configuration (`golem.toml`) or
master layout templates (`skeleton.pt`, `page.pt`, `layout.pt`) trigger full-site rebuilds.
Modifications to granular component templates only invalidate documents containing matching ASG node types.
Atomic Persistence & Locking:: Cache records are written atomically using a temporary file replacement
strategy and cross-process advisory locks (`fcntl.flock`) on a dedicated lockfile to prevent corruption
during concurrent builds.

== Build Pipeline Lifecycle

The compilation pipeline proceeds through sequential phases:

1. Stale Detection: Scans `content_dir` for `.adoc` files, purges deleted cache entries, and identifies outdated documents.
2. Static Asset Synchronization: Copies package theme, user theme, and custom static directory assets into `output_dir / "static"`.
3. Pre-Parse Hook Execution: Triggers registered `on_pre_parse` plugin hooks on raw source text.
4. AST Parsing & Hook Execution: Parses source documents into ASTs via `asciidoctrine` and executes `on_ast_created` hooks.
5. ASG Resolution & Hook Execution: Resolves ASTs into Abstract Semantic Graphs (ASG) and executes `on_asg_created` hooks.
6. Body & Table of Contents Rendering: Evaluates ASG nodes into HTML body content and generates structural table-of-contents HTML.
7. Navigation & Pagination Assembly: Discovers site navigation trees and calculates page-specific sequential pagination links.
8. Template Framing & Post-Render Hooks: Compiles the complete HTML page via Chameleon templates (`PageCompiler`) and executes `on_post_render` hooks.
9. Disk Output & Cache Update: Writes compiled HTML files to `output_dir` and updates content hashes and include dependencies in the cache.
"""

import hashlib
import json
import logging
import re
from pathlib import Path
from contextlib import contextmanager
from typing import Any
import asciidoctrine
from asciidoctrine.resolver import ASGResolver
from golem.config import GolemConfig
from golem.renderer import collect_node_types, render_body
from golem.templates import PageCompiler


def _title_from_filename(name: str) -> str:
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
    >>> _title_from_filename("01-getting-started.adoc")
    'Getting Started'
    >>> _title_from_filename("api_reference")
    'Api Reference'
    ----
    """
    stem = Path(name).stem if "." in name else name
    cleaned = re.sub(r"^\d+[-_.]\s*", "", stem)
    if not cleaned:
        cleaned = stem
    cleaned = cleaned.replace("-", " ").replace("_", " ")
    return " ".join(word.capitalize() for word in cleaned.split())


def _clean_index_url(url: str) -> str:
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
    >>> _clean_index_url("docs/guide/index.html")
    'docs/guide/'
    >>> _clean_index_url("index.html")
    './'
    >>> _clean_index_url("docs/guide/about.html")
    'docs/guide/about.html'
    ----
    """
    if url == "index.html":
        return "./"
    if url.endswith("/index.html"):
        return url[: -len("index.html")]
    return url


def _extract_metadata_from_doc(path: Path) -> dict[str, Any]:
    """Extract document metadata attributes from an AsciiDoc file header.

    Reads the leading header section of an AsciiDoc file up to the first section break
    or block delimiter. Parses document title (`= ...`), `:nav_title:`, `:nav_order:`,
    `:body_class:`, `:page_class:`, `:content_class:`, and `:toc:` attributes.
    Falls back to filename-derived titles if no header title is present.

    [parameters]
    `path` (Path):: Path to the target `.adoc` file on disk.

    [returns]
    `dict[str, Any]`:: Dictionary containing `"title"`, `"nav_title"`, `"nav_order"`, `"has_toc"`, `"page_class"`, `"body_class"`, and `"content_class"` keys.
    """
    title = None
    nav_title = None
    nav_order: int | None = None
    has_toc = False
    page_class: str | None = None
    body_class: str | None = None
    content_class: str | None = None
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
        title = _title_from_filename(path.name)
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
    }


def _extract_title_from_doc(path: Path) -> str:
    """Extract the top-level document title from an AsciiDoc file.

    Retrieves the document title by inspecting the file header via `_extract_metadata_from_doc()`,
    falling back to a formatted title derived from the filename.

    [parameters]
    `path` (Path):: Path to the target `.adoc` file.

    [returns]
    `str`:: Extracted or derived document title.
    """
    return str(_extract_metadata_from_doc(path)["title"])


def _dir_has_adoc_content(dir_path: Path) -> bool:
    """Check whether a directory contains any publishable AsciiDoc content files.

    Recursively inspects `dir_path` for `.adoc` files, ignoring hidden files
    (starting with `.`) and partial content files (starting with `_`).

    [parameters]
    `dir_path` (Path):: Directory path to inspect.

    [returns]
    `bool`:: `True` if at least one publishable `.adoc` document exists in the directory tree, `False` otherwise.
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


class BuildEngine:
    """Incremental DAG compilation engine for Golem static site builds.

    Manages the end-to-end documentation compilation lifecycle, including dependency
    graph tracking, SHA-256 caching, reverse invalidation propagation, static asset
    synchronization, navigation discovery, and Chameleon template page compilation.

    [attributes]
    `config` (GolemConfig):: Resolved site configuration and build options.
    `content_dir` (Path):: Resolved absolute path to the source content directory.
    `config_path` (Path):: Path to the active `golem.toml` or `pyproject.toml` file.
    `cache_file` (Path):: Path to the JSON cache storage file.
    `cache_data` (dict):: In-memory cache dictionary containing files, dependencies, metadata, and mtimes.
    `compiler` (PageCompiler):: Page template compiler instance.
    `errors` (list[dict[str, Any]]):: Errors and diagnostics captured during compilation.
    `diagnostics` (list[dict[str, Any]]):: Diagnostic entries (alias to `errors`).
    `pm` (pluggy.PluginManager):: Plugin manager instance for build lifecycle hooks.

    === Examples

    [source,python]
    ----
    >>> from golem.config import GolemConfig
    >>> from golem.engine import BuildEngine
    >>> from pathlib import Path
    >>> config = GolemConfig(content_dir="content", output_dir="dist")
    >>> engine = BuildEngine(config, cache_file=Path("cache.json"))
    >>> isinstance(engine.cache_data, dict)
    True
    ----
    """

    def __init__(self, config: GolemConfig, cache_file: Path | None = None):
        """Initialize the build engine with configuration and cache storage.

        Resolves content and configuration paths, loads existing cache records,
        initializes the page template compiler, and activates registered plugins.

        [parameters]
        `config` (GolemConfig):: Site configuration specifying directories, theme, and build parameters.
        `cache_file` (Path | None, optional):: Explicit path to the DAG cache file. Defaults to `<content_dir>/../.golem/cache.json`.
        """
        self.config = config
        self.content_dir = Path(config.content_dir).resolve()
        self.config_path = Path(config.config_path) if config.config_path else Path("golem.toml")
        self.cache_file = cache_file or Path(config.content_dir).parent / ".golem" / "cache.json"
        self._sha_cache: dict[str, tuple[float, int, str]] = {}
        self.cache_data = self._load_cache()
        self.compiler = PageCompiler(config)
        self.errors: list[dict[str, Any]] = []
        self.diagnostics: list[dict[str, Any]] = self.errors

        # Load Pluggy Plugin Manager
        from golem.plugins import get_plugin_manager

        plugins_dir = Path(getattr(config, "plugins_dir", "plugins"))
        self.pm = get_plugin_manager(config=config, plugins_dir=plugins_dir)

    def _load_cache(self) -> dict:
        """Load and parse the DAG dependency JSON cache from disk.

        Reads cached file hashes, include dependencies, metadata, and modification
        timestamps under an advisory lock. Initializes an empty schema if the cache
        file does not exist or is corrupted.

        [returns]
        `dict`:: Deserialized cache dictionary containing `"files"`, `"dependencies"`, and `"metadata"` tables.
        """
        with self._cache_lock():
            if self.cache_file.exists():
                try:
                    with open(self.cache_file, "r") as f:
                        data = json.load(f)
                        data.setdefault("files", {})
                        data.setdefault("dependencies", {})
                        data.setdefault("metadata", {})
                        if "mtimes" in data and isinstance(data["mtimes"], dict):
                            self._sha_cache = {
                                k: (v[0], v[1], v[2])
                                for k, v in data["mtimes"].items()
                                if isinstance(v, (list, tuple)) and len(v) == 3
                            }
                        return data
                except Exception:
                    try:
                        self.cache_file.unlink()
                    except Exception:
                        pass
            return {"files": {}, "dependencies": {}, "metadata": {}}

    def save_cache(self):
        """Persist DAG compilation hashes and metadata atomically to disk.

        Serializes cache records and timestamp caches to JSON. Uses atomic temporary
        file replacement under an advisory cross-process file lock (`_cache_lock`)
        to guarantee cache integrity.

        [raises]
        `OSError`:: If writing or renaming the temporary cache file fails.
        """
        import os
        import tempfile

        with self._cache_lock():
            if hasattr(self, "_sha_cache") and self._sha_cache:
                self.cache_data["mtimes"] = {k: list(v) for k, v in self._sha_cache.items()}
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            dir_path = self.cache_file.parent
            with tempfile.NamedTemporaryFile("w", dir=dir_path, delete=False, encoding="utf-8") as tf:
                json.dump(self.cache_data, tf, indent=2)
                temp_name = tf.name

            try:
                os.replace(temp_name, self.cache_file)
            except Exception:
                if os.path.exists(temp_name):
                    os.unlink(temp_name)
                raise

    def clean(self) -> None:
        """Purge compiled output directory, persistent cache database, and file locks.

        Removes all compiled HTML and static assets from `output_dir`, unlinks
        the DAG cache file (`cache_file`) and lockfile (`cache.lock`), and resets
        the in-memory cache data structures.

        [returns]
        `None`:: Output directory and cache files are purged from disk.

        === Examples

        [source,python]
        ----
        from golem.config import GolemConfig
        from golem.engine import BuildEngine

        config = GolemConfig(content_dir="content", output_dir="dist")
        engine = BuildEngine(config)
        engine.clean()
        ----
        """
        import shutil

        output_dir = Path(self.config.output_dir)
        if output_dir.exists():
            shutil.rmtree(output_dir)

        if self.cache_file.exists():
            try:
                self.cache_file.unlink()
            except OSError:
                pass

        lock_path = self.cache_file.parent / "cache.lock"
        if lock_path.exists():
            try:
                lock_path.unlink()
            except OSError:
                pass

        self.cache_data = {"files": {}, "dependencies": {}, "metadata": {}}
        self._sha_cache = {}

    @contextmanager
    def _cache_lock(self):
        """Acquire an advisory cross-process lock on the cache lockfile.

        Obtains an exclusive lock (`fcntl.flock`) on `<cache_file_dir>/cache.lock`
        to coordinate concurrent cache access across processes.

        [yields]
        `None`:: Yields control while holding the exclusive lock.
        """
        import fcntl

        lock_path = self.cache_file.parent / "cache.lock"
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)

        lock_fd = None
        try:
            lock_fd = open(lock_path, "w")
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
        except (ImportError, AttributeError, OSError):
            pass

        try:
            yield
        finally:
            if lock_fd:
                try:
                    fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
                    lock_fd.close()
                except Exception:
                    pass

    def is_partial(self, path: Path) -> bool:
        """Check whether a file or directory is designated as a partial content unit.

        Evaluates whether a path begins with an underscore (`_`) or resides within
        any directory segment starting with `_` relative to `content_dir`. Partials
        are excluded from standalone page generation but tracked as dependencies.

        [parameters]
        `path` (Path):: Filesystem path to evaluate.

        [returns]
        `bool`:: `True` if the path or any parent segment starts with `_`, `False` otherwise.
        """
        try:
            rel = path.resolve().relative_to(self.content_dir.resolve())
            return any(part.startswith("_") for part in rel.parts)
        except ValueError:
            return any(part.startswith("_") for part in path.parts)

    def get_file_metadata(self, path: Path) -> dict[str, Any]:
        """Retrieve cached or parsed document metadata for an AsciiDoc file.

        Returns cached metadata if the file's SHA-256 digest is unchanged. If the
        file is modified or uncached, extracts fresh metadata from disk and updates
        the cache record.

        [parameters]
        `path` (Path):: Path to the target AsciiDoc document.

        [returns]
        `dict[str, Any]`:: Dictionary containing `"title"`, `"nav_title"`, `"nav_order"`, `"has_toc"`, `"page_class"`, `"body_class"`, and `"content_class"` keys.
        """
        p_abs = str(path.resolve())
        current_hash = self._get_sha256(path)
        cached_hash = self.cache_data.get("files", {}).get(p_abs)
        cached_meta = self.cache_data.get("metadata", {}).get(p_abs)

        if cached_meta is not None and cached_hash == current_hash and current_hash != "":
            return cached_meta

        meta = _extract_metadata_from_doc(path)
        self.cache_data.setdefault("metadata", {})[p_abs] = meta
        if current_hash:
            self.cache_data.setdefault("files", {})[p_abs] = current_hash
        return meta

    def _get_sha256(self, path: Path) -> str:
        """Compute the SHA-256 hexadecimal digest of a file.

        Reads file content in 8192-byte chunks and computes its SHA-256 digest.
        Utilizes an in-memory cache keyed by path, `mtime`, and `size` to avoid
        redundant disk reads when file attributes are unmodified.

        [parameters]
        `path` (Path):: Path to the target file.

        [returns]
        `str`:: Hexadecimal SHA-256 digest string, or empty string `""` if the file cannot be accessed.
        """
        p_abs = str(path.resolve())
        try:
            stat = path.stat()
            mtime = stat.st_mtime
            size = stat.st_size
        except OSError:
            return ""

        if hasattr(self, "_sha_cache"):
            cached = self._sha_cache.get(p_abs)
            if cached and cached[0] == mtime and cached[1] == size:
                return cached[2]
        else:
            self._sha_cache = {}

        h = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(8192):
                h.update(chunk)
        hexdigest = h.hexdigest()
        self._sha_cache[p_abs] = (mtime, size, hexdigest)
        return hexdigest

    def get_outdated_files(self, commit: bool = True) -> set[Path]:
        """Identify outdated files requiring recompilation through DAG dependency analysis.

        Resolves stale documents by:
        1. Scanning `.adoc` source files and comparing current SHA-256 digests against cached hashes.
        2. Detecting deleted files and removing orphaned cache keys.
        3. Invoking plugin `golem_mark_stale` hooks for custom invalidation rules.
        4. Propagating direct modifications through reverse include dependencies to mark parent documents as outdated.
        5. Checking global configuration (`golem.toml`) and template modifications to trigger full or granular invalidations.

        [parameters]
        `commit` (bool, optional):: Whether to persist cache modifications (such as deleted file removals and updated template digests) to disk. Defaults to `True`.

        [returns]
        `set[Path]`:: Set of absolute `Path` objects for outdated documents that must be recompiled.
        """
        outdated: set[Path] = set()
        if not self.content_dir.exists():
            return outdated

        # 1. Get all actual files present on disk
        all_files = list(self.content_dir.glob("**/*.adoc"))
        current_abs_files = {str(f.resolve()) for f in all_files}

        # 2. Identify deleted files (present in cache but missing from disk)
        cached_files = set(self.cache_data.get("files", {}).keys())
        deleted_files = set()
        for f_abs_str in cached_files:
            if not Path(f_abs_str).exists():
                deleted_files.add(f_abs_str)

        changed_directly = set()

        # Mark deleted files as directly changed to trigger parent invalidation
        for d in deleted_files:
            changed_directly.add(Path(d))

        if self.pm:
            results = self.pm.hook.golem_mark_stale(
                changed_files=list(changed_directly),
                cache_metadata=self.cache_data.get("metadata", {}),
            )
            for res in results:
                if res and isinstance(res, list):
                    for path in res:
                        path_p = Path(path).resolve()
                        if path_p.exists() and not self.is_partial(path_p):
                            outdated.add(path_p)
                            changed_directly.add(path_p)

        # 3. Map current file hashes and identify immediately changed files
        for f in all_files:
            f_abs = f.resolve()
            try:
                h = self._get_sha256(f)
                cached_hash = self.cache_data["files"].get(str(f_abs))
                if cached_hash != h:
                    changed_directly.add(f_abs)
                    if not self.is_partial(f):
                        outdated.add(f_abs)
            except Exception:
                # If there's an issue reading a file, treat it as changed/outdated
                changed_directly.add(f_abs)
                if not self.is_partial(f):
                    outdated.add(f_abs)

        # Check all non-adoc files listed in cached_files that are still on disk
        for f_abs_str in cached_files:
            if f_abs_str in deleted_files:
                continue
            f_path = Path(f_abs_str)
            if f_path.suffix != ".adoc":
                try:
                    h = self._get_sha256(f_path)
                    cached_hash = self.cache_data["files"].get(f_abs_str)
                    if cached_hash != h:
                        changed_directly.add(f_path)
                except Exception:
                    changed_directly.add(f_path)

        # Check if the global config file or layout template has changed.
        global_changed = False

        if self.config_path.exists():
            h_config = self._get_sha256(self.config_path)
            cached_config = self.cache_data.get("meta", {}).get("config_file")
            if cached_config != h_config:
                global_changed = True
                if commit:
                    self.cache_data.setdefault("meta", {})["config_file"] = h_config

        # Check theme and layout templates
        current_templates = self._get_template_fingerprints()

        cached_templates = self.cache_data.get("meta", {}).get("theme_templates")
        if cached_templates is None and "skeleton_pt" in self.cache_data.get("meta", {}):
            cached_templates = {"skeleton.pt": self.cache_data["meta"]["skeleton_pt"]}

        templates_changed = False
        master_layout_keys = {"skeleton.pt", "page.pt", "layout.pt", "skeleton.html", "page.html", "layout.html"}
        master_layout_stems = {"skeleton", "page", "layout"}
        changed_granular_nodes: set[str] = set()

        if cached_templates is not None:
            all_tpl_keys = set(cached_templates.keys()) | set(current_templates.keys())
            for tpl_key in all_tpl_keys:
                old_h = cached_templates.get(tpl_key)
                new_h = current_templates.get(tpl_key)
                if old_h != new_h:
                    templates_changed = True
                    stem = Path(tpl_key).stem.lower()
                    if tpl_key in master_layout_keys or stem in master_layout_stems:
                        global_changed = True
                    else:
                        changed_granular_nodes.add(stem)
        elif self.cache_data.get("files"):
            templates_changed = True
            if current_templates:
                global_changed = True

        if changed_granular_nodes:
            for f_abs_str, meta in self.cache_data.get("metadata", {}).items():
                if not isinstance(meta, dict):
                    continue
                f_path = Path(f_abs_str)
                if not f_path.exists() or self.is_partial(f_path):
                    continue
                node_types = meta.get("node_types")
                if node_types is None or any(node in node_types for node in changed_granular_nodes):
                    outdated.add(f_path)

        if commit:
            self.cache_data.setdefault("meta", {})["theme_templates"] = current_templates

        # If a global layout or config changed, we must mark all existing non-partial .adoc documents as outdated!
        if global_changed:
            logging.info("[BuildEngine] Global configuration or template change detected. Invalidating all pages...")
            outdated.update(f for f in all_files if not self.is_partial(f))
            # Short-circuit and return full re-build
            if commit and (deleted_files or global_changed or templates_changed):
                for d in deleted_files:
                    self.cache_data["files"].pop(d, None)
                    self.cache_data["dependencies"].pop(d, None)
                    self.cache_data.get("metadata", {}).pop(d, None)
                self.save_cache()
            return outdated

        # 4. Re-verify the DAG: resolve reverse dependencies (parent links)
        reverse_deps: dict[str, set[str]] = {}
        for f_str in cached_files | current_abs_files:
            cached_deps = self.cache_data["dependencies"].get(f_str, [])
            for dep in cached_deps:
                reverse_deps.setdefault(dep, set()).add(f_str)

        # Recursively propagate changed/deleted files back up to their parents (ancestors)
        queue = list(changed_directly)
        visited = set(queue)
        while queue:
            curr = str(queue.pop(0))
            parents = reverse_deps.get(curr, set())
            for p in parents:
                p_path = Path(p)
                if p_path not in visited:
                    if p_path.exists() and not self.is_partial(p_path):
                        outdated.add(p_path)
                    visited.add(p_path)
                    queue.append(p_path)

        # 5. Purge deleted files from the cache database
        if commit and (deleted_files or global_changed or templates_changed):
            for d in deleted_files:
                self.cache_data["files"].pop(d, None)
                self.cache_data["dependencies"].pop(d, None)
                self.cache_data.get("metadata", {}).pop(d, None)
            self.save_cache()

        return outdated

    def update_cache_for_file(
        self,
        path: Path,
        included_files: list[str] | None = None,
        node_types: list[str] | None = None,
    ) -> None:
        """Update DAG cache entries, SHA-256 hashes, node types, and dependency relations for a document.

        Computes the SHA-256 digest of the specified document and updates `cache_data["files"]`
        and `cache_data["metadata"]`. Associates ASG structural node types (such as `["admonition", "listing"]`)
        for granular template invalidation. Resolves included partials and child files (`include::...[]`)
        from the supplied `included_files` list or falls back to regex/AST parsing, caching digests
        for all resolved dependencies, and persists the cache to disk.

        [parameters]
        `path` (Path):: Path to the target AsciiDoc document or partial.
        `included_files` (list[str] | None, optional):: Explicit list of resolved dependency file paths. If `None`, dependencies are parsed from file content. Defaults to `None`.
        `node_types` (list[str] | None, optional):: List of ASG node type identifiers present in the document. Defaults to `None`.

        [returns]
        `None`:: Cache dictionary is updated in memory and persisted atomically to disk.

        === Examples

        [source,python]
        ----
        from pathlib import Path
        from golem.config import GolemConfig
        from golem.engine import BuildEngine

        config = GolemConfig(content_dir="content", output_dir="dist")
        engine = BuildEngine(config)
        engine.update_cache_for_file(
            Path("content/index.adoc"),
            included_files=["content/_sidebar.adoc"],
            node_types=["admonition", "listing"],
        )
        ----
        """
        p_abs = str(path.resolve())
        self.cache_data["files"][p_abs] = self._get_sha256(path)
        meta = _extract_metadata_from_doc(path)
        existing_meta = self.cache_data.get("metadata", {}).get(p_abs, {})
        if node_types is not None:
            meta["node_types"] = node_types
        elif isinstance(existing_meta, dict) and "node_types" in existing_meta:
            meta["node_types"] = existing_meta["node_types"]
        self.cache_data.setdefault("metadata", {})[p_abs] = meta
        if included_files is not None:
            unique_deps = list(dict.fromkeys(str(Path(f).resolve()) for f in included_files))
            self.cache_data["dependencies"][p_abs] = unique_deps
        else:
            deps = []
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                ast = asciidoctrine.parse_to_ast(content, base_dir=str(path.parent))
                deps = ast.included_files
            except Exception:
                # Fallback to regex-based robust include parser
                import re

                include_regex = re.compile(r"^include::([^\[]+)\[(.*)\]\s*$")
                seen = set()

                def find_includes(f_path: Path):
                    f_abs = str(f_path.resolve())
                    if f_abs in seen:
                        return
                    seen.add(f_abs)
                    if not f_path.exists():
                        return
                    try:
                        with open(f_path, "r", encoding="utf-8", errors="replace") as f_in:
                            for line in f_in:
                                m = include_regex.match(line.strip())
                                if m:
                                    inc_name = m.group(1).strip()
                                    inc_path = (f_path.parent / inc_name).resolve()
                                    deps.append(str(inc_path))
                                    find_includes(inc_path)
                    except Exception:
                        pass

                find_includes(path)

            # De-duplicate and make sure all are absolute paths as strings
            unique_deps = list(dict.fromkeys(str(Path(d).resolve()) for d in deps))
            self.cache_data["dependencies"][p_abs] = unique_deps

        # Compute and record the SHA-256 hashes for all of the dependency files as well!
        for dep in unique_deps:
            dep_path = Path(dep)
            if dep_path.exists():
                try:
                    self.cache_data["files"][dep] = self._get_sha256(dep_path)
                except Exception:
                    pass

        self.save_cache()

    def _generate_canonical_link(self, rel_path: Path | str) -> str:
        """Generate a canonical relative HTML URL path for a document.

        Converts a content relative path to its corresponding `.html` target URL
        and normalizes `index.html` suffixes to directory-style clean URLs via
        `_clean_index_url()`.

        [parameters]
        `rel_path` (Path | str):: Document path relative to `content_dir`.

        [returns]
        `str`:: Normalized canonical URL string.

        === Examples

        [source,python]
        ----
        from golem.config import GolemConfig
        from golem.engine import BuildEngine

        config = GolemConfig(content_dir="content", output_dir="dist")
        engine = BuildEngine(config)
        assert engine._generate_canonical_link("guides/index.adoc") == "guides/"
        assert engine._generate_canonical_link("about.adoc") == "about.html"
        ----
        """
        p = Path(rel_path)
        return _clean_index_url(p.with_suffix(".html").as_posix())

    def discover_navigation(self) -> list[dict[str, Any]]:
        """Discover and assemble the hierarchical site navigation tree from content files.

        Recursively scans `content_dir` for publishable `.adoc` documents (excluding
        partial files starting with `_` and hidden files starting with `.`). Supports
        explicit ordering via `config.navigation_nav`, pins directory index documents
        (`index.adoc`, `README.adoc`) at the top of sections, respects `:nav_order:`
        attributes, and strips sorting prefixes from display titles.

        [returns]
        `list[dict[str, Any]]`:: Hierarchical list of navigation item dictionaries containing `"title"`, `"path"`, `"url"`, and `"children"`.

        === Examples

        [source,python]
        ----
        from golem.config import GolemConfig
        from golem.engine import BuildEngine

        config = GolemConfig(content_dir="content", output_dir="dist")
        engine = BuildEngine(config)
        nav_tree = engine.discover_navigation()
        ----
        """
        # If navigation_nav is explicitly configured, use it as manual override order
        if self.config.navigation_nav is not None and len(self.config.navigation_nav) > 0:
            nav_items: list[dict[str, Any]] = []
            for item in self.config.navigation_nav:
                p = self.content_dir / item
                if self.is_partial(p):
                    continue
                meta = (
                    self.get_file_metadata(p)
                    if p.exists()
                    else {
                        "title": _title_from_filename(item),
                        "nav_title": _title_from_filename(item),
                    }
                )
                title = meta.get("nav_title") or meta.get("title", _title_from_filename(item))
                rel_url = _clean_index_url(Path(item).with_suffix(".html").as_posix())
                nav_items.append(
                    {
                        "title": title,
                        "path": item,
                        "url": rel_url,
                        "children": [],
                    }
                )
            return nav_items

        if not self.content_dir.exists():
            return []

        def build_tree(current_dir: Path) -> list[dict[str, Any]]:
            items: list[dict[str, Any]] = []
            if not current_dir.exists():
                return items

            try:
                entries = list(current_dir.iterdir())
            except Exception:
                return items

            valid_entries = [e for e in entries if not e.name.startswith(".") and not e.name.startswith("_")]

            files = [e for e in valid_entries if e.is_file() and e.suffix == ".adoc"]
            dirs = [e for e in valid_entries if e.is_dir()]

            def _file_sort_key(p: Path) -> tuple[int, str]:
                meta = self.get_file_metadata(p)
                order = meta.get("nav_order")
                return (order if order is not None else 999, p.name.lower())

            def _dir_sort_key(d: Path) -> tuple[int, str]:
                sub_index: Path | None = None
                try:
                    # Prefer index.adoc first, then readme.adoc
                    for target_stem in ("index", "readme"):
                        for sub_f in d.iterdir():
                            if sub_f.is_file() and sub_f.suffix == ".adoc" and sub_f.stem.lower() == target_stem:
                                sub_index = sub_f
                                break
                        if sub_index is not None:
                            break
                except Exception:
                    pass
                if sub_index is not None:
                    meta = self.get_file_metadata(sub_index)
                    order = meta.get("nav_order")
                    if order is not None:
                        return (order, d.name.lower())
                return (999, d.name.lower())

            files.sort(key=_file_sort_key)
            dirs.sort(key=_dir_sort_key)

            index_file: Path | None = None
            for target_stem in ("index", "readme"):
                for f in files:
                    if f.stem.lower() == target_stem:
                        index_file = f
                        break
                if index_file is not None:
                    break

            if current_dir == self.content_dir and index_file is not None:
                rel_p = index_file.relative_to(self.content_dir).as_posix()
                rel_u = _clean_index_url(index_file.relative_to(self.content_dir).with_suffix(".html").as_posix())
                meta = self.get_file_metadata(index_file)
                title = meta.get("nav_title") or meta.get("title", "")
                items.append(
                    {
                        "title": title,
                        "path": rel_p,
                        "url": rel_u,
                        "children": [],
                    }
                )

            for f in files:
                if current_dir == self.content_dir and f == index_file:
                    continue
                if current_dir != self.content_dir and f == index_file:
                    continue
                rel_p = f.relative_to(self.content_dir).as_posix()
                rel_u = _clean_index_url(f.relative_to(self.content_dir).with_suffix(".html").as_posix())
                meta = self.get_file_metadata(f)
                title = meta.get("nav_title") or meta.get("title", "")
                items.append(
                    {
                        "title": title,
                        "path": rel_p,
                        "url": rel_u,
                        "children": [],
                    }
                )

            for d in dirs:
                if not _dir_has_adoc_content(d):
                    continue
                sub_index = None
                try:
                    for target_stem in ("index", "readme"):
                        for sub_f in d.iterdir():
                            if sub_f.is_file() and sub_f.suffix == ".adoc" and sub_f.stem.lower() == target_stem:
                                sub_index = sub_f
                                break
                        if sub_index is not None:
                            break
                except Exception:
                    pass

                sub_children = build_tree(d)

                if sub_index is not None:
                    meta = self.get_file_metadata(sub_index)
                    sec_title = meta.get("nav_title") or meta.get("title", "")
                    sec_url = _clean_index_url(sub_index.relative_to(self.content_dir).with_suffix(".html").as_posix())
                    sec_path = sub_index.relative_to(self.content_dir).as_posix()
                else:
                    sec_title = _title_from_filename(d.name)
                    sec_url = None
                    sec_path = d.relative_to(self.content_dir).as_posix()

                items.append(
                    {
                        "title": sec_title,
                        "path": sec_path,
                        "url": sec_url,
                        "children": sub_children,
                    }
                )

            return items

        return build_tree(self.content_dir)

    def generate_nav_html(self, current_rel_path: Path | None = None) -> str:
        """Render the hierarchical site navigation tree into semantic HTML with contextual active states.

        Converts the navigation tree from `discover_navigation()` into nested `<ul class="golem-nav-list">`
        and `<ul class="golem-nav-sublist">` HTML elements wrapped within a `<nav class="golem-nav">`
        container. Calculates relative path prefixes (`../` segments) based on `current_rel_path`
        and marks the active page with `aria-current="page"` and `class="active"`.

        [parameters]
        `current_rel_path` (Path | None, optional):: Path of the currently compiling document relative to `content_dir`, used to compute relative URL depth and highlight active items. Defaults to `None`.

        [returns]
        `str`:: Rendered semantic HTML string for the navigation menu, or empty string `""` if navigation is empty.

        === Examples

        [source,python]
        ----
        from pathlib import Path
        from golem.config import GolemConfig
        from golem.engine import BuildEngine

        config = GolemConfig(content_dir="content", output_dir="dist")
        engine = BuildEngine(config)
        nav_html = engine.generate_nav_html(current_rel_path=Path("guides/intro.adoc"))
        assert '<nav class="golem-nav">' in nav_html
        ----
        """
        nav_tree = self.discover_navigation()
        if not nav_tree:
            return ""

        prefix = ""
        if current_rel_path is not None:
            depth = len(current_rel_path.parent.parts)
            if depth > 0:
                prefix = "../" * depth

        curr_posix = current_rel_path.as_posix() if current_rel_path else None
        curr_html = current_rel_path.with_suffix(".html").as_posix() if current_rel_path else None

        def render_list(items: list[dict[str, Any]], is_nested: bool = False) -> list[str]:
            ul_class = "golem-nav-sublist" if is_nested else "golem-nav-list"
            out = [f'<ul class="{ul_class}">\n']
            for item in items:
                title = item.get("title", "")
                url = item.get("url")
                item_path = item.get("path")
                children = item.get("children", [])
                href = f"{prefix}{url}" if url else None
                # Collapse redundant './' segment: '.././' -> '../', '../.././' -> '../../'
                if href and href.endswith("./") and len(href) > 2:
                    href = href[:-2]
                is_current = bool((curr_posix and item_path == curr_posix) or (curr_html and url == curr_html))

                if children:
                    sec_class = "golem-nav-section active" if is_current else "golem-nav-section"
                    out.append(f'  <li class="{sec_class}">\n')
                    curr_attr = ' aria-current="page" class="active"' if is_current else ""
                    if href:
                        out.append(
                            f'    <span class="golem-nav-section-title"><a href="{href}"{curr_attr}>{title}</a></span>\n'
                        )
                    else:
                        out.append(f'    <span class="golem-nav-section-title">{title}</span>\n')
                    out.extend(render_list(children, is_nested=True))
                    out.append("  </li>\n")
                else:
                    item_class = "golem-nav-item active" if is_current else "golem-nav-item"
                    curr_attr = ' aria-current="page" class="active"' if is_current else ""
                    out.append(f'  <li class="{item_class}">')
                    if href:
                        out.append(f'<a href="{href}"{curr_attr}>{title}</a>')
                    else:
                        out.append(f"<span>{title}</span>")
                    out.append("</li>\n")
            out.append("</ul>\n")
            return out

        res = ['<nav class="golem-nav">\n']
        res.extend(render_list(nav_tree, is_nested=False))
        res.append("</nav>")
        return "".join(res)

    def get_ordered_nav_pages(self) -> list[dict[str, Any]]:
        """Flatten the hierarchical site navigation tree into a linear sequence of pages.

        Performs a depth-first traversal of `discover_navigation()` to produce an ordered
        linear sequence of navigable document entries. Used by `get_page_pagination()` to
        calculate previous and next sequential reading links.

        [returns]
        `list[dict[str, Any]]`:: Linear list of page dictionaries containing `"title"`, `"url"`, and `"path"`.

        === Examples

        [source,python]
        ----
        from golem.config import GolemConfig
        from golem.engine import BuildEngine

        config = GolemConfig(content_dir="content", output_dir="dist")
        engine = BuildEngine(config)
        pages = engine.get_ordered_nav_pages()
        ----
        """
        nav_tree = self.discover_navigation()
        pages: list[dict[str, Any]] = []

        def _flatten(items: list[dict[str, Any]]) -> None:
            for item in items:
                title = item.get("title", "")
                url = item.get("url")
                path = item.get("path")
                children = item.get("children", [])

                if url:
                    pages.append({"title": title, "url": url, "path": path or ""})
                if children:
                    _flatten(children)

        _flatten(nav_tree)
        return pages

    def get_page_pagination(self, current_rel_path: Path | None = None) -> tuple[dict[str, str] | None, dict[str, str] | None]:
        """Calculate previous and next sequential pagination links for a given document.

        Locates `current_rel_path` within the linear sequence produced by `get_ordered_nav_pages()`
        and determines the immediately preceding and following document links, adjusting
        relative URL prefixes (`../` segments) according to the directory depth of `current_rel_path`.

        [parameters]
        `current_rel_path` (Path | None, optional):: Relative path of the active document within `content_dir`. Defaults to `None`.

        [returns]
        `tuple[dict[str, str] | None, dict[str, str] | None]`:: A 2-tuple `(prev_page, next_page)`. Each element is either a dictionary containing `"title"`, `"url"`, and `"path"`, or `None` if at the start/end of the sequence.

        === Examples

        [source,python]
        ----
        from pathlib import Path
        from golem.config import GolemConfig
        from golem.engine import BuildEngine

        config = GolemConfig(content_dir="content", output_dir="dist")
        engine = BuildEngine(config)
        prev_p, next_p = engine.get_page_pagination(current_rel_path=Path("02-guide.adoc"))
        ----
        """
        if current_rel_path is None:
            return None, None

        pages = self.get_ordered_nav_pages()
        if not pages:
            return None, None

        depth = len(current_rel_path.parent.parts)
        prefix = ("../" * depth) if depth > 0 else ""

        curr_posix = current_rel_path.as_posix()
        curr_html = current_rel_path.with_suffix(".html").as_posix()

        curr_idx = -1
        for idx, p in enumerate(pages):
            if p["path"] == curr_posix or p["url"] == curr_html or p["url"] == _clean_index_url(curr_html):
                curr_idx = idx
                break

        if curr_idx == -1:
            return None, None

        prev_item: dict[str, str] | None = None
        if curr_idx > 0:
            raw_prev = pages[curr_idx - 1]
            prev_url = f"{prefix}{raw_prev['url']}"
            if prev_url.endswith("./") and len(prev_url) > 2:
                prev_url = prev_url[:-2]
            prev_item = {
                "title": raw_prev["title"],
                "url": prev_url,
                "path": raw_prev["path"],
            }

        next_item: dict[str, str] | None = None
        if curr_idx < len(pages) - 1:
            raw_next = pages[curr_idx + 1]
            next_url = f"{prefix}{raw_next['url']}"
            if next_url.endswith("./") and len(next_url) > 2:
                next_url = next_url[:-2]
            next_item = {
                "title": raw_next["title"],
                "url": next_url,
                "path": raw_next["path"],
            }

        return prev_item, next_item

    def _get_template_search_paths(self) -> list[Path]:
        """Collect filesystem search paths for custom and theme templates.

        Resolves template search paths in priority order:
        1. Custom template directory (`config.templates_dir`) if configured.
        2. Workspace theme directory (`themes/<theme>`) if configured.

        [returns]
        `list[Path]`:: Ordered list of existing `Path` objects to search for templates.

        === Examples

        [source,python]
        ----
        from golem.config import GolemConfig
        from golem.engine import BuildEngine

        config = GolemConfig(content_dir="content", output_dir="dist", theme="default")
        engine = BuildEngine(config)
        paths = engine._get_template_search_paths()
        ----
        """
        paths: list[Path] = []
        if hasattr(self.config, "templates_dir") and self.config.templates_dir:
            tpl_path = Path(self.config.templates_dir)
            paths.append(tpl_path.resolve() if tpl_path.exists() else tpl_path)

        if hasattr(self.config, "theme") and self.config.theme:
            theme_path = Path("themes") / self.config.theme
            paths.append(theme_path.resolve() if theme_path.exists() else theme_path)

        return paths

    def _get_template_files(self) -> list[Path]:
        """Discover all template files across configured template search paths.

        Scans directories returned by `_get_template_search_paths()` for template
        files ending in `.html` or `.pt`. Excludes hidden files (starting with `.`)
        and assets located in `static/` subdirectories.

        [returns]
        `list[Path]`:: List of paths to discovered template files.

        === Examples

        [source,python]
        ----
        from golem.config import GolemConfig
        from golem.engine import BuildEngine

        config = GolemConfig(content_dir="content", output_dir="dist", theme="default")
        engine = BuildEngine(config)
        templates = engine._get_template_files()
        ----
        """
        templates: list[Path] = []
        for search_dir in self._get_template_search_paths():
            if search_dir.exists() and search_dir.is_dir():
                for tpl_file in search_dir.rglob("*"):
                    if tpl_file.is_file() and tpl_file.suffix in (".html", ".pt"):
                        try:
                            rel = tpl_file.relative_to(search_dir)
                        except ValueError:
                            rel = Path(tpl_file.name)
                        if any(part.startswith(".") or part == "static" for part in rel.parts):
                            continue
                        templates.append(tpl_file)
        return templates

    def _get_template_fingerprints(self) -> dict[str, str]:
        """Compute SHA-256 content digests for all discoverable template files.

        Iterates through template files across template search paths, mapping each
        template's relative POSIX path to its computed SHA-256 hexadecimal hash.

        [returns]
        `dict[str, str]`:: Dictionary mapping relative template paths to SHA-256 digests.

        === Examples

        [source,python]
        ----
        from golem.config import GolemConfig
        from golem.engine import BuildEngine

        config = GolemConfig(content_dir="content", output_dir="dist")
        engine = BuildEngine(config)
        fingerprints = engine._get_template_fingerprints()
        ----
        """
        current_templates: dict[str, str] = {}
        for search_dir in self._get_template_search_paths():
            if search_dir.exists() and search_dir.is_dir():
                for tpl_file in search_dir.rglob("*"):
                    if tpl_file.is_file() and tpl_file.suffix in (".html", ".pt"):
                        try:
                            rel = tpl_file.relative_to(search_dir)
                        except ValueError:
                            rel = Path(tpl_file.name)
                        if any(part.startswith(".") or part == "static" for part in rel.parts):
                            continue
                        key = rel.as_posix()
                        if key not in current_templates:
                            current_templates[key] = self._get_sha256(tpl_file)
        return current_templates

    def sync_static_assets(self) -> None:
        """Synchronize static assets from package defaults, theme directories, and user static folders.

        Copies assets into `<output_dir>/static` in layered precedence order:
        1. Package default theme static assets (`golem/templates/<theme>/static` and `golem/templates/default/static`).
        2. Workspace theme static assets (`themes/<theme>/static`).
        3. Custom templates static assets (`<templates_dir>/static`).
        4. User project static assets (`<static_dir>`).

        Higher-precedence assets overwrite lower-precedence assets with matching relative paths.

        [returns]
        `None`:: Static assets are copied directly to disk.

        === Examples

        [source,python]
        ----
        from golem.config import GolemConfig
        from golem.engine import BuildEngine

        config = GolemConfig(content_dir="content", output_dir="dist", static_dir="static")
        engine = BuildEngine(config)
        engine.sync_static_assets()
        ----
        """
        import shutil

        output_static_dir = Path(self.config.output_dir) / "static"

        # 1. Package default theme static assets (if any)
        pkg_theme_static = Path(__file__).parent / "templates" / getattr(self.config, "theme", "default") / "static"
        if pkg_theme_static.exists() and pkg_theme_static.is_dir():
            output_static_dir.mkdir(parents=True, exist_ok=True)
            shutil.copytree(pkg_theme_static, output_static_dir, dirs_exist_ok=True)

        # Also check package default static if theme != default
        pkg_default_static = Path(__file__).parent / "templates" / "default" / "static"
        if pkg_default_static != pkg_theme_static and pkg_default_static.exists() and pkg_default_static.is_dir():
            output_static_dir.mkdir(parents=True, exist_ok=True)
            shutil.copytree(pkg_default_static, output_static_dir, dirs_exist_ok=True)

        # 2. Configured theme directory static assets (themes/<theme>/static)
        theme_name = getattr(self.config, "theme", "default")
        if theme_name:
            theme_static = Path("themes") / theme_name / "static"
            if theme_static.exists() and theme_static.is_dir():
                output_static_dir.mkdir(parents=True, exist_ok=True)
                shutil.copytree(theme_static, output_static_dir, dirs_exist_ok=True)

        # Custom templates_dir static (if configured)
        if hasattr(self.config, "templates_dir") and self.config.templates_dir:
            tpl_static = Path(self.config.templates_dir) / "static"
            if tpl_static.exists() and tpl_static.is_dir():
                output_static_dir.mkdir(parents=True, exist_ok=True)
                shutil.copytree(tpl_static, output_static_dir, dirs_exist_ok=True)

        # 3. User static_dir (e.g. static/)
        if hasattr(self.config, "static_dir") and self.config.static_dir:
            user_static = Path(self.config.static_dir)
            if user_static.exists() and user_static.is_dir():
                output_static_dir.mkdir(parents=True, exist_ok=True)
                shutil.copytree(user_static, output_static_dir, dirs_exist_ok=True)

    def build_site(self) -> list[Path]:
        """Orchestrate the incremental compilation pipeline for outdated AsciiDoc documents.

        Executes the complete documentation compilation lifecycle:
        1. Generates automated API reference documentation via `golem.plugins.apidoc` if `config.api_packages` is configured.
        2. Identifies stale or modified documents via `get_outdated_files()`.
        3. Synchronizes static assets into the output directory via `sync_static_assets()`.
        4. Compiles each outdated document through sequential AST parsing (`asciidoctrine`), ASG semantic resolution (`ASGResolver`), body rendering (`render_body`), navigation and TOC generation, and Chameleon template layout compilation (`PageCompiler`).
        5. Executes plugin hooks (`on_pre_parse`, `on_ast_created`, `on_asg_created`, `on_post_render`) across each lifecycle phase.
        6. Writes compiled HTML files to disk and updates the DAG cache via `update_cache_for_file()`.

        [returns]
        `list[Path]`:: List of output `Path` objects for all compiled HTML documents.

        [raises]
        `Exception`:: If compilation fails for any document while `config.strict` is `True`.

        === Examples

        [source,python]
        ----
        from golem.config import GolemConfig
        from golem.engine import BuildEngine

        config = GolemConfig(content_dir="content", output_dir="dist")
        engine = BuildEngine(config)
        compiled_pages = engine.build_site()
        ----
        """
        import sys

        self.errors = []
        self.diagnostics = self.errors
        compiled_files = []

        # Automated API doc generation when api_packages is configured
        if getattr(self.config, "api_packages", None):
            try:
                from golem.plugins.apidoc import generate_api_docs

                dest_dir = self.content_dir / getattr(self.config, "api_output_dir", "api")
                generate_api_docs(
                    packages=self.config.api_packages,
                    output_dir=dest_dir,
                    search_paths=[Path.cwd(), Path("src")] + [Path(p) for p in sys.path if p],
                    docstring_style=getattr(self.config, "api_docstring_style", "auto"),
                )
            except Exception as e:
                logging.warning(f"Failed to generate API documentation during build: {e}")
                if getattr(self.config, "strict", False):
                    raise

        outdated = self.get_outdated_files()

        all_docs = (
            [f for f in self.content_dir.glob("**/*.adoc") if not self.is_partial(f)] if self.content_dir.exists() else []
        )
        to_build = {f for f in outdated if not self.is_partial(f)} if (outdated or self.cache_data["files"]) else set(all_docs)

        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        self.sync_static_assets()

        search_paths = self._get_template_search_paths()

        for doc_path in to_build:
            if self.is_partial(doc_path):
                continue
            try:
                with open(doc_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()

                # Trigger pre-parse hooks sequentially (chain modifications)
                for impl in self.pm.hook.on_pre_parse.get_hookimpls():
                    content = impl.function(raw_content=content)  # type: ignore[assignment]

                # 1. Parse using asciidoctrine
                ast = asciidoctrine.parse_to_ast(content, base_dir=str(doc_path.parent))

                # Trigger AST hooks sequentially (chain modifications)
                for impl in self.pm.hook.on_ast_created.get_hookimpls():
                    ast = impl.function(ast=ast)  # type: ignore[assignment]

                # 2. Resolve AST to ASG
                resolver = ASGResolver(ast)
                asg = resolver.resolve(ast)

                # Trigger ASG hooks sequentially (chain modifications)
                for impl in self.pm.hook.on_asg_created.get_hookimpls():
                    asg = impl.function(asg=asg)  # type: ignore[assignment]

                page_node_types = collect_node_types(asg)

                # 3. Render body using Golem's ASG visitor
                body_content = render_body(asg, search_paths=search_paths)  # type: ignore[arg-type]

                # Extract title for layout framing
                title_str = ""
                if isinstance(asg, dict):
                    title_str = asg.get("title", "")
                    if not title_str and asg.get("header"):
                        header = asg["header"]
                        if isinstance(header, dict) and header.get("title"):
                            title_nodes = header["title"]
                            if isinstance(title_nodes, list) and len(title_nodes) > 0:
                                title_str = title_nodes[0].get("value", "")
                    if not title_str and asg.get("blocks"):
                        first_block = asg["blocks"][0]
                        if first_block.get("name") == "title":
                            title_str = first_block.get("value", "")
                else:
                    title_str = getattr(asg, "title", "")

                if not title_str:
                    title_str = "Golem Doc"

                # 4. Compile layout via Chameleon templates
                from golem.renderer import generate_toc_html

                toc_html = generate_toc_html(asg)  # type: ignore[arg-type]

                # Generate dynamic navigation HTML and chapter pagination for this page
                rel_path = doc_path.relative_to(self.content_dir)
                nav_html = self.generate_nav_html(current_rel_path=rel_path)
                prev_page, next_page = self.get_page_pagination(current_rel_path=rel_path)

                doc_meta = self.get_file_metadata(doc_path)
                page_class = doc_meta.get("page_class", "")
                body_class = doc_meta.get("body_class", "")
                content_class = doc_meta.get("content_class", "")

                asg_attrs: dict[str, Any] = {}
                if isinstance(asg, dict):
                    asg_attrs = asg.get("attributes") or {}
                    if not isinstance(asg_attrs, dict) and isinstance(asg.get("header"), dict):
                        asg_attrs = asg["header"].get("attributes") or {}
                elif hasattr(asg, "attributes"):
                    asg_attrs = getattr(asg, "attributes") or {}

                if isinstance(asg_attrs, dict):
                    if not body_class:
                        body_class = (
                            asg_attrs.get("body_class") or asg_attrs.get("body-class") or asg_attrs.get("bodyclass") or ""
                        )
                    if not page_class:
                        page_class = (
                            asg_attrs.get("page_class") or asg_attrs.get("page-class") or asg_attrs.get("pageclass") or ""
                        )
                    if not content_class:
                        content_class = (
                            asg_attrs.get("content_class")
                            or asg_attrs.get("content-class")
                            or asg_attrs.get("contentclass")
                            or ""
                        )

                resolved_body_class = (body_class or page_class or "").strip()
                resolved_page_class = (page_class or body_class or "").strip()
                resolved_content_class = (content_class or "").strip()

                final_html = self.compiler.compile_page(
                    title=title_str,
                    body_content=body_content,
                    toc_html=toc_html,
                    nav_html=nav_html,
                    nav_tree=self.discover_navigation(),
                    current_path=str(rel_path),
                    prev_page=prev_page,
                    next_page=next_page,
                    body_class=resolved_body_class,
                    page_class=resolved_page_class,
                    content_class=resolved_content_class,
                )

                # Trigger post-render hooks sequentially (chain modifications)
                for impl in self.pm.hook.on_post_render.get_hookimpls():
                    final_html = impl.function(html_content=final_html)  # type: ignore[assignment]

                # 5. Resolve correct output file path
                out_path = output_dir / rel_path.with_suffix(".html")
                out_path.parent.mkdir(parents=True, exist_ok=True)

                # 6. Write final page to disk
                with open(out_path, "w", encoding="utf-8") as f_out:
                    f_out.write(final_html)

                # 7. Update file dependency hash in DAG cache
                self.update_cache_for_file(doc_path, getattr(ast, "included_files", []), node_types=page_node_types)
                compiled_files.append(out_path)

                # Progress logging
                try:
                    rel_doc = doc_path.relative_to(Path.cwd())
                except ValueError:
                    rel_doc = doc_path.relative_to(self.content_dir) if self.content_dir in doc_path.parents else doc_path
                try:
                    rel_out = out_path.relative_to(Path.cwd())
                except ValueError:
                    rel_out = out_path.relative_to(output_dir) if output_dir in out_path.parents else out_path
                import click

                click.echo(f"  [COMPILE] {rel_doc} -> {rel_out}")
            except Exception as e:
                error_info = {
                    "file": str(doc_path),
                    "message": str(e),
                    "error_type": type(e).__name__,
                    "exception": e,
                    "line": getattr(e, "line", getattr(e, "lineno", None)),
                    "column": getattr(
                        e,
                        "column",
                        getattr(e, "offset", getattr(e, "col_offset", None)),
                    ),
                    "context": getattr(e, "context", None),
                }
                self.errors.append(error_info)
                logging.error(f"Failed to build file {doc_path}: {e}")
                if getattr(self.config, "strict", False):
                    raise e

        return compiled_files
