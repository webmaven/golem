from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path


def test_zero_golem_dependencies_in_core_static():
    """Verify statically via AST that src/golem/plugins/apidoc/core/ has NO imports

    from golem.config, golem.engine, golem.cli, golem.renderer, or pluggy.
    """
    core_dir = Path(__file__).parent.parent / "src" / "golem" / "plugins" / "apidoc" / "core"
    assert core_dir.exists(), f"Core directory {core_dir} must exist"

    forbidden_prefixes = (
        "golem.config",
        "golem.engine",
        "golem.cli",
        "golem.renderer",
        "pluggy",
    )

    violations = []

    for py_file in core_dir.rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if any(alias.name == f or alias.name.startswith(f + ".") for f in forbidden_prefixes):
                        violations.append(f"{py_file.name}:{node.lineno} imports '{alias.name}'")
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    if any(node.module == f or node.module.startswith(f + ".") for f in forbidden_prefixes):
                        violations.append(f"{py_file.name}:{node.lineno} imports from '{node.module}'")

    assert not violations, f"Architectural boundary violated in core: {violations}"


def test_zero_golem_dependencies_in_core_dynamic():
    """Verify dynamically in a fresh Python process that importing core as a standalone engine

    does NOT load golem, golem.config, golem.engine, golem.cli, golem.renderer, or pluggy into sys.modules.
    """
    check_code = """
import sys
from pathlib import Path

# Standalone import test: simulate standalone packaging
sys.path.insert(0, str(Path("src/golem/plugins/apidoc").resolve()))
import core
from core import AsciiDocApi, ApiGenOptions

forbidden = ["golem.config", "golem.engine", "golem.cli", "golem.renderer", "pluggy", "golem"]
violations = [m for m in forbidden if m in sys.modules]
if violations:
    print(f"VIOLATIONS:{','.join(violations)}")
    sys.exit(1)
print("OK")
"""
    res = subprocess.run(
        [sys.executable, "-c", check_code],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent.parent),
    )
    assert res.returncode == 0, f"Dynamic import check failed: {res.stdout}\n{res.stderr}"
    assert "OK" in res.stdout


def test_asciidocapi_initialization():
    from golem.plugins.apidoc.core import ApiGenOptions, AsciiDocApi

    options = ApiGenOptions(docstring_style="google", depth="methods")
    api = AsciiDocApi(search_paths=["src"], options=options)
    assert api.options.docstring_style == "google"
    assert api.options.depth == "methods"
    assert "src" in [str(p) for p in api.search_paths]


def test_load_package_and_render_module(tmp_path):
    from golem.plugins.apidoc.core import AsciiDocApi

    # Create dummy package
    pkg_dir = tmp_path / "sample_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""Sample package root docstring.

This package provides demo utilities.
"""

__version__ = "1.0.0"

def root_func(val: int) -> str:
    """Transform integer value to string.

    Args:
        val: Input number.

    Returns:
        String representation.
    """
    return str(val)
''',
        encoding="utf-8",
    )

    api = AsciiDocApi(search_paths=[str(tmp_path)])
    mod = api.load_package("sample_pkg")
    assert mod.name == "sample_pkg"

    doc = api.render_module(mod)
    assert "= sample_pkg" in doc
    assert "Sample package root docstring." in doc
    assert "== root_func" in doc or "=== root_func" in doc
    assert "def root_func(val: int) -> str:" in doc


def test_render_class_with_methods_and_docstrings(tmp_path):
    from golem.plugins.apidoc.core import AsciiDocApi

    pkg_dir = tmp_path / "class_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""Class package."""

class Calculator:
    """A simple arithmetic calculator.

    Attributes:
        precision: Decimal precision places.
    """

    precision: int = 2

    def __init__(self, precision: int = 2) -> None:
        """Initialize calculator."""
        self.precision = precision

    def add(self, a: float, b: float) -> float:
        """Add two numbers.

        Args:
            a: First operand.
            b: Second operand.

        Returns:
            The sum of a and b.
        """
        return a + b

    @classmethod
    def standard(cls) -> "Calculator":
        """Create standard instance."""
        return cls(2)
