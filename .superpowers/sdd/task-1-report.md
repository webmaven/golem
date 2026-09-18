# Task 1 Report: Bundled Plugin Entry Points & Packaging Registration (`pyproject.toml`)

## Summary
Successfully registered all 6 bundled Golem plugins under `[project.entry-points."golem.plugins"]` in `pyproject.toml`, refreshed package metadata in editable mode, and updated CLI plugin discovery in `src/golem/cli.py` to dynamically inspect entry points rather than relying on a hardcoded list.

## Changes Made
1. **`pyproject.toml`**:
   - Added `[project.entry-points."golem.plugins"]` section registering:
     - `doctest = "golem.plugins.doctest"`
     - `apidoc = "golem.plugins.apidoc"`
     - `source_links = "golem.plugins.source_links:SourceLinksPlugin"`
     - `nav_helpers = "golem.plugins.nav_helpers:NavigationHelpersPlugin"`
     - `index = "golem.plugins.index_glossary:IndexPlugin"`
     - `glossary = "golem.plugins.index_glossary:GlossaryPlugin"`

2. **Packaging Metadata Refresh**:
   - Executed `.venv/bin/pip install -e . --no-deps` to register the new entry points in the current Python virtual environment.
   - Verified that `importlib.metadata.entry_points(group="golem.plugins")` returns all 6 entry points.

3. **`src/golem/cli.py`**:
   - Updated `BUILTIN_PLUGINS` to reference the entry point names (`doctest`, `apidoc`, `source_links`, `nav_helpers`, `index`, `glossary`).
   - Added `BUILTIN_PLUGIN_TARGETS` mapping for target modules/classes.
   - Updated `plugins` command to:
     - Query `importlib.metadata.entry_points(group="golem.plugins")`.
     - Dynamically inspect entry points for built-in plugins, falling back to standard discovery if entry points are missing or mocked.
     - Check enablement against configured plugins by short name, full target value, or module name.
     - List remaining entry points (such as third-party packages) with appropriate distribution metadata.

4. **Tests**:
   - Added `test_cli_plugins_bundled_entry_points_discovery` in `tests/test_cli.py`.
   - Updated `tests/test_cli_inspection.py` (`test_cli_plugins_default`, `test_cli_plugins_json_default`, `test_cli_plugins_custom_config`) to assert the standardized entry-point plugin names.
   - Updated `tests/test_plugin_source_links.py` (`test_source_links_cli_inspection`) to support `source_links` plugin name.

## Test Verification
- Executed `pytest tests/test_cli.py tests/test_cli_inspection.py tests/test_cli_functional.py tests/test_plugin_*.py`:
  - **158 passed** in 43.44s.
- `ruff check` and `ruff format --check` passed cleanly with zero issues.
