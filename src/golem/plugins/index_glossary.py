"""Provide index and glossary accumulation and compilation plugins for Golem documentation.

Collects AsciiDoc index terms (`indexterm:[...]`, `((term))`, `(((primary, secondary, tertiary)))`)
and glossary definition list blocks (`[glossary]`) across compiled documents, providing
structured alphabetized indexes and glossaries.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import asciidoctrine
from asciidoctrine.nodes import DescriptionList, IndexTerm
from golem.model import AsgVisitor, GlossaryEntry, Node, PageContext
from golem.plugins import GolemPlugin, hookimpl

__all__ = [
    "GlossaryPlugin",
    "IndexPlugin",
]

logger = logging.getLogger(__name__)


def _extract_text(node: Any) -> str:
    """Extract and concatenate visible plain text from an AST node or subtree.

    [parameters]
    `node` (Any):: AST/ASG node, string, dictionary, or sequence.

    [returns]
    `str`:: Extracted plain text string, stripped of leading and trailing whitespace.
    """
    if node is None:
        return ""
    if isinstance(node, str):
        return node.strip()
    if hasattr(node, "walk"):
        parts: list[str] = []
        for child in node.walk():
            if hasattr(child, "value") and isinstance(child.value, str):
                parts.append(child.value)
        return "".join(parts).strip()
    if hasattr(node, "value") and isinstance(node.value, str):
        return node.value.strip()
    if isinstance(node, dict):
        if "value" in node and isinstance(node["value"], str):
            return node["value"].strip()
        if "text" in node and isinstance(node["text"], str):
            return node["text"].strip()
        parts = []
        for key in ("inlines", "children", "blocks"):
            children = node.get(key)
            if isinstance(children, list):
                for child in children:
                    txt = _extract_text(child)
                    if txt:
                        parts.append(txt)
        return " ".join(parts).strip()
    return ""


def _is_glossary_list(node: Any) -> bool:
    """Determine whether a description list node represents a glossary.

    [parameters]
    `node` (Any):: DescriptionList AST node or dictionary to inspect.

    [returns]
    `bool`:: True if the node is a description list with a glossary style or role.
    """
    if isinstance(node, dict):
        attrs = node.get("attributes")
    else:
        attrs = getattr(node, "attributes", None)

    if isinstance(attrs, dict):
        if attrs.get("role") == "glossary" or attrs.get("style") == "glossary":
            return True
        if attrs.get("1") == "glossary":
            return True
        positional = attrs.get("positional")
        if isinstance(positional, list) and "glossary" in positional:
            return True
        roles = attrs.get("roles")
        if isinstance(roles, (list, set)) and "glossary" in roles:
            return True
        if isinstance(roles, str) and "glossary" in roles.split():
            return True

    if isinstance(node, dict):
        if node.get("role") == "glossary" or node.get("style") == "glossary":
            return True
    elif getattr(node, "role", None) == "glossary" or getattr(node, "style", None) == "glossary":
        return True

    return False


def _extract_definition_list_terms(item: Any) -> list[str]:
    """Extract term strings from a description list item.

    [parameters]
    `item` (Any):: DescriptionListItem node or dictionary.

    [returns]
    `list[str]`:: List of cleaned term strings.
    """
    terms: list[str] = []
    if isinstance(item, dict):
        raw_terms = item.get("terms")
    else:
        raw_terms = getattr(item, "terms", None)

    if raw_terms is not None:
        if isinstance(raw_terms, (list, tuple)):
            for t in raw_terms:
                txt = _extract_text(t)
                if txt:
                    terms.append(txt)
        else:
            txt = _extract_text(raw_terms)
            if txt:
                terms.append(txt)
    elif isinstance(item, dict) and "term" in item:
        txt = _extract_text(item["term"])
        if txt:
            terms.append(txt)
    elif hasattr(item, "term"):
        txt = _extract_text(getattr(item, "term"))
        if txt:
            terms.append(txt)

    return terms


def _extract_definition_list_blocks(item: Any) -> str:
    """Extract and format definition text from a description list item.

    [parameters]
    `item` (Any):: DescriptionListItem node or dictionary.

    [returns]
    `str`:: Combined definition text formatted across paragraphs.
    """
    if isinstance(item, dict):
        if "definition" in item:
            return str(item["definition"]).strip()
        if "description" in item:
            return str(item["description"]).strip()
        if "blocks" in item and isinstance(item["blocks"], list):
            parts = [_extract_text(b) for b in item["blocks"]]
            return "\n\n".join(p for p in parts if p)
        if "text" in item:
            return str(item["text"]).strip()
    else:
        blocks = getattr(item, "blocks", None)
        if blocks:
            parts = [_extract_text(b) for b in blocks]
            return "\n\n".join(p for p in parts if p)

        for attr in ("definition", "description", "text"):
            val = getattr(item, attr, None)
            if val is not None:
                return _extract_text(val)

    return ""


def _is_page_role(context: PageContext | dict[str, Any], role_name: str) -> bool:
    """Check if template context or document attributes declare a specific page role.

    [parameters]
    `context` (PageContext | dict[str, Any]):: Chameleon template context dictionary.
    `role_name` (str):: Expected role string (e.g. `"index"` or `"glossary"`).

    [returns]
    `bool`:: True if context or attributes declare the target role.
    """
    target = role_name.strip().lower()

    # Direct context keys
    for key in ("page-role", "page_role", "role"):
        val = context.get(key)
        if isinstance(val, str) and val.strip().lower() == target:
            return True

    # Nested document attributes (doc_attributes, attributes)
    for attr_key in ("doc_attributes", "attributes"):
        attrs = context.get(attr_key)
        if isinstance(attrs, dict):
            for key in ("page-role", "page_role", "role"):
                val = attrs.get(key)
                if isinstance(val, str) and val.strip().lower() == target:
                    return True

    return False


class AsgCollectorVisitor(AsgVisitor):
    """AST/ASG visitor for extracting index terms and glossary definition lists."""

    def __init__(
        self,
        index_entries: dict[str, dict[str, Any]] | None = None,
        glossary_entries: dict[str, dict[str, Any]] | None = None,
        doc_path_str: str = "",
    ) -> None:
        self.index_entries = index_entries
        self.glossary_entries = glossary_entries
        self.doc_path_str = doc_path_str

    def visit(self, node: Any, **kwargs: Any) -> Any:
        """Visit an AST node or dictionary representation."""
        if node is None:
            return None
        if isinstance(node, IndexTerm):
            return self.visit_indexterm(node, **kwargs)
        if isinstance(node, DescriptionList):
            return self.visit_descriptionlist(node, **kwargs)
        if isinstance(node, dict):
            name = str(node.get("name", "")).lower()
            if name == "indexterm" or ("terms" in node and node.get("type") == "inline"):
                return self.visit_indexterm(node, **kwargs)
            if name in ("descriptionlist", "dlist", "description_list"):
                return self.visit_descriptionlist(node, **kwargs)
            method_name = f"visit_{name}"
            visitor = getattr(self, method_name, self.generic_visit)
            return visitor(node, **kwargs)
        if isinstance(node, Node):
            method_name = f"visit_{node.name.lower()}"
            visitor = getattr(self, method_name, self.generic_visit)
            return visitor(node, **kwargs)
        return self.generic_visit(node, **kwargs)

    def generic_visit(self, node: Any, **kwargs: Any) -> Any:
        """Traverse child collections of a Node or dictionary."""
        if isinstance(node, Node):
            super().generic_visit(node, **kwargs)
        elif isinstance(node, dict):
            for key in ("blocks", "items", "inlines", "children"):
                children = node.get(key)
                if isinstance(children, list):
                    for child in children:
                        self.visit(child, **kwargs)
        elif isinstance(node, (list, tuple)):
            for item in node:
                self.visit(item, **kwargs)

    def visit_indexterm(self, node: Any, **kwargs: Any) -> Any:
        """Collect index term components into accumulated index entries."""
        if self.index_entries is not None:
            self._collect_index_term(node)
        return self.generic_visit(node, **kwargs)

    def visit_descriptionlist(self, node: Any, **kwargs: Any) -> Any:
        """Collect glossary definition entries from glossary description lists."""
        if self.glossary_entries is not None and _is_glossary_list(node):
            self._collect_glossary_list(node)
        return self.generic_visit(node, **kwargs)

    def _collect_index_term(self, node: Any) -> None:
        if self.index_entries is None:
            return

        if isinstance(node, dict):
            raw_terms = node.get("terms")
            if not raw_terms:
                prim = node.get("primary")
                if prim:
                    raw_terms = [prim]
                    if node.get("secondary"):
                        raw_terms.append(node.get("secondary"))
                        if node.get("tertiary"):
                            raw_terms.append(node.get("tertiary"))
        else:
            raw_terms = getattr(node, "terms", None)

        if not raw_terms:
            return

        terms: list[str] = []
        for t in raw_terms:
            txt = _extract_text(t) if not isinstance(t, str) else t.strip()
            if txt:
                terms.append(txt)

        if not terms:
            return

        primary = terms[0]
        secondary = terms[1] if len(terms) > 1 else None
        tertiary = terms[2] if len(terms) > 2 else None

        letter = primary[0].upper() if primary else ""
        if letter not in self.index_entries:
            self.index_entries[letter] = {}

        if primary not in self.index_entries[letter]:
            self.index_entries[letter][primary] = {
                "locations": [],
                "secondary": {},
            }

        entry = self.index_entries[letter][primary]
        if self.doc_path_str and self.doc_path_str not in entry["locations"]:
            entry["locations"].append(self.doc_path_str)

        if secondary:
            sec_map = entry["secondary"]
            if secondary not in sec_map:
                sec_map[secondary] = {
                    "locations": [],
                    "secondary": {},
                }
            sec_entry = sec_map[secondary]
            if self.doc_path_str and self.doc_path_str not in sec_entry["locations"]:
                sec_entry["locations"].append(self.doc_path_str)

            if tertiary:
                tert_map = sec_entry["secondary"]
                if tertiary not in tert_map:
                    tert_map[tertiary] = {
                        "locations": [],
                        "secondary": {},
                    }
                tert_entry = tert_map[tertiary]
                if self.doc_path_str and self.doc_path_str not in tert_entry["locations"]:
                    tert_entry["locations"].append(self.doc_path_str)

    def _collect_glossary_list(self, node: Any) -> None:
        if self.glossary_entries is None:
            return

        if isinstance(node, dict):
            items = node.get("items") or node.get("children") or node.get("blocks")
        else:
            items = getattr(node, "items", None)

        if not items or not isinstance(items, (list, tuple)):
            return

        for item in items:
            terms = _extract_definition_list_terms(item)
            definition = _extract_definition_list_blocks(item)
            for term in terms:
                if term in self.glossary_entries:
                    logger.warning(
                        "Glossary term '%s' was redefined within '%s'; subsequent definition overwrites earlier ones",
                        term,
                        self.doc_path_str,
                    )
                self.glossary_entries[term] = {
                    "term": term,
                    "definition": definition,
                    "doc_path": self.doc_path_str,
                }


def _find_aggregator_pages(
    cache_metadata: dict[str, dict[str, Any]],
    role_name: str,
) -> list[Path]:
    """Find all source document paths declaring the specified page role in cache metadata.

    [parameters]
    `cache_metadata` (dict[str, dict[str, Any]]):: Cached build metadata mapping file paths to node types and attributes.
    `role_name` (str):: Expected page role string (e.g. `"index"` or `"glossary"`).

    [returns]
    `list[Path]`:: List of Path objects for documents matching the page role.
    """
    target = role_name.strip().lower()
    pages: list[Path] = []
    for path_str, meta in cache_metadata.items():
        if not isinstance(meta, dict):
            continue
        role = meta.get("page_role") or meta.get("page-role") or meta.get("role")
        if isinstance(role, str) and role.strip().lower() == target:
            pages.append(Path(path_str))
    return pages


def _lookup_meta(
    path: Path,
    cache_metadata: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Retrieve metadata dictionary for a given path from cache_metadata.

    [parameters]
    `path` (Path):: Target file path to locate.
    `cache_metadata` (dict[str, dict[str, Any]]):: Cached build metadata mapping file paths to metadata dictionaries.

    [returns]
    `dict[str, Any] | None`:: Matching metadata dictionary if found, otherwise None.
    """
    p_abs = str(path.resolve())
    if p_abs in cache_metadata:
        return cache_metadata[p_abs]
    p_str = str(path)
    if p_str in cache_metadata:
        return cache_metadata[p_str]
    for k, v in cache_metadata.items():
        try:
            if Path(k).resolve() == path.resolve():
                return v
        except Exception:
            pass
    return None


