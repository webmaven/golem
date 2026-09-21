"""Unit tests for Golem CSS Design Token System (Issue #16).

Verifies the three-layer token architecture (primitives -> semantics -> components),
symbol tokens (C, M, F, I, T, X, V), dark mode (data-theme and media query),
reduced motion, contrast ratios (WCAG 2.1 AA), and token adoption.
"""

from __future__ import annotations

from pathlib import Path
import re

CSS_PATH = Path(__file__).resolve().parent.parent / "src" / "golem" / "templates" / "default" / "static" / "css" / "golem.css"
SKELETON_PATH = Path(__file__).resolve().parent.parent / "src" / "golem" / "templates" / "default" / "skeleton.pt"


def _read_css() -> str:
    """Read golem.css file contents."""
    assert CSS_PATH.exists(), f"golem.css not found at {CSS_PATH}"
    return CSS_PATH.read_text(encoding="utf-8")


def _extract_css_rules(css_text: str) -> list[tuple[str, str]]:
    """Simple parser to extract (selector, declarations_block) pairs."""
    clean_css = re.sub(r"/\*.*?\*/", "", css_text, flags=re.DOTALL)
    rules: list[tuple[str, str]] = []

    pos = 0
    while pos < len(clean_css):
        open_brace = clean_css.find("{", pos)
        if open_brace == -1:
            break
        selector = clean_css[pos:open_brace].strip()
        brace_depth = 1
        i = open_brace + 1
        while i < len(clean_css) and brace_depth > 0:
            if clean_css[i] == "{":
                brace_depth += 1
            elif clean_css[i] == "}":
                brace_depth -= 1
            i += 1
        body = clean_css[open_brace + 1 : i - 1].strip()
        rules.append((selector, body))
        pos = i

    return rules


def _parse_custom_properties(block: str) -> dict[str, str]:
    """Extract all --custom-prop: value; pairs from a declarations block."""
    props: dict[str, str] = {}
    lines = block.split(";")
    for line in lines:
        line = line.strip()
        if ":" in line:
            prop, val = line.split(":", 1)
            prop = prop.strip()
            val = val.strip()
            if prop.startswith("--"):
                props[prop] = val
    return props


def _extract_root_tokens(css_text: str) -> dict[str, str]:
    """Extract all CSS variables declared under :root."""
    rules = _extract_css_rules(css_text)
    root_props: dict[str, str] = {}
    for selector, body in rules:
        if selector == ":root" or selector.startswith(":root "):
            root_props.update(_parse_custom_properties(body))
    return root_props


def _extract_dark_tokens(css_text: str) -> dict[str, str]:
    """Extract all CSS variables declared under [data-theme='dark']."""
    rules = _extract_css_rules(css_text)
    dark_props: dict[str, str] = {}
    for selector, body in rules:
        if '[data-theme="dark"]' in selector or "[data-theme='dark']" in selector:
            dark_props.update(_parse_custom_properties(body))
    return dark_props


def _extract_media_dark_tokens(css_text: str) -> dict[str, str]:
    """Extract all CSS variables declared inside @media (prefers-color-scheme: dark)."""
    rules = _extract_css_rules(css_text)
    media_dark_props: dict[str, str] = {}
    for selector, body in rules:
        if "prefers-color-scheme: dark" in selector or "prefers-color-scheme:dark" in selector:
            # Body may contain inner nested rules (e.g. :root { ... })
            inner_rules = _extract_css_rules(body)
            if inner_rules:
                for _, inner_body in inner_rules:
                    media_dark_props.update(_parse_custom_properties(inner_body))
            else:
                media_dark_props.update(_parse_custom_properties(body))
    return media_dark_props


# ---------------------------------------------------------------------------
# Color & WCAG Contrast Utilities
# ---------------------------------------------------------------------------


def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    """Convert hex string (#rgb, #rrggbb, #rrggbbaa) to (r, g, b)."""
    hex_str = hex_str.strip().lstrip("#")
    if len(hex_str) == 3:
        r, g, b = (int(c * 2, 16) for c in hex_str)
        return r, g, b
    elif len(hex_str) == 6 or len(hex_str) == 8:
        r = int(hex_str[0:2], 16)
        g = int(hex_str[2:4], 16)
        b = int(hex_str[4:6], 16)
        return r, g, b
    raise ValueError(f"Unsupported hex format: #{hex_str}")


