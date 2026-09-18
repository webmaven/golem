# Task 1 Report: Bundled Plugin Entry Points & Packaging Registration (`pyproject.toml`)

## Summary
Successfully registered all 6 bundled Golem plugins under `[project.entry-points."golem.plugins"]` in `pyproject.toml`, refreshed package metadata in editable mode, and updated CLI plugin discovery in `src/golem/cli.py` to dynamically inspect entry points rather than relying on any hardcoded lists or separate built-in loops.

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
   - Removed `BUILTIN_PLUGINS` and `BUILTIN_PLUGIN_TARGETS` constants completely.
   - Collapsed entry-point discovery into a single uniform loop over `importlib.metadata.entry_points(group="golem.plugins")`.
   - Identified built-in plugins dynamically by checking `dist_name in ("golem", "golem-docs")`, labeling them with `source = "built-in"`.
   - Labeled third-party plugins with `source = "entry_point"`.
   - Unified enablement resolution checking `ep_name`, `ep_value`, and `ep_module` in `config.plugins`.

4. **Tests**:
   - Added `test_cli_plugins_bundled_entry_points_discovery` in `tests/test_cli.py`.
   - Updated `tests/test_cli_inspection.py` (`test_cli_plugins_default`, `test_cli_plugins_json_default`, `test_cli_plugins_custom_config`) to assert the standardized entry-point plugin names.
   - Updated `tests/test_plugin_source_links.py` (`test_source_links_cli_inspection`) to support `source_links` plugin name.

## Review Follow-up: Removal of Hardcoded Lists & Loop Unification
- **Feedback**: Delete `BUILTIN_PLUGINS` and `BUILTIN_PLUGIN_TARGETS` from `src/golem/cli.py` and collapse discovery into a single uniform loop over entry points without privileged hardcoded branches.
- **Action Taken**: Removed `BUILTIN_PLUGINS` and `BUILTIN_PLUGIN_TARGETS`. Replaced the two-stage loop in `plugins` command with a single uniform iteration over `golem.plugins` entry points.
- **Verification Commands & Results**:
  - `.venv/bin/pytest -q tests/test_cli.py tests/test_cli_inspection.py tests/test_cli_functional.py tests/test_plugin_source_links.py`:
    - Output: `63 passed in 3.04s`
  - `.venv/bin/pytest -q -k "not test_dev_server"`:
    - Output: `443 passed in 50.30s`
  - `ruff check src/golem/cli.py` and `ruff format --check src/golem/cli.py`:
    - Clean pass, zero issues.
