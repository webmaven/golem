"""
= CLI Partial Build Tests for Golem

This module tests Phase 1 Task 5: partial builds CLI option (`golem build --partial <target>`).
"""

from pathlib import Path
import time
from click.testing import CliRunner
import pytest
from golem.cli import main
from golem.config import GolemConfig
from golem.engine import BuildEngine


@pytest.fixture
def project_setup(tmp_path, monkeypatch):
    """Set up a test Golem site with multiple documents and directories."""
    content_dir = tmp_path / "content"
    content_dir.mkdir(parents=True, exist_ok=True)
    section_dir = content_dir / "section"
    section_dir.mkdir(parents=True, exist_ok=True)

    golem_toml = tmp_path / "golem.toml"
    golem_toml.write_text(
        """
[site]
title = "Partial Build Test Site"
author = "Test Author"

[build]
content_dir = "content"
output_dir = "dist"
theme = "default"
""",
        encoding="utf-8",
    )

    (content_dir / "index.adoc").write_text(
        "= Home Page\nTest Author\n:nav_order: 1\n\nWelcome to home.",
        encoding="utf-8",
    )
    (content_dir / "guide.adoc").write_text(
        "= User Guide\nTest Author\n:nav_order: 2\n\nGuide content.",
        encoding="utf-8",
    )
    (content_dir / "about.adoc").write_text(
        "= About Us\nTest Author\n:nav_order: 3\n\nAbout content.",
        encoding="utf-8",
    )
    (section_dir / "page1.adoc").write_text(
        "= Section Page 1\nTest Author\n\nSection page 1 content.",
        encoding="utf-8",
    )
    (section_dir / "page2.adoc").write_text(
        "= Section Page 2\nTest Author\n\nSection page 2 content.",
        encoding="utf-8",
    )
    (section_dir / "_snippet.adoc").write_text(
        "Partial snippet content.",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_cli_partial_build_help_flag():
    runner = CliRunner()
    result = runner.invoke(main, ["build", "--help"])
    assert result.exit_code == 0
    assert "--partial" in result.output
    assert "Rebuild only specified file or directory path" in result.output
    assert "without wiping other outputs" in result.output


def test_cli_clean_and_partial_mutually_exclusive(project_setup):
    runner = CliRunner()
    result = runner.invoke(main, ["build", "--clean", "--partial", "content/guide.adoc"])
    assert result.exit_code != 0
    assert "Options --clean and --partial are mutually exclusive." in result.output


def test_cli_partial_single_file_force_rebuild(project_setup):
    runner = CliRunner()
    # 1. Full build
    res_full = runner.invoke(main, ["build"])
    assert res_full.exit_code == 0
    assert Path("dist/index.html").exists()
    assert Path("dist/guide.html").exists()
    assert Path("dist/about.html").exists()

    mtime_index_before = Path("dist/index.html").stat().st_mtime_ns
    mtime_guide_before = Path("dist/guide.html").stat().st_mtime_ns
    mtime_about_before = Path("dist/about.html").stat().st_mtime_ns

    time.sleep(0.05)

    # 2. Rebuild only guide.adoc with --partial (relative to cwd)
    res_partial = runner.invoke(main, ["build", "--partial", "content/guide.adoc"])
    assert res_partial.exit_code == 0
    assert "Built 1 pages" in res_partial.output or "Built 1 page" in res_partial.output

    mtime_index_after = Path("dist/index.html").stat().st_mtime_ns
    mtime_guide_after = Path("dist/guide.html").stat().st_mtime_ns
    mtime_about_after = Path("dist/about.html").stat().st_mtime_ns

    # guide.html was rebuilt (mtime increased)
    assert mtime_guide_after > mtime_guide_before
    # unchanged files were NOT rebuilt
    assert mtime_index_after == mtime_index_before
    assert mtime_about_after == mtime_about_before

    # 3. Test relative to content_dir
    time.sleep(0.05)
    res_partial_rel = runner.invoke(main, ["build", "--partial", "guide.adoc"])
    assert res_partial_rel.exit_code == 0
    assert Path("dist/guide.html").stat().st_mtime_ns > mtime_guide_after


def test_cli_partial_directory_rebuild(project_setup):
    runner = CliRunner()
    # 1. Full build
    res_full = runner.invoke(main, ["build"])
    assert res_full.exit_code == 0
    assert Path("dist/section/page1.html").exists()
    assert Path("dist/section/page2.html").exists()
    assert not Path("dist/section/_snippet.html").exists()

    mtime_p1_before = Path("dist/section/page1.html").stat().st_mtime_ns
    mtime_p2_before = Path("dist/section/page2.html").stat().st_mtime_ns
    mtime_index_before = Path("dist/index.html").stat().st_mtime_ns

    time.sleep(0.05)

    # 2. Rebuild directory
    res_dir = runner.invoke(main, ["build", "--partial", "content/section"])
    assert res_dir.exit_code == 0
    assert "Built 2 pages" in res_dir.output

    mtime_p1_after = Path("dist/section/page1.html").stat().st_mtime_ns
    mtime_p2_after = Path("dist/section/page2.html").stat().st_mtime_ns
    mtime_index_after = Path("dist/index.html").stat().st_mtime_ns

    # Both section pages rebuilt
    assert mtime_p1_after > mtime_p1_before
    assert mtime_p2_after > mtime_p2_before
    # Index was not rebuilt
    assert mtime_index_after == mtime_index_before
    # Partials still not emitted
    assert not Path("dist/section/_snippet.html").exists()


def test_cli_partial_nonexistent_target_fails(project_setup):
    runner = CliRunner()
    # Non-existent file
    res_file = runner.invoke(main, ["build", "--partial", "nonexistent.adoc"])
    assert res_file.exit_code != 0
    assert "not found" in res_file.output.lower() or "error" in res_file.output.lower()

    # Non-existent directory
    res_dir = runner.invoke(main, ["build", "--partial", "content/nonexistent_folder"])
    assert res_dir.exit_code != 0
    assert "not found" in res_dir.output.lower() or "error" in res_dir.output.lower()

    # Target outside content_dir
    res_outside = runner.invoke(main, ["build", "--partial", "golem.toml"])
    assert res_outside.exit_code != 0


def test_cli_partial_preserves_other_outputs(project_setup):
    runner = CliRunner()
    # 1. Full build
    res_full = runner.invoke(main, ["build"])
    assert res_full.exit_code == 0

    # Create an extra output artifact
    extra_file = Path("dist/custom_extra.txt")
    extra_file.write_text("persisted custom output", encoding="utf-8")

    # 2. Partial build
    res_partial = runner.invoke(main, ["build", "--partial", "content/about.adoc"])
    assert res_partial.exit_code == 0

    # Existing files must be preserved
    assert extra_file.exists()
    assert extra_file.read_text(encoding="utf-8") == "persisted custom output"
    assert Path("dist/index.html").exists()
    assert Path("dist/guide.html").exists()
    assert Path("dist/section/page1.html").exists()


def test_cli_partial_navigation_includes_full_site(project_setup):
    runner = CliRunner()
    # 1. Full build
    res_full = runner.invoke(main, ["build"])
    assert res_full.exit_code == 0

    # 2. Add a new document in content_dir but ONLY rebuild guide.adoc via --partial
    (Path("content") / "new_section.adoc").write_text(
        "= New Features\nTest Author\n:nav_order: 4\n\nNew section content.",
        encoding="utf-8",
    )

    res_partial = runner.invoke(main, ["build", "--partial", "content/guide.adoc"])
    assert res_partial.exit_code == 0

    # 3. Read guide.html - it should contain the newly discovered navigation item from full site
    guide_html = Path("dist/guide.html").read_text(encoding="utf-8")
    assert "New Features" in guide_html
    assert "Home Page" in guide_html
    assert "About Us" in guide_html

    # 4. new_section.html itself was NOT compiled
    assert not Path("dist/new_section.html").exists()


def test_engine_partial_build_direct(project_setup):
    config = GolemConfig(
        content_dir=str(project_setup / "content"),
        output_dir=str(project_setup / "dist"),
        config_path=str(project_setup / "golem.toml"),
    )
    engine = BuildEngine(config)

    # Initial build
    engine.build_site()
    assert (project_setup / "dist" / "guide.html").exists()

    # Direct call with partial target (single file)
    compiled = engine.build_site(partial_target="guide.adoc")
    assert len(compiled) == 1
    assert compiled[0] == (project_setup / "dist" / "guide.html").resolve()

    # Direct call with invalid path raises FileNotFoundError
    with pytest.raises(FileNotFoundError):
        engine.build_site(partial_target="does_not_exist.adoc")


def test_cli_partial_cascades_to_reverse_deps(project_setup):
    runner = CliRunner()
    # Create parent page that includes a child fragment
    (Path("content") / "child_fragment.adoc").write_text(
        "== Fragment Section\n\nInitial fragment content.\n",
        encoding="utf-8",
    )
    (Path("content") / "parent_page.adoc").write_text(
        "= Parent Page\nTest Author\n\ninclude::child_fragment.adoc[]\n",
        encoding="utf-8",
    )

    # 1. Full build to establish dependencies in cache
    res_full = runner.invoke(main, ["build"])
    assert res_full.exit_code == 0
    assert "Initial fragment content." in Path("dist/parent_page.html").read_text(encoding="utf-8")

    mtime_index_before = Path("dist/index.html").stat().st_mtime_ns
    mtime_parent_before = Path("dist/parent_page.html").stat().st_mtime_ns

    time.sleep(0.05)

    # 2. Modify child fragment
    (Path("content") / "child_fragment.adoc").write_text(
        "== Fragment Section\n\nUpdated fragment content.\n",
        encoding="utf-8",
    )

    # 3. Partial build targeting only child_fragment.adoc
    res_partial = runner.invoke(main, ["build", "--partial", "content/child_fragment.adoc"])
    assert res_partial.exit_code == 0

    mtime_index_after = Path("dist/index.html").stat().st_mtime_ns
    mtime_parent_after = Path("dist/parent_page.html").stat().st_mtime_ns

    # Parent page must have been recompiled
    assert mtime_parent_after > mtime_parent_before
    assert "Updated fragment content." in Path("dist/parent_page.html").read_text(encoding="utf-8")

    # Unrelated index page must remain untouched
    assert mtime_index_after == mtime_index_before