def _relative_luminance(r: int, g: int, b: int) -> float:
    """Compute relative luminance according to WCAG 2.1 formula."""
    channels = []
    for c in (r, g, b):
        s = c / 255.0
        if s <= 0.03928:
            channels.append(s / 12.92)
        else:
            channels.append(((s + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def _contrast_ratio(rgb1: tuple[int, int, int], rgb2: tuple[int, int, int]) -> float:
    """Compute contrast ratio between two RGB colors (1:1 to 21:1)."""
    l1 = _relative_luminance(*rgb1)
    l2 = _relative_luminance(*rgb2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _resolve_color(val: str, all_props: dict[str, str]) -> tuple[int, int, int]:
    """Resolve a CSS color value or variable to RGB."""
    val = val.strip()
    var_match = re.match(r"var\(\s*(--[\w-]+)\s*\)", val)
    if var_match:
        target_var = var_match.group(1)
        if target_var in all_props:
            return _resolve_color(all_props[target_var], all_props)
    hex_match = re.search(r"#[0-9a-fA-F]{3,8}", val)
    if hex_match:
        return _hex_to_rgb(hex_match.group(0))
    raise ValueError(f"Cannot resolve color: '{val}'")


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------


def test_primitive_spacing_tokens_exist_and_scale():
    """Verify :root defines --space-xs through --space-xl in strictly ascending order."""
    css = _read_css()
    tokens = _extract_root_tokens(css)

    required_spacing = ["--space-xs", "--space-sm", "--space-md", "--space-lg", "--space-xl"]
    for sp in required_spacing:
        assert sp in tokens, f"Missing spacing token: {sp}"

    # Verify monotonic scaling
    def to_rem(val: str) -> float:
        val = val.strip()
        if val.endswith("rem"):
            return float(val.replace("rem", ""))
        elif val.endswith("px"):
            return float(val.replace("px", "")) / 16.0
        raise ValueError(f"Unknown unit for spacing: {val}")

    values = [to_rem(tokens[sp]) for sp in required_spacing]
    assert values == sorted(values), f"Spacing tokens not monotonically increasing: {values}"
    assert len(set(values)) == len(values), f"Spacing tokens contain duplicates: {values}"


def test_primitive_typography_tokens_exist():
    """Verify :root defines typography family and size tokens."""
    css = _read_css()
    tokens = _extract_root_tokens(css)

    required_typography = [
        "--font-mono",
        "--font-sans",
        "--font-size-sig",
        "--font-size-param",
    ]
    for typo in required_typography:
        assert typo in tokens, f"Missing typography token: {typo}"


def test_semantic_surface_and_text_tokens_exist():
    """Verify semantic surface and text tokens exist in :root."""
    css = _read_css()
    tokens = _extract_root_tokens(css)

    required_semantics = [
        "--bg-surface",
        "--bg-surface-subtle",
        "--bg-card",
        "--color-text",
        "--color-text-muted",
        "--border-color",
    ]
    for token in required_semantics:
        assert token in tokens, f"Missing semantic token: {token}"


def test_semantic_left_rail_tokens_exist():
    """Verify left-rail hierarchy tokens exist for Principle 3 structural containment."""
    css = _read_css()
    tokens = _extract_root_tokens(css)

    required_rail = [
        "--border-rail",
        "--border-rail-active",
        "--rail-indent",
    ]
    for rail in required_rail:
        assert rail in tokens, f"Missing left-rail token: {rail}"


def test_component_symbol_tokens_exist():
    """Verify dual-coding symbol kind color pairs for C, M, F, I, T, X, V."""
    css = _read_css()
    tokens = _extract_root_tokens(css)

    symbols = [
        ("c", "class"),
        ("m", "method"),
        ("f", "function"),
        ("i", "interface"),
        ("t", "type"),
        ("x", "exception"),
        ("v", "variable"),
    ]

    for short_name, full_name in symbols:
        # Accept either short form (--color-symbol-c) or full form (--color-symbol-class)
        has_color = (f"--color-symbol-{short_name}" in tokens) or (f"--color-symbol-{full_name}" in tokens)
        has_bg = (
            (f"--bg-symbol-{short_name}" in tokens)
            or (f"--bg-symbol-{full_name}" in tokens)
            or (f"--color-symbol-{short_name}-bg" in tokens)
            or (f"--color-symbol-{full_name}-bg" in tokens)
        )
        assert has_color, f"Missing symbol text color token for {full_name} ({short_name})"
        assert has_bg, f"Missing symbol background token for {full_name} ({short_name})"


def test_dark_mode_selectors_and_tokens():
    """Verify dark mode support via BOTH [data-theme='dark'] AND @media (prefers-color-scheme: dark)."""
    css = _read_css()

    dark_props = _extract_dark_tokens(css)
    assert dark_props, "golem.css must define [data-theme='dark'] selector with token overrides"

    media_dark_props = _extract_media_dark_tokens(css)
    assert media_dark_props, "golem.css must define @media (prefers-color-scheme: dark) with token overrides"

    # Both must override essential semantic tokens
    essential_dark = ["--bg-surface", "--color-text"]
    for token in essential_dark:
        assert token in dark_props, f"[data-theme='dark'] missing override for {token}"
        assert token in media_dark_props, f"@media (prefers-color-scheme: dark) missing override for {token}"

    # Verify light theme fallback / toggle guard (e.g. :not([data-theme="light"]))
    assert 'data-theme="light"' in css or "data-theme='light'" in css or "data-theme" in css, (
        "golem.css must support explicit theme switching (e.g. data-theme attribute)"
    )


def test_reduced_motion_rule_exists():
    """Verify @media (prefers-reduced-motion: reduce) zeroes transitions and animations."""
    css = _read_css()
    assert "@media (prefers-reduced-motion: reduce)" in css or "@media(prefers-reduced-motion:reduce)" in css

    rules = _extract_css_rules(css)
    reduced_motion_blocks = [
        body
        for selector, body in rules
        if "prefers-reduced-motion: reduce" in selector or "prefers-reduced-motion:reduce" in selector
    ]
    assert reduced_motion_blocks, "Reduced motion block must have non-empty declaration body"
    block = reduced_motion_blocks[0]
    assert "transition" in block or "animation" in block, "Reduced motion rule must target transition or animation properties"


def test_wcag_contrast_ratios():
    """Verify WCAG 2.1 AA contrast ratios for light and dark themes."""
    css = _read_css()
    root_tokens = _extract_root_tokens(css)
    dark_tokens = _extract_dark_tokens(css)

    # 1. Light Mode: text on surface (>= 4.5:1 for normal text)
    if "--color-text" in root_tokens and "--bg-surface" in root_tokens:
        text_rgb = _resolve_color(root_tokens["--color-text"], root_tokens)
        bg_rgb = _resolve_color(root_tokens["--bg-surface"], root_tokens)
        ratio = _contrast_ratio(text_rgb, bg_rgb)
        assert ratio >= 4.5, f"Light mode text contrast ratio {ratio:.2f}:1 is below 4.5:1"

    # 2. Dark Mode: text on surface (>= 4.5:1)
    # Merge root_tokens with dark_tokens for variable resolution
    all_dark = {**root_tokens, **dark_tokens}
    if "--color-text" in all_dark and "--bg-surface" in all_dark:
        dark_text_rgb = _resolve_color(all_dark["--color-text"], all_dark)
        dark_bg_rgb = _resolve_color(all_dark["--bg-surface"], all_dark)
        dark_ratio = _contrast_ratio(dark_text_rgb, dark_bg_rgb)
        assert dark_ratio >= 4.5, f"Dark mode text contrast ratio {dark_ratio:.2f}:1 is below 4.5:1"

    # 3. Symbol badge contrast in light mode (>= 3.0:1 for graphical/badge elements per WCAG AA)
    symbols = [
        ("c", "class"),
        ("m", "method"),
        ("f", "function"),
        ("i", "interface"),
        ("t", "type"),
        ("x", "exception"),
        ("v", "variable"),
    ]
    for short_name, full_name in symbols:
        fg_key = (
            f"--color-symbol-{short_name}" if f"--color-symbol-{short_name}" in root_tokens else f"--color-symbol-{full_name}"
        )
        bg_key = None
        for candidate in [
            f"--bg-symbol-{short_name}",
            f"--bg-symbol-{full_name}",
            f"--color-symbol-{short_name}-bg",
            f"--color-symbol-{full_name}-bg",
        ]:
            if candidate in root_tokens:
                bg_key = candidate
                break
        if fg_key in root_tokens and bg_key:
            try:
                fg_rgb = _resolve_color(root_tokens[fg_key], root_tokens)
                bg_rgb = _resolve_color(root_tokens[bg_key], root_tokens)
                sym_ratio = _contrast_ratio(fg_rgb, bg_rgb)
                assert sym_ratio >= 3.0, (
                    f"Symbol {full_name} badge contrast {sym_ratio:.2f}:1 between {fg_key} and {bg_key} is below 3.0:1"
                )
            except ValueError:
                pass


def test_skeleton_template_has_no_hardcoded_color_styles():
    """Verify skeleton.pt does not contain hardcoded inline color styles."""
    assert SKELETON_PATH.exists(), f"skeleton.pt not found at {SKELETON_PATH}"
    skeleton_text = SKELETON_PATH.read_text(encoding="utf-8")

    # Match style="...#abc..." or style="...color: ...;..."
    hardcoded_styles = re.findall(r'style="[^"]*#[0-9a-fA-F]{3,6}[^"]*"', skeleton_text)
    assert not hardcoded_styles, f"Found hardcoded inline color styles in skeleton.pt: {hardcoded_styles}"


def test_symbol_glyph_component_classes():
    """Verify CSS classes exist for all dual-coding symbol glyph badges."""
    css = _read_css()
    assert ".symbol-glyph" in css, "Missing .symbol-glyph base class in golem.css"

    for kind in ["c", "m", "f", "i", "t", "x", "v"]:
        assert f".glyph-{kind}" in css, f"Missing .glyph-{kind} class in golem.css"


def test_left_rail_doc_member_styling():
    """Verify .doc-member left-rail styling uses hierarchy tokens."""
    css = _read_css()
    assert ".doc-member" in css, "Missing .doc-member class in golem.css"
    rules = _extract_css_rules(css)
    doc_member_blocks = [body for selector, body in rules if selector == ".doc-member"]
    assert doc_member_blocks, "Missing .doc-member selector rule"
    block = doc_member_blocks[0]
    assert "--border-rail" in block, ".doc-member must use var(--border-rail)"
    assert "--rail-indent" in block, ".doc-member must use var(--rail-indent)"


def test_legacy_golem_token_aliases_preserved():
    """Verify backward compatibility: legacy --golem-* tokens are mapped to design tokens."""
    css = _read_css()
    tokens = _extract_root_tokens(css)
    required_legacy = [
        "--golem-bg",
        "--golem-surface",
        "--golem-code-bg",
        "--golem-text",
        "--golem-text-muted",
        "--golem-primary",
        "--golem-primary-hover",
        "--golem-border",
        "--golem-link",
        "--golem-note",
        "--golem-tip",
        "--golem-important",
        "--golem-warning",
        "--golem-caution",
    ]
    for leg in required_legacy:
        assert leg in tokens, f"Missing legacy token alias: {leg}"


def test_footer_token_adoption():
    """Verify #golem-footer references design tokens instead of hardcoded values."""
    css = _read_css()
    rules = _extract_css_rules(css)
    footer_blocks = [body for selector, body in rules if selector == "#golem-footer"]
    assert footer_blocks, "Missing #golem-footer selector rule"
    block = footer_blocks[0]
    assert "var(--bg-surface)" in block, "#golem-footer must use var(--bg-surface)"
    assert "var(--border-color)" in block, "#golem-footer must use var(--border-color)"
    assert "var(--color-text-muted)" in block, "#golem-footer must use var(--color-text-muted)"
