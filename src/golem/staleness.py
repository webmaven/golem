"""Track file staleness, DAG dependency graphs, and template invalidations for Golem.

== Staleness Architecture

Golem maintains an incremental Directed Acyclic Graph (DAG) cache mapping source `.adoc`
files, included partials (`_*.adoc`), and layout templates (`.pt`/`.html`) to SHA-256 digests.
Staleness detection identifies modified documents and traverses reverse dependency links
to determine the minimum recompilation set.

== Dependency Propagation

Reverse Include Traversal:: When an included partial or child document changes, the reverse
dependency graph is traversed to invalidate all parent/ancestor documents.
Master Layout Invalidation:: Changes to master layout templates (`skeleton.pt`, `page.pt`, `layout.pt`)
or global site configuration trigger a full site rebuild.
Granular Component Invalidation:: Changes to component templates only invalidate pages
containing the matching ASG node types.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import asciidoctrine
from golem.cache import BuildCache
from golem.metadata import extract_metadata_from_doc

if TYPE_CHECKING:
    pass

__all__ = [
    "StalenessTracker",
    "is_partial",
]


def is_partial(path: Path, content_dir: Path) -> bool:
    """Check whether a file or directory is designated as a partial content unit.

    Evaluates whether a path begins with an underscore (`_`) or resides within
    any directory segment starting with `_` relative to `content_dir`. Partials
    are excluded from standalone page generation but tracked as dependencies.

    [parameters]
    `path` (Path):: Filesystem path to evaluate.
    `content_dir` (Path):: Base content directory path.

    [returns]
    `bool`:: `True` if the path or any parent segment starts with `_`, `False` otherwise.

    === Examples

    [source,python]
    ----
    >>> from pathlib import Path
    >>> from golem.staleness import is_partial
    >>> is_partial(Path("content/_partials/header.adoc"), Path("content"))
    True
    >>> is_partial(Path("content/guide/intro.adoc"), Path("content"))
    False
    ----
    """
    try:
        rel = path.resolve().relative_to(content_dir.resolve())
        return any(part.startswith("_") for part in rel.parts)
    except ValueError:
        return any(part.startswith("_") for part in path.parts)


class StalenessTracker:
    """Track document staleness, template digests, and DAG reverse dependency propagation.

    Analyzes source file SHA-256 digests against cached records, detects template
    modifications, identifies deleted files, and propagates change notifications
    through the DAG include hierarchy to determine the minimum set of documents
    requiring recompilation.

    [attributes]
    `config` (Any):: Site configuration specifying directories and build settings.
    `cache` (BuildCache):: DAG compilation cache database.
    `content_dir` (Path):: Resolved absolute path to the source content directory.
    `pm` (Any):: Plugin manager instance for stale detection hooks.
    `plugin_manager` (Any):: Alias to `pm`.
    `config_path` (Path):: Path to site configuration file (`golem.toml`).

    === Examples

    [source,python]
    ----
    >>> from pathlib import Path
    >>> import tempfile
    >>> from golem.cache import BuildCache
    >>> from golem.config import GolemConfig
    >>> from golem.staleness import StalenessTracker
    >>> with tempfile.TemporaryDirectory() as tmp_dir:
    ...     p = Path(tmp_dir)
    ...     content = p / "content"
    ...     content.mkdir()
    ...     doc = content / "index.adoc"
    ...     _ = doc.write_text("= Title\\nContent")
    ...     config = GolemConfig(content_dir=str(content), output_dir=str(p / "dist"))
    ...     cache = BuildCache(p / "cache.json")
    ...     tracker = StalenessTracker(config, cache, content)
    ...     outdated = tracker.get_outdated_files()
    ...     doc.resolve() in outdated
    True
    ----
    """

    def __init__(
        self,
        config: Any,
        cache: BuildCache,
        content_dir: Path,
        plugin_manager: Any = None,
        config_path: Path | None = None,
    ):
        """Initialize the staleness tracker with configuration, cache database, and content path.

        [parameters]
        `config` (Any):: Site configuration specifying themes, directories, and build options.
        `cache` (BuildCache):: DAG cache database instance.
        `content_dir` (Path):: Base path to the documentation content directory.
        `plugin_manager` (Any, optional):: Pluggy plugin manager instance. Defaults to `None`.
        `config_path` (Path | None, optional):: Path to the site configuration file. Defaults to `golem.toml`.
        """
        self.config = config
        self.cache = cache
        self.content_dir = Path(content_dir).resolve()
        self.pm = plugin_manager
        self.plugin_manager = plugin_manager
        if config_path is not None:
            self.config_path = Path(config_path)
        elif hasattr(config, "config_path") and config.config_path:
            self.config_path = Path(config.config_path)
        else:
            self.config_path = Path("golem.toml")

    def is_partial(self, path: Path) -> bool:
        """Check whether a path is designated as a partial within this tracker's content directory.

        [parameters]
        `path` (Path):: Filesystem path to evaluate.

        [returns]
        `bool`:: `True` if the path or any parent segment starts with `_`, `False` otherwise.
        """
        return is_partial(path, self.content_dir)

    def _build_dependency_graph(self, files: list[Path] | None = None) -> tuple[dict[Path, set[Path]], dict[Path, set[Path]]]:
        """Build forward and reverse include dependency mappings from the cache and filesystem.

        Constructs two graphs:
        - Forward dependencies: maps each document `Path` to a set of included `Path` dependencies.
        - Reverse dependencies: maps each dependency `Path` to a set of parent document `Path` objects.

        [parameters]
        `files` (list[Path] | None, optional):: Explicit list of source files to index. If `None`, uses all cached and on-disk `.adoc` files. Defaults to `None`.

        [returns]
        `tuple[dict[Path, set[Path]], dict[Path, set[Path]]]`:: A 2-tuple `(forward_deps, reverse_deps)` mapping documents to their dependencies and dependencies to their parent documents.
        """
        forward_deps: dict[Path, set[Path]] = {}
        reverse_deps: dict[Path, set[Path]] = {}

        if files is not None:
            file_keys = {str(f.resolve()) for f in files}
        else:
            cached_files = set(self.cache.data.get("files", {}).keys())
            disk_files = {str(f.resolve()) for f in self.content_dir.glob("**/*.adoc")} if self.content_dir.exists() else set()
            file_keys = cached_files | disk_files

        for f_str in file_keys:
            f_path = Path(f_str).resolve()
            cached_deps = self.cache.data.get("dependencies", {}).get(f_str, [])
            dep_paths = {Path(dep).resolve() for dep in cached_deps}
            forward_deps[f_path] = dep_paths
            for dep_path in dep_paths:
                reverse_deps.setdefault(dep_path, set()).add(f_path)

        return forward_deps, reverse_deps

    def _get_template_search_paths(self) -> list[Path]:
        """Collect filesystem search paths for custom, workspace theme, and built-in templates.

        Resolves template search paths in priority order:
        1. Custom template directory (`config.templates_dir`) if configured.
        2. Workspace theme directory (`themes/<theme>`) if configured.
        3. Built-in package theme templates (`templates/<theme>`).
        4. Built-in package default templates (`templates/default`).

        [returns]
        `list[Path]`:: Ordered list of existing `Path` objects to search for templates.

        === Examples

        [source,python]
        ----
        >>> from pathlib import Path
        >>> from golem.config import GolemConfig
        >>> from golem.cache import BuildCache
        >>> from golem.staleness import StalenessTracker
        >>> tracker = StalenessTracker(GolemConfig(), BuildCache(Path("cache.json")), Path("content"))
        >>> paths = tracker._get_template_search_paths()
        >>> isinstance(paths, list)
        True
        ----
        """
        paths: list[Path] = []
        if hasattr(self.config, "templates_dir") and self.config.templates_dir:
            tpl_path = Path(self.config.templates_dir)
            paths.append(tpl_path.resolve() if tpl_path.exists() else tpl_path)

        if hasattr(self.config, "theme") and self.config.theme:
            theme_path = Path("themes") / self.config.theme
            paths.append(theme_path.resolve() if theme_path.exists() else theme_path)

        pkg_theme = Path(__file__).parent / "templates" / getattr(self.config, "theme", "default")
        if pkg_theme.exists() and pkg_theme.is_dir():
            paths.append(pkg_theme.resolve())
        pkg_default = Path(__file__).parent / "templates" / "default"
        if pkg_default != pkg_theme and pkg_default.exists() and pkg_default.is_dir():
            paths.append(pkg_default.resolve())

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
        >>> from pathlib import Path
        >>> from golem.config import GolemConfig
        >>> from golem.cache import BuildCache
        >>> from golem.staleness import StalenessTracker
        >>> tracker = StalenessTracker(GolemConfig(), BuildCache(Path("cache.json")), Path("content"))
        >>> templates = tracker._get_template_files()
        >>> isinstance(templates, list)
        True
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
        >>> from pathlib import Path
        >>> from golem.config import GolemConfig
        >>> from golem.cache import BuildCache
        >>> from golem.staleness import StalenessTracker
        >>> tracker = StalenessTracker(GolemConfig(), BuildCache(Path("cache.json")), Path("content"))
        >>> fingerprints = tracker._get_template_fingerprints()
        >>> isinstance(fingerprints, dict)
        True
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
                            current_templates[key] = self.cache.get_sha256(tpl_file)
        return current_templates

    def get_outdated_files(
        self,
        commit: bool = True,
        adoc_files: list[Path] | None = None,
    ) -> set[Path]:
        """Identify outdated files requiring recompilation through DAG dependency analysis.

        Resolves stale documents by:
        1. Scanning `.adoc` source files and comparing current SHA-256 digests against cached hashes.
        2. Detecting deleted files and removing orphaned cache keys.
        3. Invoking plugin `golem_mark_stale` hooks for custom invalidation rules.
        4. Propagating direct modifications through reverse include dependencies to mark parent documents as outdated.
        5. Checking global configuration (`golem.toml`) and template modifications to trigger full or granular invalidations.

        [parameters]
        `commit` (bool, optional):: Whether to persist cache modifications (such as deleted file removals and updated template digests) to disk. Defaults to `True`.
        `adoc_files` (list[Path] | None, optional):: Optional explicit list of `.adoc` source files to evaluate. If `None`, scans `content_dir`. Defaults to `None`.

        [returns]
        `set[Path]`:: Set of absolute `Path` objects for outdated documents that must be recompiled.

        === Examples

        [source,python]
        ----
        >>> from pathlib import Path
        >>> import tempfile
        >>> from golem.cache import BuildCache
        >>> from golem.config import GolemConfig
        >>> from golem.staleness import StalenessTracker
        >>> with tempfile.TemporaryDirectory() as tmp_dir:
        ...     p = Path(tmp_dir)
        ...     content = p / "content"
        ...     content.mkdir()
        ...     doc = content / "index.adoc"
        ...     _ = doc.write_text("= Title\\nContent")
        ...     tracker = StalenessTracker(GolemConfig(), BuildCache(p / "cache.json"), content)
        ...     outdated = tracker.get_outdated_files()
        ...     doc.resolve() in outdated
        True
        ----
        """
        outdated: set[Path] = set()
        if not self.content_dir.exists():
            return outdated

        # 1. Get all actual files present on disk
        if adoc_files is not None:
            all_files = list(adoc_files)
        else:
            all_files = list(self.content_dir.glob("**/*.adoc"))

        # 2. Identify deleted files (present in cache but missing from disk)
        cached_files = set(self.cache.data.get("files", {}).keys())
        deleted_files = set()
        for f_abs_str in cached_files:
            if not Path(f_abs_str).exists():
                deleted_files.add(f_abs_str)

        changed_directly: set[Path] = set()

        # Mark deleted files as directly changed to trigger parent invalidation
        for d in deleted_files:
            changed_directly.add(Path(d).resolve())

        if self.pm:
            results = self.pm.hook.golem_mark_stale(
                changed_files=list(changed_directly),
                cache_metadata=self.cache.data.get("metadata", {}),
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
                h = self.cache.get_sha256(f)
                cached_hash = self.cache.data.get("files", {}).get(str(f_abs))
                if cached_hash != h:
                    changed_directly.add(f_abs)
                    if not self.is_partial(f):
                        outdated.add(f_abs)
            except Exception:
                changed_directly.add(f_abs)
                if not self.is_partial(f):
                    outdated.add(f_abs)

        # Check all non-adoc files listed in cached_files that are still on disk
        for f_abs_str in cached_files:
            if f_abs_str in deleted_files:
                continue
            f_path = Path(f_abs_str).resolve()
            if f_path.suffix != ".adoc":
                try:
                    h = self.cache.get_sha256(f_path)
                    cached_hash = self.cache.data.get("files", {}).get(f_abs_str)
                    if cached_hash != h:
                        changed_directly.add(f_path)
                except Exception:
                    changed_directly.add(f_path)

        # Check if the global config file or layout template has changed.
        global_changed = False

        if self.config_path.exists():
            h_config = self.cache.get_sha256(self.config_path)
            cached_config = self.cache.data.get("meta", {}).get("config_file")
            if cached_config != h_config:
                global_changed = True
                if commit:
                    self.cache.data.setdefault("meta", {})["config_file"] = h_config

        # Check theme and layout templates
        current_templates = self._get_template_fingerprints()

        cached_templates = self.cache.data.get("meta", {}).get("theme_templates")
        if cached_templates is None and "skeleton_pt" in self.cache.data.get("meta", {}):
            cached_templates = {"skeleton.pt": self.cache.data["meta"]["skeleton_pt"]}

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
        elif self.cache.data.get("files"):
            templates_changed = True
            if current_templates:
                global_changed = True

        if changed_granular_nodes:
            for f_abs_str, meta in self.cache.data.get("metadata", {}).items():
                if not isinstance(meta, dict):
                    continue
                f_path = Path(f_abs_str).resolve()
                if not f_path.exists() or self.is_partial(f_path):
                    continue
                node_types = meta.get("node_types")
                if node_types is None or any(node in node_types for node in changed_granular_nodes):
                    outdated.add(f_path)

        if commit:
            self.cache.data.setdefault("meta", {})["theme_templates"] = current_templates

        # If a global layout or config changed, we must mark all existing non-partial .adoc documents as outdated!
        if global_changed:
            logging.info("[StalenessTracker] Global configuration or template change detected. Invalidating all pages...")
            outdated.update(f.resolve() for f in all_files if not self.is_partial(f))
            # Short-circuit and return full re-build
            if commit and (deleted_files or global_changed or templates_changed):
                for d in deleted_files:
                    self.cache.data.get("files", {}).pop(d, None)
                    self.cache.data.get("dependencies", {}).pop(d, None)
                    self.cache.data.get("metadata", {}).pop(d, None)
                self.cache.save_cache()
            return outdated

        # 4. Re-verify the DAG: resolve reverse dependencies (parent links)
        _, reverse_deps = self._build_dependency_graph(files=all_files)

        # Recursively propagate changed/deleted files back up to their parents (ancestors)
        queue = list(changed_directly)
        visited = set(queue)
        while queue:
            curr = queue.pop(0)
            parents = reverse_deps.get(curr, set())
            for p_path in parents:
                if p_path not in visited:
                    if p_path.exists() and not self.is_partial(p_path):
                        outdated.add(p_path)
                    visited.add(p_path)
                    queue.append(p_path)

        # 5. Purge deleted files from the cache database
        if commit and (deleted_files or global_changed or templates_changed):
            for d in deleted_files:
                self.cache.data.get("files", {}).pop(d, None)
                self.cache.data.get("dependencies", {}).pop(d, None)
                self.cache.data.get("metadata", {}).pop(d, None)
            self.cache.save_cache()

        return outdated

    def update_cache_for_file(
        self,
        path: Path,
        included_files: list[str] | None = None,
        node_types: list[str] | None = None,
    ) -> None:
        """Update DAG cache entries, SHA-256 hashes, node types, and dependency relations for a document.

        Computes the SHA-256 digest of the specified document and updates `cache.data["files"]`
        and `cache.data["metadata"]`. Associates ASG structural node types (such as `["admonition", "listing"]`)
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
        >>> from pathlib import Path
        >>> import tempfile
        >>> from golem.cache import BuildCache
        >>> from golem.config import GolemConfig
        >>> from golem.staleness import StalenessTracker
        >>> with tempfile.TemporaryDirectory() as tmp_dir:
        ...     p = Path(tmp_dir)
        ...     content = p / "content"
        ...     content.mkdir()
        ...     doc = content / "index.adoc"
        ...     _ = doc.write_text("= Title\\nContent")
        ...     tracker = StalenessTracker(GolemConfig(), BuildCache(p / "cache.json"), content)
        ...     tracker.update_cache_for_file(doc)
        ...     str(doc.resolve()) in tracker.cache.data["files"]
        True
        ----
        """
        p_abs = str(path.resolve())
        self.cache.data.setdefault("files", {})[p_abs] = self.cache.get_sha256(path)
        meta = extract_metadata_from_doc(path)
        existing_meta = self.cache.data.get("metadata", {}).get(p_abs, {})
        if node_types is not None:
            meta["node_types"] = node_types
        elif isinstance(existing_meta, dict) and "node_types" in existing_meta:
            meta["node_types"] = existing_meta["node_types"]
        self.cache.data.setdefault("metadata", {})[p_abs] = meta
        if included_files is not None:
            unique_deps = list(dict.fromkeys(str(Path(f).resolve()) for f in included_files))
            self.cache.data.setdefault("dependencies", {})[p_abs] = unique_deps
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
            self.cache.data.setdefault("dependencies", {})[p_abs] = unique_deps

        # Compute and record the SHA-256 hashes for all of the dependency files as well!
        for dep in unique_deps:
            dep_path = Path(dep)
            if dep_path.exists():
                try:
                    self.cache.data.setdefault("files", {})[dep] = self.cache.get_sha256(dep_path)
                except Exception:
                    pass

        self.cache.save_cache()
