"""Tests for aggregator page staleness invalidation during incremental builds (#34).

Verifies that pages declaring `:page-role: index` or `:page-role: glossary`
are marked stale when documents containing index terms or glossary definitions
are modified or deleted, while unrelated document changes do not invalidate aggregators.
"""

from pathlib import Path
from typing import Any

from golem.config import GolemConfig
from golem.engine import BuildEngine
from golem.plugins.index_glossary import GlossaryPlugin, IndexPlugin


def test_index_page_marked_stale_when_index_term_modified(tmp_path: Path) -> None:
    content_dir = tmp_path / "content"
    content_dir.mkdir()

    index_page = content_dir / "site_index.adoc"
    index_page.write_text("= Index\n:page-role: index\n\nIndex content.\n", encoding="utf-8")

    doc1 = content_dir / "guide.adoc"
    doc1.write_text("= Guide\n\nHere is an indexterm:[Compiler].\n", encoding="utf-8")

    unrelated = content_dir / "about.adoc"
    unrelated.write_text("= About\n\nGeneral about page.\n", encoding="utf-8")

    config = GolemConfig(
        content_dir=str(content_dir),
        output_dir=str(tmp_path / "dist"),
        site_title="Test Site",
    )
    engine = BuildEngine(config, cache_file=tmp_path / "cache.json")
    idx_plugin = IndexPlugin()
    glo_plugin = GlossaryPlugin()
    engine.pm.register(idx_plugin)
    engine.pm.register(glo_plugin)

    # Initial full build
    initial_compiled = engine.build_site()
    assert len(initial_compiled) == 3

    # Modify the document containing index terms
    doc1.write_text("= Guide\n\nHere is an indexterm:[Compiler] and ((Parser)).\n", encoding="utf-8")

    outdated = engine.staleness_tracker.get_outdated_files(commit=False)
    outdated_resolved = {p.resolve() for p in outdated}

    assert doc1.resolve() in outdated_resolved
    assert index_page.resolve() in outdated_resolved, "Index page must be marked stale when index terms change"
    assert unrelated.resolve() not in outdated_resolved


def test_glossary_page_marked_stale_when_glossary_term_modified(tmp_path: Path) -> None:
    content_dir = tmp_path / "content"
    content_dir.mkdir()

    glossary_page = content_dir / "site_glossary.adoc"
    glossary_page.write_text("= Glossary\n:page-role: glossary\n\nGlossary content.\n", encoding="utf-8")

    doc1 = content_dir / "api.adoc"
    doc1.write_text(
        "= API Reference\n\n[glossary]\nAPI:: Application Programming Interface\n",
        encoding="utf-8",
    )

    unrelated = content_dir / "about.adoc"
    unrelated.write_text("= About\n\nGeneral about page.\n", encoding="utf-8")

    config = GolemConfig(
        content_dir=str(content_dir),
        output_dir=str(tmp_path / "dist"),
        site_title="Test Site",
    )
    engine = BuildEngine(config, cache_file=tmp_path / "cache.json")
    idx_plugin = IndexPlugin()
    glo_plugin = GlossaryPlugin()
    engine.pm.register(idx_plugin)
    engine.pm.register(glo_plugin)

    # Initial full build
    initial_compiled = engine.build_site()
    assert len(initial_compiled) == 3

    # Modify the document containing glossary definitions
    doc1.write_text(
        "= API Reference\n\n[glossary]\nAPI:: Application Programming Interface\nCLI:: Command Line Interface\n",
        encoding="utf-8",
    )

    outdated = engine.staleness_tracker.get_outdated_files(commit=False)
    outdated_resolved = {p.resolve() for p in outdated}

    assert doc1.resolve() in outdated_resolved
    assert glossary_page.resolve() in outdated_resolved, "Glossary page must be marked stale when glossary definitions change"
    assert unrelated.resolve() not in outdated_resolved