''',
        encoding="utf-8",
    )

    api = AsciiDocApi(search_paths=[str(tmp_path)])
    cls_obj = api.resolve_symbol("class_pkg.Calculator")
    assert cls_obj is not None

    rendered = api.render_class(cls_obj)
    assert "class Calculator" in rendered
    assert "A simple arithmetic calculator." in rendered
    assert "def add(self, a: float, b: float) -> float:" in rendered
    assert "Add two numbers." in rendered
    assert "standard" in rendered


def test_render_symbol_depth(tmp_path):
    from golem.plugins.apidoc.core import AsciiDocApi

    pkg_dir = tmp_path / "depth_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''
class Greeter:
    """Greeting class."""
    def say_hello(self, name: str) -> str:
        """Greet someone."""
        return f"Hello, {name}!"
''',
        encoding="utf-8",
    )

    api = AsciiDocApi(search_paths=[str(tmp_path)])
    # Render with summary depth
    summary_doc = api.render_symbol("depth_pkg.Greeter", depth="summary")
    assert "class Greeter" in summary_doc
    assert "Greeting class." in summary_doc


def test_generate_package_docs(tmp_path):
    from golem.plugins.apidoc.core import AsciiDocApi

    pkg_dir = tmp_path / "multi_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""Multi package root."""
def main_entry() -> None:
    pass
''',
        encoding="utf-8",
    )

    sub_dir = pkg_dir / "utils"
    sub_dir.mkdir()
    (sub_dir / "__init__.py").write_text(
        '''"""Utils submodule."""
def helper() -> bool:
    return True
''',
        encoding="utf-8",
    )

    api = AsciiDocApi(search_paths=[str(tmp_path)])
    docs = api.generate_package_docs("multi_pkg")
    assert isinstance(docs, dict)
    assert len(docs) >= 1
    # Check that keys are relative paths to adoc files
    assert any("multi_pkg" in k for k in docs.keys())
    for adoc_path, content in docs.items():
        assert adoc_path.endswith(".adoc")
        assert content.strip().startswith("=")


def test_parameter_signature_variations(tmp_path):
    from golem.plugins.apidoc.core import AsciiDocApi

    pkg_dir = tmp_path / "sig_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''
def complex_fn(pos1: int, /, normal: str, default_val: float = 3.14, *args: int, kw_only: bool = True, **kwargs: str) -> bool:
    """Function with comprehensive parameter kinds."""
    return True
''',
        encoding="utf-8",
    )

    api = AsciiDocApi(search_paths=[str(tmp_path)])
    func_obj = api.resolve_symbol("sig_pkg.complex_fn")
    rendered = api.render_function(func_obj)
    assert "pos1: int, /, normal: str" in rendered
    assert "*args: int" in rendered
    assert "kw_only: bool = True" in rendered
    assert "**kwargs: str" in rendered
    assert "-> bool:" in rendered


def test_async_and_decorators(tmp_path):
    from golem.plugins.apidoc.core import AsciiDocApi

    pkg_dir = tmp_path / "async_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''
class AsyncWorker:
    @property
    def is_running(self) -> bool:
        """Check if worker is running."""
        return True

    @staticmethod
    async def fetch_data(url: str) -> str:
        """Fetch remote data asynchronously."""
        return "data"
