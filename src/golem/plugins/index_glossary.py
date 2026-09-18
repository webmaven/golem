"""Provide index and glossary accumulation and compilation plugins for Golem documentation.

Collects AsciiDoc index terms (`indexterm:[...]`, `((term))`, `(((primary, secondary, tertiary)))`)
and glossary definition list blocks (`[glossary]`) across compiled documents, providing
structured alphabetized indexes and glossaries.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from asciidoctrine.nodes import Node
from golem.plugins import hookimpl

__all__ = [
    "GlossaryPlugin",
    "IndexGlossaryPlugin",
    "IndexPlugin",
]

logger = logging.getLogger(__name__)


def _walk_asg(node: Any) -> Iterator[Any]:
    """Recursively traverse AST/ASG nodes and dict representations.

    [parameters]
    `node` (Any):: Root AST/ASG Node or dictionary to traverse.

    [returns]
    `Iterator[Any]`:: Generator yielding every node in the graph depth-first.
    """
    if node is None:
        return
    yield node
    if hasattr(node, "walk"):
        for child in node.walk():
            if child is not node:
                yield child
    elif isinstance(node, dict):
        for key in ("blocks", "items", "inlines", "children"):
            children = node.get(key)
            if isinstance(children, list):
                for child in children:
                    yield from _walk_asg(child)
    elif isinstance(node, (list, tuple)):
        for item in node:
            yield from _walk_asg(item)


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
    """Determine whether an AST node represents a glossary description list.

    [parameters]
    `node` (Any):: AST node or dictionary to inspect.

    [returns]
    `bool`:: True if the node is a description list with a glossary style or role.
    """
    name = getattr(node, "name", "")
    type_name = type(node).__name__
    if not (
        type_name in ("DescriptionList", "Dlist")
        or name in ("descriptionList", "dlist", "description_list")
        or (isinstance(node, dict) and node.get("name") in ("descriptionList", "dlist", "description_list"))
    ):
        return False

    attrs = getattr(node, "attributes", None)
    if attrs is None and isinstance(node, dict):
        attrs = node.get("attributes")

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

    if getattr(node, "role", None) == "glossary" or getattr(node, "style", None) == "glossary":
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
    raw_terms = getattr(item, "terms", None)
    if raw_terms is None and isinstance(item, dict):
        raw_terms = item.get("terms")

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
    blocks = getattr(item, "blocks", None)
    if blocks:
        parts = [_extract_text(b) for b in blocks]
        return "\n\n".join(p for p in parts if p)

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

    for attr in ("definition", "description", "text"):
        val = getattr(item, attr, None)
        if val is not None:
            return _extract_text(val)

    return ""


class IndexPlugin:
    """Collect and compile index terms across documentation pages.

    Traverses ASG documents for `IndexTerm` occurrences, accumulating primary,
    secondary, and tertiary terms with their source document paths, and produces
    alphabetized hierarchical index structures.
    """

    def __init__(self) -> None:
        self._entries: dict[str, dict[str, Any]] = {}

    @classmethod
    def from_config(cls, config: Any = None) -> IndexPlugin:
        """Construct an IndexPlugin instance from configuration."""
        return cls()

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

        for node in _walk_asg(asg):
            type_name = type(node).__name__
            name = getattr(node, "name", "")
            is_index_term = (
                type_name == "IndexTerm"
                or name == "indexterm"
                or (isinstance(node, dict) and node.get("name") == "indexterm")
                or (isinstance(node, dict) and "terms" in node and node.get("type") == "inline")
            )
            if not is_index_term:
                continue

            raw_terms = getattr(node, "terms", None)
            if raw_terms is None and isinstance(node, dict):
                raw_terms = node.get("terms")
            if not raw_terms:
                continue

            terms: list[str] = []
            for t in raw_terms:
                txt = _extract_text(t) if not isinstance(t, str) else t.strip()
                if txt:
                    terms.append(txt)

            if not terms:
                continue

            primary = terms[0]
            secondary = terms[1] if len(terms) > 1 else None
            tertiary = terms[2] if len(terms) > 2 else None

            letter = primary[0].upper() if primary else ""
            if letter not in self._entries:
                self._entries[letter] = {}

            if primary not in self._entries[letter]:
                self._entries[letter][primary] = {
                    "locations": [],
                    "secondary": {},
                }

            entry = self._entries[letter][primary]
            if doc_path_str and doc_path_str not in entry["locations"]:
                entry["locations"].append(doc_path_str)

            if secondary:
                sec_map = entry["secondary"]
                if secondary not in sec_map:
                    sec_map[secondary] = {
                        "locations": [],
                        "secondary": {},
                    }
                sec_entry = sec_map[secondary]
                if doc_path_str and doc_path_str not in sec_entry["locations"]:
                    sec_entry["locations"].append(doc_path_str)

                if tertiary:
                    tert_map = sec_entry["secondary"]
                    if tertiary not in tert_map:
                        tert_map[tertiary] = {
                            "locations": [],
                            "secondary": {},
                        }
                    tert_entry = tert_map[tertiary]
                    if doc_path_str and doc_path_str not in tert_entry["locations"]:
                        tert_entry["locations"].append(doc_path_str)

        return asg

    def compile_index(self) -> dict[str, dict[str, Any]]:
        """Return alphabetized index: {letter: {primary_term: {"locations": [doc_path_strings]}}}."""
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
        """Clear accumulated index entries (for fresh builds)."""
        self._entries.clear()

    @hookimpl
    def on_template_context(self, context: dict[str, Any], doc_path: Path) -> dict[str, Any]:
        """Inject compiled index into template context."""
        context.setdefault("site_index", self.compile_index())
        return context


class GlossaryPlugin:
    """Collect and compile glossary definitions across documentation pages.

    Traverses ASG documents for description list blocks annotated with `[glossary]`,
    accumulating term definitions with their origin document paths, and produces
    alphabetized glossary collections.
    """

    def __init__(self) -> None:
        self._entries: dict[str, dict[str, Any]] = {}

    @classmethod
    def from_config(cls, config: Any = None) -> GlossaryPlugin:
        """Construct a GlossaryPlugin instance from configuration."""
        return cls()

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

        for node in _walk_asg(asg):
            if not _is_glossary_list(node):
                continue

            items = getattr(node, "items", None)
            if items is None and isinstance(node, dict):
                items = node.get("items") or node.get("children") or node.get("blocks")
            if not items or not isinstance(items, (list, tuple)):
                continue

            for item in items:
                terms = _extract_definition_list_terms(item)
                definition = _extract_definition_list_blocks(item)
                for term in terms:
                    self._entries[term] = {
                        "term": term,
                        "definition": definition,
                        "doc_path": doc_path_str,
                    }

        return asg

    def compile_glossary(self) -> dict[str, list[dict[str, Any]]]:
        """Return alphabetized glossary: {letter: [{"term": str, "definition": str, "doc_path": str}]}."""
        grouped: dict[str, list[dict[str, Any]]] = {}
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

        result: dict[str, list[dict[str, Any]]] = {}
        for letter in sorted(grouped.keys()):
            result[letter] = sorted(grouped[letter], key=lambda e: (e["term"].lower(), e["term"]))

        return result

    def reset(self) -> None:
        """Clear accumulated glossary entries (for fresh builds)."""
        self._entries.clear()

    @hookimpl
    def on_template_context(self, context: dict[str, Any], doc_path: Path) -> dict[str, Any]:
        """Inject compiled glossary into template context."""
        context.setdefault("site_glossary", self.compile_glossary())
        return context


class IndexGlossaryPlugin:
    """Combined plugin providing both index and glossary accumulation and compilation."""

    def __init__(self) -> None:
        self.index_plugin = IndexPlugin()
        self.glossary_plugin = GlossaryPlugin()

    @classmethod
    def from_config(cls, config: Any = None) -> IndexGlossaryPlugin:
        """Construct an IndexGlossaryPlugin instance from configuration."""
        return cls()

    @hookimpl
    def on_asg_created(self, asg: Node, doc_path: Path | None = None) -> Node:
        """Walk the ASG collecting both index terms and glossary definitions.

        [parameters]
        `asg` (Node):: Root ASG document node to inspect.
        `doc_path` (Path | None, optional):: Path to the documentation source file.

        [returns]
        `Node`:: Unmodified ASG node.
        """
        self.index_plugin.on_asg_created(asg, doc_path=doc_path)
        self.glossary_plugin.on_asg_created(asg, doc_path=doc_path)
        return asg

    def compile_index(self) -> dict[str, dict[str, Any]]:
        """Return compiled alphabetized index."""
        return self.index_plugin.compile_index()

    def compile_glossary(self) -> dict[str, list[dict[str, Any]]]:
        """Return compiled alphabetized glossary."""
        return self.glossary_plugin.compile_glossary()

    def reset(self) -> None:
        """Clear accumulated index and glossary entries."""
        self.index_plugin.reset()
        self.glossary_plugin.reset()

    @hookimpl
    def on_template_context(self, context: dict[str, Any], doc_path: Path) -> dict[str, Any]:
        """Inject compiled index and glossary into template context."""
        self.index_plugin.on_template_context(context, doc_path=doc_path)
        self.glossary_plugin.on_template_context(context, doc_path=doc_path)
        return context
