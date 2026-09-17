from pathlib import Path
from typing import Any
from golem.config import GolemConfig
from golem.engine import BuildEngine, _invoke_doc_hook
from golem.plugins import hookimpl


class PartialSignaturePlugin:
    """Plugin with partial signatures: only primary argument, omitting doc_path."""

    def __init__(self) -> None:
        self.asg_called = False
        self.context_called = False

    @hookimpl
    def on_asg_created(self, asg: dict[str, Any]) -> dict[str, Any]:
        self.asg_called = True
        return asg

    @hookimpl
    def on_template_context(self, context: dict[str, Any]) -> dict[str, Any]:
        self.context_called = True
        context["partial_hook_injected"] = "partial_signature_works"
        return context


class FullSignaturePlugin:
    """Plugin with full signatures: primary argument and doc_path."""

    def __init__(self) -> None:
        self.received_asg_doc_path: Path | None = None
        self.received_context_doc_path: Path | None = None

    @hookimpl
    def on_asg_created(self, asg: dict[str, Any], doc_path: Path) -> dict[str, Any]:
        self.received_asg_doc_path = doc_path
        return asg

    @hookimpl
    def on_template_context(self, context: dict[str, Any], doc_path: Path) -> dict[str, Any]:
        self.received_context_doc_path = doc_path
        return context


def test_invoke_doc_hook_direct() -> None:
    """Unit test for _invoke_doc_hook helper supporting both full and partial signatures."""

    class DummyImpl:
        def __init__(self, fn: Any, argnames: tuple[str, ...]) -> None:
            self.function = fn
            self.argnames = argnames

    # Partial signature for asg
    impl_partial_asg = DummyImpl(lambda asg: f"processed_{asg}", ("asg",))
    res = _invoke_doc_hook(impl_partial_asg, "asg", "test_val", Path("dummy.adoc"))
    assert res == "processed_test_val"

    # Partial signature for context
    impl_partial_ctx = DummyImpl(lambda context: {"k": "v"}, ("context",))
    res_ctx = _invoke_doc_hook(impl_partial_ctx, "context", {"old": 1}, Path("dummy.adoc"))
    assert res_ctx == {"k": "v"}

    # Full signature
    impl_full = DummyImpl(lambda context, doc_path: f"ctx_{context}_{doc_path.name}", ("context", "doc_path"))
    res_full = _invoke_doc_hook(impl_full, "context", "val", Path("dummy.adoc"))
    assert res_full == "ctx_val_dummy.adoc"


def test_partial_signature_plugins_dispatch(tmp_path: Path) -> None:
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    doc_file = content_dir / "index.adoc"
    doc_file.write_text("= Test Page\n\nContent.\n", encoding="utf-8")

    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    (templates_dir / "page.pt").write_text(
        '<html><body><span>${partial_hook_injected}</span><div tal:content="structure body_html"/></body></html>',
        encoding="utf-8",
    )

    config = GolemConfig(
        content_dir=str(content_dir),
        output_dir=str(tmp_path / "dist"),
        templates_dir=str(templates_dir),
    )
    engine = BuildEngine(config)
    plugin = PartialSignaturePlugin()
    full_plugin = FullSignaturePlugin()
    engine.pm.register(plugin)
    engine.pm.register(full_plugin)

    compiled = engine.build_site()
    assert len(compiled) == 1
    assert plugin.asg_called is True
    assert plugin.context_called is True
    assert full_plugin.received_asg_doc_path == doc_file
    assert full_plugin.received_context_doc_path == doc_file
    html = compiled[0].read_text(encoding="utf-8")
    assert "<span>partial_signature_works</span>" in html
