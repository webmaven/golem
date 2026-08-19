# Golem (`golem-docs`)

[![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://www.python.org/downloads/)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Release: Alpha MVP](https://img.shields.io/badge/release-v0.1.0a1-green.svg)](https://github.com/webmaven/golem)

Golem is an extensible, Python-native static site generator (SSG) built from the ground up for technical, interactive documentation using **AsciiDoc** as its primary source format.

---

## Key Features

- **AsciiDoc Ecosystem Native:** Powered by `asciidoctrine` for standard-compliant parsing and `asciidoctype` for Chameleon ZPT template rendering supporting 39 standard node types (admonitions, callouts, stem math, tables, footnotes, description lists).
- **Intelligent Navigation Auto-Discovery:** Discovers documentation hierarchies, strips numeric sorting prefixes (`01-intro.adoc` $\to$ `Intro`), pins overview root pages, and supports explicit TOML overrides.
- **Incremental DAG Build Engine:** Tracks file inclusion trees and SHA-256 hashes in `.golem/cache.json`, rebuilding only modified files and their dependents.
- **Modern Dev Server with Live Reloading:** Zero-dependency multi-threaded dev server with Server-Sent Events (SSE) live browser reloading and non-crashing interactive error overlays.
- **Compiler-Grade Diagnostics:** Pinpoint file coordinates, line numbers, contextual source snippets, and caret pointers for AsciiDoc syntax errors.
- **Pluggy Plugin Architecture:** Hooks into pre-parse, AST creation, ASG resolution, and post-render lifecycle stages.
- **Doctest & API Integration:** Verifies Python listing blocks directly using `asciidoctest` and extracts docstrings with `asciidocstring`.

---

## Quick Start

### 1. Installation

```bash
# In your virtual environment (Python >= 3.14)
pip install golem-docs
```

Or install locally for development:

```bash
git clone https://github.com/webmaven/golem.git
cd golem
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 2. Initialize a Project

```bash
golem init my-docs
cd my-docs
```

This creates a standard project layout:
```text
my-docs/
├── golem.toml          # Site & build configuration
└── content/            # AsciiDoc source files
    └── index.adoc      # Homepage entry point
```

### 3. Build & Serve

```bash
# Incremental build
golem build

# Strict mode for CI/CD pipelines
golem build --strict

# Launch live dev server with SSE hot-reloading
golem serve --port 8000
```

---

## Configuration (`golem.toml` / `pyproject.toml`)

Golem supports configuration via `golem.toml` or directly inside `pyproject.toml` under `[tool.golem]`:

```toml
[site]
title = "Golem Documentation"
author = "Michael Bernstein"
site_url = "https://webmaven.github.io/golem/"

[build]
content_dir = "content"
output_dir = "dist"
theme = "default"
strict = false

[navigation]
# Optional explicit sidebar order override (defaults to auto-discovery)
nav = [
    "index.adoc",
    "getting-started.adoc",
    "architecture.adoc",
    "reference/api.adoc",
]
```

---

## CLI Reference

| Command | Options | Description |
|---|---|---|
| `golem init` | `[--template=<type>] [-C <dir>]` | Initialize documentation scaffold (`site`, `package`, `book`). |
| `golem new` | `<type> <name> [-C <dir>]` | Generate a new `.adoc` document skeleton. |
| `golem build` | `[--clean] [--strict] [-v] [-C <dir>]` | Run DAG compiler to render HTML pages into output directory. |
| `golem serve` | `[--port=<port>] [--host=<host>] [--strict] [-C <dir>]` | Run live-reload HTTP server watching source directories. |
| `golem doctest` | `[--mode=<mode>] [-C <dir>]` | Extract and verify executable code examples with pytest. |

---

## License

Licensed under the [Apache License, Version 2.0](LICENSE).
