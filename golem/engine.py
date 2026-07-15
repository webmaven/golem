"""
= Site Build Orchestration and Incremental Compilation

This module drives the central compile orchestrator (`BuildEngine`) which
inspects source paths, parses content using `asciidoctrine`, renders bodies,
and maps dependency links into a JSON-based DAG cache.
"""

import hashlib
import json
import logging
from pathlib import Path
import asciidoctrine
from asciidoctrine.resolver import ASGResolver
from golem.config import GolemConfig
from golem.renderer import render_body
from golem.templates import PageCompiler


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

    def __init__(self, config: GolemConfig, cache_file: Path = None):
        """
        == __init__

        Initialize compiler engine state and load existing DAG cache file.
        """
        self.config = config
        self.content_dir = Path(config.content_dir).resolve()
        self.cache_file = (
            cache_file or Path(config.content_dir).parent / ".golem" / "cache.json"
        )
        self.cache_data = self._load_cache()
        self.compiler = PageCompiler(config)

    def _load_cache(self) -> dict:
        """
        == _load_cache

        Load and parse the DAG dependency JSON cache.
        """
        if self.cache_file.exists():
            try:
                with open(self.cache_file, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"files": {}, "dependencies": {}}

    def save_cache(self):
        """
        == save_cache

        Persist DAG compilation hashes back to the local file system.
        """
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_file, "w") as f:
            json.dump(self.cache_data, f, indent=2)

    def _get_sha256(self, path: Path) -> str:
        """
        == _get_sha256

        Compute SHA-256 hash of a file on disk.
        """
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(8192):
                h.update(chunk)
        return h.hexdigest()

    def get_outdated_files(self) -> set[Path]:
        """
        == get_outdated_files

        Resolve file hashes and walk parents recursively to flag outdated nodes.
        """
        outdated = set()
        if not self.content_dir.exists():
            return outdated
        all_files = list(self.content_dir.glob("**/*.adoc"))

        # 1. Map current file hashes and identify immediately changed files
        current_hashes = {}
        changed_directly = set()
        for f in all_files:
            f_abs = f.resolve()
            h = self._get_sha256(f)
            current_hashes[str(f_abs)] = h
            cached_hash = self.cache_data["files"].get(str(f_abs))
            if cached_hash != h:
                changed_directly.add(f_abs)
                outdated.add(f_abs)

        # 2. Re-verify the DAG: pull and resolve all native inclusions
        reverse_deps: dict[str, set[str]] = {}
        for f in all_files:
            f_abs = str(f.resolve())
            cached_deps = self.cache_data["dependencies"].get(f_abs, [])
            for dep in cached_deps:
                reverse_deps.setdefault(dep, set()).add(f_abs)

        # Recursively propagate changed files back up to their parents (ancestors)
        queue = list(changed_directly)
        visited = set(queue)
        while queue:
            curr = str(queue.pop(0))
            parents = reverse_deps.get(curr, set())
            for p in parents:
                p_path = Path(p)
                if p_path not in visited:
                    outdated.add(p_path)
                    visited.add(p_path)
                    queue.append(p_path)

        return outdated

    def update_cache_for_file(self, path: Path, included_files: list[str] = None):
        """
        == update_cache_for_file

        Parse inclusions inside an AsciiDoc file and record hashes to cache.
        """
        p_abs = str(path.resolve())
        self.cache_data["files"][p_abs] = self._get_sha256(path)
        if included_files is not None:
            self.cache_data["dependencies"][p_abs] = [
                str(Path(f).resolve()) for f in included_files
            ]
        else:
            deps = []
            try:
                with open(path, "r", encoding="utf-8") as f:
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
                        with open(f_path, "r", encoding="utf-8") as f_in:
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
        self.save_cache()

    def build_site(self) -> list[Path]:
        """
        == build_site

        Orchestrate complete Golem compilation of outdated adoc pages.
        """
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

        for doc_path in to_build:
            try:
                with open(doc_path, "r", encoding="utf-8") as f:
                    content = f.read()

                # 1. Parse using asciidoctrine
                ast = asciidoctrine.parse_to_ast(content, base_dir=str(doc_path.parent))

                # 2. Resolve AST to ASG
                resolver = ASGResolver(ast)
                asg = resolver.resolve(ast)

                # 3. Render body using Golem's ASG visitor
                body_content = render_body(asg)

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
                final_html = self.compiler.compile_page(
                    title=title_str, body_content=body_content, toc_html=""
                )

                # 5. Resolve correct output file path
                rel_path = doc_path.relative_to(self.content_dir)
                out_path = output_dir / rel_path.with_suffix(".html")
                out_path.parent.mkdir(parents=True, exist_ok=True)

                # 6. Write final page to disk
                with open(out_path, "w", encoding="utf-8") as f_out:
                    f_out.write(final_html)

                # 7. Update file dependency hash in DAG cache
                self.update_cache_for_file(doc_path, getattr(ast, "included_files", []))
                compiled_files.append(out_path)
            except Exception as e:
                logging.error(f"Failed to build file {doc_path}: {e}")

        return compiled_files
