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
            # Returning updated dict or new dict
            return {"val_b": "from_b"}

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
    assert "<span>from_b</span>" in output_html


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