def test_unrelated_file_change_does_not_mark_aggregators_stale(tmp_path: Path) -> None:
    content_dir = tmp_path / "content"
    content_dir.mkdir()

    index_page = content_dir / "site_index.adoc"
    index_page.write_text("= Index\n:page-role: index\n\nIndex content.\n", encoding="utf-8")

    glossary_page = content_dir / "site_glossary.adoc"
    glossary_page.write_text("= Glossary\n:page-role: glossary\n\nGlossary content.\n", encoding="utf-8")

    doc_index = content_dir / "guide.adoc"
    doc_index.write_text("= Guide\n\n((Compiler))\n", encoding="utf-8")

    doc_glossary = content_dir / "api.adoc"
    doc_glossary.write_text("= API\n\n[glossary]\nAPI:: Interface\n", encoding="utf-8")

    unrelated = content_dir / "about.adoc"
    unrelated.write_text("= About\n\nInitial about content.\n", encoding="utf-8")

    config = GolemConfig(
        content_dir=str(content_dir),
        output_dir=str(tmp_path / "dist"),
        site_title="Test Site",
    )
    engine = BuildEngine(config, cache_file=tmp_path / "cache.json")
    idx_plugin = IndexPlugin()
    glo_plugin = GlossaryPlugin()
    engine.pm.register(idx_plugin)
    engine.pm.register(glo_plugin)

    # Initial full build
    initial_compiled = engine.build_site()
    assert len(initial_compiled) == 5

    # Modify ONLY the unrelated document
    unrelated.write_text("= About\n\nUpdated about content.\n", encoding="utf-8")

    outdated = engine.staleness_tracker.get_outdated_files(commit=False)
    outdated_resolved = {p.resolve() for p in outdated}

    assert unrelated.resolve() in outdated_resolved
    assert index_page.resolve() not in outdated_resolved, "Index page must not be stale for unrelated changes"
    assert glossary_page.resolve() not in outdated_resolved, "Glossary page must not be stale for unrelated changes"
    assert doc_index.resolve() not in outdated_resolved
    assert doc_glossary.resolve() not in outdated_resolved


def test_direct_plugin_golem_mark_stale_hook() -> None:
    idx_plugin = IndexPlugin()
    glo_plugin = GlossaryPlugin()

    cache_metadata: dict[str, dict[str, Any]] = {
        "/site/index.adoc": {
            "title": "Index",
            "page_role": "index",
            "node_types": ["document", "title"],
        },
        "/site/glossary.adoc": {
            "title": "Glossary",
            "page_role": "glossary",
            "node_types": ["document", "title"],
        },
        "/site/doc_with_terms.adoc": {
            "title": "Doc With Terms",
            "page_role": None,
            "node_types": ["document", "indexterm", "descriptionlist"],
        },
        "/site/doc_unrelated.adoc": {
            "title": "Unrelated",
            "page_role": None,
            "node_types": ["document", "paragraph"],
        },
    }

    # When doc_with_terms is changed
    idx_stale = idx_plugin.golem_mark_stale(
        changed_files=[Path("/site/doc_with_terms.adoc")],
        cache_metadata=cache_metadata,
    )
    assert idx_stale == [Path("/site/index.adoc")]

    glo_stale = glo_plugin.golem_mark_stale(
        changed_files=[Path("/site/doc_with_terms.adoc")],
        cache_metadata=cache_metadata,
    )
    assert glo_stale == [Path("/site/glossary.adoc")]

    # When unrelated file is changed
    idx_unrelated = idx_plugin.golem_mark_stale(
        changed_files=[Path("/site/doc_unrelated.adoc")],
        cache_metadata=cache_metadata,
    )
    assert not idx_unrelated

    glo_unrelated = glo_plugin.golem_mark_stale(
        changed_files=[Path("/site/doc_unrelated.adoc")],
        cache_metadata=cache_metadata,
    )
    assert not glo_unrelated


