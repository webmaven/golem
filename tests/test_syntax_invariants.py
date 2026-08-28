"""Canary tests for Python 3 syntax invariants that static linters miss."""
import ast
from pathlib import Path

SRC_ROOT = Path(__file__).parent.parent / "src" / "golem"


def _all_source_files() -> list[Path]:
    return list(SRC_ROOT.rglob("*.py"))


def test_no_python2_except_comma_syntax():
    """
    Ensure no source file uses the Python 2 `except A, B:` form.
    """
    violations: list[str] = []
    for src_file in _all_source_files():
        tree = ast.parse(src_file.read_text(encoding="utf-8"), filename=str(src_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                # We specifically want to catch the `except A, B:` pattern.
                # In Python 3, `except (A, B):` results in `type` as `Tuple`.
                # The Python 2 syntax `except A, B:` is invalid in Python 3, 
                # but valid in Python 2. 
                # We should look for the AST representation that IS NOT `except (A, B):`.
                pass

    assert not violations, (
        "Python 2-style `except A, B:` forms detected:\n" + "\n".join(violations)
    )
