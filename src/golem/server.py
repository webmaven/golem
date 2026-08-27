"""Provide a multi-threaded development server with SSE live reloading and build error overlay injection.

== Threading Model

The server uses a dual-layer concurrent threading architecture:
1. `http.server.ThreadingHTTPServer` handles client HTTP requests concurrently across individual worker threads, preventing long-running connections (such as persistent Server-Sent Events streams) from blocking static file transfers.
2. A dedicated daemon background thread runs a continuous filesystem watcher loop that monitors source paths and triggers recompilation.

Thread safety across concurrent request handlers and the background watcher is ensured via `queues_lock`, which serializes registration, unregistration, and broadcasting across all active client event queues (`reload_queues`).

== Live Reload Loop

The background watcher thread executes a polling loop:
1. Sleeps for a fixed interval (1.0 second).
2. Invokes `change_detected_func()` to check for modified source files.
3. Upon detecting modifications, invokes `rebuild_func()` to trigger site recompilation.
4. If compilation succeeds, clears any recorded error messages. If compilation raises an exception, records the failure in `last_error_message`.
5. Broadcasts a `"reload"` message to all active SSE client queues in `reload_queues`.

== SSE Event Streaming & Injection

Connected browser clients receive live updates via standard Server-Sent Events (SSE):
1. Browsers establish a persistent SSE connection to the `/golem-reload` endpoint.
2. The server registers a thread-safe message queue for the client and streams `data: reload\n\n` frames upon rebuild events.
3. Periodic `: ping\n\n` comments are transmitted during idle intervals to maintain socket liveness and prevent client timeouts.
4. When serving HTML files, `send_head()` automatically injects a lightweight client JavaScript snippet that subscribes to `/golem-reload` and reloads the active viewport on event receipt.
5. If build errors or warnings are detected, `send_head()` dynamically injects a top-level error overlay banner (`#golem-error-overlay`) displaying formatted diagnostic messages.
"""

import http.server
import io
import logging
import queue
import threading
import time
from pathlib import Path
from typing import Callable, List

logger = logging.getLogger("golem.server")


