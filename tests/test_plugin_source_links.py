from pathlib import Path

from golem.config import GolemConfig
from golem.engine import BuildEngine
from golem.plugins.source_links import (
    SourceLinksPlugin,
    detect_branch,
    detect_provider,
    detect_repo_url,
    normalize_repo_url,
)


def test_normalize_repo_url_ssh():
    assert normalize_repo_url("git@github.com:webmaven/golem.git") == "https://github.com/webmaven/golem"
    assert normalize_repo_url("git@gitlab.com:group/subgroup/repo.git") == "https://gitlab.com/group/subgroup/repo"
    assert normalize_repo_url("ssh://git@github.com/webmaven/golem.git") == "https://github.com/webmaven/golem"
    assert normalize_repo_url("ssh://git@gitlab.com:22/group/repo.git") == "https://gitlab.com/group/repo"


def test_normalize_repo_url_https():
    assert normalize_repo_url("https://github.com/webmaven/golem.git") == "https://github.com/webmaven/golem"
    assert normalize_repo_url("https://github.com/webmaven/golem/") == "https://github.com/webmaven/golem"
    assert normalize_repo_url("https://gitlab.com/group/repo.git") == "https://gitlab.com/group/repo"


def test_normalize_repo_url_empty_and_custom():
    assert normalize_repo_url("") == ""
    assert normalize_repo_url("git://github.com/webmaven/golem.git") == "https://github.com/webmaven/golem"


def test_detect_provider():
    assert detect_provider("https://github.com/webmaven/golem") == "github"
    assert detect_provider("https://gitlab.com/group/repo") == "gitlab"
    assert detect_provider("https://my-gitlab-instance.org/group/repo") == "gitlab"
    assert detect_provider("https://bitbucket.org/group/repo") == "custom"
    assert detect_provider("https://git.sr.ht/~user/repo") == "custom"


def test_git_auto_detection_in_repo(tmp_path):
    # Create a mock .git directory with config and HEAD
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    config_file = git_dir / "config"
    config_file.write_text(
        '[core]\n\trepositoryformatversion = 0\n[remote "origin"]\n\turl = git@github.com:testorg/testrepo.git\n\tfetch = +refs/heads/*:refs/remotes/origin/*\n',
        encoding="utf-8",
    )
    head_file = git_dir / "HEAD"
    head_file.write_text("ref: refs/heads/develop\n", encoding="utf-8")

    detected_url = detect_repo_url(tmp_path)
    assert detected_url == "git@github.com:testorg/testrepo.git"

    detected_branch = detect_branch(tmp_path)
    assert detected_branch == "develop"

    plugin = SourceLinksPlugin(root_dir=tmp_path)
    assert plugin.repo_url == "https://github.com/testorg/testrepo"
    assert plugin.branch == "develop"
    assert plugin.provider == "github"


def test_source_links_plugin_github_urls():
    plugin = SourceLinksPlugin(
        repo_url="https://github.com/webmaven/golem",
        branch="main",
        docs_dir="docs",
    )
    context = {"current_path": "guide/index.adoc"}
    result = plugin.on_template_context(context, Path("guide/index.adoc"))

    assert result["source_repo_url"] == "https://github.com/webmaven/golem"
    assert result["source_edit_url"] == "https://github.com/webmaven/golem/edit/main/docs/guide/index.adoc"
    assert result["source_view_url"] == "https://github.com/webmaven/golem/blob/main/docs/guide/index.adoc"
    assert result["source_url"] == "https://github.com/webmaven/golem/blob/main/docs/guide/index.adoc"
    assert result["source_provider"] == "github"


def test_source_links_plugin_gitlab_urls():
    plugin = SourceLinksPlugin(
        repo_url="https://gitlab.com/group/repo",
        branch="release",
        docs_dir="docs",
    )
    context = {"current_path": "index.adoc"}
    result = plugin.on_template_context(context, Path("index.adoc"))

    assert result["source_repo_url"] == "https://gitlab.com/group/repo"
    assert result["source_edit_url"] == "https://gitlab.com/group/repo/-/edit/release/docs/index.adoc"
    assert result["source_view_url"] == "https://gitlab.com/group/repo/-/blob/release/docs/index.adoc"
    assert result["source_url"] == "https://gitlab.com/group/repo/-/blob/release/docs/index.adoc"
    assert result["source_provider"] == "gitlab"


def test_source_links_plugin_custom_templates():
    plugin = SourceLinksPlugin(
        repo_url="https://git.example.com/org/repo",
        branch="trunk",
        docs_dir="docs",
        provider="custom",
        edit_url_template="{repo_url}/src/{branch}/{doc_path}?edit=true",
        view_url_template="{repo_url}/src/{branch}/{doc_path}?raw=true",
    )
    result = plugin.on_template_context({}, Path("index.adoc"))
    assert result["source_edit_url"] == "https://git.example.com/org/repo/src/trunk/docs/index.adoc?edit=true"
    assert result["source_view_url"] == "https://git.example.com/org/repo/src/trunk/docs/index.adoc?raw=true"
    assert result["source_provider"] == "custom"


