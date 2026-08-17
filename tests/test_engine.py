"""
= Build Engine Unit Tests for Golem

This module contains unit tests for verifying the Golem incremental build orchestration engine.
"""

from pathlib import Path
from golem.engine import BuildEngine
from golem.config import GolemConfig


def test_incremental_rebuild_logic(tmp_path):
    content_dir = tmp_path / "content"
    content_dir.mkdir()

    file_a = content_dir / "index.adoc"
    file_a.write_text("= Welcome\ninclude::sidebar.adoc[]")

    file_b = content_dir / "sidebar.adoc"
    file_b.write_text("Sidebar content")

    config = GolemConfig(
        content_dir=str(content_dir), output_dir=str(tmp_path / "dist")
    )
    engine = BuildEngine(config)

    # First compilation
    rebuild_set = engine.get_outdated_files()
    assert Path(file_a).resolve() in rebuild_set
    assert Path(file_b).resolve() in rebuild_set

    # Update cache mock state
    engine.update_cache_for_file(file_a)
    engine.update_cache_for_file(file_b)

    # Second check (unmodified)
    assert len(engine.get_outdated_files()) == 0

    # Edit file_b (the included sidebar)
    file_b.write_text("Modified Sidebar content")

    # Verify that file_a is flagged for recompilation because file_b is in its include-chain
    new_rebuild_set = engine.get_outdated_files()
    assert Path(file_a).resolve() in new_rebuild_set


def test_engine_build_site_unit(tmp_path):
    content_dir = tmp_path / "content"
    content_dir.mkdir()

    doc = content_dir / "test.adoc"
    doc.write_text("= Test Document\nSimple content.", encoding="utf-8")

    config = GolemConfig(
        content_dir=str(content_dir), output_dir=str(tmp_path / "dist")
    )
    engine = BuildEngine(config, cache_file=tmp_path / "cache.json")

    compiled = engine.build_site()
    assert len(compiled) == 1
    assert compiled[0] == tmp_path / "dist" / "test.html"


def test_cache_file_deletion_propagation(tmp_path):
    content_dir = tmp_path / "content"
    content_dir.mkdir()

    file_a = content_dir / "index.adoc"
    file_a.write_text("= Welcome\n\ninclude::sidebar.adoc[]\n", encoding="utf-8")

    file_b = content_dir / "sidebar.adoc"
    file_b.write_text("Sidebar content\n", encoding="utf-8")

    config = GolemConfig(
        content_dir=str(content_dir), output_dir=str(tmp_path / "dist")
    )
    engine = BuildEngine(config, cache_file=tmp_path / "cache.json")

    # Initial build and cache update
    engine.build_site()

    # Verify that the cache maps file_b as a dependency of file_a
    assert str(file_b.resolve()) in engine.cache_data["dependencies"].get(
        str(file_a.resolve()), []
    )

    # Second check (unmodified) should be empty
    assert len(engine.get_outdated_files()) == 0

    # Delete the included sidebar.adoc on disk
    file_b.unlink()

    # The engine must detect the deletion, propagate it to parent index.adoc, and clean up the cache
    outdated = engine.get_outdated_files()
    assert file_a.resolve() in outdated
    assert str(file_b.resolve()) not in engine.cache_data["files"]


def test_cache_global_config_edit_propagation(tmp_path):
    content_dir = tmp_path / "content"
    content_dir.mkdir()

    file_a = content_dir / "index.adoc"
    file_a.write_text("= Welcome\n\nContent here\n", encoding="utf-8")

    config_path = tmp_path / "golem.toml"
    config_path.write_text("[site]\ntitle = 'Old Title'\n", encoding="utf-8")

    config = GolemConfig(
        content_dir=str(content_dir),
        output_dir=str(tmp_path / "dist"),
        config_path=str(config_path.resolve()),
    )
    engine = BuildEngine(config, cache_file=tmp_path / "cache.json")

    # Initial build and cache update
    engine.build_site()

    # Second check (unmodified) should be empty
    assert len(engine.get_outdated_files()) == 0

    # Modify the config file
    config_path.write_text("[site]\ntitle = 'New Title'\n", encoding="utf-8")

    # The engine must detect the global config edit and invalidate index.adoc
    outdated = engine.get_outdated_files()
    assert file_a.resolve() in outdated