class LiveReloadServer:
    """Provide an independent multi-threaded development server with SSE live reloading and error reporting.

    Manages the lifecycle of the HTTP listener (`ThreadingHTTPServer`), background filesystem
    polling thread, SSE subscriber queues, and real-time build error overlay injection for
    compiled static sites.

    [attributes]
    `public_dir` (Path):: Root filesystem directory containing compiled static output files to serve over HTTP.
    `watch_dir` (Path):: Root directory containing source documents monitored for changes.
    `change_detected_func` (Callable[[], bool]):: Predicate function returning `True` when source changes are detected.
    `rebuild_func` (Callable[[], None]):: Callback function invoked to recompile the static site upon detected modifications.
    `port` (int):: TCP port on which the HTTP server listens. Defaults to `8000`.
    `errors_func` (Callable[[], list[dict]] | None):: Optional callback returning a list of build error dictionaries for overlay rendering. Defaults to `None`.
    `reload_queues` (list[queue.Queue]):: Active client message queues for connected SSE browser streams.
    `queues_lock` (threading.Lock):: Mutex lock protecting concurrent access to `reload_queues`.
    `is_running` (bool):: Flag indicating whether the server and background watcher threads are active.
    `last_error_message` (str | None):: Last captured error message from failed rebuild invocations, or `None` if clean.

    === Examples

    [source,python]
    ----
    >>> from pathlib import Path
    >>> from golem.server import LiveReloadServer
    >>> server = LiveReloadServer(
    ...     public_dir=Path("dist"),
    ...     watch_dir=Path("content"),
    ...     change_detected_func=lambda: False,
    ...     rebuild_func=lambda: None,
    ...     port=8999
    ... )
    >>> server.port
    8999
    >>> server.is_running
    False
    ----
    """

    def __init__(
        self,
        public_dir: Path,
        watch_dir: Path,
        change_detected_func: Callable[[], bool],
        rebuild_func: Callable[[], None],
        port: int = 8000,
        errors_func: Callable[[], list[dict]] | None = None,
    ):
        """Initialize a LiveReloadServer instance.

        Configures server directories, rebuild hooks, SSE synchronization queues,
        and internal state flags.

        [parameters]
        `public_dir` (Path):: Directory containing built static files to serve.
        `watch_dir` (Path):: Directory monitored for filesystem modifications.
        `change_detected_func` (Callable[[], bool]):: Predicate callable returning `True` when source changes are detected.
        `rebuild_func` (Callable[[], None]):: Callback callable invoked to trigger site recompilation upon detected changes.
        `port` (int, optional):: TCP port on which the HTTP server listens. Defaults to `8000`.
        `errors_func` (Callable[[], list[dict]] | None, optional):: Optional callable returning a list of build error dictionaries. Defaults to `None`.
        """
        self.public_dir = Path(public_dir)
        self.watch_dir = Path(watch_dir)
        self.change_detected_func = change_detected_func
        self.rebuild_func = rebuild_func
        self.port = port
        self.errors_func = errors_func
        self.reload_queues: List[queue.Queue] = []
        self.queues_lock = threading.Lock()
        self.is_running = False
        self.last_error_message: str | None = None

    def run(self):
        """Launch the development server event loops and block until interrupted.

        Starts the concurrent background filesystem watcher thread and initializes
        the multi-threaded HTTP server (`http.server.ThreadingHTTPServer`) to serve
        static files, stream SSE events on `/golem-reload`, and inject live reload
        scripts and error overlays into served HTML responses.

        NOTE: This method blocks the calling thread on `serve_forever()` until `shutdown()`
        is invoked or a termination signal is received.
        """
        self.is_running = True
        dist_abs = str(self.public_dir.resolve())
        server_instance = self

        # 1. Start concurrent file system watcher thread
        def watch_loop():
            logger.info("[LiveReload] Starting file system poll loop...")
            while self.is_running:
                try:
                    time.sleep(1.0)
                    if self.change_detected_func():
                        logger.info("[LiveReload] File modification detected. Triggering rebuild...")
                        try:
                            self.rebuild_func()
                            self.last_error_message = None
                            logger.info("[LiveReload] Rebuild finished successfully. Notifying connected tabs.")
                        except Exception as e:
                            self.last_error_message = str(e)
                            logger.error(f"[LiveReload] Rebuild encountered compilation error: {e}")

                        with server_instance.queues_lock:
                            for q in server_instance.reload_queues:
                                q.put("reload")
                except Exception as e:
                    logger.error(f"[LiveReload] Error in watcher loop: {e}")

        watcher_thread = threading.Thread(target=watch_loop, daemon=True)
        watcher_thread.start()

        # 2. Define custom SSE-enabled Threading Request Handler
        class CustomHTTPHandler(http.server.SimpleHTTPRequestHandler):
            """Handle HTTP requests with live reload script injection and SSE event streaming."""

            def __init__(self, *args, **kwargs):
                """Initialize the request handler with the resolved static output directory.

                [parameters]
                `args` (Any):: Positional arguments forwarded to `SimpleHTTPRequestHandler`.
                `kwargs` (Any):: Keyword arguments forwarded to `SimpleHTTPRequestHandler`.
                """
                super().__init__(*args, directory=dist_abs, **kwargs)

            def log_message(self, format, *args):
                """Log an HTTP request with ANSI color-coded status codes.

                [parameters]
                `format` (str):: Standard format string for the log message.
                `args` (Any):: Positional arguments containing method, path, and response status code.
                """
                status_code = args[1] if len(args) > 1 else ""
                method_path = args[0] if len(args) > 0 else ""
                if status_code.startswith("2") or status_code.startswith("3"):
                    color_code = "\033[32m"  # Green
                elif status_code.startswith("4"):
                    color_code = "\033[33m"  # Yellow
                else:
                    color_code = "\033[31m"  # Red
                reset_code = "\033[0m"
                logger.info(f"HTTP {color_code}{status_code}{reset_code} - {method_path}")

            def do_GET(self):
                """Handle HTTP GET requests, routing SSE stream subscriptions or serving static files."""
                # Handle SSE subscription requests
                if self.path == "/golem-reload":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "keep-alive")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()

                    client_queue = queue.Queue()
                    with server_instance.queues_lock:
                        server_instance.reload_queues.append(client_queue)

                    logger.debug("[LiveReload] Browser tab established SSE hot-reload connection.")
                    try:
                        while server_instance.is_running:
                            try:
                                # Non-blocking wait for reload messages
                                msg = client_queue.get(timeout=10)
                                if msg == "reload":
                                    self.wfile.write(b"data: reload\n\n")
                                    self.wfile.flush()
                            except queue.Empty:
                                # Send keep-alive comments to prevent socket timeouts
                                self.wfile.write(b": ping\n\n")
                                self.wfile.flush()
                    except ConnectionResetError, BrokenPipeError:
                        pass
                    except Exception as e:
                        logger.debug(f"[LiveReload] SSE connection error: {e}")
                    finally:
                        with server_instance.queues_lock:
                            if client_queue in server_instance.reload_queues:
                                server_instance.reload_queues.remove(client_queue)
                        logger.debug("[LiveReload] Browser tab closed SSE connection.")
                    return

                return super().do_GET()

            def send_head(self):
                """Send HTTP response headers and inject SSE scripts and error overlays into HTML responses.

                Translates the requested URL path to the filesystem. For HTML responses,
                reads the file content, injects a visual error banner overlay if build
                errors are present, injects the SSE client listener script before `</head>`,
                and returns an in-memory byte stream. For non-HTML requests, delegates to
                standard static file resolution.

                [returns]
                `io.BytesIO | io.BufferedReader | None`:: File-like object containing response body data, or `None` if headers have already been sent.
                """
                path = self.translate_path(self.path)
                f_path = Path(path)
                if f_path.is_dir():
                    f_path = f_path / "index.html"

                if f_path.exists() and f_path.suffix == ".html":
                    try:
                        with open(f_path, "r", encoding="utf-8") as f_in:
                            html_content = f_in.read()

                        # Check for build errors to render overlay
                        error_banner = ""
                        err_msg = server_instance.last_error_message
                        if not err_msg and server_instance.errors_func is not None:
                            errs = server_instance.errors_func()
                            if errs:
                                err_msg = "\n".join(f"[{e.get('file', 'unknown')}] {e.get('message', '')}" for e in errs)

                        if err_msg:
                            escaped_err = err_msg.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                            error_banner = f"""
                            <div id="golem-error-overlay" style="position:fixed;top:0;left:0;right:0;background:#ef4444;color:#ffffff;padding:12px 20px;font-family:monospace;font-size:14px;z-index:99999;box-shadow:0 4px 6px -1px rgba(0,0,0,0.2);">
                                <strong>[Golem Build Warning/Error]</strong>
                                <pre style="margin:6px 0 0 0;white-space:pre-wrap;">{escaped_err}</pre>
                            </div>
                            """

                        # Embedded lightweight SSE listener
                        sse_snippet = f"""
                        <!-- Golem SSE Hot Reloader -->
                        {error_banner}
                        <script>
                        (function() {{
                          const sse = new EventSource('/golem-reload');
                          sse.onmessage = function(e) {{
                            if (e.data === 'reload') {{
                              console.log('[Golem] Rebuild detected. Refreshing active viewport...');
                              window.location.reload();
                            }}
                          }};
                          sse.onerror = function() {{
                            console.debug('[Golem] SSE connection lost. Attempting to reconnect...');
                          }};
                        }})();
                        </script>
                        """
                        if "</head>" in html_content:
                            html_content = html_content.replace("</head>", sse_snippet + "</head>", 1)
                        else:
                            html_content += sse_snippet

                        encoded = html_content.encode("utf-8")
                        f_mem = io.BytesIO(encoded)
                        self.send_response(200)
                        self.send_header("Content-Type", "text/html")
                        self.send_header("Content-Length", str(len(encoded)))
                        self.end_headers()
                        return f_mem
                    except Exception as e:
                        logger.error(f"[LiveReload] Failed to inject hot-reloader into HTML: {e}")

                return super().send_head()

        # Custom ThreadingHTTPServer that logs client disconnects cleanly at DEBUG level
        class _ThreadingDevHTTPServer(http.server.ThreadingHTTPServer):
            """Threading HTTP server with graceful client disconnection logging."""

            daemon_threads = True

            def handle_error(self, request, client_address):
                """Handle server errors, suppressing noisy client disconnect stack traces.

                Logs benign network disconnections (`ConnectionResetError`, `BrokenPipeError`,
                `ConnectionAbortedError`) at `DEBUG` level and forwards genuine internal server
                exceptions to standard error handling.

                [parameters]
                `request` (Any):: Active network socket or request instance.
                `client_address` (tuple):: Remote client address `(ip, port)`.
                """
                import sys

                exc_type, exc_val = sys.exc_info()[:2]
                if exc_type is not None and issubclass(
                    exc_type, (ConnectionResetError, BrokenPipeError, ConnectionAbortedError)
                ):
                    logger.debug(
                        "[LiveReload] Client %s disconnected during request processing: %s",
                        client_address,
                        exc_val,
                    )
                    return
                super().handle_error(request, client_address)

        # ThreadingHTTPServer enables concurrent multi-client and SSE streaming
        self.httpd = _ThreadingDevHTTPServer(("", self.port), CustomHTTPHandler)
        logger.info(f"[LiveReload] DevServer active on http://127.0.0.1:{self.port}...")
        try:
            self.httpd.serve_forever()
        except KeyboardInterrupt, SystemExit:
            pass
        finally:
            self.is_running = False
            logger.info("[LiveReload] Shutting down DevServer...")
            self.httpd.server_close()

    def shutdown(self):
        """Cleanly stop the running development server and terminate event streams.

        Sets `is_running` to `False`, dispatches a `"shutdown"` message to all
        connected SSE client queues to unblock active response streams, and halts the
        underlying `ThreadingHTTPServer`.
        """
        self.is_running = False
        with self.queues_lock:
            for q in self.reload_queues:
                try:
                    q.put("shutdown")
                except Exception:
                    pass
        if hasattr(self, "httpd"):
            self.httpd.shutdown()
