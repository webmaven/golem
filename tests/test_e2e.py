"""
= End-to-End Workflow Tests for Golem

This module contains end-to-end integration and workflow verification tests
driving Golem from initialization, adding includes, building, and rebuild invalidation.
"""

from pathlib import Path
from click.testing import CliRunner
from golem.cli import main


def test_full_golem_workflow_e2e(tmp_path):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        # 1. Initialize a Golem Documentation Portal
        init_res = runner.invoke(main, ["init"])
        assert init_res.exit_code == 0

        # Create secondary include page in the content folder
        sidebar = Path("content/sidebar.adoc")
        sidebar.write_text("This is sidebar help.\n", encoding="utf-8")

        # Update index.adoc to include the sidebar
        index = Path("content/index.adoc")
        index.write_text(
            "= My Golem Documentation\n\ninclude::sidebar.adoc[]\n",
            encoding="utf-8",
        )

        # 2. Run initial Golem Build (E2E Integration)
        build_res_1 = runner.invoke(main, ["build"])
        assert build_res_1.exit_code == 0
        assert "Built 2 pages" in build_res_1.output

        index_html = Path("dist/index.html")
        assert index_html.exists()
        html_text_1 = index_html.read_text(encoding="utf-8")
        assert "My Golem Documentation" in html_text_1
        assert "This is sidebar help" in html_text_1

        # 3. Modify only the sidebar include document
        sidebar.write_text("Sidebar help has been updated.\n", encoding="utf-8")

        # 4. Trigger E2E Rebuild (Verifies that DAG Cache correctly invalidates index and compiles both)
        build_res_2 = runner.invoke(main, ["build"])
        assert build_res_2.exit_code == 0
        assert "Built 2 pages" in build_res_2.output

        html_text_2 = index_html.read_text(encoding="utf-8")
        assert "Sidebar help has been updated" in html_text_2