def test_cache_global_template_edit_propagation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    content_dir = tmp_path / "content"
    content_dir.mkdir()

    file_a = content_dir / "index.adoc"
    file_a.write_text("= Welcome\n\nContent here\n", encoding="utf-8")

    theme_dir = tmp_path / "themes" / "default"
    theme_dir.mkdir(parents=True)
    skeleton_pt = theme_dir / "skeleton.pt"
    skeleton_pt.write_text(
        "<html><body>${body_content}</body></html>", encoding="utf-8"
    )

    config = GolemConfig(
        content_dir="content",
        output_dir="dist",
        theme="default",
    )
    engine = BuildEngine(config, cache_file=tmp_path / "cache.json")

    # Initial build and cache update
    engine.build_site()

    # Second check (unmodified) should be empty
    assert len(engine.get_outdated_files()) == 0

    # Modify the template skeleton
    skeleton_pt.write_text(
        "<html><body>NEW ${body_content}</body></html>", encoding="utf-8"
    )

    # The engine must detect the global template edit and invalidate index.adoc
    outdated = engine.get_outdated_files()
    assert file_a.resolve() in outdated


def test_cache_non_adoc_edit_propagation(tmp_path):
    content_dir = tmp_path / "content"
    content_dir.mkdir()

    file_a = content_dir / "index.adoc"
    file_a.write_text("= Welcome\n\ninclude::code.py[]\n", encoding="utf-8")

    file_b = content_dir / "code.py"
    file_b.write_text("print('hello')\n", encoding="utf-8")

    config = GolemConfig(
        content_dir=str(content_dir), output_dir=str(tmp_path / "dist")
    )
    engine = BuildEngine(config, cache_file=tmp_path / "cache.json")

    # Initial build and cache update
    engine.build_site()

    # Verify that the cache maps file_b as a dependency of file_a
    assert str(file_b.resolve()) in engine.cache_data["dependencies"].get(
        str(file_a.resolve()), []
    )

    # Second check (unmodified) should be empty
    assert len(engine.get_outdated_files()) == 0

    # Edit the non-adoc file_b on disk
    file_b.write_text("print('hello modified')\n", encoding="utf-8")

    # The engine must detect the edit of code.py and invalidate parent index.adoc
    outdated = engine.get_outdated_files()
    assert file_a.resolve() in outdated


def test_cache_file_addition(tmp_path):
    content_dir = tmp_path / "content"
    content_dir.mkdir()

    file_a = content_dir / "index.adoc"
    file_a.write_text("= Welcome\n\nContent here\n", encoding="utf-8")

    config = GolemConfig(
        content_dir=str(content_dir), output_dir=str(tmp_path / "dist")
    )
    engine = BuildEngine(config, cache_file=tmp_path / "cache.json")

    # Initial build
    engine.build_site()
    assert len(engine.get_outdated_files()) == 0

    # Add a brand new file
    file_b = content_dir / "about.adoc"
    file_b.write_text("= About\n\nAbout content\n", encoding="utf-8")

    # The engine must detect the addition of about.adoc and mark it as outdated
    outdated = engine.get_outdated_files()
    assert file_b.resolve() in outdated

    # Compile site again
    compiled = engine.build_site()
    assert len(compiled) == 1
    assert compiled[0] == tmp_path / "dist" / "about.html"

    # Subsequent check should be empty
    assert len(engine.get_outdated_files()) == 0


