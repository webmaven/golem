"""Canary tests for Python 3 syntax invariants that static linters miss."""

import ast
import io
import token
import tokenize
from pathlib import Path

SRC_ROOT = Path(__file__).parent.parent / "src" / "golem"


def _all_source_files() -> list[Path]:
    return list(SRC_ROOT.rglob("*.py"))


def find_except_comma_violations(source_code: str, filename: str = "<string>") -> list[str]:
    """
    Find occurrences of Python 2-style `except A, B:` or unparenthesized multiple exceptions.

    In Python 2, `except A, B:` bound exception A to name B (or was misused as multi-exception).
    In Python 3, multiple exceptions MUST be enclosed in a tuple: `except (A, B):`.
    Valid forms in Python 3:
      - `except Exception:`
      - `except Exception as e:`
      - `except (A, B):`
      - `except (A, B) as e:`
      - `except:`
    Invalid Python 2 forms:
      - `except A, B:`
      - `except A, B, C:`
      - `except A, B as e:`
    """
    violations: list[str] = []
    try:
        tokens = list(tokenize.tokenize(io.BytesIO(source_code.encode("utf-8")).readline))
    except tokenize.TokenError:
        return violations

    tok_list = [t for t in tokens if t.type not in (tokenize.COMMENT, tokenize.NL, tokenize.INDENT, tokenize.DEDENT)]

    i = 0
    while i < len(tok_list):
        t = tok_list[i]
        if t.type == token.NAME and t.string == "except":
            paren_depth = 0
            has_unparenthesized_comma = False
            j = i + 1
            while j < len(tok_list):
                curr = tok_list[j]
                if curr.string in ("(", "[", "{"):
                    paren_depth += 1
                elif curr.string in (")", "]", "}"):
                    paren_depth = max(0, paren_depth - 1)
                elif curr.string == "," and paren_depth == 0:
                    has_unparenthesized_comma = True
                elif curr.string == ":" and paren_depth == 0:
                    break
                j += 1
            if has_unparenthesized_comma:
                violations.append(f"{filename}:{t.start[0]}: {t.line.strip()}")
        i += 1

    return violations


def test_no_python2_except_comma_syntax():
    """
    Ensure no source file in src/golem uses the Python 2 `except A, B:` form.
    Also verifies all files parse cleanly with AST.
    """
    violations: list[str] = []
    for src_file in _all_source_files():
        source = src_file.read_text(encoding="utf-8")
        # Ensure AST parse passes
        ast.parse(source, filename=str(src_file))
        # Ensure no unparenthesized except comma syntax
        file_violations = find_except_comma_violations(source, filename=str(src_file))
        violations.extend(file_violations)

    assert not violations, "Python 2-style `except A, B:` forms detected:\n" + "\n".join(violations)


def test_except_comma_detector_valid_and_invalid_cases():
    """Unit tests for the detector to verify positive and negative cases."""
    invalid_cases = [
        "try:\n    pass\nexcept ImportError, OSError:\n    pass",
        "try:\n    pass\nexcept Exception, e:\n    pass",
        "try:\n    pass\nexcept A, B, C:\n    pass",
        "try:\n    pass\nexcept (A), B:\n    pass",
    ]
    for case in invalid_cases:
        assert len(find_except_comma_violations(case)) > 0, f"Expected violation for:\n{case}"

    valid_cases = [
        "try:\n    pass\nexcept (ImportError, OSError):\n    pass",
        "try:\n    pass\nexcept (ImportError, OSError) as e:\n    pass",
        "try:\n    pass\nexcept ImportError as e:\n    pass",
        "try:\n    pass\nexcept Exception:\n    pass",
        "try:\n    pass\nexcept:\n    pass",
        "# except ImportError, OSError:\ntry:\n    pass\nexcept Exception as e:\n    pass",
        's = """except ImportError, OSError:"""',
        "try:\n    pass\nexcept (\n    ImportError,\n    OSError,\n) as e:\n    pass",
    ]
    for case in valid_cases:
        assert len(find_except_comma_violations(case)) == 0, f"Unexpected violation for:\n{case}"
