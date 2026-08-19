# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0a1] - 2026-08-18

### Added
- **Incremental DAG Build Engine**: Dependency tracking with SHA-256 content hashing in `.golem/cache.json`, rebuilding only modified files and their inclusion dependents.
- **AsciiDoc Native Pipeline**: Integration with `asciidoctrine` (Lark AST parser/ASG resolver) and `asciidoctype` (Chameleon ZPT templates) supporting 39 standard node types.
- **Hierarchical Navigation Auto-Discovery**: Automatic sidebar tree generation with numeric prefix stripping (`01-intro.adoc` $\to$ `Intro`), homepage pinning, and explicit `golem.toml` overrides.
- **Multi-Threaded Live Dev Server**: Zero-dependency `ThreadingHTTPServer` with Server-Sent Events (SSE) live browser reload under `/golem-reload` and interactive compiler error overlays.
- **Pluggy Plugin Architecture**: Lifecycle hooks for `on_pre_parse`, `on_ast_created`, `on_asg_created`, `on_post_render`, and `golem_add_subcommands`.
- **CLI Inspection Commands**: `golem plugins` and `golem themes` commands to discover, inspect, and list active and installed extensions.
- **Doctest Integration**: Executable Python code example verification in listing blocks using `asciidoctest`.
- **Fired Clay / Workbench Default Theme**:
  - Handcrafted warm paper / workbench aesthetic with automatic `prefers-color-scheme: dark` mode.
  - Complete typography system built on Google Fonts **Source** family (`Source Serif 4` for display/body, `Source Sans 3` for UI chrome, `Source Code Pro` for monospaced code blocks).
  - Sub-perceptible SVG `feTurbulence` paper-grain texture data URIs.
  - Distinct earth-tone admonition palette (`NOTE`, `TIP`, `IMPORTANT`, `WARNING`, `CAUTION`).
- **Comprehensive Documentation Suite**: Complete user manual (`docs/user_manual.adoc`), developer guide (`docs/developer_guide.adoc`), and technical specification (`SPECIFICATION.adoc`).

### Fixed
- **TOC Scroll Anchors & Description Lists**: Fixed table-of-contents slug anchors and description list node rendering.
- **Navigation Pruning**: Pruned empty non-AsciiDoc directories and defaulted plugin lists cleanly to avoid empty navigation nodes.
