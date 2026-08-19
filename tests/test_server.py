import requests
import threading
import time
import socket
from golem.server import LiveReloadServer


def get_free_port():
    """Helper to locate a free port on localhost."""
    s = socket.socket()
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_dev_server_hosting(tmp_path):
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    index_file = dist_dir / "index.html"
    index_file.write_text("Hello from server")

    port = get_free_port()
    server = LiveReloadServer(
        public_dir=dist_dir,
        watch_dir=tmp_path / "content",
        change_detected_func=lambda: False,
        rebuild_func=lambda: None,
        port=port,
    )

    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    time.sleep(0.5)

    try:
        resp = requests.get(f"http://127.0.0.1:{port}/")
        assert resp.status_code == 200
        assert "Hello from server" in resp.text
    finally:
        server.shutdown()
        t.join(timeout=2)


def test_dev_server_html_injection(tmp_path):
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    index_file = dist_dir / "index.html"
    index_file.write_text("<html><head><title>Test</title></head><body>Hello</body></html>")

    port = get_free_port()
    server = LiveReloadServer(
        public_dir=dist_dir,
        watch_dir=tmp_path / "content",
        change_detected_func=lambda: False,
        rebuild_func=lambda: None,
        port=port,
    )

    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    time.sleep(0.5)

    try:
        resp = requests.get(f"http://127.0.0.1:{port}/index.html")
        assert resp.status_code == 200
        assert "</head>" in resp.text
        assert "<!-- Golem SSE Hot Reloader -->" in resp.text
        assert "new EventSource('/golem-reload')" in resp.text
    finally:
        server.shutdown()
        t.join(timeout=2)


def test_dev_server_sse_live_reload(tmp_path):
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()

    port = get_free_port()
    rebuild_called = threading.Event()

    # We want a change detected once to trigger rebuild after client connects
    trigger_change = True

    def mock_change_detected():
        nonlocal trigger_change
        if trigger_change and len(server.reload_queues) > 0:
            trigger_change = False
            return True
        return False

    def mock_rebuild():
        rebuild_called.set()

    server = LiveReloadServer(
        public_dir=dist_dir,
        watch_dir=tmp_path / "content",
        change_detected_func=mock_change_detected,
        rebuild_func=mock_rebuild,
        port=port,
    )

    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    time.sleep(0.5)

    try:
        # Establish an EventSource subscription in a background thread
        sse_events = []

        def sse_client():
            try:
                # stream=True keeps the chunked event stream open
                with requests.get(f"http://127.0.0.1:{port}/golem-reload", stream=True, timeout=5) as r:
                    line = r.raw.readline()
                    if line:
                        sse_events.append(line.decode("utf-8"))
            except Exception as e:
                print("Client thread error:", e)

        client_thread = threading.Thread(target=sse_client, daemon=True)
        client_thread.start()
        time.sleep(0.5)

        # Verify the file watcher triggered rebuild and queued a reload event
        assert rebuild_called.wait(timeout=3)

        # Join the client thread to allow it to collect the events
        client_thread.join(timeout=3)

        # We expect a "data: reload" or standard chunked response in the SSE logs
        assert any("reload" in ev for ev in sse_events)
    finally:
        server.shutdown()
        t.join(timeout=2)


def test_dev_server_error_overlay_injection(tmp_path):
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    index_file = dist_dir / "index.html"
    index_file.write_text("<html><head><title>Test</title></head><body>Hello</body></html>")

    port = get_free_port()
    server = LiveReloadServer(
        public_dir=dist_dir,
        watch_dir=tmp_path / "content",
        change_detected_func=lambda: False,
        rebuild_func=lambda: None,
        port=port,
        errors_func=lambda: [
            {
                "file": "docs/bad.adoc",
                "message": "Syntax error: Unclosed attribute",
            }
        ],
    )

    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    time.sleep(0.5)

    try:
        resp = requests.get(f"http://127.0.0.1:{port}/index.html")
        assert resp.status_code == 200
        assert 'id="golem-error-overlay"' in resp.text
        assert "Syntax error: Unclosed attribute" in resp.text
        assert "docs/bad.adoc" in resp.text
    finally:
        server.shutdown()
        t.join(timeout=2)
