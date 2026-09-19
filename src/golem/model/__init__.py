"""golem.model — public API for typed ASG traversal.

Re-exports asciidoctrine's visitor/transformer infrastructure under
Golem-stable names so plugins can subclass without importing asciidoctrine
internals directly.
"""

from asciidoctrine.nodes import (
    Node,
    NodeTransformer as AsgTransformer,
    NodeVisitor as AsgVisitor,
)

__all__ = ["Node", "AsgVisitor", "AsgTransformer"]