def test_deleted_file_with_terms_marks_aggregators_stale(tmp_path: Path) -> None:
    content_dir = tmp_path / "content"
    content_dir.mkdir()

    index_page = content_dir / "site_index.adoc"
    index_page.write_text("= Index\n:page-role: index\n\nIndex content.\n", encoding="utf-8")

    glossary_page = content_dir / "site_glossary.adoc"
    glossary_page.write_text("= Glossary\n:page-role: glossary\n\nGlossary content.\n", encoding="utf-8")

    doc_index = content_dir / "guide.adoc"
    doc_index.write_text("= Guide\n\n((Compiler))\n", encoding="utf-8")

    doc_glossary = content_dir / "api.adoc"
    doc_glossary.write_text("= API\n\n[glossary]\nAPI:: Interface\n", encoding="utf-8")

    config = GolemConfig(
        content_dir=str(content_dir),
        output_dir=str(tmp_path / "dist"),
        site_title="Test Site",
    )
    engine = BuildEngine(config, cache_file=tmp_path / "cache.json")
    idx_plugin = IndexPlugin()
    glo_plugin = GlossaryPlugin()
    engine.pm.register(idx_plugin)
    engine.pm.register(glo_plugin)

    # Initial build
    engine.build_site()

    # Delete the index term document
    doc_index.unlink()

    outdated = engine.staleness_tracker.get_outdated_files(commit=False)
    outdated_resolved = {p.resolve() for p in outdated}

    assert index_page.resolve() in outdated_resolved, "Index page must be stale when document with index terms is deleted"
    assert glossary_page.resolve() not in outdated_resolved

    # Delete the glossary document
    doc_glossary.unlink()

    outdated_after_glossary = engine.staleness_tracker.get_outdated_files(commit=False)
    outdated_after_glossary_resolved = {p.resolve() for p in outdated_after_glossary}

    assert glossary_page.resolve() in outdated_after_glossary_resolved, (
        "Glossary page must be stale when document with glossary definitions is deleted"
    )


def test_non_glossary_description_list_does_not_mark_glossary_stale(tmp_path: Path) -> None:
    content_dir = tmp_path / "content"
    content_dir.mkdir()

    glossary_page = content_dir / "site_glossary.adoc"
    glossary_page.write_text("= Glossary\n:page-role: glossary\n\nGlossary content.\n", encoding="utf-8")

    faq_page = content_dir / "faq.adoc"
    faq_page.write_text("= FAQ\n\nQuestion:: Answer\n", encoding="utf-8")

    config = GolemConfig(
        content_dir=str(content_dir),
        output_dir=str(tmp_path / "dist"),
        site_title="Test Site",
    )
    engine = BuildEngine(config, cache_file=tmp_path / "cache.json")
    glo_plugin = GlossaryPlugin()
    engine.pm.register(glo_plugin)

    # Initial build
    engine.build_site()

    # Modify the regular description list (not annotated with [glossary])
    faq_page.write_text("= FAQ\n\nQuestion:: Updated Answer\nAnother Question:: Another Answer\n", encoding="utf-8")

    outdated = engine.staleness_tracker.get_outdated_files(commit=False)
    outdated_resolved = {p.resolve() for p in outdated}

    assert faq_page.resolve() in outdated_resolved
    assert glossary_page.resolve() not in outdated_resolved, (
        "Glossary page must NOT be marked stale for regular description lists"
    )


def test_added_file_with_terms_marks_aggregators_stale(tmp_path: Path) -> None:
    content_dir = tmp_path / "content"
    content_dir.mkdir()

    index_page = content_dir / "site_index.adoc"
    index_page.write_text("= Index\n:page-role: index\n\nIndex content.\n", encoding="utf-8")

    glossary_page = content_dir / "site_glossary.adoc"
    glossary_page.write_text("= Glossary\n:page-role: glossary\n\nGlossary content.\n", encoding="utf-8")

    unrelated = content_dir / "about.adoc"
    unrelated.write_text("= About\n\nAbout text.\n", encoding="utf-8")

    config = GolemConfig(
        content_dir=str(content_dir),
        output_dir=str(tmp_path / "dist"),
        site_title="Test Site",
    )
    engine = BuildEngine(config, cache_file=tmp_path / "cache.json")
    idx_plugin = IndexPlugin()
    glo_plugin = GlossaryPlugin()
    engine.pm.register(idx_plugin)
    engine.pm.register(glo_plugin)

    # Initial build
    engine.build_site()

    # Add a brand new file with index term
    new_index_doc = content_dir / "new_guide.adoc"
    new_index_doc.write_text("= New Guide\n\n((NewConcept))\n", encoding="utf-8")

    outdated = engine.staleness_tracker.get_outdated_files(commit=False)
    outdated_resolved = {p.resolve() for p in outdated}

    assert new_index_doc.resolve() in outdated_resolved
    assert index_page.resolve() in outdated_resolved, "Index page must be stale when new file with index terms is added"
    assert glossary_page.resolve() not in outdated_resolved
