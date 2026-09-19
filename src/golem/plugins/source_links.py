"""Provide canonical GitHub and GitLab source link generation for Golem documentation pages.

Enriches Chameleon template context with canonical repository, file view, and edit URLs
for AsciiDoc pages, with support for GitHub, GitLab, and custom git providers.
"""

from __future__ import annotations

import logging
import re
import subprocess
import urllib.parse
from pathlib import Path
from typing import Any

from golem.model import PageContext, SourceLinksContext
from golem.plugins import GolemPlugin, hookimpl

__all__ = [
    "SourceLinksPlugin",
    "detect_branch",
    "detect_provider",
    "detect_repo_url",
    "normalize_repo_url",
]

logger = logging.getLogger(__name__)


def normalize_repo_url(url: str) -> str:
    """Normalize a git remote URL into a canonical HTTPS web browsing URL.

    Strips trailing `.git` extensions, resolves SCP-like SSH shorthand (`git@host:org/repo`),
    normalizes `ssh://` URLs, and removes trailing slashes.

    [parameters]
    `url` (str):: Raw git repository or remote URL.

    [returns]
    `str`:: Normalized HTTPS repository root URL.
    """
    if not url:
        return ""
    clean = url.strip()

    # Handle SCP-style: git@host:owner/repo(.git)
    scp_match = re.match(r"^git@([^:]+):(.*)$", clean)
    if scp_match:
        host, path = scp_match.group(1), scp_match.group(2)
        clean = f"https://{host}/{path}"
    elif clean.startswith("ssh://"):
        # Handle ssh://[user@]host[:port]/path(.git)
        ssh_match = re.match(r"^ssh://(?:[^@]+@)?([^:/]+)(?::\d+)?/(.*)$", clean)
        if ssh_match:
            host, path = ssh_match.group(1), ssh_match.group(2)
            clean = f"https://{host}/{path}"
    elif clean.startswith("git://"):
        clean = "https://" + clean[6:]

    if clean.endswith(".git"):
        clean = clean[:-4]

    return clean.rstrip("/")


def detect_provider(repo_url: str) -> str:
    """Determine the git hosting provider from a repository URL.

    Inspects the hostname to distinguish between GitHub, GitLab, or custom git services.

    [parameters]
    `repo_url` (str):: Normalized repository URL.

    [returns]
    `str`:: Hosting provider identifier: `"github"`, `"gitlab"`, or `"custom"`.
    """
    parsed = urllib.parse.urlparse(repo_url)
    host = (parsed.netloc or "").lower()
    if "github" in host:
        return "github"
    if "gitlab" in host:
        return "gitlab"
    return "custom"


def _run_git_cmd(args: list[str], cwd: Path | None = None) -> str | None:
    """Execute a git CLI subcommand and return stripped stdout or None on failure."""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
        if proc.returncode == 0:
            out = proc.stdout.strip()
            return out if out else None
    except Exception:
        pass
    return None


def _find_git_dir(start_dir: Path | None = None) -> Path | None:
    """Locate the .git directory by traversing upwards from start_dir."""
    current = (start_dir or Path.cwd()).resolve()
    for directory in [current, *current.parents]:
        candidate = directory / ".git"
        if candidate.exists():
            if candidate.is_file():
                # Git worktree or submodule pointer
                try:
                    content = candidate.read_text(encoding="utf-8").strip()
                    if content.startswith("gitdir:"):
                        ptr_path = Path(content[7:].strip())
                        if not ptr_path.is_absolute():
                            ptr_path = (directory / ptr_path).resolve()
                        if ptr_path.exists():
                            return ptr_path
                except Exception:
                    pass
            elif candidate.is_dir():
                return candidate
    return None


def detect_repo_url(root_dir: Path | None = None) -> str | None:
    """Auto-detect the remote origin repository URL from git configuration.

    Attempts to invoke `git config --get remote.origin.url`, falling back to parsing
    the local `.git/config` file directly.

    [parameters]
    `root_dir` (Path | None, optional):: Repository root directory to inspect.

    [returns]
    `str | None`:: Raw remote URL if discovered, or None.
    """
    # 1. Try git CLI
    url = _run_git_cmd(["config", "--get", "remote.origin.url"], cwd=root_dir)
    if url:
        return url

    # 2. Direct .git/config fallback
    git_dir = _find_git_dir(root_dir)
    if git_dir:
        config_file = git_dir / "config"
        if config_file.exists():
            try:
                content = config_file.read_text(encoding="utf-8", errors="replace")
                match = re.search(r'\[remote\s+"origin"\][^\[]*?url\s*=\s*([^\r\n]+)', content)
                if match:
                    return match.group(1).strip()
            except Exception:
                pass
    return None


