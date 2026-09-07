import socket
import threading
import time
from pathlib import Path

import pytest
import requests
from golem.diagnostics import Diagnostic
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
        resp = requests.get(f"http://127.0.0.1:{server.port}/")
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
        resp = requests.get(f"http://127.0.0.1:{server.port}/index.html")
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
                with requests.get(f"http://127.0.0.1:{server.port}/golem-reload", stream=True, timeout=5) as r:
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
            Diagnostic(
                file="docs/bad.adoc",
                message="Syntax error: Unclosed attribute",
            )
        ],
    )

    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    time.sleep(0.5)

    try:
        resp = requests.get(f"http://127.0.0.1:{server.port}/index.html")
        assert resp.status_code == 200
        assert 'id="golem-error-overlay"' in resp.text
        assert "Syntax error: Unclosed attribute" in resp.text
        assert "docs/bad.adoc" in resp.text
    finally:
        server.shutdown()
        t.join(timeout=2)


def test_dev_server_client_disconnect_handling(tmp_path, capsys):
    """Verify that abrupt client socket resets are handled cleanly without stderr tracebacks."""
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    index_file = dist_dir / "index.html"
    index_file.write_text("<html><body>Test</body></html>")

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
        # Connect and immediately close with TCP RST
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(("127.0.0.1", server.port))
        # SO_LINGER with timeout 0 sends RST on close
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, b"\x01\x00\x00\x00\x00\x00\x00\x00")
        s.close()
        time.sleep(0.2)

        # Standard GET should still succeed cleanly
        resp = requests.get(f"http://127.0.0.1:{server.port}/index.html")
        assert resp.status_code == 200

        # Confirm no socketserver traceback leaked to stderr
        captured = capsys.readouterr()
        assert "Traceback" not in captured.err
        assert "ConnectionResetError" not in captured.err
    finally:
        server.shutdown()
        t.join(timeout=2)


def test_dev_server_port_collision_fallback(tmp_path):
    """Verify that LiveReloadServer falls back to port + 1 upon address collision."""
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    index_file = dist_dir / "index.html"
    index_file.write_text("Fallback port test")

    initial_port = get_free_port()
    # Occupy initial_port with a listening socket
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    blocker.bind(("", initial_port))
    blocker.listen(1)

    server = LiveReloadServer(
        public_dir=dist_dir,
        watch_dir=tmp_path / "content",
        change_detected_func=lambda: False,
        rebuild_func=lambda: None,
        port=initial_port,
        max_port_retries=25,
    )

    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    time.sleep(0.5)

    try:
        assert server.port > initial_port
        assert server.port <= initial_port + 25
        resp = requests.get(f"http://127.0.0.1:{server.port}/index.html")
        assert resp.status_code == 200
        assert "Fallback port test" in resp.text
    finally:
        server.shutdown()
        t.join(timeout=2)
        blocker.close()


def test_dev_server_port_collision_exhaustion(tmp_path):
    """Verify that LiveReloadServer raises OSError when port retries are exhausted."""
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()

    initial_port = get_free_port()
    b1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    b1.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    b1.bind(("", initial_port))
    b1.listen(1)

    b2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    b2.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    b2.bind(("", initial_port + 1))
    b2.listen(1)

    try:
        server = LiveReloadServer(
            public_dir=dist_dir,
            watch_dir=tmp_path / "content",
            change_detected_func=lambda: False,
            rebuild_func=lambda: None,
            port=initial_port,
            max_port_retries=1,
        )
        with pytest.raises(OSError):
            server.bind()
    finally:
        b1.close()
        b2.close()


def test_dev_server_watch_directories_attribute(tmp_path):
    """Verify watch_directories configuration and property exposure."""
    content_dir = tmp_path / "content"
    templates_dir = tmp_path / "templates"
    themes_dir = tmp_path / "themes"

    # Default watch directories
    s_default = LiveReloadServer(public_dir=tmp_path / "dist")
    assert s_default.watch_directories == [Path("docs"), Path("templates"), Path("themes")]
    assert s_default.watch_dir == Path("docs")

    # Single watch_dir specified
    s_dir = LiveReloadServer(public_dir=tmp_path / "dist", watch_dir=content_dir)
    assert s_dir.watch_directories == [content_dir]
    assert s_dir.watch_dir == content_dir

    # Explicit watch_directories specified
    s_custom = LiveReloadServer(
        public_dir=tmp_path / "dist",
        watch_directories=[content_dir, templates_dir, themes_dir],
    )
    assert s_custom.watch_directories == [content_dir, templates_dir, themes_dir]
    assert s_custom.watch_dir == content_dir


