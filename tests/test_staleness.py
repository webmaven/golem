"""Unit tests for golem.staleness (StalenessTracker and is_partial)."""

from golem.cache import BuildCache
from golem.config import GolemConfig
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
    doc_a.write_text("= Index\ninclude::_sidebar.adoc[]", encoding="utf-8")
    doc_b.write_text("Sidebar content", encoding="utf-8")

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
