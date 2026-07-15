"""
= Build Engine Integration Tests for Golem

This module contains integration tests verifying Golem's BuildEngine end-to-end orchestration,
Chameleon layout framing, and DAG dependency graph invalidations.
"""

from golem.engine import BuildEngine
from golem.config import GolemConfig


def test_incremental_build_integration(tmp_path):
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    output_dir = tmp_path / "dist"

    file_a = content_dir / "index.adoc"
    file_a.write_text("= Welcome\ninclude::sidebar.adoc[]", encoding="utf-8")

    file_b = content_dir / "sidebar.adoc"
    file_b.write_text("Sidebar details", encoding="utf-8")

    config = GolemConfig(
        content_dir=str(content_dir), output_dir=str(output_dir)
    )
    engine = BuildEngine(config, cache_file=tmp_path / "cache.json")

    # First compilation (both files get compiled/recorded in dependency cache)
    compiled = engine.build_site()
    assert len(compiled) == 2
    assert (output_dir / "index.html").exists()
    assert (output_dir / "sidebar.html").exists()

    # Second execution (no files changed, nothing is outputted)
    engine2 = BuildEngine(config, cache_file=tmp_path / "cache.json")
    compiled_empty = engine2.build_site()
    assert len(compiled_empty) == 0

    # Third execution: modify child sidebar file, which invalidates and triggers parent rebuild
    file_b.write_text("Sidebar details modified", encoding="utf-8")
    engine3 = BuildEngine(config, cache_file=tmp_path / "cache.json")
    compiled_rebuilt = engine3.build_site()

    # Both index and sidebar rebuilt because index depends on sidebar
    assert len(compiled_rebuilt) == 2