def test_source_links_plugin_no_duplicate_docs_dir():
    plugin = SourceLinksPlugin(
        repo_url="https://github.com/webmaven/golem",
        branch="main",
        docs_dir="docs",
    )
    # When doc_path already includes docs_dir
    result = plugin.on_template_context({}, Path("docs/index.adoc"))
    assert result["source_edit_url"] == "https://github.com/webmaven/golem/edit/main/docs/index.adoc"

    # When docs_dir is not set
    plugin_no_docs_dir = SourceLinksPlugin(
        repo_url="https://github.com/webmaven/golem",
        branch="main",
        docs_dir=None,
    )
    result2 = plugin_no_docs_dir.on_template_context({}, Path("index.adoc"))
    assert result2["source_edit_url"] == "https://github.com/webmaven/golem/edit/main/index.adoc"


def test_source_links_plugin_missing_repo_url(tmp_path):
    # In an empty temp dir with no git repository
    plugin = SourceLinksPlugin(repo_url=None, root_dir=tmp_path)
    assert plugin.repo_url is None
    context = {"title": "Test"}
    result = plugin.on_template_context(context, Path("index.adoc"))
    # Context should not be polluted with broken URLs
    assert "source_edit_url" not in result
    assert result["title"] == "Test"


def test_source_links_from_config(tmp_path):
    config = GolemConfig(
        plugin_configs={
            "source_links": {
                "repo_url": "git@github.com:webmaven/golem.git",
                "branch": "develop",
                "docs_dir": "docs",
            }
        }
    )
    plugin = SourceLinksPlugin.from_config(config)
    assert plugin.repo_url == "https://github.com/webmaven/golem"
    assert plugin.branch == "develop"
    assert plugin.docs_dir == "docs"
    assert plugin.provider == "github"


def test_source_links_integration_build_site(tmp_path):
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    (content_dir / "index.adoc").write_text("= Welcome to Golem\n\nPage content.\n", encoding="utf-8")

    config = GolemConfig(
        content_dir=str(content_dir),
        output_dir=str(tmp_path / "dist"),
        plugin_configs={
            "source_links": {
                "repo_url": "https://github.com/webmaven/golem",
                "branch": "main",
                "docs_dir": "content",
            }
        },
    )
    engine = BuildEngine(config)
    plugin = SourceLinksPlugin.from_config(config)
    engine.pm.register(plugin)

    compiled = engine.build_site()
    assert len(compiled) == 1
    html = compiled[0].read_text(encoding="utf-8")
    assert "golem-edit-link" in html
    assert "https://github.com/webmaven/golem/edit/main/content/index.adoc" in html


def test_source_links_registered_via_plugin_manager(tmp_path):
    from golem.plugins import get_plugin_manager

    config = GolemConfig(
        plugins=["golem.plugins.source_links"],
        plugin_configs={
            "source_links": {
                "repo_url": "https://github.com/webmaven/golem",
                "branch": "main",
            }
        },
    )
    pm = get_plugin_manager(config=config)
    plugin = pm.get_plugin("golem.plugins.source_links")
    assert isinstance(plugin, SourceLinksPlugin)
    assert plugin.repo_url == "https://github.com/webmaven/golem"


def test_source_links_worktree_detection(tmp_path):
    real_git_dir = tmp_path / "actual_git_dir"
    real_git_dir.mkdir()
    (real_git_dir / "config").write_text(
        '[remote "origin"]\n\turl = git@gitlab.com:enterprise/docs.git\n',
        encoding="utf-8",
    )
    (real_git_dir / "HEAD").write_text("ref: refs/heads/feature/nav\n", encoding="utf-8")

    worktree_dir = tmp_path / "worktree"
    worktree_dir.mkdir()
    (worktree_dir / ".git").write_text(f"gitdir: {real_git_dir}\n", encoding="utf-8")

    plugin = SourceLinksPlugin(root_dir=worktree_dir)
    assert plugin.repo_url == "https://gitlab.com/enterprise/docs"
    assert plugin.branch == "feature/nav"
    assert plugin.provider == "gitlab"


def test_source_links_cli_inspection():
    import json
    from click.testing import CliRunner
    from golem.cli import main

    runner = CliRunner()
    result = runner.invoke(main, ["plugins", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    plugin_entry = next((p for p in data if p["name"] in ("source_links", "golem.plugins.source_links")), None)
    assert plugin_entry is not None
    assert plugin_entry["source"] == "built-in"


def test_source_links_toml_config_loading(tmp_path):
    from golem.config import load_config

    config_file = tmp_path / "golem.toml"
    config_file.write_text(
        """
[site]
title = "My Site"

[source_links]
repo_url = "git@github.com:myorg/myrepo.git"
branch = "staging"
docs_dir = "documentation"
provider = "github"
""",
        encoding="utf-8",
    )
    config = load_config(config_file)
    assert config.plugin_configs["source_links"]["repo_url"] == "git@github.com:myorg/myrepo.git"
    assert config.plugin_configs["source_links"]["branch"] == "staging"
    assert config.plugin_configs["source_links"]["docs_dir"] == "documentation"

    plugin = SourceLinksPlugin.from_config(config)
    assert plugin.repo_url == "https://github.com/myorg/myrepo"
    assert plugin.branch == "staging"
    assert plugin.docs_dir == "documentation"
    assert plugin.provider == "github"