def test_dev_server_adaptive_polling_change_detection(tmp_path):
    """Verify adaptive polling triggers rebuild and live reload notification."""
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    (dist_dir / "index.html").write_text("<html><body>Hello</body></html>")

    port = get_free_port()
    rebuild_event = threading.Event()
    change_counter = 0

    def mock_change():
        nonlocal change_counter
        if change_counter == 1:
            change_counter += 1
            return True
        return False

    server = LiveReloadServer(
        public_dir=dist_dir,
        watch_dir=tmp_path / "content",
        change_detected_func=mock_change,
        rebuild_func=lambda: rebuild_event.set(),
        port=port,
        watcher_backend="polling",
    )

    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    time.sleep(0.3)

    try:
        change_counter = 1
        assert rebuild_event.wait(timeout=1.5)
    finally:
        server.shutdown()
        t.join(timeout=2)


def test_dev_server_directory_mtime_fallback(tmp_path):
    """Verify directory mtime fallback triggers rebuild when change_detected_func is None."""
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    (dist_dir / "index.html").write_text("<html><body>Hello</body></html>")
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    doc = content_dir / "page.adoc"
    doc.write_text("Initial")

    port = get_free_port()
    rebuild_event = threading.Event()

    server = LiveReloadServer(
        public_dir=dist_dir,
        watch_directories=[content_dir],
        rebuild_func=lambda: rebuild_event.set(),
        port=port,
        watcher_backend="polling",
        debounce_interval=0.01,
    )

    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    time.sleep(0.3)

    try:
        time.sleep(0.05)
        doc.write_text("Modified content")
        assert rebuild_event.wait(timeout=2.0)
    finally:
        server.shutdown()
        t.join(timeout=2)


def test_dev_server_event_driven_watchfiles(tmp_path, monkeypatch):
    """Verify event-driven file monitoring using watchfiles with sub-100ms latency."""
    import sys
    import types

    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    (dist_dir / "index.html").write_text("<html><body>Hello</body></html>")
    content_dir = tmp_path / "content"
    content_dir.mkdir()

    rebuild_event = threading.Event()
    trigger_watch = threading.Event()

    def mock_watch(*paths, stop_event=None, debounce=50, step=20):
        while stop_event is not None and not stop_event.is_set():
            if trigger_watch.wait(timeout=0.02):
                trigger_watch.clear()
                yield {(1, str(content_dir / "file.adoc"))}

    fake_watchfiles = types.ModuleType("watchfiles")
    fake_watchfiles.watch = mock_watch
    monkeypatch.setitem(sys.modules, "watchfiles", fake_watchfiles)

    port = get_free_port()
    server = LiveReloadServer(
        public_dir=dist_dir,
        watch_directories=[content_dir],
        rebuild_func=lambda: rebuild_event.set(),
        port=port,
        watcher_backend="watchfiles",
        debounce_interval=0.01,
    )

    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    time.sleep(0.3)

    try:
        t0 = time.perf_counter()
        trigger_watch.set()
        assert rebuild_event.wait(timeout=1.0)
        elapsed = time.perf_counter() - t0
        assert elapsed < 0.1
    finally:
        server.shutdown()
        t.join(timeout=2)


def test_dev_server_event_driven_watchdog(tmp_path, monkeypatch):
    """Verify event-driven file monitoring using watchdog with sub-100ms latency."""
    import sys
    import types

    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    (dist_dir / "index.html").write_text("<html><body>Hello</body></html>")
    content_dir = tmp_path / "content"
    content_dir.mkdir()

    rebuild_event = threading.Event()
    scheduled_handlers = []

    class MockHandler:
        def on_any_event(self, event):
            pass

    class MockObserver:
        def schedule(self, handler, path, recursive=True):
            scheduled_handlers.append(handler)

        def start(self):
            pass

        def stop(self):
            pass

        def join(self, timeout=None):
            pass

    fake_watchdog = types.ModuleType("watchdog")
    fake_events = types.ModuleType("watchdog.events")
    fake_observers = types.ModuleType("watchdog.observers")
    fake_events.FileSystemEventHandler = MockHandler
    fake_observers.Observer = MockObserver

    monkeypatch.setitem(sys.modules, "watchdog", fake_watchdog)
    monkeypatch.setitem(sys.modules, "watchdog.events", fake_events)
    monkeypatch.setitem(sys.modules, "watchdog.observers", fake_observers)

    port = get_free_port()
    server = LiveReloadServer(
        public_dir=dist_dir,
        watch_directories=[content_dir],
        rebuild_func=lambda: rebuild_event.set(),
        port=port,
        watcher_backend="watchdog",
        debounce_interval=0.01,
    )

    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    time.sleep(0.3)

    try:
        assert len(scheduled_handlers) > 0
        handler = scheduled_handlers[0]

        class FakeEvent:
            is_directory = False

        t0 = time.perf_counter()
        handler.on_any_event(FakeEvent())
        assert rebuild_event.wait(timeout=1.0)
        elapsed = time.perf_counter() - t0
        assert elapsed < 0.1
    finally:
        server.shutdown()
        t.join(timeout=2)
