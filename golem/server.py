import http.server
import socketserver
from pathlib import Path
from golem.config import GolemConfig

class DevServer:
    def __init__(self, config: GolemConfig, port: int = 8000):
        self.config = config
        self.dist_dir = Path(config.output_dir)
        self.port = port

    def run(self):
        dist_abs = str(self.dist_dir.resolve())
        
        class CustomHTTPHandler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=dist_abs, **kwargs)

        # Allow immediate reuse of address port
        socketserver.TCPServer.allow_reuse_address = True
        with socketserver.TCPServer(("", self.port), CustomHTTPHandler) as httpd:
            httpd.serve_forever()