def test_get_outdated_files_with_commit_false_does_not_mutate_cache(tmp_path):
    from golem.config import GolemConfig
    from golem.engine import BuildEngine

    content = tmp_path / "content"
    content.mkdir()
    (content / "index.adoc").write_text(
        "= Home\ninclude::sub.adoc[]\n", encoding="utf-8"
    )
    (content / "sub.adoc").write_text("Subcontent\n", encoding="utf-8")

    config = GolemConfig(content_dir=str(content), output_dir=str(tmp_path / "dist"))
    engine = BuildEngine(config, cache_file=tmp_path / "cache.json")

    # Initial build to populate cache
    engine.build_site()
    assert (tmp_path / "cache.json").exists()

    # Delete sub.adoc to simulate file deletion
    (content / "sub.adoc").unlink()

    # Query outdated files with commit=False
    outdated = engine.get_outdated_files(commit=False)
    assert len(outdated) > 0
    assert (content / "index.adoc").resolve() in outdated

    # Verify cache on disk STILL contains sub.adoc because commit was False!
    import json

    with open(tmp_path / "cache.json", "r") as f:
        disk_cache = json.load(f)
    assert str((content / "sub.adoc").resolve()) in disk_cache["files"]

    # Query with commit=True should now mutate and purge sub.adoc
    outdated_commit = engine.get_outdated_files(commit=True)
    assert len(outdated_commit) > 0
    with open(tmp_path / "cache.json", "r") as f:
        disk_cache_after = json.load(f)
    assert str((content / "sub.adoc").resolve()) not in disk_cache_after["files"]


def test_engine_corrupt_cache_handling(tmp_path):
    from golem.config import GolemConfig
    from golem.engine import BuildEngine

    content = tmp_path / "content"
    content.mkdir()
    (content / "index.adoc").write_text("= Home\n", encoding="utf-8")

    config = GolemConfig(content_dir=str(content), output_dir=str(tmp_path / "dist"))

    # 1. Non-JSON malformed cache file
    cache_file = tmp_path / "corrupt_cache.json"
    cache_file.write_text("Not valid JSON at all!!!", encoding="utf-8")

    engine = BuildEngine(config, cache_file=cache_file)
    assert engine.cache_data == {"files": {}, "dependencies": {}, "metadata": {}}
    # The corrupted file should have been deleted/cleared
    assert not cache_file.exists() or cache_file.read_text().strip() == ""

    # 2. Re-building should work perfectly and write a valid JSON cache
    engine.build_site()
    assert cache_file.exists()
    assert "files" in cache_file.read_text()


def test_engine_watcher_cpu_optimization(tmp_path):
    from unittest.mock import patch
    from golem.config import GolemConfig
    from golem.engine import BuildEngine

    content = tmp_path / "content"
    content.mkdir()
    file_a = content / "index.adoc"
    file_a.write_text("= Home\n", encoding="utf-8")

    config = GolemConfig(content_dir=str(content), output_dir=str(tmp_path / "dist"))
    engine = BuildEngine(config, cache_file=tmp_path / "cache.json")

    # First call: populates the SHA-256 and caches it
    h1 = engine._get_sha256(file_a)
    assert len(h1) == 64

    # Second call: should retrieve from cache without reading file again
    with patch("builtins.open") as mock_open:
        h2 = engine._get_sha256(file_a)
        assert h2 == h1
        mock_open.assert_not_called()


def test_engine_cache_concurrency_lock(tmp_path):
    from golem.config import GolemConfig
    from golem.engine import BuildEngine
    import threading
    import time

    content = tmp_path / "content"
    content.mkdir()
    (content / "index.adoc").write_text("= Home\n", encoding="utf-8")

    config = GolemConfig(content_dir=str(content), output_dir=str(tmp_path / "dist"))
    engine = BuildEngine(config, cache_file=tmp_path / "cache.json")

    acquired = []

    def worker():
        with engine._cache_lock():
            acquired.append("A")
            time.sleep(0.5)
            acquired.append("A_done")

    t = threading.Thread(target=worker)
    t.start()

    time.sleep(0.1)

    start_time = time.time()
    with engine._cache_lock():
        acquired.append("B")
    duration = time.time() - start_time

    t.join()

    assert acquired == ["A", "A_done", "B"]
    assert duration >= 0.3


