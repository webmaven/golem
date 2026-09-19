from pathlib import Path
from typing import Any

import pluggy

from golem.cache import BuildCache
from golem.config import GolemConfig
from golem.plugins import GolemSpecs, hookimpl
from golem.staleness import StalenessTracker, is_partial


def test_is_partial_function(tmp_path):
    content = tmp_path / "content"
    content.mkdir()

    p1 = content / "_partial.adoc"
    p2 = content / "guide" / "_snippet.adoc"
    p3 = content / "_includes" / "header.adoc"
    p4 = content / "index.adoc"
    p5 = content / "guide" / "intro.adoc"

    assert is_partial(p1, content) is True
    assert is_partial(p2, content) is True
    assert is_partial(p3, content) is True
    assert is_partial(p4, content) is False
    assert is_partial(p5, content) is False


def test_staleness_tracker_is_partial_method(tmp_path):
    content = tmp_path / "content"
    content.mkdir()
    cache = BuildCache(tmp_path / "cache.json")
    config = GolemConfig(content_dir=str(content), output_dir=str(tmp_path / "dist"))
    tracker = StalenessTracker(config, cache, content)

    assert tracker.is_partial(content / "_sidebar.adoc") is True
    assert tracker.is_partial(content / "about.adoc") is False


def test_staleness_tracker_dependency_graph(tmp_path):
    content = tmp_path / "content"
    content.mkdir()
    doc_a = content / "index.adoc"
    doc_b = content / "_sidebar.adoc"
    doc_a.write_text("= Index\ninclude::_sidebar.adoc[]\n", encoding="utf-8")
    doc_b.write_text("Sidebar content\n", encoding="utf-8")

    cache = BuildCache(tmp_path / "cache.json")
    config = GolemConfig(content_dir=str(content), output_dir=str(tmp_path / "dist"))
    tracker = StalenessTracker(config, cache, content)

    tracker.update_cache_for_file(doc_a)
    tracker.update_cache_for_file(doc_b)

    forward_deps, reverse_deps = tracker._build_dependency_graph()
    assert doc_b.resolve() in forward_deps[doc_a.resolve()]
    assert doc_a.resolve() in reverse_deps[doc_b.resolve()]


def test_staleness_tracker_template_discovery(tmp_path):
    content = tmp_path / "content"
    content.mkdir()
    templates = tmp_path / "custom_templates"
    templates.mkdir()
    (templates / "layout.html").write_text("<html></html>", encoding="utf-8")
    (templates / "component.pt").write_text("<div></div>", encoding="utf-8")
    (templates / ".hidden.html").write_text("<!-- hidden -->", encoding="utf-8")
    static_dir = templates / "static"
    static_dir.mkdir()
    (static_dir / "preview.pt").write_text("preview", encoding="utf-8")

    config = GolemConfig(
        content_dir=str(content),
        output_dir=str(tmp_path / "dist"),
        templates_dir=str(templates),
    )
    cache = BuildCache(tmp_path / "cache.json")
    tracker = StalenessTracker(config, cache, content)

    search_paths = tracker._get_template_search_paths()
    assert templates.resolve() in [p.resolve() for p in search_paths]

    tpl_files = tracker._get_template_files()
    tpl_names = {t.name for t in tpl_files}
    assert "layout.html" in tpl_names
    assert "component.pt" in tpl_names
    assert ".hidden.html" not in tpl_names
    assert "preview.pt" not in tpl_names

    fingerprints = tracker._get_template_fingerprints()
    assert "layout.html" in fingerprints
    assert "component.pt" in fingerprints


def test_staleness_tracker_outdated_file_detection(tmp_path):
    content = tmp_path / "content"
    content.mkdir()
    doc1 = content / "page1.adoc"
    doc2 = content / "page2.adoc"
    doc1.write_text("= Page 1", encoding="utf-8")
    doc2.write_text("= Page 2", encoding="utf-8")

    config = GolemConfig(content_dir=str(content), output_dir=str(tmp_path / "dist"))
    cache = BuildCache(tmp_path / "cache.json")
    tracker = StalenessTracker(config, cache, content)

    # Initial state: all docs outdated
    outdated = tracker.get_outdated_files()
    assert doc1.resolve() in outdated
    assert doc2.resolve() in outdated

    # Update cache for both
    tracker.update_cache_for_file(doc1)
    tracker.update_cache_for_file(doc2)

    # Now no files are outdated
    assert len(tracker.get_outdated_files()) == 0

    # Modify doc1
    doc1.write_text("= Page 1 Modified", encoding="utf-8")
    outdated = tracker.get_outdated_files()
    assert doc1.resolve() in outdated
    assert doc2.resolve() not in outdated


def test_staleness_tracker_golem_mark_stale_ordering_captures_modified_files(tmp_path: Path) -> None:
    content = tmp_path / "content"
    content.mkdir()
    doc1 = content / "page1.adoc"
    doc2 = content / "page2.adoc"
    doc1.write_text("= Page 1", encoding="utf-8")
    doc2.write_text("= Page 2", encoding="utf-8")

    config = GolemConfig(content_dir=str(content), output_dir=str(tmp_path / "dist"))
    cache = BuildCache(tmp_path / "cache.json")

    # Set up a plugin manager with a spy hook for golem_mark_stale
    pm = pluggy.PluginManager("golem")
    pm.add_hookspecs(GolemSpecs)

    captured_changed_files: list[list[Path]] = []

    class SpyPlugin:
        @hookimpl
        def golem_mark_stale(
            self,
            changed_files: list[Path],
            cache_metadata: dict[str, dict[str, Any]],
        ) -> list[Path] | None:
            captured_changed_files.append(list(changed_files))
            return None

    pm.register(SpyPlugin())
    tracker = StalenessTracker(config, cache, content, plugin_manager=pm)

    # Populate cache for both documents initially
    tracker.update_cache_for_file(doc1)
    tracker.update_cache_for_file(doc2)
    cache.save_cache()

    # Modify doc1 on disk so its hash differs from cache
    doc1.write_text("= Page 1 - Modified Content", encoding="utf-8")

    # Call get_outdated_files()
    outdated = tracker.get_outdated_files(commit=False)

    # Verify spy captured changed_files
    assert len(captured_changed_files) == 1, "golem_mark_stale hook must have been called once"
    passed_files = captured_changed_files[0]
    passed_files_resolved = {p.resolve() for p in passed_files}

    # Assert that doc1 is present in changed_files passed to the hook
    assert doc1.resolve() in passed_files_resolved, (
        "Modified file must be present in changed_files passed to golem_mark_stale (proving the hook runs after hash scanning)"
    )
    assert doc2.resolve() not in passed_files_resolved, "Unmodified file must not be in changed_files"
    assert doc1.resolve() in {p.resolve() for p in outdated}
