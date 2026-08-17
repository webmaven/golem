"""
= Site Build Orchestration and Incremental Compilation

This module drives the central compile orchestrator (`BuildEngine`) which
inspects source paths, parses content using `asciidoctrine`, renders bodies,
and maps dependency links into a JSON-based DAG cache.
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
from golem.renderer import render_body
from golem.templates import PageCompiler


def _title_from_filename(name: str) -> str:
    """Derive display title from a filename or directory name, stripping numeric prefixes."""
    stem = Path(name).stem if "." in name else name
    cleaned = re.sub(r"^\d+[-_.]\s*", "", stem)
    if not cleaned:
        cleaned = stem
    cleaned = cleaned.replace("-", " ").replace("_", " ")
    return " ".join(word.capitalize() for word in cleaned.split())


def _extract_title_from_doc(path: Path) -> str:
    """Extract first top-level header title from an AsciiDoc file, or fallback to cleaned filename."""
    if path.exists() and path.is_file():
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line_s = line.strip()
                    if line_s.startswith("= ") and not line_s.startswith("== "):
                        title = line_s[2:].strip()
                        if title:
                            return title
        except Exception:
            pass
    return _title_from_filename(path.name)


class BuildEngine:
    """
    = BuildEngine

    Incremental DAG compilation loop to parse, resolve, and generate pages.

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
        """
        == __init__

        Initialize compiler engine state and load existing DAG cache file.
        """
        self.config = config
        self.content_dir = Path(config.content_dir).resolve()
        self.config_path = (
            Path(config.config_path) if config.config_path else Path("golem.toml")
        )
        self.cache_file = (
            cache_file or Path(config.content_dir).parent / ".golem" / "cache.json"
        )
        self.cache_data = self._load_cache()
        self.compiler = PageCompiler(config)
        self.errors: list[dict[str, Any]] = []
        self.diagnostics: list[dict[str, Any]] = self.errors

        # Load Pluggy Plugin Manager
        from golem.plugins import get_plugin_manager

        plugins_dir = Path(getattr(config, "plugins_dir", "plugins"))
        self.pm = get_plugin_manager(plugins_dir=plugins_dir)
        self._sha_cache: dict[str, tuple[float, int, str]] = {}

    def _load_cache(self) -> dict:
        """
        == _load_cache

        Load and parse the DAG dependency JSON cache.
        """
        with self._cache_lock():
            if self.cache_file.exists():
                try:
                    with open(self.cache_file, "r") as f:
                        return json.load(f)
                except Exception:
                    try:
                        self.cache_file.unlink()
                    except Exception:
                        pass
            return {"files": {}, "dependencies": {}}

    def save_cache(self):
        """
        == save_cache

        Persist DAG compilation hashes back to the local file system atomically.
        """
        import os
        import tempfile

        with self._cache_lock():
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            dir_path = self.cache_file.parent
            with tempfile.NamedTemporaryFile(
                "w", dir=dir_path, delete=False, encoding="utf-8"
            ) as tf:
                json.dump(self.cache_data, tf, indent=2)
                temp_name = tf.name

            try:
                os.replace(temp_name, self.cache_file)
            except Exception:
                if os.path.exists(temp_name):
                    os.unlink(temp_name)
                raise

    @contextmanager
    def _cache_lock(self):
        """
        == _cache_lock

        Advisory cross-process lock using fcntl.flock on a dedicated lock file.
        """
        import fcntl

        lock_path = self.cache_file.parent / "cache.lock"
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)

        lock_fd = None
        try:
            lock_fd = open(lock_path, "w")
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
        except ImportError, AttributeError, OSError:
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

    def _get_sha256(self, path: Path) -> str:
        """
        == _get_sha256

        Compute SHA-256 hash of a file on disk, utilizing an in-memory mtime/size cache.
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
        """
        == get_outdated_files

        Resolve file hashes, detect deleted files, purge orphaned cache keys,
        and walk parents recursively to flag outdated nodes in the DAG.
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

        # 3. Map current file hashes and identify immediately changed files
        for f in all_files:
            f_abs = f.resolve()
            try:
                h = self._get_sha256(f)
                cached_hash = self.cache_data["files"].get(str(f_abs))
                if cached_hash != h:
                    changed_directly.add(f_abs)
                    outdated.add(f_abs)
            except Exception:
                # If there's an issue reading a file, treat it as changed/outdated
                changed_directly.add(f_abs)
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

        # Check template skeleton.pt
        theme_dir = Path("themes") / self.config.theme
        skeleton_pt = theme_dir / "skeleton.pt"
        if skeleton_pt.exists():
            h_pt = self._get_sha256(skeleton_pt)
            cached_pt = self.cache_data.get("meta", {}).get("skeleton_pt")
            if cached_pt != h_pt:
                global_changed = True
                if commit:
                    self.cache_data.setdefault("meta", {})["skeleton_pt"] = h_pt

        # If a global layout or config changed, we must mark all existing .adoc documents as outdated!
        if global_changed:
            logging.info(
                "[BuildEngine] Global configuration or template change detected. Invalidating all pages..."
            )
            outdated.update(all_files)
            # Short-circuit and return full re-build
            if commit and (deleted_files or global_changed):
                for d in deleted_files:
                    self.cache_data["files"].pop(d, None)
                    self.cache_data["dependencies"].pop(d, None)
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
                    if p_path.exists():
                        outdated.add(p_path)
                    visited.add(p_path)
                    queue.append(p_path)

        # 5. Purge deleted files from the cache database
        if commit and (deleted_files or global_changed):
            for d in deleted_files:
                self.cache_data["files"].pop(d, None)
                self.cache_data["dependencies"].pop(d, None)
            self.save_cache()

        return outdated

    def update_cache_for_file(
        self, path: Path, included_files: list[str] | None = None
    ):
        """
        == update_cache_for_file

        Parse inclusions inside an AsciiDoc file and record hashes to cache.
        """
        p_abs = str(path.resolve())
        self.cache_data["files"][p_abs] = self._get_sha256(path)
        if included_files is not None:
            unique_deps = list(
                dict.fromkeys(str(Path(f).resolve()) for f in included_files)
            )
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
                        with open(
                            f_path, "r", encoding="utf-8", errors="replace"
                        ) as f_in:
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

    def discover_navigation(self) -> list[dict[str, Any]]:
        """
        == discover_navigation

        Discover hierarchical site map and navigation tree from content files,
        supporting explicit config overrides (navigation_nav), index page pinning,
        and numeric prefix stripping.
        """
        # If navigation_nav is explicitly configured, use it as manual override order
        if (
            self.config.navigation_nav is not None
            and len(self.config.navigation_nav) > 0
        ):
            nav_items: list[dict[str, Any]] = []
            for item in self.config.navigation_nav:
                p = self.content_dir / item
                title = (
                    _extract_title_from_doc(p)
                    if p.exists()
                    else _title_from_filename(item)
                )
                rel_url = Path(item).with_suffix(".html").as_posix()
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

            valid_entries = [
                e
                for e in entries
                if not e.name.startswith(".") and not e.name.startswith("__")
            ]

            files = [e for e in valid_entries if e.is_file() and e.suffix == ".adoc"]
            dirs = [e for e in valid_entries if e.is_dir()]

            files.sort(key=lambda x: x.name.lower())
            dirs.sort(key=lambda x: x.name.lower())

            index_file: Path | None = None
            for f in files:
                if f.stem.lower() in ("index", "readme"):
                    index_file = f
                    break

            if current_dir == self.content_dir and index_file is not None:
                rel_p = index_file.relative_to(self.content_dir).as_posix()
                rel_u = (
                    index_file.relative_to(self.content_dir)
                    .with_suffix(".html")
                    .as_posix()
                )
                title = _extract_title_from_doc(index_file)
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
                rel_u = f.relative_to(self.content_dir).with_suffix(".html").as_posix()
                title = _extract_title_from_doc(f)
                items.append(
                    {
                        "title": title,
                        "path": rel_p,
                        "url": rel_u,
                        "children": [],
                    }
                )

            for d in dirs:
                sub_index: Path | None = None
                try:
                    for sub_f in d.iterdir():
                        if (
                            sub_f.is_file()
                            and sub_f.suffix == ".adoc"
                            and sub_f.stem.lower() in ("index", "readme")
                        ):
                            sub_index = sub_f
                            break
                except Exception:
                    pass

                sub_children = build_tree(d)

                if sub_index is not None:
                    sec_title = _extract_title_from_doc(sub_index)
                    sec_url = (
                        sub_index.relative_to(self.content_dir)
                        .with_suffix(".html")
                        .as_posix()
                    )
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
        """
        == generate_nav_html

        Render navigation tree into semantic HTML with proper relative links.
        """
        nav_tree = self.discover_navigation()
        if not nav_tree:
            return ""

        prefix = ""
        if current_rel_path is not None:
            depth = len(current_rel_path.parent.parts)
            if depth > 0:
                prefix = "../" * depth

        def render_list(
            items: list[dict[str, Any]], is_nested: bool = False
        ) -> list[str]:
            ul_class = "golem-nav-sublist" if is_nested else "golem-nav-list"
            out = [f'<ul class="{ul_class}">\n']
            for item in items:
                title = item.get("title", "")
                url = item.get("url")
                children = item.get("children", [])
                href = f"{prefix}{url}" if url else None

                if children:
                    out.append('  <li class="golem-nav-section">\n')
                    if href:
                        out.append(
                            f'    <span class="golem-nav-section-title"><a href="{href}">{title}</a></span>\n'
                        )
                    else:
                        out.append(
                            f'    <span class="golem-nav-section-title">{title}</span>\n'
                        )
                    out.extend(render_list(children, is_nested=True))
                    out.append("  </li>\n")
                else:
                    out.append('  <li class="golem-nav-item">')
                    if href:
                        out.append(f'<a href="{href}">{title}</a>')
                    else:
                        out.append(f"<span>{title}</span>")
                    out.append("</li>\n")
            out.append("</ul>\n")
            return out

        res = ['<nav class="golem-nav">\n']
        res.extend(render_list(nav_tree, is_nested=False))
        res.append("</nav>")
        return "".join(res)

    def _get_template_search_paths(self) -> list[Path]:
        """Collect template search paths for asciidoctype / Chameleon."""
        paths: list[Path] = []
        if hasattr(self.config, "templates_dir") and self.config.templates_dir:
            tpl_path = Path(self.config.templates_dir)
            paths.append(tpl_path.resolve() if tpl_path.exists() else tpl_path)

        if hasattr(self.config, "theme") and self.config.theme:
            theme_path = Path("themes") / self.config.theme
            paths.append(theme_path.resolve() if theme_path.exists() else theme_path)

        return paths

    def build_site(self) -> list[Path]:
        """
        == build_site

        Orchestrate complete Golem compilation of outdated adoc pages.
        """
        self.errors = []
        self.diagnostics = self.errors
        compiled_files = []
        outdated = self.get_outdated_files()

        all_docs = (
            list(self.content_dir.glob("**/*.adoc"))
            if self.content_dir.exists()
            else []
        )
        to_build = outdated if (outdated or self.cache_data["files"]) else set(all_docs)

        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        search_paths = self._get_template_search_paths()

        for doc_path in to_build:
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

                # Generate dynamic navigation HTML for this page
                rel_path = doc_path.relative_to(self.content_dir)
                nav_html = self.generate_nav_html(current_rel_path=rel_path)

                final_html = self.compiler.compile_page(
                    title=title_str,
                    body_content=body_content,
                    toc_html=toc_html,
                    nav_html=nav_html,
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
                self.update_cache_for_file(doc_path, getattr(ast, "included_files", []))
                compiled_files.append(out_path)

                # Progress logging
                try:
                    rel_doc = doc_path.relative_to(Path.cwd())
                except ValueError:
                    rel_doc = (
                        doc_path.relative_to(self.content_dir)
                        if self.content_dir in doc_path.parents
                        else doc_path
                    )
                try:
                    rel_out = out_path.relative_to(Path.cwd())
                except ValueError:
                    rel_out = (
                        out_path.relative_to(output_dir)
                        if output_dir in out_path.parents
                        else out_path
                    )
                import click

                click.echo(f"  [COMPILE] {rel_doc} -> {rel_out}")
            except Exception as e:
                error_info = {
                    "file": str(doc_path),
                    "message": str(e),
                    "error_type": type(e).__name__,
                    "exception": e,
                    "line": getattr(e, "line", None),
                    "column": getattr(e, "column", None),
                    "context": getattr(e, "context", None),
                }
                self.errors.append(error_info)
                logging.error(f"Failed to build file {doc_path}: {e}")
                if getattr(self.config, "strict", False):
                    raise e

        return compiled_files