def _get_or_create_doc_meta(
    path: Path,
    cache_metadata: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Retrieve or initialize metadata dictionary for a given path in cache_metadata.

    [parameters]
    `path` (Path):: Target file path to locate or create.
    `cache_metadata` (dict[str, dict[str, Any]]):: Cached build metadata mapping file paths to metadata dictionaries.

    [returns]
    `dict[str, Any]`:: Matching or newly initialized metadata dictionary.
    """
    existing = _lookup_meta(path, cache_metadata)
    if existing is not None and isinstance(existing, dict):
        return existing
    p_abs = str(path.resolve())
    new_meta: dict[str, Any] = {}
    cache_metadata[p_abs] = new_meta
    return new_meta


def _merge_index_entries(
    target: dict[str, dict[str, Any]],
    source: dict[str, dict[str, Any]],
) -> None:
    """Merge source index entries into target index entries in-place.

    [parameters]
    `target` (dict[str, dict[str, Any]]):: Destination index entries mapping letters to terms.
    `source` (dict[str, dict[str, Any]]):: Source index entries mapping letters to terms to merge.

    [returns]
    `None`:: Modifies target dictionary in place.
    """
    for letter, terms in source.items():
        if not isinstance(terms, dict):
            continue
        if letter not in target:
            target[letter] = {}

        for term, entry_data in terms.items():
            if not isinstance(entry_data, dict):
                continue
            if term not in target[letter]:
                target[letter][term] = {
                    "locations": list(entry_data.get("locations", [])),
                    "secondary": {},
                }
            else:
                for loc in entry_data.get("locations", []):
                    if loc not in target[letter][term]["locations"]:
                        target[letter][term]["locations"].append(loc)

            target_sec = target[letter][term].setdefault("secondary", {})
            source_sec = entry_data.get("secondary", {})
            if isinstance(source_sec, dict):
                for sec_term, sec_data in source_sec.items():
                    if not isinstance(sec_data, dict):
                        continue
                    if sec_term not in target_sec:
                        target_sec[sec_term] = {
                            "locations": list(sec_data.get("locations", [])),
                            "secondary": {},
                        }
                    else:
                        for loc in sec_data.get("locations", []):
                            if loc not in target_sec[sec_term]["locations"]:
                                target_sec[sec_term]["locations"].append(loc)

                    target_tert = target_sec[sec_term].setdefault("secondary", {})
                    source_tert = sec_data.get("secondary", {})
                    if isinstance(source_tert, dict):
                        for tert_term, tert_data in source_tert.items():
                            if not isinstance(tert_data, dict):
                                continue
                            if tert_term not in target_tert:
                                target_tert[tert_term] = {
                                    "locations": list(tert_data.get("locations", [])),
                                }
                            else:
                                for loc in tert_data.get("locations", []):
                                    if loc not in target_tert[tert_term]["locations"]:
                                        target_tert[tert_term]["locations"].append(loc)


def _file_has_index_terms(path: Path) -> bool:
    """Check if a file on disk contains AsciiDoc index terms.

    [parameters]
    `path` (Path):: File path on disk to inspect.

    [returns]
    `bool`:: True if the file contains indexterm macros or syntax.
    """
    if not path.exists() or not path.is_file() or path.suffix != ".adoc":
        return False
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        if "indexterm:" not in content and "((" not in content:
            return False
        doc = asciidoctrine.loads(content)
        visitor = AsgCollectorVisitor(index_entries={})
        visitor.visit(doc)
        return bool(visitor.index_entries)
    except Exception:
        return False


def _file_has_glossary_definitions(path: Path) -> bool:
    """Check if a file on disk contains AsciiDoc glossary definition lists.

    [parameters]
    `path` (Path):: File path on disk to inspect.

    [returns]
    `bool`:: True if the file contains glossary definition lists.
    """
    if not path.exists() or not path.is_file() or path.suffix != ".adoc":
        return False
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        if "[glossary]" not in content and "glossary" not in content.lower():
            return False
        doc = asciidoctrine.loads(content)
        visitor = AsgCollectorVisitor(glossary_entries={})
        visitor.visit(doc)
        return bool(visitor.glossary_entries)
    except Exception:
        return False


class IndexPlugin(GolemPlugin):
    """Collect and compile index terms across documentation pages.

    Traverses ASG documents for `IndexTerm` occurrences, accumulating primary,
    secondary, and tertiary terms with their source document paths, and produces
    alphabetized hierarchical index structures.
    """

    name = "index"

    def __init__(self, cache: Any = None, **extra: Any) -> None:
        super().__init__(**extra)
        self.cache = cache
        self._entries: dict[str, dict[str, Any]] = {}
        self._compiled_doc_paths: set[str] = set()
        self._cache_metadata: dict[str, dict[str, Any]] | None = None

    @classmethod
    def from_config(cls, config: Any = None) -> IndexPlugin:
        """Construct an IndexPlugin instance from configuration.

        [parameters]
        `config` (Any, optional):: Site configuration object or dictionary. Defaults to `None`.

        [returns]
        `IndexPlugin`:: Configured index plugin instance.
        """
        instance = super().from_config(config)
        if config is not None and hasattr(config, "cache"):
            instance.cache = getattr(config, "cache")
        return instance

    def _get_cache_metadata(self) -> dict[str, dict[str, Any]] | None:
        if self.cache is not None and hasattr(self.cache, "data") and isinstance(self.cache.data, dict):
            return self.cache.data.setdefault("metadata", {})
        return self._cache_metadata

    @hookimpl
    def on_asg_created(self, asg: Node, doc_path: Path | None = None) -> Node:
        """Walk the ASG collecting IndexTerm nodes, accumulating into self._entries.

        [parameters]
        `asg` (Node):: Root ASG document node to inspect.
        `doc_path` (Path | None, optional):: Path to the documentation source file.

        [returns]
        `Node`:: Unmodified ASG node.
        """
        doc_path_str = str(doc_path) if doc_path is not None else ""
        file_entries: dict[str, dict[str, Any]] = {}
        visitor = AsgCollectorVisitor(index_entries=file_entries, doc_path_str=doc_path_str)
        visitor.visit(asg)

        _merge_index_entries(self._entries, file_entries)

        if doc_path is not None:
            self._compiled_doc_paths.add(str(doc_path.resolve()))
            self._compiled_doc_paths.add(doc_path_str)

            metadata = self._get_cache_metadata()
            if metadata is not None:
                doc_meta = _get_or_create_doc_meta(doc_path, metadata)
                doc_meta["index_entries"] = file_entries

        return asg

    def _seed_from_cache(self) -> None:
        """Merge cached index entries from unchanged files into self._entries."""
        metadata = self._get_cache_metadata()
        if not metadata:
            return

        to_evict: list[str] = []
        for doc_path_str, meta in list(metadata.items()):
            if not isinstance(meta, dict):
                continue
            p = Path(doc_path_str)
            if not p.exists() and not p.resolve().exists():
                to_evict.append(doc_path_str)
                continue

            resolved_str = str(p.resolve())
            if resolved_str in self._compiled_doc_paths or doc_path_str in self._compiled_doc_paths:
                continue

            cached_entries = meta.get("index_entries")
            if isinstance(cached_entries, dict):
                _merge_index_entries(self._entries, cached_entries)

        if to_evict:
            for k in to_evict:
                metadata.pop(k, None)
            if self.cache is not None and hasattr(self.cache, "save_cache"):
                try:
                    self.cache.save_cache()
                except Exception:
                    pass

    def compile_index(self) -> dict[str, dict[str, Any]]:
        """Return alphabetized hierarchical index compiled from collected terms.

        [returns]
        `dict[str, dict[str, Any]]`:: Nested dictionary mapping first letters to term entries and subterms.
        """
        self._seed_from_cache()
        result: dict[str, dict[str, Any]] = {}
        for letter in sorted(self._entries.keys()):
            result[letter] = {}
            for term in sorted(self._entries[letter].keys(), key=lambda s: (s.lower(), s)):
                entry_data = self._entries[letter][term]
                compiled_term: dict[str, Any] = {
                    "locations": sorted(entry_data["locations"]),
                    "secondary": {},
                    "subterms": {},
                }
                for sec_term in sorted(entry_data["secondary"].keys(), key=lambda s: (s.lower(), s)):
                    sec_data = entry_data["secondary"][sec_term]
                    compiled_sec: dict[str, Any] = {
                        "locations": sorted(sec_data["locations"]),
                        "secondary": {},
                        "subterms": {},
                    }
                    for tert_term in sorted(sec_data.get("secondary", {}).keys(), key=lambda s: (s.lower(), s)):
                        tert_data = sec_data["secondary"][tert_term]
                        compiled_tert: dict[str, Any] = {
                            "locations": sorted(tert_data["locations"]),
                        }
                        compiled_sec["secondary"][tert_term] = compiled_tert
                        compiled_sec["subterms"][tert_term] = compiled_tert

                    compiled_term["secondary"][sec_term] = compiled_sec
                    compiled_term["subterms"][sec_term] = compiled_sec

                result[letter][term] = compiled_term

        return result

    def reset(self) -> None:
        """Clear accumulated index entries.

        [returns]
        `None`:: Clears state in place with no return value.
        """
        self._entries.clear()
        self._compiled_doc_paths.clear()

    @hookimpl
    def on_build_start(self, config: Any = None) -> None:
        """Reset state at the beginning of each build run.

        [parameters]
        `config` (Any, optional):: Site configuration object. Defaults to `None`.

        [returns]
        `None`:: Clears state in place.
        """
        self.reset()

    @hookimpl
    def on_template_context(self, context: PageContext, doc_path: Path) -> PageContext:
        """Inject compiled index into template context if page declares index role.

        [parameters]
        `context` (PageContext):: Chameleon template context dictionary.
        `doc_path` (Path):: Path to the documentation source file being processed.

        [returns]
        `PageContext`:: Enriched template context containing `site_index` if role matches.
        """
        if _is_page_role(context, "index"):
            context.update({"site_index": self.compile_index()})
        return context

    @hookimpl
    def golem_mark_stale(
        self,
        changed_files: list[Path],
        cache_metadata: dict[str, dict[str, Any]],
    ) -> list[Path] | None:
        """Register index aggregator pages for recompilation when documents with index terms change.

        [parameters]
        `changed_files` (list[Path]):: List of file paths directly modified or deleted in the current build cycle.
        `cache_metadata` (dict[str, dict[str, Any]]):: Cached build metadata mapping file paths to node types and attributes.

        [returns]
        `list[Path] | None`:: List of index aggregator pages to recompile, or `None` if no invalidation is needed.
        """
        self._cache_metadata = cache_metadata
        aggregator_pages = _find_aggregator_pages(cache_metadata, "index")
        if not aggregator_pages:
            return None

        for f in changed_files:
            meta = _lookup_meta(f, cache_metadata)
            if meta and isinstance(meta, dict):
                node_types = meta.get("node_types")
                if isinstance(node_types, (list, tuple, set)):
                    if any(str(nt).lower() in ("indexterm", "index_term", "index") for nt in node_types):
                        return aggregator_pages
            if _file_has_index_terms(f):
                return aggregator_pages

        return None


class GlossaryPlugin(GolemPlugin):
    """Collect and compile glossary definitions across documentation pages.

    Traverses ASG documents for description list blocks annotated with `[glossary]`,
    accumulating term definitions with their origin document paths, and produces
    alphabetized glossary collections.
    """

    name = "glossary"

    def __init__(self, cache: Any = None, **extra: Any) -> None:
        super().__init__(**extra)
        self.cache = cache
        self._entries: dict[str, dict[str, Any]] = {}
        self._compiled_doc_paths: set[str] = set()
        self._cache_metadata: dict[str, dict[str, Any]] | None = None

    @classmethod
    def from_config(cls, config: Any = None) -> GlossaryPlugin:
        """Construct a GlossaryPlugin instance from configuration.

        [parameters]
        `config` (Any, optional):: Site configuration object or dictionary. Defaults to `None`.

        [returns]
        `GlossaryPlugin`:: Configured glossary plugin instance.
        """
        instance = super().from_config(config)
        if config is not None and hasattr(config, "cache"):
            instance.cache = getattr(config, "cache")
        return instance

    def _get_cache_metadata(self) -> dict[str, dict[str, Any]] | None:
        if self.cache is not None and hasattr(self.cache, "data") and isinstance(self.cache.data, dict):
            return self.cache.data.setdefault("metadata", {})
        return self._cache_metadata

    @hookimpl
    def on_asg_created(self, asg: Node, doc_path: Path | None = None) -> Node:
        """Walk the ASG collecting glossary definition list entries.

        [parameters]
        `asg` (Node):: Root ASG document node to inspect.
        `doc_path` (Path | None, optional):: Path to the documentation source file.

        [returns]
        `Node`:: Unmodified ASG node.
        """
        doc_path_str = str(doc_path) if doc_path is not None else ""
        file_entries: dict[str, dict[str, Any]] = {}
        visitor = AsgCollectorVisitor(glossary_entries=file_entries, doc_path_str=doc_path_str)
        visitor.visit(asg)

        for term, entry in file_entries.items():
            if term in self._entries:
                old_doc_path = self._entries[term].get("doc_path", "")
                new_doc_path = entry.get("doc_path", doc_path_str)
                if old_doc_path != new_doc_path:
                    logger.warning(
                        "Glossary term '%s' defined in '%s' collides with existing definition from '%s'; '%s' definition takes precedence (last page wins)",
                        term,
                        new_doc_path,
                        old_doc_path,
                        new_doc_path,
                    )
            self._entries[term] = entry

        if doc_path is not None:
            self._compiled_doc_paths.add(str(doc_path.resolve()))
            self._compiled_doc_paths.add(doc_path_str)

            metadata = self._get_cache_metadata()
            if metadata is not None:
                doc_meta = _get_or_create_doc_meta(doc_path, metadata)
                doc_meta["glossary_entries"] = file_entries

        return asg

    def _seed_from_cache(self) -> None:
        """Merge cached glossary entries from unchanged files into self._entries."""
        metadata = self._get_cache_metadata()
        if not metadata:
            return

        to_evict: list[str] = []
        for doc_path_str, meta in list(metadata.items()):
            if not isinstance(meta, dict):
                continue
            p = Path(doc_path_str)
            if not p.exists() and not p.resolve().exists():
                to_evict.append(doc_path_str)
                continue

            resolved_str = str(p.resolve())
            if resolved_str in self._compiled_doc_paths or doc_path_str in self._compiled_doc_paths:
                continue

            cached_entries = meta.get("glossary_entries")
            if isinstance(cached_entries, dict):
                for term, entry in cached_entries.items():
                    if term in self._entries:
                        old_doc_path = self._entries[term].get("doc_path", "")
                        new_doc_path = entry.get("doc_path", doc_path_str)
                        if old_doc_path != new_doc_path:
                            logger.warning(
                                "Glossary term '%s' defined in '%s' collides with existing definition from '%s'; '%s' definition takes precedence (last page wins)",
                                term,
                                new_doc_path,
                                old_doc_path,
                                new_doc_path,
                            )
                            self._entries[term] = entry
                    else:
                        self._entries[term] = entry

            self._compiled_doc_paths.add(resolved_str)
            self._compiled_doc_paths.add(doc_path_str)

        if to_evict:
            for k in to_evict:
                metadata.pop(k, None)
            if self.cache is not None and hasattr(self.cache, "save_cache"):
                try:
                    self.cache.save_cache()
                except Exception:
                    pass

    def compile_glossary(self) -> dict[str, list[GlossaryEntry]]:
        """Return alphabetized glossary compiled from collected definition lists.

        [returns]
        `dict[str, list[GlossaryEntry]]`:: Grouped dictionary mapping first letters to term entries.
        """
        self._seed_from_cache()
        grouped: dict[str, list[GlossaryEntry]] = {}
        for term, entry in self._entries.items():
            if not term:
                continue
            letter = term[0].upper()
            if letter not in grouped:
                grouped[letter] = []
            grouped[letter].append(
                {
                    "term": term,
                    "definition": entry["definition"],
                    "doc_path": entry["doc_path"],
                }
            )

        result: dict[str, list[GlossaryEntry]] = {}
        for letter in sorted(grouped.keys()):
            result[letter] = sorted(grouped[letter], key=lambda e: (e["term"].lower(), e["term"]))

        return result

    def reset(self) -> None:
        """Clear accumulated glossary entries.

        [returns]
        `None`:: Clears state in place with no return value.
        """
        self._entries.clear()
        self._compiled_doc_paths.clear()

    @hookimpl
    def on_build_start(self, config: Any = None) -> None:
        """Reset state at the beginning of each build run.

        [parameters]
        `config` (Any, optional):: Site configuration object. Defaults to `None`.

        [returns]
        `None`:: Clears state in place.
        """
        self.reset()

    @hookimpl
    def on_template_context(self, context: PageContext, doc_path: Path) -> PageContext:
        """Inject compiled glossary into template context if page declares glossary role.

        [parameters]
        `context` (PageContext):: Chameleon template context dictionary.
        `doc_path` (Path):: Path to the documentation source file being processed.

        [returns]
        `PageContext`:: Enriched template context containing `site_glossary` if role matches.
        """
        if _is_page_role(context, "glossary"):
            context.update({"site_glossary": self.compile_glossary()})
        return context

    @hookimpl
    def golem_mark_stale(
        self,
        changed_files: list[Path],
        cache_metadata: dict[str, dict[str, Any]],
    ) -> list[Path] | None:
        """Register glossary aggregator pages for recompilation when documents with glossary definitions change.

        [parameters]
        `changed_files` (list[Path]):: List of file paths directly modified or deleted in the current build cycle.
        `cache_metadata` (dict[str, dict[str, Any]]):: Cached build metadata mapping file paths to node types and attributes.

        [returns]
        `list[Path] | None`:: List of glossary aggregator pages to recompile, or `None` if no invalidation is needed.
        """
        self._cache_metadata = cache_metadata
        aggregator_pages = _find_aggregator_pages(cache_metadata, "glossary")
        if not aggregator_pages:
            return None

        for f in changed_files:
            meta = _lookup_meta(f, cache_metadata)
            if meta and isinstance(meta, dict):
                node_types = meta.get("node_types")
                if isinstance(node_types, (list, tuple, set)):
                    if any(str(nt).lower() == "glossary" for nt in node_types):
                        return aggregator_pages
            if f.exists() and f.is_file():
                if _file_has_glossary_definitions(f):
                    return aggregator_pages
            elif meta and isinstance(meta, dict):
                node_types = meta.get("node_types")
                if isinstance(node_types, (list, tuple, set)):
                    if any(str(nt).lower() in ("descriptionlist", "dlist") for nt in node_types):
                        return aggregator_pages

        return None