def detect_branch(root_dir: Path | None = None) -> str:
    """Auto-detect current or default branch name from local git metadata.

    Attempts `git symbolic-ref --short HEAD` or `git rev-parse --abbrev-ref HEAD`,
    falling back to `.git/HEAD` inspection and finally defaulting to `'main'`.

    [parameters]
    `root_dir` (Path | None, optional):: Repository root directory to inspect.

    [returns]
    `str`:: Detected branch name, or `'main'`.
    """
    # 1. Try git CLI symbolic-ref
    branch = _run_git_cmd(["symbolic-ref", "--short", "HEAD"], cwd=root_dir)
    if branch and branch != "HEAD":
        return branch

    # 2. Try git CLI rev-parse
    branch = _run_git_cmd(["rev-parse", "--abbrev-ref", "HEAD"], cwd=root_dir)
    if branch and branch != "HEAD":
        return branch

    # 3. Direct .git/HEAD fallback
    git_dir = _find_git_dir(root_dir)
    if git_dir:
        head_file = git_dir / "HEAD"
        if head_file.exists():
            try:
                content = head_file.read_text(encoding="utf-8", errors="replace").strip()
                if content.startswith("ref: refs/heads/"):
                    return content[len("ref: refs/heads/") :].strip()
            except Exception:
                pass

    return "main"


def _resolve_relative_doc_path(
    doc_path: Path,
    docs_dir: str | None = None,
    root_dir: Path | None = None,
    current_path: str | None = None,
) -> str:
    """Resolve the canonical repository-relative path for a documentation file.

    [parameters]
    `doc_path` (Path):: Path to the documentation source file.
    `docs_dir` (str | None, optional):: Root documentation directory name within the repository.
    `root_dir` (Path | None, optional):: Repository root directory.
    `current_path` (str | None, optional):: Relative path already resolved in template context.

    [returns]
    `str`:: Normalized POSIX path relative to repository root.
    """
    if doc_path.is_absolute() and root_dir:
        try:
            return doc_path.resolve().relative_to(root_dir.resolve()).as_posix()
        except ValueError:
            pass

    rel_str = (current_path or (doc_path.name if doc_path.is_absolute() else doc_path.as_posix())).lstrip("/")

    clean_docs_dir = docs_dir.strip("/") if docs_dir else None
    if clean_docs_dir:
        parts = rel_str.split("/", 1)
        if parts[0] == clean_docs_dir:
            return rel_str
        return f"{clean_docs_dir}/{rel_str}"
    return rel_str