def test_engine_watcher_deleted_file_handling(tmp_path):
    from golem.config import GolemConfig
    from golem.engine import BuildEngine

    content = tmp_path / "content"
    content.mkdir()
    file_a = content / "deleted.adoc"

    config = GolemConfig(content_dir=str(content), output_dir=str(tmp_path / "dist"))
    engine = BuildEngine(config, cache_file=tmp_path / "cache.json")

    # Accessing SHA-256 for a nonexistent/deleted file should return "" without raising OSError
    h = engine._get_sha256(file_a)
    assert h == ""


def test_engine_cache_lock_file_creation(tmp_path):
    from golem.config import GolemConfig
    from golem.engine import BuildEngine

    content = tmp_path / "content"
    content.mkdir()

    config = GolemConfig(content_dir=str(content), output_dir=str(tmp_path / "dist"))
    engine = BuildEngine(config, cache_file=tmp_path / "cache.json")

    # Assert that accessing lock_file creates cache.lock under the correct directory
    lock_path = tmp_path / "cache.lock"
    with engine._cache_lock():
        assert lock_path.exists()


def test_engine_cache_lock_release_on_error(tmp_path):
    from golem.config import GolemConfig
    from golem.engine import BuildEngine

    content = tmp_path / "content"
    content.mkdir()

    config = GolemConfig(content_dir=str(content), output_dir=str(tmp_path / "dist"))
    engine = BuildEngine(config, cache_file=tmp_path / "cache.json")

    # Assert that if an exception is raised inside the lock block, lock is still released
    try:
        with engine._cache_lock():
            raise ValueError("Intentional crash")
    except ValueError:
        pass

    # A second acquisition should succeed immediately (if lock was not released, it would block/crash)
    with engine._cache_lock():
        pass


def test_navigation_auto_discovery_basic(tmp_path):
    content = tmp_path / "content"
    content.mkdir()
    (content / "index.adoc").write_text(
        "= Golem Docs\n\nWelcome page", encoding="utf-8"
    )
    (content / "01-getting-started.adoc").write_text(
        "= Getting Started\n\nGetting started guide", encoding="utf-8"
    )
    (content / "02-architecture.adoc").write_text(
        "Architecture content", encoding="utf-8"
    )
    (content / "03_advanced_features.adoc").write_text(
        "Advanced features", encoding="utf-8"
    )

    config = GolemConfig(content_dir=str(content), output_dir=str(tmp_path / "dist"))
    engine = BuildEngine(config, cache_file=tmp_path / "cache.json")

    nav = engine.discover_navigation()
    assert len(nav) == 4
    # Index pinned at top
    assert nav[0]["title"] == "Golem Docs"
    assert nav[0]["url"] == "index.html"

    # Numeric sorting prefixes stripped for display titles
    assert nav[1]["title"] == "Getting Started"
    assert nav[1]["url"] == "01-getting-started.html"

    assert nav[2]["title"] == "Architecture"
    assert nav[2]["url"] == "02-architecture.html"

    assert nav[3]["title"] == "Advanced Features"
    assert nav[3]["url"] == "03_advanced_features.html"


