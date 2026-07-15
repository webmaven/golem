# golem/templates.py
from chameleon import PageTemplate
from golem.config import GolemConfig

DEFAULT_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>${title}</title>
    <style>
        :root {
            --golem-bg: #121214;
            --golem-fg: #e2e8f0;
            --golem-primary: #818cf8;
        }
        body {
            background-color: var(--golem-bg);
            color: var(--golem-fg);
            font-family: system-ui, sans-serif;
            display: flex;
            margin: 0;
        }
        #golem-sidebar {
            width: 250px;
            background: #1e1e24;
            padding: 20px;
            height: 100vh;
        }
        #golem-content {
            flex: 1;
            padding: 40px;
        }
        #golem-toc {
            width: 200px;
            padding: 20px;
        }
    </style>
</head>
<body>
    <aside id="golem-sidebar">
        <h3>Documentation</h3>
    </aside>
    <main id="golem-content">
        <h1>${title}</h1>
        <div tal:content="structure body_content" />
    </main>
    <aside id="golem-toc" class="golem-toc">
        <h4>On This Page</h4>
        <div tal:content="structure toc_html" />
    </aside>
</body>
</html>
"""

class PageCompiler:
    def __init__(self, config: GolemConfig):
        self.config = config
        self.template = PageTemplate(DEFAULT_TEMPLATE)

    def compile_page(self, title: str, body_content: str, toc_html: str) -> str:
        return self.template(
            title=title,
            body_content=body_content,
            toc_html=toc_html
        )
