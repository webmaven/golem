"""
Development HTTP server with live-reload and build-error overlays for Golem.

Threading model
---------------
The server uses two concurrent execution contexts:

1. **File-watcher thread** (daemon) — polls the ``watch_dir`` once per
   second via :attr:`~LiveReloadServer.change_detected_func`.  On
   detecting a change it calls :attr:`~LiveReloadServer.rebuild_func`,
   then puts a ``"reload"`` message onto every registered SSE queue.

2. **ThreadingHTTPServer** (main thread, blocking) — handles each HTTP
   request in its own thread.  Requests to the synthetic
   ``/golem-reload`` endpoint block indefinitely in SSE streaming mode,
   reading from a per-connection :class:`~queue.Queue` until the
   watcher signals or the client disconnects.

Live-reload protocol
--------------------
Golem injects a tiny ``<script>`` block into every served ``.html``
page that opens an SSE connection to ``/golem-reload``.  When the
watcher signals, the script calls ``window.location.reload()``
in every connected browser tab simultaneously.  A ``": ping\\n\\n"``
keep-alive comment is sent every 10 s to prevent socket timeouts on
proxies and load balancers.

Build-error overlays
--------------------
If the rebuild callback raises an exception, its message is stored in
:attr:`~LiveReloadServer.last_error_message`.  The next page served has
a red fixed-position banner injected at the top of the ``<head>``
showing the error; the banner disappears once a subsequent clean rebuild
clears :attr:`~LiveReloadServer.last_error_message`.
"""

import http.server
import logging
import queue
import threading
import time
from pathlib import Path
from typing import Callable, List
import io

logger = logging.getLogger("golem.server")


class LiveReloadServer:
    """

    An independent, multi-threaded static file development server
    featuring standard Server-Sent Events (SSE) live hot-reloading and
    live build error notification overlays.

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
        """Initialise a live-reload dev server.

        === Arguments

        - ``public_dir``:: Directory of pre-built static files to serve
          (typically the Golem ``output_dir``, e.g. ``dist/``).
        - ``watch_dir``:: Directory to monitor for source changes
          (typically the Golem ``content_dir``).
        - ``change_detected_func``:: Zero-argument callable returning
          ``True`` if source files have changed since the last poll
          cycle.  Called once per second from the watcher thread.
        - ``rebuild_func``:: Zero-argument callable that performs a full
          or incremental site rebuild.  Called immediately after
          *change_detected_func* returns ``True``; exceptions are caught
          and stored in :attr:`last_error_message`.
        - ``port``:: TCP port to bind.  Default: ``8000``.
        - ``errors_func``:: Optional callable returning a list of
          ``{"file": …, "message": …}`` dicts from the most recent
          build.  When provided, its output is merged with
          :attr:`last_error_message` to populate the error overlay.
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
        """Start the server and block until interrupted.

        Launches the file-watcher daemon thread, then enters the
        :class:`~http.server.ThreadingHTTPServer` serve-forever loop on
        the configured :attr:`port`.  Returns only after
        :meth:`shutdown` is called or a ``KeyboardInterrupt`` /
        ``SystemExit`` is raised.

        Each ``.html`` response has the SSE listener ``<script>`` and
        optional error banner injected just before ``</head>`` on the
        fly, so the built files themselves remain unmodified on disk.

        The method sets :attr:`is_running` to ``True`` on entry and
        ``False`` in the ``finally`` block, making it safe to use
        :attr:`is_running` as a liveness sentinel from other threads.
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
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=dist_abs, **kwargs)

            def log_message(self, format, *args):
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
                """
                Injects standard LiveReload client javascript listener and error overlays on-the-fly.
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

        # ThreadingHTTPServer enables concurrent multi-client and SSE streaming
        self.httpd = http.server.ThreadingHTTPServer(("", self.port), CustomHTTPHandler)
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
        """Cleanly stop the server and release all resources.

        Sets :attr:`is_running` to ``False`` to signal the watcher
        thread to exit its next iteration, sends a ``"shutdown"``
        sentinel to all open SSE queues so their request-handler threads
        can drain and exit, then calls
        :meth:`~http.server.HTTPServer.shutdown` on the underlying
        :class:`~http.server.ThreadingHTTPServer` to stop
        ``serve_forever``.

        Safe to call from any thread, including from the watcher thread
        itself or from a signal handler.
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
