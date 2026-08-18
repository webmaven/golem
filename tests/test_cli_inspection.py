"""
= CLI Inspection Commands Tests for Golem

This module tests the introspection CLI commands `golem plugins` and `golem themes`.
"""

import json
from pathlib import Path
from click.testing import CliRunner
from golem.cli import main


class MockDist:
    def __init__(self, name: str, version: str):
        self.name = name
        self.version = version


class MockEntryPoint:
    def __init__(self, name: str, value: str, group: str, dist: MockDist | None = None):
        self.name = name
        self.value = value
        self.group = group
        self.dist = dist


def test_cli_plugins_help():
    runner = CliRunner()
    result = runner.invoke(main, ["plugins", "--help"])
    assert result.exit_code == 0
    assert "--json" in result.output
    assert "-C" in result.output or "--directory" in result.output


def test_cli_themes_help():
    runner = CliRunner()
    result = runner.invoke(main, ["themes", "--help"])
    assert result.exit_code == 0
    assert "--json" in result.output
    assert "-C" in result.output or "--directory" in result.output


def test_cli_plugins_default(tmp_path):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(main, ["plugins"])
        assert result.exit_code == 0
        assert "[DISABLED]" in result.output
        assert "golem.plugins.doctest" in result.output
        assert "golem.plugins.apidoc" in result.output
        assert "(built-in)" in result.output


