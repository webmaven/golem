import pytest
import requests
import threading
import time
from golem.server import DevServer
from golem.config import GolemConfig

def test_dev_server_hosting(tmp_path):
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    index_file = dist_dir / "index.html"
    index_file.write_text("Hello from server")
    
    config = GolemConfig(output_dir=str(dist_dir))
    server = DevServer(config, port=19283)
    
    # Run in a daemon thread
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    
    # Wait for server startup
    time.sleep(0.5)
    
    # Request the root file
    resp = requests.get("http://127.0.0.1:19283/")
    assert resp.status_code == 200
    assert "Hello from server" in resp.text
