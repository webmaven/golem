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
    assert str(file_b.resolve()) in engine.cache_data["dependencies"].get(str(file_a.resolve()), [])

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
    skeleton_pt.write_text("<html><body>${body_content}</body></html>", encoding="utf-8")

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
    skeleton_pt.write_text("<html><body>NEW ${body_content}</body></html>", encoding="utf-8")

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
    assert str(file_b.resolve()) in engine.cache_data["dependencies"].get(str(file_a.resolve()), [])

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
    (content / "index.adoc").write_text("= Home\ninclude::sub.adoc[]\n", encoding="utf-8")
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
    assert engine.cache_data == {"files": {}, "dependencies": {}}
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







