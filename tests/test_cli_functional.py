"""
= CLI Functional Tests for Golem

This module contains functional tests verifying Golem's Click command-line interface,
including template scaffolding initialization and clean build options.
"""

from pathlib import Path
from click.testing import CliRunner
from golem.cli import main


def test_cli_init_command_creates_scaffold(tmp_path):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(main, ["init"])
        assert result.exit_code == 0
        assert "Initializing" in result.output
        assert "golem.toml" in [f.name for f in Path(".").iterdir()]
        assert Path("content/index.adoc").exists()


def test_cli_build_respects_clean_flag(tmp_path):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        runner.invoke(main, ["init"])

        # Manually write an old artifact inside the output dist folder
        dist_dir = Path("dist")
        dist_dir.mkdir(exist_ok=True)
        old_file = dist_dir / "old_stale.html"
        old_file.write_text("stale", encoding="utf-8")

        # Build with --clean flag
        build_result = runner.invoke(main, ["build", "--clean"])
        assert build_result.exit_code == 0

        # Stale file must be cleaned, but active index compiled
        assert not old_file.exists()
        assert Path("dist/index.html").exists()


def test_cli_build_clean_rebuilds_all(tmp_path):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        runner.invoke(main, ["init"])

        # 1. First build (creates cache.json and dist/index.html)
        res_1 = runner.invoke(main, ["build"])
        assert res_1.exit_code == 0
        assert Path("dist/index.html").exists()

        # 2. Second build with --clean (empties output folder, MUST rebuild index.html)
        res_2 = runner.invoke(main, ["build", "--clean"])
        assert res_2.exit_code == 0
        assert Path("dist/index.html").exists()