def test_cli_plugins_json_default(tmp_path):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(main, ["plugins", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        names = [p["name"] for p in data]
        assert "golem.plugins.doctest" in names
        assert "golem.plugins.apidoc" in names
        for p in data:
            if p["name"] in ("golem.plugins.doctest", "golem.plugins.apidoc"):
                assert p["enabled"] is False
                assert p["source"] == "built-in"


def test_cli_plugins_custom_config(tmp_path):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        Path("golem.toml").write_text(
            """
[plugins]
plugins = ["golem.plugins.doctest", "custom_pkg.plugin"]
""",
            encoding="utf-8",
        )
        result = runner.invoke(main, ["plugins"])
        assert result.exit_code == 0
        # doctest is enabled
        assert "[ENABLED]" in result.output
        assert "golem.plugins.doctest" in result.output
        # apidoc is disabled since it was omitted from config.plugins
        assert "[DISABLED]" in result.output
        assert "golem.plugins.apidoc" in result.output
        # custom_pkg.plugin is enabled
        assert "custom_pkg.plugin" in result.output


def test_cli_plugins_local_plugins(tmp_path):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        plugins_dir = Path("plugins")
        plugins_dir.mkdir()
        (plugins_dir / "my_custom_macro.py").write_text("# plugin", encoding="utf-8")
        (plugins_dir / "disabled_macro.py").write_text("# disabled", encoding="utf-8")

        Path("golem.toml").write_text(
            """
[plugins]
plugins = ["golem.plugins.doctest", "golem.plugins.apidoc", "my_custom_macro"]
""",
            encoding="utf-8",
        )

        result = runner.invoke(main, ["plugins"])
        assert result.exit_code == 0
        assert "my_custom_macro" in result.output
        assert "(local: plugins/my_custom_macro.py)" in result.output
        assert "disabled_macro" in result.output
        assert "(local: plugins/disabled_macro.py)" in result.output

        # Check JSON output
        json_result = runner.invoke(main, ["plugins", "--json"])
        assert json_result.exit_code == 0
        json_data = json.loads(json_result.output)
        macro_entry = next(
            (p for p in json_data if p["name"] == "my_custom_macro"), None
        )
        assert macro_entry is not None
        assert macro_entry["enabled"] is True
        assert macro_entry["source"] == "local"

        disabled_entry = next(
            (p for p in json_data if p["name"] == "disabled_macro"), None
        )
        assert disabled_entry is not None
        assert disabled_entry["enabled"] is False
        assert disabled_entry["source"] == "local"


def test_cli_plugins_with_entry_points(tmp_path, monkeypatch):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        mock_eps = [
            MockEntryPoint(
                name="golem-analytics",
                value="golem_analytics:plugin",
                group="golem.plugins",
                dist=MockDist("golem-analytics-pkg", "1.4.2"),
            )
        ]

        def mock_entry_points(group=None):
            if group == "golem.plugins":
                return mock_eps
            return []

        import importlib.metadata

        monkeypatch.setattr(importlib.metadata, "entry_points", mock_entry_points)

        result = runner.invoke(main, ["plugins"])
        assert result.exit_code == 0
        assert "golem-analytics" in result.output
        assert "(entry_point: golem-analytics-pkg 1.4.2)" in result.output
        assert "[DISABLED]" in result.output

        # Enable it in golem.toml
        Path("golem.toml").write_text(
            """
[plugins]
plugins = ["golem.plugins.doctest", "golem-analytics"]
""",
            encoding="utf-8",
        )
        res_enabled = runner.invoke(main, ["plugins"])
        assert res_enabled.exit_code == 0
        for line in res_enabled.output.splitlines():
            if "golem-analytics" in line:
                assert "[ENABLED]" in line


def test_cli_plugins_directory_flag(tmp_path):
    runner = CliRunner()
    project_dir = tmp_path / "other_project"
    project_dir.mkdir()
    plugins_dir = project_dir / "plugins"
    plugins_dir.mkdir()
    (plugins_dir / "extra_helper.py").write_text("# helper", encoding="utf-8")

    (project_dir / "golem.toml").write_text(
        """
[plugins]
plugins = ["golem.plugins.doctest", "extra_helper"]
""",
        encoding="utf-8",
    )

    result = runner.invoke(main, ["plugins", "-C", str(project_dir)])
    assert result.exit_code == 0
    assert "extra_helper" in result.output
    assert "(local: plugins/extra_helper.py)" in result.output

    # Using --directory
    result2 = runner.invoke(
        main, ["plugins", "--directory", str(project_dir), "--json"]
    )
    assert result2.exit_code == 0
    data = json.loads(result2.output)
    entry = next((p for p in data if p["name"] == "extra_helper"), None)
    assert entry is not None
    assert entry["enabled"] is True


def test_cli_themes_default(tmp_path):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(main, ["themes"])
        assert result.exit_code == 0
        assert "Active Theme: 'default' (built-in)" in result.output
        assert "Available Themes:" in result.output
        assert "default (built-in)" in result.output


def test_cli_themes_json_default(tmp_path):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(main, ["themes", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["active"] == "default"
        assert data["active_source"] == "(built-in)"
        assert isinstance(data["themes"], list)
        default_theme = next(
            (t for t in data["themes"] if t["name"] == "default"), None
        )
        assert default_theme is not None
        assert default_theme["source"] == "built-in"
        assert default_theme["active"] is True


def test_cli_themes_local_and_custom_active(tmp_path):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        themes_dir = Path("themes")
        themes_dir.mkdir()
        (themes_dir / "nord").mkdir()
        (themes_dir / "dracula").mkdir()

        Path("golem.toml").write_text(
            """
[build]
theme = "nord"
""",
            encoding="utf-8",
        )

        result = runner.invoke(main, ["themes"])
        assert result.exit_code == 0
        assert "Active Theme: 'nord' (local: themes/nord)" in result.output
        assert "Available Themes:" in result.output
        assert "default (built-in)" in result.output
        assert "nord (local: themes/nord)" in result.output
        assert "dracula (local: themes/dracula)" in result.output

        json_result = runner.invoke(main, ["themes", "--json"])
        assert json_result.exit_code == 0
        data = json.loads(json_result.output)
        assert data["active"] == "nord"
        assert data["active_source"] == "(local: themes/nord)"

        nord_theme = next((t for t in data["themes"] if t["name"] == "nord"), None)
        assert nord_theme is not None
        assert nord_theme["active"] is True
        assert nord_theme["source"] == "local"

        dracula_theme = next(
            (t for t in data["themes"] if t["name"] == "dracula"), None
        )
        assert dracula_theme is not None
        assert dracula_theme["active"] is False
        assert dracula_theme["source"] == "local"


def test_cli_themes_with_entry_points(tmp_path, monkeypatch):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        mock_eps = [
            MockEntryPoint(
                name="ocean",
                value="golem_ocean_theme:Theme",
                group="golem.themes",
                dist=MockDist("golem-theme-ocean", "0.3.0"),
            )
        ]

        def mock_entry_points(group=None):
            if group == "golem.themes":
                return mock_eps
            return []

        import importlib.metadata

        monkeypatch.setattr(importlib.metadata, "entry_points", mock_entry_points)

        # 1. Default active theme with entry point theme available
        result = runner.invoke(main, ["themes"])
        assert result.exit_code == 0
        assert "Active Theme: 'default' (built-in)" in result.output
        assert "ocean (entry_point: golem-theme-ocean 0.3.0)" in result.output

        # 2. Config active theme set to entry point theme
        Path("golem.toml").write_text(
            """
[build]
theme = "ocean"
""",
            encoding="utf-8",
        )
        result2 = runner.invoke(main, ["themes"])
        assert result2.exit_code == 0
        assert (
            "Active Theme: 'ocean' (entry_point: golem-theme-ocean 0.3.0)"
            in result2.output
        )

        json_result = runner.invoke(main, ["themes", "--json"])
        assert json_result.exit_code == 0
        data = json.loads(json_result.output)
        assert data["active"] == "ocean"
        ocean_theme = next((t for t in data["themes"] if t["name"] == "ocean"), None)
        assert ocean_theme is not None
        assert ocean_theme["active"] is True
        assert ocean_theme["source"] == "entry_point"


def test_cli_themes_directory_flag(tmp_path):
    runner = CliRunner()
    project_dir = tmp_path / "custom_theme_project"
    project_dir.mkdir()
    themes_dir = project_dir / "themes"
    themes_dir.mkdir()
    (themes_dir / "solarized").mkdir()

    (project_dir / "golem.toml").write_text(
        """
[build]
theme = "solarized"
""",
        encoding="utf-8",
    )

    result = runner.invoke(main, ["themes", "-C", str(project_dir)])
    assert result.exit_code == 0
    assert "Active Theme: 'solarized' (local: themes/solarized)" in result.output
    assert "solarized (local: themes/solarized)" in result.output

    result2 = runner.invoke(main, ["themes", "--directory", str(project_dir), "--json"])
    assert result2.exit_code == 0
    data = json.loads(result2.output)
    assert data["active"] == "solarized"
    theme_entry = next((t for t in data["themes"] if t["name"] == "solarized"), None)
    assert theme_entry is not None
    assert theme_entry["active"] is True
