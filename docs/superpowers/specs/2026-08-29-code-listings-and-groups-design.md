# Enhanced Code Listings, Semantic Groups, and Derived Multi-View Renderings Design

**Date:** 2026-08-29  
**Status:** Approved  
**Initial Implementation Target:** Phase 1 (Enhanced Single Listings & AsciiDoc Derived Renderings)

---

## 1. Overview & Problem Statement

Golem's current code listing implementation renders source blocks inside `<pre>` tags, overlaying the language label in the top-right corner using CSS pseudo-elements (`pre.highlight::before`). When code lines are long or wide, the code text scrolls directly beneath or overlaps the language badge, creating visual clutter and readability issues. Furthermore, there is no title bar for filenames or controls like clipboard copying, test badges, or expand/collapse toggles.

Additionally, technical documentation frequently requires presenting code in multiple forms:
1. **Manual Alternatives:** Parallel versions of a snippet in different programming languages, platforms, or styles (e.g. Python vs. Perl vs. Ruby, or synchronous vs. asynchronous).
2. **Derived Representations / Views:** Multi-stage compilation artifacts of a single source snippet (e.g., AsciiDoc Source $\to$ ASG JSON AST $\to$ HTML Source $\to$ Live Rendered DOM Preview).

This specification outlines a unified architecture for enhanced single listings, a general-purpose semantic `[group]` block for manual variants, and a pluggable derived views engine (`render="..."` / `views="..."`) for machine-generated multi-representation listings.

---

## 2. Component Architecture & UI Layout

### 2.1 Single Listing Header & Frame

Code listings are encapsulated in a semantic `<figure class="listingblock">` structure with a dedicated, non-overlapping `.listing-header` flex bar sitting above the code container:

```html
<figure class="listingblock">
  <header class="listing-header">
    <div class="listing-title">
      <span class="title-text">example.py</span>
    </div>
    <div class="listing-actions">
      <!-- Status & Role Badges -->
      <span class="badge badge-test" title="Executable Test Example">test</span>
      <span class="badge badge-shared" title="Named Context: server">shared: server</span>
      <span class="badge badge-lang">PYTHON</span>
      <!-- Progressive Enhancement Controls -->
      <button type="button" class="listing-copy-btn" aria-label="Copy code to clipboard" title="Copy code">
        <svg class="icon-copy" aria-hidden="true" width="16" height="16" viewBox="0 0 24 24">...</svg>
      </button>
    </div>
  </header>
  <div class="listing-content">
    <pre class="highlight"><code class="language-python">...</code></pre>
  </div>
</figure>
```

#### Layout Rules:
* `.listing-header` is fixed above `<pre>` and does not scroll horizontally with code text.
* Title / filename appears on the left; badges and action buttons align to the right.
* If a block has neither a title, badges, nor language label, the header collapses gracefully or renders minimal controls.
* Zero-JS baseline: Language badges and titles are fully static HTML/CSS. Copy buttons are enhanced via unobtrusive vanilla JS with fallback clipboard support.

---

### 2.2 Multi-View / Multi-Tab Switcher Component

When a listing represents multiple views or belongs to a group:
* **Interactive Tabs ($\le 4$ items):** Rendered as an accessible tab list (`role="tablist"`, `role="tab"`, `role="tabpanel"`).
* **Dropdown Selector ($> 4$ items or narrow viewports):** Rendered with a select switcher to prevent tab bar overflow.
* **No-JS Compatibility:** Accessible fallback utilizing semantic markup and CSS-based visibility states.
* **Clipboard Copy Scoping:** Copying from a tabbed container copies exclusively from the active tab panel's `<code>` text (with callout markers automatically stripped).

---

## 3. Authoring Semantics

### 3.1 Derived Multi-View Renderings (`render="..."` / `views="..."`)

For derived representations, authors do not manually duplicate output. Instead, an attribute on the `[source]` listing instructs Golem to compile and display the requested views:

```asciidoc
.Admonition Example
[source,asciidoc,render="source,asg,html,preview"]
----
NOTE: This is a callout note.
----
```

#### Supported Aliases:
To accommodate different mental models across domains, Golem treats the following block attributes as synonymous:
* `render="..."`
* `views="..."`
* `display="..."`
* `formats="..."`

#### Built-in AsciiDoc Derived View Identifiers:
* `source`: Syntax-highlighted AsciiDoc source input.
* `asg`: Syntax-highlighted JSON representation of the parsed AsciiDoc Syntax Graph (AST).
* `html`: Syntax-highlighted generated HTML source markup.
* `preview`: Live, styled HTML rendered inside an isolated preview container.

---

### 3.2 Semantic `[group]` Block (Manual Alternatives)

For parallel, author-written alternatives, authors use the generic `[group]` open block:

```asciidoc
[group]
====
.Python
[source,python]
----
print("Hello World")
----

.Perl
[source,perl]
----
print "Hello World\n";
----

.Ruby
[source,ruby]
----
puts "Hello World"
----
====
```

* **Semantics:** Declares that child blocks represent alternative representations or equivalent choices.
* **Tab Labels:** Inferred directly from standard AsciiDoc child block titles (`.Python`).

---

## 4. Doctest & State Isolation Invariants

When executable listings (`role="test"`, `role="shared"`) appear inside a `[group]`:
1. **Sandbox Sub-Contexts:** Parallel sibling blocks in a group are executed in isolated namespaces to prevent state collisions (e.g. Sync vs. Async client definitions).
2. **Explicit Named Contexts for Shared State:** A block inside a `[group]` cannot export shared state to the default document scope. If a grouped block specifies `role="shared"`, Golem requires an explicit named context attribute (`shared="context_name"`). Downstream blocks must explicitly opt into that context (`context="context_name"`).
3. **Derived Views Exemption:** Derived views (`asg`, `html`, `preview`) are non-executable representations generated at build time and do not execute independently in doctest runners.

---

## 5. Scope & Phased Roadmap

### Phase 1: Core Single Listing & AsciiDoc Derived Renderings (Immediate Implementation)
1. **Single Listing Header & Badges:**
   * Refactor listing HTML template and CSS in default skeleton.
   * Remove overlapping `pre::before` CSS rules.
   * Introduce `.listing-header` flex container with title, language badge, and test/shared badges.
   * Add lightweight vanilla JS for clipboard copy.
2. **AsciiDoc Derived View Processor:**
   * Implement view transform pipeline in Golem engine for `asciidoc` source blocks.
   * Support `source`, `asg`, `html`, and `preview` view generation.
   * Render multi-view tabbed listing container with accessible switching.

### Phase 2: Generalized `[group]` Block & Extensible Registry (Future Extension)
* Generic `[group]` AST node parser in `asciidoctrine` / Golem engine.
* Pluggable Transform Registry for other languages (Graphviz DOT $\to$ SVG/Preview, Python $\to$ AST/Output).
* Doctest runner isolation for grouped blocks with named context enforcement.

---

## 6. Verification & Test Plan

1. **Unit & Integration Tests:**
   * Verify HTML structure of single listing templates contains `.listing-header` and `.listing-content`.
   * Verify derived views compilation (`render="source,asg,html,preview"`) produces expected tab panels and syntax-highlighted code.
   * Verify error handling when an unsupported view is specified.
2. **Visual & Rendering Audit:**
   * Check wide/long code lines for zero badge overlap.
   * Verify tab switching interaction and copy button functionality across light and dark themes.
