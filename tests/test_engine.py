import pytest
from pathlib import Path
from golem.engine import BuildEngine
from golem.config import GolemConfig

def test_incremental_rebuild_logic(tmp_path):
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    
    file_a = content_dir / "index.adoc"
    file_a.write_text("= Welcome\ninclude::sidebar.adoc[]")
    
    file_b = content_dir / "sidebar.adoc"
    file_b.write_text("Sidebar content")
    
    config = GolemConfig(content_dir=str(content_dir), output_dir=str(tmp_path / "dist"))
    engine = BuildEngine(config)
    
    # First compilation
    rebuild_set = engine.get_outdated_files()
    assert Path(file_a).resolve() in rebuild_set
    assert Path(file_b).resolve() in rebuild_set
    
    # Update cache mock state
    engine.update_cache_for_file(file_a)
    engine.update_cache_for_file(file_b)
    
    # Second check (unmodified)
    assert len(engine.get_outdated_files()) == 0
    
    # Edit file_b (the included sidebar)
    file_b.write_text("Modified Sidebar content")
    
    # Verify that file_a is flagged for recompilation because file_b is in its include-chain
    new_rebuild_set = engine.get_outdated_files()
    assert Path(file_a).resolve() in new_rebuild_set
