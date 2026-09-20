"""Tests for Index and Glossary compilation plugins."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

import asciidoctrine
from asciidoctrine.nodes import (
    DescriptionList,
    DescriptionListItem,
    DescriptionListTerm,
    Document,
    IndexTerm,
    Paragraph,
    Text,
)

from golem.plugins.index_glossary import (
    GlossaryPlugin,
    IndexPlugin,
)


def test_index_single_doc_single_term() -> None:
    plugin = IndexPlugin()
    node = IndexTerm(terms=["Compiler"])
    doc = Document([Paragraph([node])])
    doc_path = Path("docs/compiler.adoc")

    result = plugin.on_asg_created(doc, doc_path=doc_path)
    assert result is doc

    index = plugin.compile_index()
    assert "C" in index
    assert "Compiler" in index["C"]
    assert index["C"]["Compiler"]["locations"] == ["docs/compiler.adoc"]


def test_index_multiple_docs_same_term() -> None:
    plugin = IndexPlugin()
    doc1 = Document([Paragraph([IndexTerm(terms=["Parser"])])])
    doc2 = Document([Paragraph([IndexTerm(terms=["Parser"])])])

    plugin.on_asg_created(doc1, doc_path=Path("docs/doc1.adoc"))
    plugin.on_asg_created(doc2, doc_path=Path("docs/doc2.adoc"))

    index = plugin.compile_index()
    assert "P" in index
    assert "Parser" in index["P"]
    assert index["P"]["Parser"]["locations"] == ["docs/doc1.adoc", "docs/doc2.adoc"]


def test_index_alphabetical_grouping() -> None:
    plugin = IndexPlugin()
    doc = Document(
        [
            Paragraph(
                [
                    IndexTerm(terms=["AST"]),
                    IndexTerm(terms=["Bytecode"]),
                    IndexTerm(terms=["Compiler"]),
                    IndexTerm(terms=["Architecture"]),
                ]
            )
        ]
    )
    plugin.on_asg_created(doc, doc_path=Path("docs/overview.adoc"))

    index = plugin.compile_index()
    assert list(index.keys()) == ["A", "B", "C"]
    assert list(index["A"].keys()) == ["Architecture", "AST"]
    assert list(index["B"].keys()) == ["Bytecode"]
    assert list(index["C"].keys()) == ["Compiler"]


def test_index_secondary_term() -> None:
    plugin = IndexPlugin()
    node = IndexTerm(terms=["Compiler", "Optimization"])
    doc = Document([Paragraph([node])])
    doc_path = Path("docs/compiler.adoc")

    plugin.on_asg_created(doc, doc_path=doc_path)

    index = plugin.compile_index()
    assert "C" in index
    assert "Compiler" in index["C"]
    compiler_entry = index["C"]["Compiler"]
    assert "docs/compiler.adoc" in compiler_entry["locations"]
    assert "Optimization" in compiler_entry["secondary"]
    assert compiler_entry["secondary"]["Optimization"]["locations"] == ["docs/compiler.adoc"]


def test_index_reset_clears_entries() -> None:
    plugin = IndexPlugin()
    doc = Document([Paragraph([IndexTerm(terms=["Compiler"])])])
    plugin.on_asg_created(doc, doc_path=Path("docs/compiler.adoc"))
    assert len(plugin.compile_index()) == 1

    plugin.reset()
    assert plugin.compile_index() == {}


def test_glossary_single_entry() -> None:
    plugin = GlossaryPlugin()
    item = DescriptionListItem(
        terms=[DescriptionListTerm([Text("API")])],
        blocks=[Paragraph([Text("Application Programming Interface")])],
    )
    dlist = DescriptionList([item])
    dlist.attributes["role"] = "glossary"
    doc = Document([dlist])

    result = plugin.on_asg_created(doc, doc_path=Path("docs/glossary.adoc"))
    assert result is doc

    glossary = plugin.compile_glossary()
    assert "A" in glossary
    assert len(glossary["A"]) == 1
    assert glossary["A"][0] == {
        "term": "API",
        "definition": "Application Programming Interface",
        "doc_path": "docs/glossary.adoc",
    }


def test_glossary_multiple_docs() -> None:
    plugin = GlossaryPlugin()

    item1 = DescriptionListItem(
        terms=[DescriptionListTerm([Text("API")])],
        blocks=[Paragraph([Text("Application Programming Interface")])],
    )
    dlist1 = DescriptionList([item1])
    dlist1.attributes["role"] = "glossary"
    doc1 = Document([dlist1])

    item2 = DescriptionListItem(
        terms=[DescriptionListTerm([Text("CLI")])],
        blocks=[Paragraph([Text("Command Line Interface")])],
    )
    dlist2 = DescriptionList([item2])
    dlist2.attributes["role"] = "glossary"
    doc2 = Document([dlist2])

    plugin.on_asg_created(doc1, doc_path=Path("docs/doc1.adoc"))
    plugin.on_asg_created(doc2, doc_path=Path("docs/doc2.adoc"))

    glossary = plugin.compile_glossary()
    assert "A" in glossary
    assert "C" in glossary
    assert glossary["A"][0]["term"] == "API"
    assert glossary["A"][0]["doc_path"] == "docs/doc1.adoc"
    assert glossary["C"][0]["term"] == "CLI"
    assert glossary["C"][0]["doc_path"] == "docs/doc2.adoc"


def test_glossary_alphabetical_grouping() -> None:
    plugin = GlossaryPlugin()

    items = [
        DescriptionListItem(
            terms=[DescriptionListTerm([Text("CLI")])],
            blocks=[Paragraph([Text("Command Line Interface")])],
        ),
        DescriptionListItem(
            terms=[DescriptionListTerm([Text("API")])],
            blocks=[Paragraph([Text("Application Programming Interface")])],
        ),
        DescriptionListItem(
            terms=[DescriptionListTerm([Text("AST")])],
            blocks=[Paragraph([Text("Abstract Syntax Tree")])],
        ),
        DescriptionListItem(
            terms=[DescriptionListTerm([Text("ASG")])],
            blocks=[Paragraph([Text("Abstract Semantic Graph")])],
        ),
    ]
    dlist = DescriptionList(items)
    dlist.attributes["role"] = "glossary"
    doc = Document([dlist])

    plugin.on_asg_created(doc, doc_path=Path("docs/terms.adoc"))
    glossary = plugin.compile_glossary()

    assert list(glossary.keys()) == ["A", "C"]
    terms_in_a = [entry["term"] for entry in glossary["A"]]
    assert terms_in_a == ["API", "ASG", "AST"]
    terms_in_c = [entry["term"] for entry in glossary["C"]]
    assert terms_in_c == ["CLI"]


def test_glossary_reset() -> None:
    plugin = GlossaryPlugin()
    item = DescriptionListItem(
        terms=[DescriptionListTerm([Text("API")])],
        blocks=[Paragraph([Text("Application Programming Interface")])],
    )
    dlist = DescriptionList([item])
    dlist.attributes["role"] = "glossary"
    doc = Document([dlist])

    plugin.on_asg_created(doc, doc_path=Path("docs/glossary.adoc"))
    assert len(plugin.compile_glossary()) == 1

    plugin.reset()
    assert plugin.compile_glossary() == {}


def test_plugins_collect_both_from_same_doc() -> None:
    idx_plugin = IndexPlugin()
    glo_plugin = GlossaryPlugin()

    glossary_item = DescriptionListItem(
        terms=[DescriptionListTerm([Text("API")])],
        blocks=[Paragraph([Text("Application Programming Interface")])],
    )
    dlist = DescriptionList([glossary_item])
    dlist.attributes["role"] = "glossary"

    index_node = IndexTerm(terms=["Compiler"])
    p = Paragraph([Text("Here is "), index_node])

    doc = Document([dlist, p])
    doc_path = Path("docs/combined.adoc")

    res_idx = idx_plugin.on_asg_created(doc, doc_path=doc_path)
    res_glo = glo_plugin.on_asg_created(doc, doc_path=doc_path)
    assert res_idx is doc
    assert res_glo is doc

    index = idx_plugin.compile_index()
    glossary = glo_plugin.compile_glossary()

    assert "C" in index
    assert "Compiler" in index["C"]
    assert index["C"]["Compiler"]["locations"] == ["docs/combined.adoc"]

    assert "A" in glossary
    assert glossary["A"][0]["term"] == "API"
    assert glossary["A"][0]["definition"] == "Application Programming Interface"
    assert glossary["A"][0]["doc_path"] == "docs/combined.adoc"


def test_on_asg_created_returns_node_unchanged() -> None:
    idx_plugin = IndexPlugin()
    glo_plugin = GlossaryPlugin()

    doc = Document([Paragraph([Text("Simple paragraph")])])

    assert idx_plugin.on_asg_created(doc) is doc
    assert glo_plugin.on_asg_created(doc) is doc


def test_index_deduplicates_locations_in_same_doc() -> None:
    plugin = IndexPlugin()
    doc = Document(
        [
            Paragraph([IndexTerm(terms=["Compiler"])]),
            Paragraph([IndexTerm(terms=["Compiler"])]),
        ]
    )
    plugin.on_asg_created(doc, doc_path=Path("docs/compiler.adoc"))

    index = plugin.compile_index()
    assert index["C"]["Compiler"]["locations"] == ["docs/compiler.adoc"]


def test_index_tertiary_term() -> None:
    plugin = IndexPlugin()
    node = IndexTerm(terms=["Language", "Python", "Syntax"])
    doc = Document([Paragraph([node])])
    plugin.on_asg_created(doc, doc_path=Path("docs/lang.adoc"))

    index = plugin.compile_index()
    assert "L" in index
    assert "Language" in index["L"]
    lang = index["L"]["Language"]
    assert "Python" in lang["secondary"]
    python_entry = lang["secondary"]["Python"]
    assert "Syntax" in python_entry["secondary"]
    assert python_entry["secondary"]["Syntax"]["locations"] == ["docs/lang.adoc"]


def test_glossary_style_attribute() -> None:
    plugin = GlossaryPlugin()
    item = DescriptionListItem(
        terms=[DescriptionListTerm([Text("SDK")])],
        blocks=[Paragraph([Text("Software Development Kit")])],
    )
    dlist = DescriptionList([item])
    dlist.attributes["style"] = "glossary"
    doc = Document([dlist])

    plugin.on_asg_created(doc, doc_path=Path("docs/sdk.adoc"))
    glossary = plugin.compile_glossary()

    assert "S" in glossary
    assert glossary["S"][0]["term"] == "SDK"
    assert glossary["S"][0]["definition"] == "Software Development Kit"


def test_glossary_multiple_terms_single_item() -> None:
    plugin = GlossaryPlugin()
    item = DescriptionListItem(
        terms=[
            DescriptionListTerm([Text("GUI")]),
            DescriptionListTerm([Text("Graphical User Interface")]),
        ],
        blocks=[Paragraph([Text("A visual user interface.")])],
    )
    dlist = DescriptionList([item])
    dlist.attributes["role"] = "glossary"
    doc = Document([dlist])

    plugin.on_asg_created(doc, doc_path=Path("docs/ui.adoc"))
    glossary = plugin.compile_glossary()

    assert "G" in glossary
    terms_in_g = [e["term"] for e in glossary["G"]]
    assert "Graphical User Interface" in terms_in_g
    assert "GUI" in terms_in_g


def test_real_asciidoctrine_parsing() -> None:
    idx_plugin = IndexPlugin()
    glo_plugin = GlossaryPlugin()
    doc_src = """= Reference Manual

