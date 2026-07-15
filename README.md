# Golem (`golem-pub`)

Golem is an extensible, Python-native static site generator (SSG) built from the ground up for highly technical, interactive documentation using **AsciiDoc** as its primary source format.

## Core Features
*   **AsciiDoc-First:** Based on the standard-compliant `asciidoctrine` parser.
*   **Deep Extensibility:** Extensible via plugins manipulating the Abstract Semantic Graph (ASG).
*   **Integrated API Documentation:** Automatic docstring cleaning and extraction via `asciidocstring` and `pdoc`.
*   **Testable Documentation:** Integration with `asciidoctest` / `pytest` to guarantee all technical code examples remain valid.
*   **Semantic Skeleton Themes:** Modular HTML skeletons styled with modern, accessible, vanilla CSS.

## Getting Started

### Installation & Setup
To set up a local development environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```