def test_navigation_auto_discovery_nested_hierarchy(tmp_path):
    content = tmp_path / "content"
    content.mkdir()
    (content / "README.adoc").write_text("= Overview\n\nReadme", encoding="utf-8")
    (content / "01-intro.adoc").write_text("= Introduction\n\nIntro", encoding="utf-8")

    guides_dir = content / "02-guides"
    guides_dir.mkdir()
    (guides_dir / "index.adoc").write_text(
        "= Guides Overview\n\nGuides index", encoding="utf-8"
    )
    (guides_dir / "01-config.adoc").write_text("Configuration", encoding="utf-8")
    (guides_dir / "02-deploy.adoc").write_text("Deployment", encoding="utf-8")

    config = GolemConfig(content_dir=str(content), output_dir=str(tmp_path / "dist"))
    engine = BuildEngine(config, cache_file=tmp_path / "cache.json")

    nav = engine.discover_navigation()
    assert len(nav) == 3
    # Root README pinned at top
    assert nav[0]["title"] == "Overview"
    assert nav[0]["url"] == "README.html"

    assert nav[1]["title"] == "Introduction"
    assert nav[1]["url"] == "01-intro.html"

    # Nested section
    assert nav[2]["title"] == "Guides Overview"
    assert nav[2]["url"] == "02-guides/index.html"
    children = nav[2]["children"]
    assert len(children) == 2
    assert children[0]["title"] == "Config"
    assert children[0]["url"] == "02-guides/01-config.html"
    assert children[1]["title"] == "Deploy"
    assert children[1]["url"] == "02-guides/02-deploy.html"


def test_navigation_explicit_override_with_navigation_nav(tmp_path):
    content = tmp_path / "content"
    content.mkdir()
    (content / "01-intro.adoc").write_text("Intro", encoding="utf-8")
    (content / "02-architecture.adoc").write_text("Architecture", encoding="utf-8")
    (content / "index.adoc").write_text("= Welcome\n\nWelcome", encoding="utf-8")

    config = GolemConfig(
        content_dir=str(content),
        output_dir=str(tmp_path / "dist"),
        navigation_nav=["02-architecture.adoc", "01-intro.adoc"],
    )
    engine = BuildEngine(config, cache_file=tmp_path / "cache.json")

    nav = engine.discover_navigation()
    assert len(nav) == 2
    assert nav[0]["title"] == "Architecture"
    assert nav[0]["url"] == "02-architecture.html"
    assert nav[1]["title"] == "Intro"
    assert nav[1]["url"] == "01-intro.html"


def test_navigation_html_generation_and_relative_urls(tmp_path):
    content = tmp_path / "content"
    content.mkdir()
    (content / "index.adoc").write_text("= Welcome\n\nRoot welcome", encoding="utf-8")

    guides = content / "guides"
    guides.mkdir()
    (guides / "intro.adoc").write_text(
        "= Guides Intro\n\nGuide intro", encoding="utf-8"
    )

    config = GolemConfig(content_dir=str(content), output_dir=str(tmp_path / "dist"))
    engine = BuildEngine(config, cache_file=tmp_path / "cache.json")

    compiled = engine.build_site()
    assert len(compiled) == 2

    root_html = (tmp_path / "dist" / "index.html").read_text(encoding="utf-8")
    assert 'href="index.html"' in root_html
    assert 'href="guides/intro.html"' in root_html

    nested_html = (tmp_path / "dist" / "guides" / "intro.html").read_text(
        encoding="utf-8"
    )
    assert 'href="../index.html"' in nested_html
    assert (
        'href="../guides/intro.html"' in nested_html
        or 'href="intro.html"' in nested_html
    )


def test_engine_error_interception_permissive_mode(tmp_path, monkeypatch):
    content = tmp_path / "content"
    content.mkdir()
    (content / "valid.adoc").write_text("= Valid\n\nValid text", encoding="utf-8")
    (content / "broken.adoc").write_text("= Broken\n\nBroken text", encoding="utf-8")

    config = GolemConfig(
        content_dir=str(content),
        output_dir=str(tmp_path / "dist"),
        strict=False,
    )
    engine = BuildEngine(config, cache_file=tmp_path / "cache.json")

    import asciidoctrine

    orig_parse = asciidoctrine.parse_to_ast

    def mock_parse(text, base_dir=None):
        if "Broken text" in text:
            raise ValueError("AsciiDoc syntax parse error simulated")
        return orig_parse(text, base_dir=base_dir)

    monkeypatch.setattr(asciidoctrine, "parse_to_ast", mock_parse)

    compiled = engine.build_site()
    # In permissive mode, valid page is built and broken page error is intercepted
    assert len(compiled) == 1
    assert compiled[0] == tmp_path / "dist" / "valid.html"
    assert len(engine.errors) == 1
    assert "broken.adoc" in engine.errors[0]["file"]
    assert "AsciiDoc syntax parse error simulated" in engine.errors[0]["message"]
    assert engine.errors[0]["error_type"] == "ValueError"


