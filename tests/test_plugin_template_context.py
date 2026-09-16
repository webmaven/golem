from pathlib import Path
from golem.config import GolemConfig
from golem.engine import BuildEngine
from golem.plugins import hookimpl


class ContextInjectPlugin:
    @hookimpl
    def on_template_context(self, context: dict, doc_path: Path) -> dict:
        context["injected_variable"] = "Hello from Hook"
        return context


def test_on_template_context_injected_variable(tmp_path):
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    (content_dir / "index.adoc").write_text("= Test Page\n\nBody content.\n", encoding="utf-8")

    # Custom skeleton rendering injected_variable
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    (templates_dir / "page.pt").write_text(
        '<html><body><span id="injected">${injected_variable}</span><div tal:content="structure body_html"/></body></html>',
        encoding="utf-8",
    )

    config = GolemConfig(
        content_dir=str(content_dir),
        output_dir=str(tmp_path / "dist"),
        templates_dir=str(templates_dir),
    )
    engine = BuildEngine(config)
    plugin = ContextInjectPlugin()
    engine.pm.register(plugin)

    compiled = engine.build_site()
    assert len(compiled) == 1
    output_html = compiled[0].read_text(encoding="utf-8")
    assert '<span id="injected">Hello from Hook</span>' in output_html


def test_on_template_context_receives_standard_context_and_doc_path(tmp_path):
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    doc_file = content_dir / "guide.adoc"
    doc_file.write_text("= Guide Title\n\nSome body text.\n", encoding="utf-8")

    captured_contexts = []

    class InspectPlugin:
        @hookimpl
        def on_template_context(self, context: dict, doc_path: Path) -> dict:
            captured_contexts.append((dict(context), doc_path))
            return context

    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    (templates_dir / "page.pt").write_text(
        '<html><body><div tal:content="structure body_html"/></body></html>',
        encoding="utf-8",
    )

    config = GolemConfig(
        content_dir=str(content_dir),
        output_dir=str(tmp_path / "dist"),
        templates_dir=str(templates_dir),
    )
    engine = BuildEngine(config)
    engine.pm.register(InspectPlugin())

    compiled = engine.build_site()
    assert len(compiled) == 1
    assert len(captured_contexts) == 1

    ctx, path = captured_contexts[0]
    assert path == doc_file
    assert ctx["title"] == "Guide Title"
    assert "Some body text" in ctx["body_html"]
    assert "current_path" in ctx


def test_on_template_context_multiple_plugins_chain(tmp_path):
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    (content_dir / "index.adoc").write_text("= Multi Plugin\n\nContent.\n", encoding="utf-8")

    class PluginA:
        @hookimpl
        def on_template_context(self, context: dict, doc_path: Path) -> dict:
            context["val_a"] = "from_a"
            return context

    class PluginB:
        @hookimpl
        def on_template_context(self, context: dict, doc_path: Path) -> dict:
            # PluginB should see PluginA's contribution in forward sequential order
            prev_val = context.get("val_a", "missing")
            return {"val_b": f"from_b_saw_{prev_val}"}

    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    (templates_dir / "page.pt").write_text(
        "<html><body><span>${val_a}</span><span>${val_b}</span></body></html>",
        encoding="utf-8",
    )

    config = GolemConfig(
        content_dir=str(content_dir),
        output_dir=str(tmp_path / "dist"),
        templates_dir=str(templates_dir),
    )
    engine = BuildEngine(config)
    engine.pm.register(PluginA())
    engine.pm.register(PluginB())

    compiled = engine.build_site()
    assert len(compiled) == 1
    output_html = compiled[0].read_text(encoding="utf-8")
    assert "<span>from_a</span>" in output_html
    assert "<span>from_b_saw_from_a</span>" in output_html


