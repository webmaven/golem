"""
= CLI New Subcommands Tests for Golem

This module contains unit and functional tests for the `golem new` command group,
including backward-compatible document scaffolding, `golem new theme`, and `golem new plugin`.
"""

from pathlib import Path
import chameleon
from click.testing import CliRunner

from golem.cli import main
from golem.config import GolemConfig
from golem.plugins import get_plugin_manager


def test_cli_new_help():
    """Verify that golem new, golem new theme, and golem new plugin show help."""
    runner = CliRunner()
    res = runner.invoke(main, ["new", "--help"])
    assert res.exit_code == 0
    assert "theme" in res.output
    assert "plugin" in res.output

    res_theme = runner.invoke(main, ["new", "theme", "--help"])
    assert res_theme.exit_code == 0
    assert "theme" in res_theme.output.lower()

    res_plugin = runner.invoke(main, ["new", "plugin", "--help"])
    assert res_plugin.exit_code == 0
    assert "plugin" in res_plugin.output.lower()


def test_cli_new_doc_backward_compatibility(tmp_path):
    """Verify that golem new <doc_type> <name> continues to scaffold .adoc files."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        runner.invoke(main, ["init"])

        res = runner.invoke(main, ["new", "post", "hello-world"])
        assert res.exit_code == 0
        assert "Created new post" in res.output

        target_file = Path("content/hello-world.adoc")
        assert target_file.exists()
        content = target_file.read_text(encoding="utf-8")
        assert "= hello-world" in content
        assert ":golem-type: post" in content
        assert "Welcome to your newly scaffolded post" in content

        # Overwrite prevention
        res_fail = runner.invoke(main, ["new", "post", "hello-world"])
        assert res_fail.exit_code != 0
        assert "File already exists" in res_fail.output


def test_cli_new_doc_invalid_name(tmp_path):
    """Verify that golem new with invalid document name fails."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        runner.invoke(main, ["init"])
        res = runner.invoke(main, ["new", "post", "!@#$%"])
        assert res.exit_code != 0
        assert "Invalid document name" in res.output


def test_cli_new_theme_scaffolding(tmp_path):
    """Verify that golem new theme <name> scaffolds a complete, functional theme."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        runner.invoke(main, ["init"])

        res = runner.invoke(main, ["new", "theme", "solar-flare"])
        assert res.exit_code == 0
        assert "solar-flare" in res.output
        assert 'theme = "solar-flare"' in res.output

        theme_dir = Path("themes/solar-flare")
        assert theme_dir.is_dir()

        # Core templates
        assert (theme_dir / "skeleton.pt").exists()
        assert (theme_dir / "page.pt").exists()
        assert (theme_dir / "layout.pt").exists()

        # templates/ subdirectory support
        assert (theme_dir / "templates" / "skeleton.pt").exists()
        assert (theme_dir / "templates" / "page.pt").exists()
        assert (theme_dir / "templates" / "layout.pt").exists()

        # Static assets
        assert (theme_dir / "static/css/solar-flare.css").exists()
        assert (theme_dir / "static/css/theme.css").exists()

        # Metadata
        assert (theme_dir / "theme.toml").exists()
        assert (theme_dir / "README.md").exists()

        # Verify skeleton.pt is valid Chameleon template
        skeleton_content = (theme_dir / "skeleton.pt").read_text(encoding="utf-8")
        tpl = chameleon.PageTemplate(skeleton_content)
        rendered = tpl(
            title="My Page",
            site_title="My Site",
            root_path="./",
            custom_css=[],
            body_class=None,
            site_url=None,
            site_author="Test Author",
            nav_html=None,
            body_html="<p>Test Body</p>",
            toc_html=None,
            generator_version="0.1.0",
        )
        assert "<p>Test Body</p>" in rendered
        assert "My Page" in rendered

        # Verify golem themes lists the new theme
        res_themes = runner.invoke(main, ["themes"])
        assert res_themes.exit_code == 0
        assert "solar-flare" in res_themes.output

        # Verify building a site with this theme works
        golem_toml = Path("golem.toml")
        golem_toml.write_text(
            golem_toml.read_text(encoding="utf-8").replace('theme = "default"', 'theme = "solar-flare"'),
            encoding="utf-8",
        )
        res_build = runner.invoke(main, ["build"])
        assert res_build.exit_code == 0
        assert Path("dist/index.html").exists()
        assert Path("dist/static/css/solar-flare.css").exists()


def test_cli_new_theme_already_exists(tmp_path):
    """Verify that golem new theme fails when the target directory already exists and is non-empty."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        runner.invoke(main, ["init"])

        res1 = runner.invoke(main, ["new", "theme", "nordic"])
        assert res1.exit_code == 0

        res2 = runner.invoke(main, ["new", "theme", "nordic"])
        assert res2.exit_code != 0
        assert "already exists" in res2.output


