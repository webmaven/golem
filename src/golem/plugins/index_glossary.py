"""Provide index and glossary accumulation and compilation plugins for Golem documentation.

Collects AsciiDoc index terms (`indexterm:[...]`, `((term))`, `(((primary, secondary, tertiary)))`)
and glossary definition list blocks (`[glossary]`) across compiled documents, providing
structured alphabetized indexes and glossaries.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from asciidoctrine.nodes import DescriptionList, IndexTerm
from golem.model import AsgVisitor, Node
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


def _is_page_role(context: dict[str, Any], role_name: str) -> bool:
    """Check if template context or document attributes declare a specific page role.

    [parameters]
    `context` (dict[str, Any]):: Chameleon template context dictionary.
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
                self.glossary_entries[term] = {
                    "term": term,
                    "definition": definition,
                    "doc_path": self.doc_path_str,
                }


class IndexPlugin(GolemPlugin):
    """Collect and compile index terms across documentation pages.

    Traverses ASG documents for `IndexTerm` occurrences, accumulating primary,
    secondary, and tertiary terms with their source document paths, and produces
    alphabetized hierarchical index structures.
    """

    name = "index"

    def __init__(self, **extra: Any) -> None:
        super().__init__(**extra)
        self._entries: dict[str, dict[str, Any]] = {}

    @classmethod
    def from_config(cls, config: Any = None) -> IndexPlugin:
        """Construct an IndexPlugin instance from configuration.

        [parameters]
        `config` (Any, optional):: Site configuration object or dictionary. Defaults to `None`.

        [returns]
        `IndexPlugin`:: Configured index plugin instance.
        """
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
        visitor = AsgCollectorVisitor(index_entries=self._entries, doc_path_str=doc_path_str)
        visitor.visit(asg)
        return asg

    def compile_index(self) -> dict[str, dict[str, Any]]:
        """Return alphabetized hierarchical index compiled from collected terms.

        [returns]
        `dict[str, dict[str, Any]]`:: Nested dictionary mapping first letters to term entries and subterms.
        """
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

    @hookimpl
    def on_template_context(self, context: dict[str, Any], doc_path: Path) -> dict[str, Any]:
        """Inject compiled index into template context if page declares index role.

        [parameters]
        `context` (dict[str, Any]):: Chameleon template context dictionary.
        `doc_path` (Path):: Path to the documentation source file being processed.

        [returns]
        `dict[str, Any]`:: Enriched template context containing `site_index` if role matches.
        """
        if _is_page_role(context, "index"):
            context.update({"site_index": self.compile_index()})
        return context


class GlossaryPlugin(GolemPlugin):
    """Collect and compile glossary definitions across documentation pages.

    Traverses ASG documents for description list blocks annotated with `[glossary]`,
    accumulating term definitions with their origin document paths, and produces
    alphabetized glossary collections.
    """

    name = "glossary"

    def __init__(self, **extra: Any) -> None:
        super().__init__(**extra)
        self._entries: dict[str, dict[str, Any]] = {}

    @classmethod
    def from_config(cls, config: Any = None) -> GlossaryPlugin:
        """Construct a GlossaryPlugin instance from configuration.

        [parameters]
        `config` (Any, optional):: Site configuration object or dictionary. Defaults to `None`.

        [returns]
        `GlossaryPlugin`:: Configured glossary plugin instance.
        """
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
        visitor = AsgCollectorVisitor(glossary_entries=self._entries, doc_path_str=doc_path_str)
        visitor.visit(asg)
        return asg

    def compile_glossary(self) -> dict[str, list[dict[str, Any]]]:
        """Return alphabetized glossary compiled from collected definition lists.

        [returns]
        `dict[str, list[dict[str, Any]]]`:: Grouped dictionary mapping first letters to term entries.
        """
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
        """Clear accumulated glossary entries.

        [returns]
        `None`:: Clears state in place with no return value.
        """
        self._entries.clear()

    @hookimpl
    def on_template_context(self, context: dict[str, Any], doc_path: Path) -> dict[str, Any]:
        """Inject compiled glossary into template context if page declares glossary role.

        [parameters]
        `context` (dict[str, Any]):: Chameleon template context dictionary.
        `doc_path` (Path):: Path to the documentation source file being processed.

        [returns]
        `dict[str, Any]`:: Enriched template context containing `site_glossary` if role matches.
        """
        if _is_page_role(context, "glossary"):
            context.update({"site_glossary": self.compile_glossary()})
        return context
