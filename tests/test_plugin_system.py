from pathlib import Path
from golem.config import GolemConfig
from golem.engine import BuildEngine
from golem.plugins import hookimpl


def test_plugin_golem_mark_stale_hook(tmp_path):
    content_dir = tmp_path / "content"
    content_dir.mkdir()

    doc1 = content_dir / "doc1.adoc"
    doc1.write_text("= Math Doc\n\n[stem]\n++++\nx = y\n++++\n", encoding="utf-8")

    doc2 = content_dir / "doc2.adoc"
    doc2.write_text("= Text Doc\n\nSimple text\n", encoding="utf-8")

    config = GolemConfig(content_dir=str(content_dir), output_dir=str(tmp_path / "dist"))
    engine = BuildEngine(config, cache_file=tmp_path / "cache.json")
    engine.build_site()

    class MathPlugin:
        @hookimpl
        def golem_mark_stale(self, changed_files, cache_metadata):
            stale = []
            for path_str, meta in cache_metadata.items():
                if "stem" in meta.get("node_types", []):
                    stale.append(Path(path_str))
            return stale

    engine.pm.register(MathPlugin())
    # Force rebuild of metadata to ensure it's up to date
    engine.staleness_tracker.update_cache_for_file(doc1, node_types=["stem"])
    engine.staleness_tracker.update_cache_for_file(doc2, node_types=["text"])

    outdated = engine.staleness_tracker.get_outdated_files(commit=False)
    assert doc1.resolve() in outdated
    assert doc2.resolve() not in outdated
