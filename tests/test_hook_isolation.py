import logging
from pathlib import Path
import pytest
from golem.config import GolemConfig
from golem.engine import BuildEngine
from golem.plugins import hookimpl


def _setup_test_engine(tmp_path: Path) -> tuple[BuildEngine, Path]:
    content_dir = tmp_path / "content"
    content_dir.mkdir(exist_ok=True)
    doc = content_dir / "index.adoc"
    doc.write_text("= Title\n\nHello World\n", encoding="utf-8")
    config = GolemConfig(content_dir=str(content_dir), output_dir=str(tmp_path / "dist"))
    engine = BuildEngine(config, cache_file=tmp_path / "cache.json")
    return engine, doc


def test_on_pre_parse_exception_isolation_and_warning(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    engine, _ = _setup_test_engine(tmp_path)

    class FailingPlugin:
        @hookimpl
        def on_pre_parse(self, raw_content: str) -> str:
            raise ValueError("Pre-parse explosion!")

    class SucceedingPlugin:
        @hookimpl
        def on_pre_parse(self, raw_content: str) -> str:
            return raw_content.replace("Hello World", "Replaced Content")

    engine.pm.register(FailingPlugin(), name="failing_plugin")
    engine.pm.register(SucceedingPlugin(), name="succeeding_plugin")

    with caplog.at_level(logging.WARNING):
        compiled = engine.build_site()

    assert len(compiled) == 1
    out_html = compiled[0].read_text(encoding="utf-8")
    assert "Replaced Content" in out_html

    # Check warning log for exception
    warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any(
        "failing_plugin raised an exception in on_pre_parse for index.adoc: Pre-parse explosion!" in r.message
        for r in warning_records
    )
    # Ensure no multiple-modifiers warning since only one plugin modified content
    assert not any("Multiple plugins modified raw_content" in r.message for r in warning_records)


def test_on_ast_created_exception_isolation(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    engine, _ = _setup_test_engine(tmp_path)

    class FailingASTPlugin:
        @hookimpl
        def on_ast_created(self, ast):
            raise RuntimeError("AST failure")

    engine.pm.register(FailingASTPlugin(), name="failing_ast")

    with caplog.at_level(logging.WARNING):
        compiled = engine.build_site()

    assert len(compiled) == 1
    assert any(
        "failing_ast raised an exception in on_ast_created for index.adoc: AST failure" in r.message for r in caplog.records
    )


def test_on_asg_created_exception_isolation(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    engine, _ = _setup_test_engine(tmp_path)

    class FailingASGPlugin:
        @hookimpl
        def on_asg_created(self, asg):
            raise RuntimeError("ASG failure")

    engine.pm.register(FailingASGPlugin(), name="failing_asg")

    with caplog.at_level(logging.WARNING):
        compiled = engine.build_site()

    assert len(compiled) == 1
    assert any(
        "failing_asg raised an exception in on_asg_created for index.adoc: ASG failure" in r.message for r in caplog.records
    )


def test_on_post_render_exception_isolation(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    engine, _ = _setup_test_engine(tmp_path)

    class FailingPostRenderPlugin:
        @hookimpl
        def on_post_render(self, html_content: str) -> str:
            raise RuntimeError("Post-render failure")

    class NormalPostRenderPlugin:
        @hookimpl
        def on_post_render(self, html_content: str) -> str:
            return html_content + "<!-- footer -->"

    engine.pm.register(FailingPostRenderPlugin(), name="failing_render")
    engine.pm.register(NormalPostRenderPlugin(), name="normal_render")

    with caplog.at_level(logging.WARNING):
        compiled = engine.build_site()

    assert len(compiled) == 1
    out_html = compiled[0].read_text(encoding="utf-8")
    assert "<!-- footer -->" in out_html
    assert any(
        "failing_render raised an exception in on_post_render for index.adoc: Post-render failure" in r.message
        for r in caplog.records
    )


def test_multiple_modifiers_warning_on_pre_parse(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    engine, _ = _setup_test_engine(tmp_path)

    class PluginOne:
        @hookimpl
        def on_pre_parse(self, raw_content: str) -> str:
            return raw_content.replace("Hello", "Greetings")

    class PluginTwo:
        @hookimpl
        def on_pre_parse(self, raw_content: str) -> str:
            return raw_content.replace("World", "Universe")

    engine.pm.register(PluginOne(), name="plugin_one")
    engine.pm.register(PluginTwo(), name="plugin_two")

    with caplog.at_level(logging.WARNING):
        compiled = engine.build_site()

    assert len(compiled) == 1
    warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
    conflict_warnings = [
        r.message
        for r in warning_records
        if "Multiple plugins modified raw_content in on_pre_parse for index.adoc" in r.message
    ]
    assert len(conflict_warnings) == 1
    assert "plugin_one" in conflict_warnings[0]
    assert "plugin_two" in conflict_warnings[0]


def test_single_modifier_and_none_return_no_conflict_warning(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    engine, _ = _setup_test_engine(tmp_path)

    class ModifyingPlugin:
        @hookimpl
        def on_pre_parse(self, raw_content: str) -> str:
            return raw_content.replace("Hello", "Hi")

    class NoOpPlugin:
        @hookimpl
        def on_pre_parse(self, raw_content: str) -> str:
            return raw_content  # Unchanged

    class NoneReturnPlugin:
        @hookimpl
        def on_pre_parse(self, raw_content: str):
            return None  # None return should not count as modifier or overwrite

    engine.pm.register(ModifyingPlugin(), name="mod_plugin")
    engine.pm.register(NoOpPlugin(), name="noop_plugin")
    engine.pm.register(NoneReturnPlugin(), name="none_plugin")

    with caplog.at_level(logging.WARNING):
        compiled = engine.build_site()

    assert len(compiled) == 1
    conflict_warnings = [r.message for r in caplog.records if "Multiple plugins modified" in r.message]
    assert len(conflict_warnings) == 0


def test_multiple_modifiers_warning_on_post_render(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    engine, _ = _setup_test_engine(tmp_path)

    class RenderModOne:
        @hookimpl
        def on_post_render(self, html_content: str) -> str:
            return html_content + "<!-- mod1 -->"

    class RenderModTwo:
        @hookimpl
        def on_post_render(self, html_content: str) -> str:
            return html_content + "<!-- mod2 -->"

    engine.pm.register(RenderModOne(), name="render_one")
    engine.pm.register(RenderModTwo(), name="render_two")

    with caplog.at_level(logging.WARNING):
        compiled = engine.build_site()

    assert len(compiled) == 1
    conflict_warnings = [
        r.message
        for r in caplog.records
        if "Multiple plugins modified html_content in on_post_render for index.adoc" in r.message
    ]
    assert len(conflict_warnings) == 1
    assert "render_one" in conflict_warnings[0]
    assert "render_two" in conflict_warnings[0]


def test_multiple_modifiers_warning_on_ast_created(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    import copy

    engine, _ = _setup_test_engine(tmp_path)

    class ASTModOne:
        @hookimpl
        def on_ast_created(self, ast):
            return copy.deepcopy(ast)

    class ASTModTwo:
        @hookimpl
        def on_ast_created(self, ast):
            return copy.deepcopy(ast)

    engine.pm.register(ASTModOne(), name="ast_one")
    engine.pm.register(ASTModTwo(), name="ast_two")

    with caplog.at_level(logging.WARNING):
        compiled = engine.build_site()

    assert len(compiled) == 1
    conflict_warnings = [
        r.message for r in caplog.records if "Multiple plugins modified ast in on_ast_created for index.adoc" in r.message
    ]
    assert len(conflict_warnings) == 1
    assert "ast_one" in conflict_warnings[0]
    assert "ast_two" in conflict_warnings[0]


def test_multiple_modifiers_warning_on_asg_created(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    import copy

    engine, _ = _setup_test_engine(tmp_path)

    class ASGModOne:
        @hookimpl
        def on_asg_created(self, asg):
            new_asg = copy.deepcopy(asg)
            return new_asg

    class ASGModTwo:
        @hookimpl
        def on_asg_created(self, asg):
            new_asg = copy.deepcopy(asg)
            return new_asg

    engine.pm.register(ASGModOne(), name="asg_one")
    engine.pm.register(ASGModTwo(), name="asg_two")

    with caplog.at_level(logging.WARNING):
        compiled = engine.build_site()

    assert len(compiled) == 1
    conflict_warnings = [
        r.message for r in caplog.records if "Multiple plugins modified asg in on_asg_created for index.adoc" in r.message
    ]
    assert len(conflict_warnings) == 1
    assert "asg_one" in conflict_warnings[0]
    assert "asg_two" in conflict_warnings[0]


def test_ast_and_asg_none_return_preserves_content(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    engine, _ = _setup_test_engine(tmp_path)

    class NoneASTPlugin:
        @hookimpl
        def on_ast_created(self, ast):
            return None

    class NoneASGPlugin:
        @hookimpl
        def on_asg_created(self, asg):
            return None

    engine.pm.register(NoneASTPlugin(), name="none_ast")
    engine.pm.register(NoneASGPlugin(), name="none_asg")

    with caplog.at_level(logging.WARNING):
        compiled = engine.build_site()

    assert len(compiled) == 1
    conflict_warnings = [r.message for r in caplog.records if "Multiple plugins modified" in r.message]
    assert len(conflict_warnings) == 0


def test_ast_and_asg_same_instance_no_conflict_warning(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    engine, _ = _setup_test_engine(tmp_path)

    class SameASTPlugin1:
        @hookimpl
        def on_ast_created(self, ast):
            return ast

    class SameASTPlugin2:
        @hookimpl
        def on_ast_created(self, ast):
            return ast

    class SameASGPlugin1:
        @hookimpl
        def on_asg_created(self, asg):
            return asg

    class SameASGPlugin2:
        @hookimpl
        def on_asg_created(self, asg):
            return asg

    engine.pm.register(SameASTPlugin1(), name="same_ast_1")
    engine.pm.register(SameASTPlugin2(), name="same_ast_2")
    engine.pm.register(SameASGPlugin1(), name="same_asg_1")
    engine.pm.register(SameASGPlugin2(), name="same_asg_2")

    with caplog.at_level(logging.WARNING):
        compiled = engine.build_site()

    assert len(compiled) == 1
    conflict_warnings = [r.message for r in caplog.records if "Multiple plugins modified" in r.message]
    assert len(conflict_warnings) == 0


def test_anonymous_plugin_modifier_labels(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    engine, _ = _setup_test_engine(tmp_path)

    class AnonymousPluginA:
        @hookimpl
        def on_pre_parse(self, raw_content: str) -> str:
            return raw_content.replace("Hello", "Hey")

    class AnonymousPluginB:
        @hookimpl
        def on_pre_parse(self, raw_content: str) -> str:
            return raw_content.replace("World", "Earth")

    # Register without explicit name
    engine.pm.register(AnonymousPluginA())
    engine.pm.register(AnonymousPluginB())

    with caplog.at_level(logging.WARNING):
        compiled = engine.build_site()

    assert len(compiled) == 1
    conflict_warnings = [
        r.message
        for r in caplog.records
        if "Multiple plugins modified raw_content in on_pre_parse for index.adoc" in r.message
    ]
    assert len(conflict_warnings) == 1
