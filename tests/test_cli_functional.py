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


def test_cli_init_with_existing_pyproject_toml(tmp_path):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        # 1. Create a mock pre-existing pyproject.toml
        pyproject = Path("pyproject.toml")
        pyproject.write_text("""[tool.poetry]
name = "my_library"
version = "0.1.0"
""", encoding="utf-8")

        # 2. Run golem init
        result = runner.invoke(main, ["init"])
        assert result.exit_code == 0
        assert "Found pyproject.toml!" in result.output

        # 3. Assert [tool.golem] configuration is appended
        content = pyproject.read_text(encoding="utf-8")
        assert "[tool.golem.site]" in content
        assert "[tool.golem.build]" in content
        assert "content_dir = \"docs\"" in content

        # 4. Assert library docs/ folder is scaffolded instead of content/
        assert not Path("content").exists()
        assert Path("docs/index.adoc").exists()
        assert "Welcome to Golem" in Path("docs/index.adoc").read_text(encoding="utf-8")


def test_cli_init_idempotency(tmp_path):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        # --- Standard Mode Idempotency ---
        # 1st execution
        res_std1 = runner.invoke(main, ["init"])
        assert res_std1.exit_code == 0
        golem_toml_content_1 = Path("golem.toml").read_text(encoding="utf-8")
        index_content_1 = Path("content/index.adoc").read_text(encoding="utf-8")

        # 2nd execution
        res_std2 = runner.invoke(main, ["init"])
        assert res_std2.exit_code == 0
        golem_toml_content_2 = Path("golem.toml").read_text(encoding="utf-8")
        index_content_2 = Path("content/index.adoc").read_text(encoding="utf-8")

        # Verify nothing changed/duplicated
        assert golem_toml_content_1 == golem_toml_content_2
        assert index_content_1 == index_content_2

    with runner.isolated_filesystem(temp_dir=tmp_path):
        # --- Pyproject Mode Idempotency ---
        pyproject = Path("pyproject.toml")
        pyproject.write_text("""[tool.poetry]
name = "library"
""", encoding="utf-8")

        # 1st execution
        res_py1 = runner.invoke(main, ["init"])
        assert res_py1.exit_code == 0
        pyproject_content_1 = pyproject.read_text(encoding="utf-8")

        # 2nd execution
        res_py2 = runner.invoke(main, ["init"])
        assert res_py2.exit_code == 0
        pyproject_content_2 = pyproject.read_text(encoding="utf-8")

        # Verify nothing was appended again
        assert pyproject_content_1 == pyproject_content_2
        assert pyproject_content_1.count("[tool.golem.site]") == 1
        assert pyproject_content_1.count("[tool.golem.build]") == 1


def test_cli_init_non_empty_docs_decline(tmp_path):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        # 1. Pre-create a non-empty docs directory
        docs_dir = Path("docs")
        docs_dir.mkdir(exist_ok=True)
        other_file = docs_dir / "custom.adoc"
        other_file.write_text("Hello", encoding="utf-8")

        # Create pyproject.toml to trigger docs/ folder targeting
        pyproject = Path("pyproject.toml")
        pyproject.write_text("[tool.poetry]\nname='lib'", encoding="utf-8")

        # 2. Run golem init and decline the scaffolding prompt
        result = runner.invoke(main, ["init"], input="n\n")
        assert result.exit_code == 0
        
        # Verify the custom file exists, but standard index.adoc was NOT scaffolded
        assert other_file.exists()
        assert not Path("docs/index.adoc").exists()


def test_cli_init_non_empty_docs_accept_never_overwrite(tmp_path):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        # 1. Pre-create a non-empty content directory with a custom index.adoc
        content_dir = Path("content")
        content_dir.mkdir(exist_ok=True)
        custom_index = content_dir / "index.adoc"
        custom_index.write_text("My Sacred Content", encoding="utf-8")
        
        other_file = content_dir / "other.adoc"
        other_file.write_text("Other content", encoding="utf-8")

        # 2. Run golem init and accept the scaffolding prompt
        result = runner.invoke(main, ["init"], input="y\n")
        assert result.exit_code == 0
        
        # Verify custom files exist and the existing index.adoc was absolutely NOT overwritten!
        assert custom_index.read_text(encoding="utf-8") == "My Sacred Content"
        assert other_file.read_text(encoding="utf-8") == "Other content"


def test_cli_init_standalone_scaffolds_full_site(tmp_path):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(main, ["init"])
        assert result.exit_code == 0
        
        # Verify standalone configuration and content folder
        assert Path("golem.toml").exists()
        assert Path("content/index.adoc").exists()
        
        # Verify static and templates directories were scaffolded
        assert Path("static/css/custom.css").exists()
        assert Path("templates/page.pt").exists()
        
        # Verify golem.toml contains static_dir and templates_dir settings
        golem_toml_content = Path("golem.toml").read_text(encoding="utf-8")
        assert 'static_dir = "static"' in golem_toml_content
        assert 'templates_dir = "templates"' in golem_toml_content