[glossary]
API:: Application Programming Interface
CLI:: Command Line Interface

Here is an indexterm:[Compiler] and ((Parser)).
"""
    doc = asciidoctrine.loads(doc_src)
    idx_plugin.on_asg_created(doc, doc_path=Path("docs/ref.adoc"))
    glo_plugin.on_asg_created(doc, doc_path=Path("docs/ref.adoc"))

    index = idx_plugin.compile_index()
    glossary = glo_plugin.compile_glossary()

    assert "C" in index
    assert "Compiler" in index["C"]
    assert "P" in index
    assert "Parser" in index["P"]

    assert "A" in glossary
    assert glossary["A"][0]["term"] == "API"
    assert "C" in glossary
    assert glossary["C"][0]["term"] == "CLI"


def test_build_engine_integration(tmp_path: Path) -> None:
    from golem.config import GolemConfig
    from golem.engine import BuildEngine

    content_dir = tmp_path / "content"
    content_dir.mkdir()
    (content_dir / "index.adoc").write_text(
        """= Documentation Index

[glossary]
API:: Application Programming Interface
CLI:: Command Line Interface

A paragraph with indexterm:[Compiler] and ((Parser)).
""",
        encoding="utf-8",
    )

    out_dir = tmp_path / "dist"
    config = GolemConfig(
        content_dir=str(content_dir),
        output_dir=str(out_dir),
        site_title="Test Site",
    )
    engine = BuildEngine(config)
    idx_plugin = IndexPlugin()
    glo_plugin = GlossaryPlugin()
    engine.pm.register(idx_plugin)
    engine.pm.register(glo_plugin)

    compiled = engine.build_site()
    assert len(compiled) == 1

    index = idx_plugin.compile_index()
    glossary = glo_plugin.compile_glossary()

    assert "C" in index
    assert "Compiler" in index["C"]
    assert "P" in index
    assert "Parser" in index["P"]

    assert "A" in glossary
    assert glossary["A"][0]["term"] == "API"
    assert "C" in glossary
    assert glossary["C"][0]["term"] == "CLI"


def test_glossary_raw_dict_asg() -> None:
    plugin = GlossaryPlugin()
    raw_asg: dict[str, Any] = {
        "name": "document",
        "type": "block",
        "blocks": [
            {
                "name": "descriptionList",
                "type": "block",
                "attributes": {"style": "glossary"},
                "items": [
                    {
                        "name": "descriptionListItem",
                        "type": "block",
                        "terms": [
                            {
                                "name": "descriptionListTerm",
                                "type": "inline",
                                "inlines": [{"name": "text", "type": "string", "value": "API"}],
                            }
                        ],
                        "blocks": [
                            {
                                "name": "paragraph",
                                "type": "block",
                                "inlines": [
                                    {
                                        "name": "text",
                                        "type": "string",
                                        "value": "Application Programming Interface",
                                    }
                                ],
                            }
                        ],
                    },
                    {
                        "name": "descriptionListItem",
                        "type": "block",
                        "terms": [
                            {
                                "name": "descriptionListTerm",
                                "type": "inline",
                                "inlines": [{"name": "text", "type": "string", "value": "CLI"}],
                            }
                        ],
                        "blocks": [
                            {
                                "name": "paragraph",
                                "type": "block",
                                "inlines": [
                                    {
                                        "name": "text",
                                        "type": "string",
                                        "value": "Command Line Interface",
                                    }
                                ],
                            }
                        ],
                    },
                ],
            }
        ],
    }

    result = plugin.on_asg_created(raw_asg, doc_path=Path("docs/raw_glossary.adoc"))  # type: ignore[arg-type]
    assert result is raw_asg

    glossary = plugin.compile_glossary()
    assert "A" in glossary
    assert "C" in glossary
    assert glossary["A"][0] == {
        "term": "API",
        "definition": "Application Programming Interface",
        "doc_path": "docs/raw_glossary.adoc",
    }
    assert glossary["C"][0] == {
        "term": "CLI",
        "definition": "Command Line Interface",
        "doc_path": "docs/raw_glossary.adoc",
    }


def test_index_raw_dict_asg() -> None:
    plugin = IndexPlugin()
    raw_asg: dict[str, Any] = {
        "name": "document",
        "type": "block",
        "blocks": [
            {
                "name": "paragraph",
                "type": "block",
                "inlines": [
                    {
                        "name": "indexterm",
                        "type": "inline",
                        "terms": ["Compiler", "Optimization"],
                    },
                    {
                        "name": "indexterm",
                        "type": "inline",
                        "primary": "Parser",
                    },
                ],
            }
        ],
    }

    result = plugin.on_asg_created(raw_asg, doc_path=Path("docs/raw_index.adoc"))  # type: ignore[arg-type]
    assert result is raw_asg

    index = plugin.compile_index()
    assert "C" in index
    assert "Compiler" in index["C"]
    assert index["C"]["Compiler"]["locations"] == ["docs/raw_index.adoc"]
    assert "Optimization" in index["C"]["Compiler"]["secondary"]
    assert "P" in index
    assert "Parser" in index["P"]
    assert index["P"]["Parser"]["locations"] == ["docs/raw_index.adoc"]


def test_index_plugin_inheritance():
    from golem.plugins import GolemPlugin

    assert issubclass(IndexPlugin, GolemPlugin)
    assert IndexPlugin.name == "index"
    plugin = IndexPlugin()
    assert plugin.name == "index"


def test_glossary_plugin_inheritance():
    from golem.plugins import GolemPlugin

    assert issubclass(GlossaryPlugin, GolemPlugin)
    assert GlossaryPlugin.name == "glossary"
    plugin = GlossaryPlugin()
    assert plugin.name == "glossary"


def test_index_template_context_conditional_injection():
    plugin = IndexPlugin()
    doc = Document([Paragraph([IndexTerm(terms=["Compiler"])])])
    plugin.on_asg_created(doc, doc_path=Path("docs/compiler.adoc"))

    # 1. Ordinary page: site_index should NOT be injected
    ctx_normal: dict[str, Any] = {"title": "Normal Page"}
    res_normal = plugin.on_template_context(ctx_normal, Path("docs/normal.adoc"))
    assert "site_index" not in res_normal

    # 2. Page with page-role: "index" in doc_attributes: site_index MUST be injected
    ctx_role_attr: dict[str, Any] = {"doc_attributes": {"page-role": "index"}}
    res_role_attr = plugin.on_template_context(ctx_role_attr, Path("docs/index.adoc"))
    assert "site_index" in res_role_attr
    assert "C" in res_role_attr["site_index"]
    assert "Compiler" in res_role_attr["site_index"]["C"]

    # 3. Page with page_role: "index" directly: site_index MUST be injected
    ctx_role_direct: dict[str, Any] = {"page_role": "index"}
    res_role_direct = plugin.on_template_context(ctx_role_direct, Path("docs/index.adoc"))
    assert "site_index" in res_role_direct

    # 4. Page with page-role: "glossary" (wrong role): site_index should NOT be injected
    ctx_wrong_role: dict[str, Any] = {"doc_attributes": {"page-role": "glossary"}}
    res_wrong_role = plugin.on_template_context(ctx_wrong_role, Path("docs/glossary.adoc"))
    assert "site_index" not in res_wrong_role


def test_glossary_template_context_conditional_injection():
    plugin = GlossaryPlugin()
    item = DescriptionListItem(
        terms=[DescriptionListTerm([Text("API")])],
        blocks=[Paragraph([Text("Application Programming Interface")])],
    )
    dlist = DescriptionList([item])
    dlist.attributes["role"] = "glossary"
    doc = Document([dlist])
    plugin.on_asg_created(doc, doc_path=Path("docs/glossary.adoc"))

    # 1. Ordinary page: site_glossary should NOT be injected
    ctx_normal: dict[str, Any] = {"title": "Normal Page"}
    res_normal = plugin.on_template_context(ctx_normal, Path("docs/normal.adoc"))
    assert "site_glossary" not in res_normal

    # 2. Page with page-role: "glossary" in doc_attributes: site_glossary MUST be injected
    ctx_role_attr: dict[str, Any] = {"doc_attributes": {"page-role": "glossary"}}
    res_role_attr = plugin.on_template_context(ctx_role_attr, Path("docs/glossary.adoc"))
    assert "site_glossary" in res_role_attr
    assert "A" in res_role_attr["site_glossary"]
    assert res_role_attr["site_glossary"]["A"][0]["term"] == "API"

    # 3. Page with page_role: "glossary" directly: site_glossary MUST be injected
    ctx_role_direct: dict[str, Any] = {"page_role": "glossary"}
    res_role_direct = plugin.on_template_context(ctx_role_direct, Path("docs/glossary.adoc"))
    assert "site_glossary" in res_role_direct

    # 4. Page with page-role: "index" (wrong role): site_glossary should NOT be injected
    ctx_wrong_role: dict[str, Any] = {"doc_attributes": {"page-role": "index"}}
    res_wrong_role = plugin.on_template_context(ctx_wrong_role, Path("docs/index.adoc"))
    assert "site_glossary" not in res_wrong_role


def test_glossary_duplicate_definitions_same_page(caplog: pytest.LogCaptureFixture) -> None:
    plugin = GlossaryPlugin()
    item1 = DescriptionListItem(
        terms=[DescriptionListTerm([Text("API")])],
        blocks=[Paragraph([Text("First definition")])],
    )
    item2 = DescriptionListItem(
        terms=[DescriptionListTerm([Text("API")])],
        blocks=[Paragraph([Text("Second definition")])],
    )
    dlist = DescriptionList([item1, item2])
    dlist.attributes["role"] = "glossary"
    doc = Document([dlist])

    with caplog.at_level(logging.WARNING):
        plugin.on_asg_created(doc, doc_path=Path("docs/glossary.adoc"))

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "API" in warnings[0].message
    assert "redefined within 'docs/glossary.adoc'" in warnings[0].message
    assert "subsequent definition overwrites earlier ones" in warnings[0].message

    glossary = plugin.compile_glossary()
    assert len(glossary["A"]) == 1
    assert glossary["A"][0]["term"] == "API"
    assert glossary["A"][0]["definition"] == "Second definition"


def test_glossary_duplicate_definitions_different_pages(caplog: pytest.LogCaptureFixture) -> None:
    plugin = GlossaryPlugin()
    item1 = DescriptionListItem(
        terms=[DescriptionListTerm([Text("API")])],
        blocks=[Paragraph([Text("API from doc1")])],
    )
    dlist1 = DescriptionList([item1])
    dlist1.attributes["role"] = "glossary"
    doc1 = Document([dlist1])

    item2 = DescriptionListItem(
        terms=[DescriptionListTerm([Text("API")])],
        blocks=[Paragraph([Text("API from doc2")])],
    )
    dlist2 = DescriptionList([item2])
    dlist2.attributes["role"] = "glossary"
    doc2 = Document([dlist2])

    with caplog.at_level(logging.WARNING):
        plugin.on_asg_created(doc1, doc_path=Path("docs/doc1.adoc"))
        assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 0

        plugin.on_asg_created(doc2, doc_path=Path("docs/doc2.adoc"))

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "API" in warnings[0].message
    assert "defined in 'docs/doc2.adoc' collides with existing definition from 'docs/doc1.adoc'" in warnings[0].message
    assert "docs/doc2.adoc' definition takes precedence (last page wins)" in warnings[0].message

    glossary = plugin.compile_glossary()
    assert len(glossary["A"]) == 1
    assert glossary["A"][0]["term"] == "API"
    assert glossary["A"][0]["definition"] == "API from doc2"
    assert glossary["A"][0]["doc_path"] == "docs/doc2.adoc"


def test_glossary_duplicate_definitions_cached_pages(caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
    plugin = GlossaryPlugin()
    p1 = tmp_path / "page1.adoc"
    p1.touch()
    p2 = tmp_path / "page2.adoc"
    p2.touch()

    plugin._cache_metadata = {
        str(p1): {
            "glossary_entries": {
                "API": {
                    "term": "API",
                    "definition": "Definition from page 1",
                    "doc_path": str(p1),
                }
            }
        },
        str(p2): {
            "glossary_entries": {
                "API": {
                    "term": "API",
                    "definition": "Definition from page 2",
                    "doc_path": str(p2),
                }
            }
        },
    }

    with caplog.at_level(logging.WARNING):
        glossary = plugin.compile_glossary()

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "API" in warnings[0].message
    assert f"defined in '{p2}' collides with existing definition from '{p1}'" in warnings[0].message
    assert f"'{p2}' definition takes precedence (last page wins)" in warnings[0].message

    assert len(glossary["A"]) == 1
    assert glossary["A"][0]["term"] == "API"
    assert glossary["A"][0]["definition"] == "Definition from page 2"
    assert glossary["A"][0]["doc_path"] == str(p2)