def test_engine_error_interception_strict_mode(tmp_path, monkeypatch):
    import pytest

    content = tmp_path / "content"
    content.mkdir()
    (content / "broken.adoc").write_text("= Broken\n\nBroken text", encoding="utf-8")

    config = GolemConfig(
        content_dir=str(content),
        output_dir=str(tmp_path / "dist"),
        strict=True,
    )
    engine = BuildEngine(config, cache_file=tmp_path / "cache.json")

    import asciidoctrine

    def mock_parse(text, base_dir=None):
        raise ValueError("Fatal syntax error in strict mode")

    monkeypatch.setattr(asciidoctrine, "parse_to_ast", mock_parse)

    with pytest.raises(ValueError, match="Fatal syntax error in strict mode"):
        engine.build_site()

    assert len(engine.errors) >= 1
    assert "broken.adoc" in engine.errors[0]["file"]


def test_engine_passes_template_search_paths_to_render_body(tmp_path, monkeypatch):
    content = tmp_path / "content"
    content.mkdir()
    (content / "index.adoc").write_text("= Test\n\nContent", encoding="utf-8")

    custom_tpl = tmp_path / "my_templates"
    custom_tpl.mkdir()

    config = GolemConfig(
        content_dir=str(content),
        output_dir=str(tmp_path / "dist"),
        templates_dir=str(custom_tpl),
        theme="custom_theme",
    )
    engine = BuildEngine(config, cache_file=tmp_path / "cache.json")

    captured_search_paths = []
    import golem.engine

    orig_render_body = golem.engine.render_body

    def mock_render_body(asg, search_paths=None):
        captured_search_paths.append(search_paths)
        return orig_render_body(asg, search_paths=search_paths)

    monkeypatch.setattr(golem.engine, "render_body", mock_render_body)

    engine.build_site()

    assert len(captured_search_paths) == 1
    assert captured_search_paths[0] is not None
    # Check that custom_tpl is in the search paths
    search_path_strs = [str(p) for p in captured_search_paths[0]]
    assert (
        str(custom_tpl.resolve()) in search_path_strs
        or str(custom_tpl) in search_path_strs
    )


def test_partials_exclusion_and_dependency_propagation(tmp_path):
    content_dir = tmp_path / "content"
    content_dir.mkdir()

    file_main = content_dir / "index.adoc"
    file_main.write_text(
        "= Home\ninclude::_sidebar.adoc[]\ninclude::_snippets/note.adoc[]\n",
        encoding="utf-8",
    )

    file_partial = content_dir / "_sidebar.adoc"
    file_partial.write_text("Sidebar partial content\n", encoding="utf-8")

    snippets_dir = content_dir / "_snippets"
    snippets_dir.mkdir()
    file_snippet = snippets_dir / "note.adoc"
    file_snippet.write_text("Snippet partial content\n", encoding="utf-8")

    file_regular = content_dir / "regular.adoc"
    file_regular.write_text("= Regular\nRegular page\n", encoding="utf-8")

    config = GolemConfig(
        content_dir=str(content_dir), output_dir=str(tmp_path / "dist")
    )
    engine = BuildEngine(config, cache_file=tmp_path / "cache.json")

    # Initial site build
    compiled = engine.build_site()

    # Partials must NOT generate standalone .html output files
    assert tmp_path / "dist" / "index.html" in compiled
    assert tmp_path / "dist" / "regular.html" in compiled
    assert (tmp_path / "dist" / "index.html").exists()
    assert (tmp_path / "dist" / "regular.html").exists()
    assert not (tmp_path / "dist" / "_sidebar.html").exists()
    assert not (tmp_path / "dist" / "_snippets" / "note.html").exists()

    # Partials MUST be tracked in cache dependencies and files
    assert str(file_partial.resolve()) in engine.cache_data["dependencies"].get(
        str(file_main.resolve()), []
    )
    assert str(file_snippet.resolve()) in engine.cache_data["dependencies"].get(
        str(file_main.resolve()), []
    )
    assert str(file_partial.resolve()) in engine.cache_data["files"]
    assert str(file_snippet.resolve()) in engine.cache_data["files"]

    # Initial check (unmodified) should have no outdated files
    assert len(engine.get_outdated_files()) == 0

    # Modify the partial file _sidebar.adoc
    file_partial.write_text("Modified sidebar partial content\n", encoding="utf-8")

    # Modifying partial must flag parent index.adoc as outdated, but not partial itself as output
    outdated = engine.get_outdated_files()
    assert file_main.resolve() in outdated
    assert file_partial.resolve() not in outdated

    # Rebuild site
    recompiled = engine.build_site()
    assert tmp_path / "dist" / "index.html" in recompiled
    assert not (tmp_path / "dist" / "_sidebar.html").exists()
    assert len(engine.get_outdated_files()) == 0