def test_cli_new_theme_invalid_name(tmp_path):
    """Verify that golem new theme fails with empty/invalid name."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        res = runner.invoke(main, ["new", "theme", "!@#$%"])
        assert res.exit_code != 0
        assert "Invalid theme name" in res.output


def test_cli_new_plugin_scaffolding(tmp_path):
    """Verify that golem new plugin <name> scaffolds a functional plugin."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        runner.invoke(main, ["init"])

        res = runner.invoke(main, ["new", "plugin", "seo-enhancer"])
        assert res.exit_code == 0
        assert "seo_enhancer" in res.output
        assert 'plugins = ["seo_enhancer"]' in res.output

        plugin_file = Path("plugins/seo_enhancer.py")
        assert plugin_file.exists()

        content = plugin_file.read_text(encoding="utf-8")
        assert "@hookimpl" in content
        assert "on_build_start" in content
        assert "on_template_context" in content

        # Verify plugin can be loaded by PluginManager
        cfg = GolemConfig(plugins=["seo_enhancer"])
        pm = get_plugin_manager(config=cfg, plugins_dir=Path("plugins"))
        assert "seo_enhancer" in [p.__name__ for p in pm.get_plugins() if hasattr(p, "__name__")]

        # Verify golem plugins CLI lists it
        res_plugins = runner.invoke(main, ["plugins"])
        assert res_plugins.exit_code == 0
        assert "seo_enhancer" in res_plugins.output

        # Verify building with the plugin enabled works
        golem_toml = Path("golem.toml")
        golem_toml_text = golem_toml.read_text(encoding="utf-8")
        if "[build]" in golem_toml_text:
            golem_toml_text = golem_toml_text.replace("[build]", '[build]\nplugins = ["seo_enhancer"]')
        else:
            golem_toml_text += '\n[build]\nplugins = ["seo_enhancer"]\n'
        golem_toml.write_text(golem_toml_text, encoding="utf-8")

        res_build = runner.invoke(main, ["build"])
        assert res_build.exit_code == 0
        assert Path("dist/index.html").exists()


def test_cli_new_plugin_already_exists(tmp_path):
    """Verify that golem new plugin fails when the target file already exists."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        runner.invoke(main, ["init"])

        res1 = runner.invoke(main, ["new", "plugin", "analytics"])
        assert res1.exit_code == 0

        res2 = runner.invoke(main, ["new", "plugin", "analytics"])
        assert res2.exit_code != 0
        assert "already exists" in res2.output


def test_cli_new_plugin_invalid_name(tmp_path):
    """Verify that golem new plugin fails with invalid identifier name."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        res = runner.invoke(main, ["new", "plugin", "!@#$%"])
        assert res.exit_code != 0
        assert "Invalid plugin name" in res.output


def test_cli_new_directory_flag(tmp_path):
    """Verify that -C / --directory works for both theme and plugin scaffolding."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        proj_dir = Path("my_project")
        proj_dir.mkdir()

        # Initialize in proj_dir
        res_init = runner.invoke(main, ["-C", str(proj_dir), "init"])
        assert res_init.exit_code == 0

        # New doc in proj_dir
        res_doc = runner.invoke(main, ["-C", str(proj_dir), "new", "page", "about"])
        assert res_doc.exit_code == 0
        assert (proj_dir / "content/about.adoc").exists()

        # New theme in proj_dir
        res_theme = runner.invoke(main, ["new", "theme", "test-theme", "-C", str(proj_dir)])
        assert res_theme.exit_code == 0
        assert (proj_dir / "themes/test-theme/skeleton.pt").exists()

        # New plugin in proj_dir
        res_plugin = runner.invoke(main, ["new", "-C", str(proj_dir), "plugin", "test-plugin"])
        assert res_plugin.exit_code == 0
        assert (proj_dir / "plugins/test_plugin.py").exists()
