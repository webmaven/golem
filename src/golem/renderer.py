import asciidoctrine
from asciidoctrine.nodes import Document, Section, Paragraph, Text, Node

class HtmlRenderer:
    def __init__(self):
        self.output = []

    def render(self, node) -> str:
        self.output = []
        self.visit(node)
        return "".join(self.output)

    def visit(self, node):
        if isinstance(node, dict):
            name = node.get("name", "")
        else:
            name = getattr(node, "name", node.__class__.__name__.lower())
        
        method_name = f"visit_{name.lower()}"
        visitor = getattr(self, method_name, self.generic_visit)
        visitor(node)

    def generic_visit(self, node):
        if isinstance(node, dict):
            for key in ["blocks", "inlines", "children"]:
                if key in node:
                    for child in node[key]:
                        self.visit(child)
        else:
            if hasattr(node, "get_child_collections"):
                for collection in node.get_child_collections().values():
                    for child in collection:
                        self.visit(child)
            elif hasattr(node, "children"):
                for child in node.children:
                    self.visit(child)

    def visit_document(self, node):
        if isinstance(node, dict):
            for child in node.get("blocks", []):
                self.visit(child)
        else:
            blocks = getattr(node, "blocks", []) or getattr(node, "children", [])
            for child in blocks:
                self.visit(child)

    def _get_plain_text(self, node) -> str:
        if not node:
            return ""
        if isinstance(node, list):
            return "".join(self._get_plain_text_single(item) for item in node)
        return self._get_plain_text_single(node)

    def _get_plain_text_single(self, node) -> str:
        if isinstance(node, dict):
            if node.get("name") == "text":
                return node.get("value", "")
            res = []
            for key in ["inlines", "children"]:
                if key in node:
                    for child in node[key]:
                        res.append(self._get_plain_text_single(child))
            return "".join(res)
        else:
            if hasattr(node, "value"):
                return str(node.value)
            res = []
            if hasattr(node, "get_child_collections"):
                for collection in node.get_child_collections().values():
                    for child in collection:
                        res.append(self._get_plain_text_single(child))
            elif hasattr(node, "children"):
                for child in node.children:
                    res.append(self._get_plain_text_single(child))
            return "".join(res)

    def visit_section(self, node):
        level = node.get("level", 1) if isinstance(node, dict) else getattr(node, "level", 1)
        if isinstance(node, dict):
            title_str = self._get_plain_text(node.get("title", []))
            children = node.get("blocks", [])
        else:
            title_str = self._get_plain_text(getattr(node, "title", ""))
            children = getattr(node, "blocks", []) or getattr(node, "children", [])
            
        anchor_id = title_str.lower().replace(" ", "-").replace("_", "-")
        self.output.append(f'<section id="{anchor_id}">\n')
        self.output.append(f'<h{level + 1}>{title_str}</h{level + 1}>\n')
        for child in children:
            if child != getattr(node, "title", None):
                self.visit(child)
        self.output.append("</section>\n")

    def visit_paragraph(self, node):
        self.output.append("<p>")
        if isinstance(node, dict):
            for child in node.get("inlines", []):
                self.visit(child)
        else:
            inlines = getattr(node, "inlines", []) or getattr(node, "children", [])
            for child in inlines:
                self.visit(child)
        self.output.append("</p>\n")

    def visit_text(self, node):
        val = node.get("value", "") if isinstance(node, dict) else getattr(node, "value", "")
        # Render formatting: inline bold/italic tags
        val = val.replace("*", "<strong>", 1).replace("*", "</strong>", 1)
        val = val.replace("_", "<em>", 1).replace("_", "</em>", 1)
        self.output.append(val)

    def visit_span(self, node):
        variant = node.get("variant", "") if isinstance(node, dict) else getattr(node, "variant", "")
        if variant == "strong":
            self.output.append("<strong>")
        elif variant == "emphasis":
            self.output.append("<em>")
        
        if isinstance(node, dict):
            for child in node.get("inlines", []):
                self.visit(child)
        else:
            inlines = getattr(node, "inlines", []) or getattr(node, "children", [])
            for child in inlines:
                self.visit(child)
                
        if variant == "strong":
            self.output.append("</strong>")
        elif variant == "emphasis":
            self.output.append("</em>")

    def visit_listing(self, node):
        if isinstance(node, dict):
            lang = node.get("attributes", {}).get("language", "text") or "text"
            code = "".join(child.get("value", "") if isinstance(child, dict) else getattr(child, "value", "") for child in node.get("inlines", []))
        else:
            attributes = getattr(node, "attributes", {})
            lang = attributes.get("language", "text") or "text"
            if not lang or lang == "text":
                lang = getattr(node, "language", "text") or "text"
            code = getattr(node, "code", "")
            if not code:
                inlines = getattr(node, "inlines", []) or getattr(node, "children", [])
                code = "".join(child.value if hasattr(child, "value") else "" for child in inlines)
        
        if code and not code.endswith("\n"):
            code += "\n"
            
        import html
        escaped_code = html.escape(code)
        self.output.append(f'<pre><code class="language-{lang}">{escaped_code}</code></pre>\n')

    def visit_list(self, node):
        variant = node.get("variant", "unordered") if isinstance(node, dict) else getattr(node, "variant", "unordered")
        tag = "ol" if variant == "ordered" else "ul"
        self.output.append(f"<{tag}>\n")
        
        items = node.get("items", []) if isinstance(node, dict) else getattr(node, "items", []) or getattr(node, "children", [])
        for item in items:
            self.visit(item)
        self.output.append(f"</{tag}>\n")

    def visit_listitem(self, node):
        self.output.append("<li>")
        checked = node.get("checked", None) if isinstance(node, dict) else getattr(node, "checked", None)
        if checked is not None:
            if checked:
                self.output.append('<input type="checkbox" checked disabled /> ')
            else:
                self.output.append('<input type="checkbox" disabled /> ')
                
        principal = node.get("principal", []) if isinstance(node, dict) else getattr(node, "principal", [])
        for p in principal:
            self.visit(p)
            
        blocks = node.get("blocks", []) if isinstance(node, dict) else getattr(node, "blocks", [])
        for b in blocks:
            self.visit(b)
            
        self.output.append("</li>\n")

    def visit_descriptionlist(self, node):
        self.output.append("<dl>\n")
        items = node.get("items", []) if isinstance(node, dict) else getattr(node, "items", [])
        for item in items:
            self.visit(item)
        self.output.append("</dl>\n")

    def visit_descriptionlistitem(self, node):
        terms = node.get("terms", []) if isinstance(node, dict) else getattr(node, "terms", [])
        for term in terms:
            self.visit(term)
        
        self.output.append("<dd>\n")
        blocks = node.get("blocks", []) if isinstance(node, dict) else getattr(node, "blocks", [])
        for block in blocks:
            self.visit(block)
        self.output.append("</dd>\n")

    def visit_descriptionlistterm(self, node):
        self.output.append("<dt>")
        inlines = node.get("inlines", []) if isinstance(node, dict) else getattr(node, "inlines", [])
        for inline in inlines:
            self.visit(inline)
        self.output.append("</dt>\n")

    def visit_admonition(self, node):
        variant = node.get("variant", "note") if isinstance(node, dict) else getattr(node, "variant", "note")
        variant_lower = variant.lower()
        self.output.append(f'<div class="admonition {variant_lower}">\n')
        self.output.append(f'<div class="admonition-title">{variant.upper()}</div>\n')
        
        blocks = node.get("blocks", []) if isinstance(node, dict) else getattr(node, "blocks", [])
        for block in blocks:
            self.visit(block)
        self.output.append("</div>\n")

    def visit_image(self, node):
        if isinstance(node, dict):
            target = node.get("target", "")
            alt = node.get("attributes", {}).get("alt", "")
        else:
            target = getattr(node, "target", "")
            alt = node.attributes.get("alt", "") if hasattr(node, "attributes") else ""
        self.output.append(f'<img src="{target}" alt="{alt}" />\n')

    def visit_table(self, node):
        self.output.append("<table>\n")
        rows = node.get("rows", []) if isinstance(node, dict) else getattr(node, "rows", []) or getattr(node, "children", [])
        for row in rows:
            self.visit(row)
        self.output.append("</table>\n")

    def visit_row(self, node):
        self.output.append("<tr>\n")
        cells = node.get("cells", []) if isinstance(node, dict) else getattr(node, "cells", []) or getattr(node, "children", [])
        for cell in cells:
            self.visit(cell)
        self.output.append("</tr>\n")

    def visit_cell(self, node):
        # Read colspan, rowspan, alignments
        attrs = []
        if isinstance(node, dict):
            colspan = node.get("colspan", 1)
            rowspan = node.get("rowspan", 1)
            align = node.get("align", None)
        else:
            colspan = getattr(node, "colspan", 1)
            rowspan = getattr(node, "rowspan", 1)
            align = getattr(node, "align", None)
            
        if colspan > 1:
            attrs.append(f'colspan="{colspan}"')
        if rowspan > 1:
            attrs.append(f'rowspan="{rowspan}"')
        if align:
            attrs.append(f'align="{align}"')
            
        attr_str = " " + " ".join(attrs) if attrs else ""
        self.output.append(f"<td{attr_str}>")
        
        blocks = node.get("blocks", []) if isinstance(node, dict) else getattr(node, "blocks", [])
        for block in blocks:
            self.visit(block)
            
        self.output.append("</td>\n")




def render_body(asg_root: Node) -> str:
    renderer = HtmlRenderer()
    return renderer.render(asg_root)