def test_partials_excluded_from_navigation(tmp_path):
    content_dir = tmp_path / "content"
    content_dir.mkdir()

    (content_dir / "index.adoc").write_text("= Home\n", encoding="utf-8")
    (content_dir / "01-guide.adoc").write_text("= Guide\n", encoding="utf-8")
    (content_dir / "_sidebar.adoc").write_text("= Sidebar\n", encoding="utf-8")

    snippets_dir = content_dir / "_snippets"
    snippets_dir.mkdir()
    (snippets_dir / "note.adoc").write_text("= Note\n", encoding="utf-8")

    guides_dir = content_dir / "guides"
    guides_dir.mkdir()
    (guides_dir / "index.adoc").write_text("= Guides\n", encoding="utf-8")
    (guides_dir / "_internal.adoc").write_text("= Internal\n", encoding="utf-8")
    (guides_dir / "tutorial.adoc").write_text("= Tutorial\n", encoding="utf-8")

    config = GolemConfig(
        content_dir=str(content_dir), output_dir=str(tmp_path / "dist")
    )
    engine = BuildEngine(config, cache_file=tmp_path / "cache.json")

    nav = engine.discover_navigation()

    # Collect all titles and paths in nav recursively
    def collect_nav(items):
        res = []
        for item in items:
            res.append((item.get("title"), item.get("path")))
            res.extend(collect_nav(item.get("children", [])))
        return res

    all_nav = collect_nav(nav)
    titles = [t[0] for t in all_nav]
    paths = [t[1] for t in all_nav]

    assert "Home" in titles
    assert "Guide" in titles
    assert "Guides" in titles
    assert "Tutorial" in titles

    # Underscore partials and partial dirs must NOT appear
    assert "Sidebar" not in titles
    assert "Note" not in titles
    assert "Internal" not in titles

    for p in paths:
        if p:
            parts = Path(p).parts
            assert not any(part.startswith("_") for part in parts)