class SourceLinksPlugin(GolemPlugin):
    """Golem plugin providing canonical repository view and edit links in page template contexts.

    Injects `source_repo_url`, `source_edit_url`, `source_view_url`, `source_url`, and `source_provider`
    into the Chameleon template context for each rendered document.

    [parameters]
    `repo_url` (str | None, optional):: Canonical repository web URL. Auto-detected from git remote if None.
    `branch` (str | None, optional):: Git branch name to link against. Auto-detected if None.
    `docs_dir` (str | None, optional):: Path prefix for documentation files inside the repository.
    `provider` (str | None, optional):: Git provider (`"github"`, `"gitlab"`, or `"custom"`).
    `edit_url_template` (str | None, optional):: Custom format string for edit links.
    `view_url_template` (str | None, optional):: Custom format string for view links.
    `root_dir` (Path | None, optional):: Base directory used for local git repository discovery.
    """

    name = "source_links"

    def __init__(
        self,
        repo_url: str | None = None,
        branch: str | None = None,
        docs_dir: str | None = None,
        provider: str | None = None,
        edit_url_template: str | None = None,
        view_url_template: str | None = None,
        root_dir: Path | None = None,
        **extra: Any,
    ) -> None:
        super().__init__(
            repo_url=repo_url,
            branch=branch,
            docs_dir=docs_dir,
            provider=provider,
            edit_url_template=edit_url_template,
            view_url_template=view_url_template,
            **extra,
        )
        self.root_dir = root_dir.resolve() if root_dir else Path.cwd().resolve()

        # 1. Resolve repo_url
        if repo_url:
            self.repo_url: str | None = normalize_repo_url(repo_url)
        else:
            detected = detect_repo_url(self.root_dir)
            self.repo_url = normalize_repo_url(detected) if detected else None

        # 2. Resolve branch
        if branch:
            self.branch = branch
        else:
            self.branch = detect_branch(self.root_dir)

        # 3. Resolve provider
        if provider:
            self.provider = provider
        elif self.repo_url:
            self.provider = detect_provider(self.repo_url)
        else:
            self.provider = "github"

        # 4. Resolve docs_dir
        self.docs_dir = docs_dir.strip("/") if docs_dir else None

        # 5. Templates
        self.edit_url_template = edit_url_template
        self.view_url_template = view_url_template

    @classmethod
    def from_config(cls, config: Any = None) -> SourceLinksPlugin:
        """Construct a SourceLinksPlugin instance from GolemConfig or a configuration dictionary.

        [parameters]
        `config` (Any, optional):: GolemConfig instance or dictionary of site/plugin options.

        [returns]
        `SourceLinksPlugin`:: Configured plugin instance.
        """
        if config is None:
            return cls()

        plugin_configs = getattr(config, "plugin_configs", {}) or {}
        source_links_cfg = plugin_configs.get("source_links", {}) if isinstance(plugin_configs, dict) else {}

        if isinstance(config, dict):
            source_links_cfg = config.get("source_links", config)

        if not isinstance(source_links_cfg, dict):
            source_links_cfg = {}

        repo_url = source_links_cfg.get("repo_url")
        branch = source_links_cfg.get("branch")
        docs_dir = source_links_cfg.get("docs_dir") or getattr(config, "content_dir", None)
        provider = source_links_cfg.get("provider")
        edit_url_template = source_links_cfg.get("edit_url_template")
        view_url_template = source_links_cfg.get("view_url_template")

        root_dir = None
        if hasattr(config, "config_path") and config.config_path:
            root_dir = Path(config.config_path).parent
        elif hasattr(config, "content_dir") and config.content_dir:
            root_dir = Path(config.content_dir).parent

        return cls(
            repo_url=repo_url,
            branch=branch,
            docs_dir=docs_dir,
            provider=provider,
            edit_url_template=edit_url_template,
            view_url_template=view_url_template,
            root_dir=root_dir,
        )

    def _format_url(self, template: str | None, default_pattern: str, file_path: str) -> str:
        """Format an edit or view URL using custom template or default pattern."""
        repo_url = self.repo_url or ""
        branch = self.branch
        if template:
            try:
                return template.format(
                    repo_url=repo_url,
                    branch=branch,
                    doc_path=file_path,
                    path=file_path,
                )
            except Exception as e:
                logger.warning("Failed to format source link template %r: %s", template, e)
        return default_pattern.format(
            repo_url=repo_url,
            branch=branch,
            doc_path=file_path,
            path=file_path,
        )

    @hookimpl
    def on_template_context(self, context: PageContext, doc_path: Path) -> PageContext:
        """Inject repository, file edit, and file view URLs into template context.

        [parameters]
        `context` (PageContext):: Chameleon template context dictionary.
        `doc_path` (Path):: Path to the documentation source file being processed.

        [returns]
        `PageContext`:: Enriched template context containing source URL keys.
        """
        if not self.repo_url:
            return context

        current_path = context.get("current_path") if isinstance(context.get("current_path"), str) else None
        file_path = _resolve_relative_doc_path(
            doc_path=doc_path,
            docs_dir=self.docs_dir,
            root_dir=self.root_dir,
            current_path=current_path,
        )

        if self.provider == "gitlab":
            default_edit = "{repo_url}/-/edit/{branch}/{doc_path}"
            default_view = "{repo_url}/-/blob/{branch}/{doc_path}"
        else:
            default_edit = "{repo_url}/edit/{branch}/{doc_path}"
            default_view = "{repo_url}/blob/{branch}/{doc_path}"

        edit_url = self._format_url(self.edit_url_template, default_edit, file_path)
        view_url = self._format_url(self.view_url_template, default_view, file_path)

        injected: SourceLinksContext = {
            "source_repo_url": self.repo_url,
            "source_edit_url": edit_url,
            "source_view_url": view_url,
            "source_url": view_url,
            "source_provider": self.provider,
        }
        context.update(injected)
        return context