''',
        encoding="utf-8",
    )

    api = AsciiDocApi(search_paths=[str(tmp_path)])
    cls_obj = api.resolve_symbol("async_pkg.AsyncWorker")
    rendered = api.render_class(cls_obj)
    assert "is_running" in rendered
    assert "@staticmethod" in rendered
    assert "async def fetch_data" in rendered


def test_docstring_styles(tmp_path):
    from golem.plugins.apidoc.core import ApiGenOptions, AsciiDocApi

    pkg_dir = tmp_path / "doc_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''
def google_style(x: int) -> int:
    """Google style function.

    Args:
        x: An integer input.

    Returns:
        The incremented value.

    Raises:
        ValueError: If x is negative.
    """
    if x < 0:
        raise ValueError("negative")
    return x + 1

def numpy_style(y: float) -> float:
    """NumPy style function.

    Parameters
    ----------
    y : float
        Float input value.

    Returns
    -------
    float
        Doubled value.
    """
    return y * 2.0
''',
        encoding="utf-8",
    )

    api = AsciiDocApi(search_paths=[str(tmp_path)], options=ApiGenOptions(docstring_style="auto"))
    g_rendered = api.render_symbol("doc_pkg.google_style")
    assert "Google style function." in g_rendered
    assert "[parameters]" in g_rendered or "`x`::" in g_rendered
    assert "[returns]" in g_rendered or "`int`::" in g_rendered or "incremented value" in g_rendered

    n_rendered = api.render_symbol("doc_pkg.numpy_style")
    assert "NumPy style function." in n_rendered


def test_get_asg_nodes_returns_list(tmp_path):
    from golem.plugins.apidoc.core import AsciiDocApi

    pkg_dir = tmp_path / "asg_func_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""Math utilities."""
def add(a: int, b: int) -> int:
    """Add two integers.

    Args:
        a: First operand.
        b: Second operand.

    Returns:
        Sum of a and b.
    """
    return a + b
''',
        encoding="utf-8",
    )

    api = AsciiDocApi(search_paths=[str(tmp_path)])
    nodes = api.get_asg_nodes("asg_func_pkg.add")

    assert isinstance(nodes, list)
    assert len(nodes) >= 1
    assert any(isinstance(n, dict) and n.get("name") in ("section", "paragraph", "listing") for n in nodes)


def test_get_asg_nodes_structure(tmp_path):
    from golem.plugins.apidoc.core import AsciiDocApi

    pkg_dir = tmp_path / "asg_cls_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""Class package."""
class Service:
    """A background worker service."""
    port: int = 8080
    """Port number."""

    def start(self) -> bool:
        """Start the worker."""
        return True
''',
        encoding="utf-8",
    )

    api = AsciiDocApi(search_paths=[str(tmp_path)])
    all_nodes = api.get_asg_nodes("asg_cls_pkg.Service", depth="all")
    assert isinstance(all_nodes, list)
    assert len(all_nodes) >= 1
    for node in all_nodes:
        assert isinstance(node, dict)
        assert "name" in node
        assert "type" in node


def test_get_asg_nodes_missing_symbol_raises(tmp_path):
    import pytest
    from golem.plugins.apidoc.core import AsciiDocApi

    api = AsciiDocApi(search_paths=[str(tmp_path)])
    with pytest.raises(Exception):
        api.get_asg_nodes("nonexistent_pkg_xyz.missing_symbol")


def test_get_asg_nodes_heading_level_offset(tmp_path):
    from golem.plugins.apidoc.core import AsciiDocApi

    pkg_dir = tmp_path / "asg_offset_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""Offset test package."""
def compute() -> None:
    """Compute something."""
    pass
''',
        encoding="utf-8",
    )

    api = AsciiDocApi(search_paths=[str(tmp_path)])
    base_nodes = api.get_asg_nodes("asg_offset_pkg.compute", heading_level_offset=0)
    offset_nodes = api.get_asg_nodes("asg_offset_pkg.compute", heading_level_offset=1)

    assert isinstance(base_nodes, list)
    assert isinstance(offset_nodes, list)
    base_section = next((n for n in base_nodes if n.get("name") == "section"), None)
    offset_section = next((n for n in offset_nodes if n.get("name") == "section"), None)
    if base_section and offset_section:
        assert offset_section.get("level", 0) == base_section.get("level", 0) + 1