def test_sync_static_assets_user_and_theme(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    content_dir = tmp_path / "content"
    content_dir.mkdir()
    (content_dir / "index.adoc").write_text("= Home\n", encoding="utf-8")

    # Create user static dir
    user_static = tmp_path / "static"
    (user_static / "css").mkdir(parents=True)
    (user_static / "css" / "style.css").write_text(
        "body { color: red; }", encoding="utf-8"
    )
    (user_static / "app.js").write_text("console.log('app');", encoding="utf-8")

    # Create theme static dir
    theme_static = tmp_path / "themes" / "custom" / "static"
    (theme_static / "css").mkdir(parents=True)
    (theme_static / "css" / "style.css").write_text(
        "body { color: blue; }", encoding="utf-8"
    )
    (theme_static / "theme.css").write_text("/* theme */", encoding="utf-8")

    output_dir = tmp_path / "dist"

    config = GolemConfig(
        content_dir="content",
        output_dir="dist",
        static_dir=str(user_static),
        theme="custom",
    )
    engine = BuildEngine(config, cache_file=tmp_path / "cache.json")

    # Test sync_static_assets directly
    engine.sync_static_assets()

    dist_static = output_dir / "static"
    assert (dist_static / "theme.css").exists()
    assert (dist_static / "theme.css").read_text(encoding="utf-8") == "/* theme */"
    assert (dist_static / "app.js").exists()
    assert (dist_static / "app.js").read_text(encoding="utf-8") == "console.log('app');"
    # User static asset overrides theme static asset
    assert (dist_static / "css" / "style.css").read_text(
        encoding="utf-8"
    ) == "body { color: red; }"

    # Test that build_site() automatically triggers sync_static_assets()
    import shutil

    shutil.rmtree(output_dir)
    assert not output_dir.exists()

    engine.build_site()
    assert (dist_static / "css" / "style.css").exists()
    assert (dist_static / "theme.css").exists()


def test_metadata_caching_and_recovery(tmp_path):
    from unittest.mock import patch

    content_dir = tmp_path / "content"
    content_dir.mkdir()

    doc1 = content_dir / "doc1.adoc"
    doc1.write_text(
        "= Custom Title\n:nav_title: Short Nav\n:toc:\n\nContent\n", encoding="utf-8"
    )

    doc2 = content_dir / "doc2.adoc"
    doc2.write_text("= Other Doc\n:!toc:\n\nOther content\n", encoding="utf-8")

    cache_file = tmp_path / "cache.json"

    config = GolemConfig(
        content_dir=str(content_dir), output_dir=str(tmp_path / "dist")
    )
    engine = BuildEngine(config, cache_file=cache_file)

    # Calling discover_navigation populates cache_data["metadata"]
    nav = engine.discover_navigation()
    assert len(nav) == 2

    assert "metadata" in engine.cache_data
    meta1 = engine.cache_data["metadata"].get(str(doc1.resolve()))
    assert meta1 is not None
    assert meta1["title"] == "Custom Title"
    assert meta1["nav_title"] == "Short Nav"
    assert meta1["has_toc"] is True

    meta2 = engine.cache_data["metadata"].get(str(doc2.resolve()))
    assert meta2 is not None
    assert meta2["title"] == "Other Doc"
    assert meta2["has_toc"] is False

    engine.save_cache()

    # Re-instantiate engine with existing cache file
    engine2 = BuildEngine(config, cache_file=cache_file)
    assert "metadata" in engine2.cache_data
    assert str(doc1.resolve()) in engine2.cache_data["metadata"]

    # When files are unmodified, discover_navigation uses cached metadata without re-reading from disk
    orig_open = open
    open_calls = []

    def tracking_open(file, *args, **kwargs):
        open_calls.append(str(file))
        return orig_open(file, *args, **kwargs)

    with patch("builtins.open", side_effect=tracking_open):
        nav2 = engine2.discover_navigation()
        assert len(nav2) == 2
        # Neither doc1.adoc nor doc2.adoc should have been opened for reading
        assert not any(
            str(doc1.resolve()) in call or "doc1.adoc" in call for call in open_calls
        )
        assert not any(
            str(doc2.resolve()) in call or "doc2.adoc" in call for call in open_calls
        )

    # When a file is modified, discover_navigation refreshes the cached metadata
    doc1.write_text("= Updated Title\n:nav_title: Updated Nav\n", encoding="utf-8")
    nav3 = engine2.discover_navigation()
    assert len(nav3) == 2
    updated_meta1 = engine2.cache_data["metadata"].get(str(doc1.resolve()))
    assert updated_meta1["title"] == "Updated Title"
    assert updated_meta1["nav_title"] == "Updated Nav"