def test_on_template_context_preserves_dict_named_extra_context(tmp_path):
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    (content_dir / "index.adoc").write_text("= Extra Context Doc\n\nContent.\n", encoding="utf-8")

    class ExtraContextPlugin:
        @hookimpl
        def on_template_context(self, context: dict, doc_path: Path) -> dict:
            return {"extra_context": {"nested_key": "preserved_val"}}

    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    (templates_dir / "page.pt").write_text(
        '<html><body><span>${extra_context["nested_key"]}</span></body></html>',
        encoding="utf-8",
    )

    config = GolemConfig(
        content_dir=str(content_dir),
        output_dir=str(tmp_path / "dist"),
        templates_dir=str(templates_dir),
    )
    engine = BuildEngine(config)
    engine.pm.register(ExtraContextPlugin())

    compiled = engine.build_site()
    assert len(compiled) == 1
    output_html = compiled[0].read_text(encoding="utf-8")
    assert "<span>preserved_val</span>" in output_html


def test_on_template_context_optional_doc_path(tmp_path):
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    (content_dir / "index.adoc").write_text("= Title\n\nBody.\n", encoding="utf-8")

    class SubsetArgsPlugin:
        @hookimpl
        def on_template_context(self, context: dict) -> dict:
            context["from_subset"] = "works"
            return context

    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    (templates_dir / "page.pt").write_text(
        "<html><body><span>${from_subset}</span></body></html>",
        encoding="utf-8",
    )

    config = GolemConfig(
        content_dir=str(content_dir),
        output_dir=str(tmp_path / "dist"),
        templates_dir=str(templates_dir),
    )
    engine = BuildEngine(config)
    engine.pm.register(SubsetArgsPlugin())

    compiled = engine.build_site()
    assert len(compiled) == 1
    assert "<span>works</span>" in compiled[0].read_text(encoding="utf-8")


def test_on_template_context_exception_isolation(tmp_path, caplog):
    import logging

    content_dir = tmp_path / "content"
    content_dir.mkdir()
    (content_dir / "index.adoc").write_text("= Title\n\nBody.\n", encoding="utf-8")

    class FailingPlugin:
        @hookimpl
        def on_template_context(self, context: dict, doc_path: Path) -> dict:
            raise RuntimeError("Context crash!")

    class GoodPlugin:
        @hookimpl
        def on_template_context(self, context: dict, doc_path: Path) -> dict:
            context["good_key"] = "recovered"
            return context

    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    (templates_dir / "page.pt").write_text(
        "<html><body><span>${good_key}</span></body></html>",
        encoding="utf-8",
    )

    config = GolemConfig(
        content_dir=str(content_dir),
        output_dir=str(tmp_path / "dist"),
        templates_dir=str(templates_dir),
    )
    engine = BuildEngine(config)
    engine.pm.register(FailingPlugin(), name="failing_plugin")
    engine.pm.register(GoodPlugin(), name="good_plugin")

    with caplog.at_level(logging.WARNING):
        compiled = engine.build_site()

    assert len(compiled) == 1
    assert "<span>recovered</span>" in compiled[0].read_text(encoding="utf-8")
    assert any(
        "failing_plugin raised an exception in on_template_context for index.adoc: Context crash!" in r.message
        for r in caplog.records
    )


def test_on_template_context_exception_strict_raises(tmp_path):
    import pytest

    content_dir = tmp_path / "content"
    content_dir.mkdir()
    (content_dir / "index.adoc").write_text("= Title\n\nBody.\n", encoding="utf-8")

    class FailingPlugin:
        @hookimpl
        def on_template_context(self, context: dict, doc_path: Path) -> dict:
            raise RuntimeError("Strict crash!")

    config = GolemConfig(
        content_dir=str(content_dir),
        output_dir=str(tmp_path / "dist"),
        strict=True,
    )
    engine = BuildEngine(config)
    engine.pm.register(FailingPlugin())

    with pytest.raises(RuntimeError, match="Strict crash!"):
        engine.build_site()
