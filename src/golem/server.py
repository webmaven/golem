"""Provide a multi-threaded development server with SSE live reloading, event-driven watching, and port fallback.

== Threading Model

The server uses a dual-layer concurrent threading architecture:
1. `http.server.ThreadingHTTPServer` handles client HTTP requests concurrently across individual worker threads, preventing long-running connections (such as persistent Server-Sent Events streams) from blocking static file transfers.
2. A dedicated daemon background thread runs a filesystem watcher loop monitoring configured source and asset directories.

Thread safety across concurrent request handlers and the background watcher is ensured via `queues_lock`, which serializes registration, unregistration, and broadcasting across all active client event queues (`reload_queues`).

== Event-Driven File Watching & Adaptive Polling

The background watcher thread utilizes an event-driven model when native file system event notification libraries (`watchfiles` or `watchdog`) are installed:
1. If `watchfiles` or `watchdog` is available, file events trigger recompilation and viewport reloads with latency below 100ms.
2. If neither package is installed, the watcher falls back to an adaptive low-latency polling loop (0.1s debounce interval backing off up to 0.25s during idle periods) evaluating `change_detected_func()` or directory modification times.
3. Upon detecting modifications, invokes `rebuild_func()` to recompile the static site.
4. If compilation succeeds, clears any recorded error messages. If compilation raises an exception, records the failure in `last_error_message`.
5. Broadcasts a `"reload"` message to all active SSE client queues in `reload_queues`.

== Port Collision Fallback

When binding to `(host, port)`:
1. If the target TCP port is already occupied (raising `OSError` with `EADDRINUSE`), the server automatically increments the port (`port + 1`) up to a configurable maximum retry limit (`max_port_retries`).
2. The successfully bound fallback port is logged at `WARNING` level, updating `self.port` to ensure clients connect to the active listener.

== SSE Event Streaming & Injection

Connected browser clients receive live updates via standard Server-Sent Events (SSE):
1. Browsers establish a persistent SSE connection to the `/golem-reload` endpoint.
2. The server registers a thread-safe message queue for the client and streams `data: reload\\n\\n` frames upon rebuild events.
3. Periodic `: ping\\n\\n` comments are transmitted during idle intervals to maintain socket liveness and prevent client timeouts.
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
from typing import Any, Callable, List

from golem.diagnostics import Diagnostic, format_diagnostic

logger = logging.getLogger("golem.server")


def detect_watcher_backend() -> str:
    """Detect the most responsive filesystem watcher backend available.

    Checks for the presence of `watchfiles` first, then `watchdog`, and falls back
    to `"polling"` if neither package is installed in the current environment.

    [returns]
    `str`:: Identifier of the detected watcher backend (`"watchfiles"`, `"watchdog"`, or `"polling"`).
    """
    try:
        import watchfiles  # type: ignore[import-not-found,import-untyped]  # noqa: F401

        return "watchfiles"
    except ImportError:
        pass

    try:
        import watchdog  # type: ignore[import-not-found,import-untyped]  # noqa: F401

        return "watchdog"
    except ImportError:
        pass

    return "polling"


class _ThreadingDevHTTPServer(http.server.ThreadingHTTPServer):
    """Threading HTTP server with graceful client disconnection logging."""

    daemon_threads = True

    def handle_error(self, request: Any, client_address: tuple[str, int] | Any) -> None:
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
        if exc_type is not None and issubclass(exc_type, (ConnectionResetError, BrokenPipeError, ConnectionAbortedError)):
            logger.debug(
                "[LiveReload] Client %s disconnected during request processing: %s",
                client_address,
                exc_val,
            )
            return
        super().handle_error(request, client_address)


class LiveReloadServer:
    """Provide an independent multi-threaded development server with SSE live reloading and error reporting.

    Manages the lifecycle of the HTTP listener (`ThreadingHTTPServer`), background filesystem
    event watcher thread, SSE subscriber queues, and real-time build error overlay injection for
    compiled static sites.

    [attributes]
    `public_dir` (Path):: Root filesystem directory containing compiled static output files to serve over HTTP.
    `watch_dir` (Path):: Primary directory monitored for source modifications.
    `watch_directories` (list[Path]):: All directories monitored for filesystem modifications.
    `change_detected_func` (Callable[[], bool] | None):: Predicate function returning `True` when source changes are detected.
    `rebuild_func` (Callable[[], None] | None):: Callback function invoked to recompile the static site upon detected modifications.
    `port` (int):: TCP port on which the HTTP server listens. Defaults to `8000`.
    `initial_port` (int):: Initial configured TCP port before any collision fallback resolution.
    `host` (str):: Host address to bind the HTTP server to. Defaults to `""` (all interfaces).
    `errors_func` (Callable[[], list[Diagnostic]] | None):: Optional callback returning a list of build diagnostic entries for overlay rendering. Defaults to `None`.
    `max_port_retries` (int):: Maximum number of sequential port increments to attempt on collision. Defaults to `10`.
    `debounce_interval` (float):: Debounce delay in seconds applied after file events. Defaults to `0.05`.
    `watcher_backend` (str):: Active filesystem watcher backend (`"watchfiles"`, `"watchdog"`, or `"polling"`).
    `watcher_type` (str):: Alias to `watcher_backend`.
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
        watch_dir: Path | None = None,
        change_detected_func: Callable[[], bool] | None = None,
        rebuild_func: Callable[[], None] | None = None,
        port: int = 8000,
        errors_func: Callable[[], list[Diagnostic]] | None = None,
        host: str = "",
        watch_directories: list[Path] | None = None,
        max_port_retries: int = 10,
        debounce_interval: float = 0.05,
        watcher_backend: str | None = None,
    ):
        """Initialize a LiveReloadServer instance.

        Configures server directories, rebuild hooks, SSE synchronization queues,
        port fallback parameters, and event-driven filesystem watcher settings.

        [parameters]
        `public_dir` (Path):: Directory containing built static files to serve.
        `watch_dir` (Path | None, optional):: Primary source directory monitored for modifications. Defaults to `None`.
        `change_detected_func` (Callable[[], bool] | None, optional):: Predicate callable returning `True` when changes are detected. Defaults to `None`.
        `rebuild_func` (Callable[[], None] | None, optional):: Callback callable invoked to trigger site recompilation upon detected changes. Defaults to `None`.
        `port` (int, optional):: TCP port on which the HTTP server listens. Defaults to `8000`.
        `errors_func` (Callable[[], list[Diagnostic]] | None, optional):: Optional callable returning a list of build diagnostic entries. Defaults to `None`.
        `host` (str, optional):: Host address to bind the HTTP server to. Defaults to `""`.
        `watch_directories` (list[Path] | None, optional):: List of directories to monitor for changes. Defaults to `None`.
        `max_port_retries` (int, optional):: Maximum sequential port increments attempted on collision. Defaults to `10`.
        `debounce_interval` (float, optional):: Debounce delay in seconds applied after file events. Defaults to `0.05`.
        `watcher_backend` (str | None, optional):: Explicit watcher backend selection (`"watchfiles"`, `"watchdog"`, or `"polling"`). Defaults to auto-detection.
        """
        self.public_dir = Path(public_dir)

        if watch_directories is not None:
            self.watch_directories = [Path(d) for d in watch_directories]
        elif watch_dir is not None:
            self.watch_directories = [Path(watch_dir)]
        else:
            self.watch_directories = [Path("docs"), Path("templates"), Path("themes")]

        if watch_dir is not None:
            self.watch_dir = Path(watch_dir)
        elif self.watch_directories:
            self.watch_dir = self.watch_directories[0]
        else:
            self.watch_dir = Path("docs")

        self.change_detected_func = change_detected_func
        self.rebuild_func = rebuild_func
        self.port = port
        self.initial_port = port
        self.host = host
        self.errors_func = errors_func
        self.max_port_retries = max_port_retries
        self.debounce_interval = debounce_interval
        self.watcher_backend = watcher_backend or detect_watcher_backend()
        self.watcher_type = self.watcher_backend

        self.reload_queues: List[queue.Queue] = []
        self.queues_lock = threading.Lock()
        self.is_running = False
        self.last_error_message: str | None = None

        self._stop_watcher = threading.Event()
        self._change_event = threading.Event()
        self._last_mtimes: dict[Path, float] | None = None
        self.httpd: _ThreadingDevHTTPServer | None = None
        self.observer: Any = None
        self.watcher_thread: threading.Thread | None = None
        self._serving: bool = False

    def _create_handler_class(self) -> type[http.server.SimpleHTTPRequestHandler]:
        """Generate a custom HTTP request handler configured for live reloading and error reporting.

        [returns]
        `type[http.server.SimpleHTTPRequestHandler]`:: Configured handler class bound to this server instance.
        """
        dist_abs = str(self.public_dir.resolve())
        server_instance = self

        class CustomHTTPHandler(http.server.SimpleHTTPRequestHandler):
            """Handle HTTP requests with live reload script injection and SSE event streaming."""

            def __init__(self, *args: Any, **kwargs: Any) -> None:
                """Initialize the request handler with the resolved static output directory.

                [parameters]
                `args` (Any):: Positional arguments forwarded to `SimpleHTTPRequestHandler`.
                `kwargs` (Any):: Keyword arguments forwarded to `SimpleHTTPRequestHandler`.
                """
                super().__init__(*args, directory=dist_abs, **kwargs)

            def log_message(self, format: str, *args: Any) -> None:
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
                logger.info("HTTP %s%s%s - %s", color_code, status_code, reset_code, method_path)

            def do_GET(self) -> None:
                """Handle HTTP GET requests, routing SSE stream subscriptions or serving static files."""
                # Handle SSE subscription requests
                if self.path == "/golem-reload":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "keep-alive")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()

                    client_queue: queue.Queue = queue.Queue()
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
                    except (ConnectionResetError, BrokenPipeError):
                        pass
                    except Exception as e:
                        logger.debug("[LiveReload] SSE connection error: %s", e)
                    finally:
                        with server_instance.queues_lock:
                            if client_queue in server_instance.reload_queues:
                                server_instance.reload_queues.remove(client_queue)
                        logger.debug("[LiveReload] Browser tab closed SSE connection.")
                    return

                return super().do_GET()

            def send_head(self) -> Any:
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
                                err_items = [Diagnostic(**e) if isinstance(e, dict) else e for e in errs]
                                err_msg = "\n\n".join(
                                    format_diagnostic(e, content_dir=server_instance.watch_dir) for e in err_items
                                )

                        if err_msg:
                            escaped_err = err_msg.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                            error_banner = f"""
                            <div id="golem-error-overlay" style="position:fixed;top:0;left:0;right:0;background:#b91c1c;color:#ffffff;padding:14px 20px;font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;font-size:13px;z-index:99999;box-shadow:0 10px 25px -5px rgba(0,0,0,0.4);max-height:50vh;overflow-y:auto;">
                                <strong style="color:#ffffff;font-size:14px;">[Golem Build Warning/Error]</strong>
                                <pre style="margin:8px 0 0 0;padding:12px 14px;background:#18181b;color:#f4f4f5;border:1px solid #3f3f46;border-radius:4px;white-space:pre-wrap;font-family:inherit;line-height:1.45;">{escaped_err}</pre>
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
                        logger.error("[LiveReload] Failed to inject hot-reloader into HTML: %s", e)

                return super().send_head()

        return CustomHTTPHandler

    def bind(self) -> int:
        """Bind the HTTP listener socket to host and port, falling back to sequential ports on collision.

        Attempts to bind `(host, port)`. If binding raises an `OSError` due to address collision
        (`errno.EADDRINUSE`, Errno 48 on macOS, Errno 98 on Linux, or Windows WSAEADDRINUSE), iteratively
        increments the candidate port up to `max_port_retries` attempts and logs the bound port.

        [returns]
        `int`:: Resolved TCP port successfully bound by the HTTP server.

        [raises]
        `OSError`:: If port binding fails for non-collision reasons or all retries are exhausted.
        """
        if self.httpd is not None:
            return self.port

        bind_host = self.host if self.host else ""
        initial_port = self.initial_port
        handler_class = self._create_handler_class()

        for attempt in range(self.max_port_retries + 1):
            candidate_port = initial_port + attempt
            try:
                self.httpd = _ThreadingDevHTTPServer((bind_host, candidate_port), handler_class)
                self.port = candidate_port
                if attempt > 0:
                    logger.warning(
                        "[LiveReload] Port %d collision detected; fell back to http://%s:%d (attempt %d/%d).",
                        initial_port,
                        self.host or "127.0.0.1",
                        self.port,
                        attempt,
                        self.max_port_retries,
                    )
                return self.port
            except OSError as exc:
                import errno

                is_in_use = (
                    exc.errno == errno.EADDRINUSE
                    or (hasattr(errno, "WSAEADDRINUSE") and exc.errno == errno.WSAEADDRINUSE)
                    or exc.errno in (48, 98)
                    or "address already in use" in str(exc).lower()
                )
                if is_in_use and attempt < self.max_port_retries:
                    logger.info(
                        "[LiveReload] Port %d collision (%s); attempting port %d...",
                        candidate_port,
                        exc,
                        candidate_port + 1,
                    )
                    continue
                raise
        return self.port

    def _trigger_rebuild(self) -> None:
        """Trigger site recompilation and broadcast live reload frames to SSE subscribers."""
        logger.info("[LiveReload] File modification detected. Triggering rebuild...")
        try:
            if self.rebuild_func is not None:
                self.rebuild_func()
            self.last_error_message = None
            logger.info("[LiveReload] Rebuild finished successfully. Notifying connected tabs.")
        except Exception as e:
            self.last_error_message = str(e)
            logger.error("[LiveReload] Rebuild encountered compilation error: %s", e)

        with self.queues_lock:
            for q in self.reload_queues:
                try:
                    q.put("reload")
                except Exception:
                    pass

    def _get_watch_mtimes(self) -> dict[Path, float]:
        """Collect latest modification times across all configured watch directories.

        [returns]
        `dict[Path, float]`:: Mapping of file paths to their modification timestamps.
        """
        mtimes: dict[Path, float] = {}
        for watch_dir in self.watch_directories:
            if not watch_dir.exists():
                continue
            try:
                if watch_dir.is_file():
                    mtimes[watch_dir] = watch_dir.stat().st_mtime
                else:
                    for entry in watch_dir.rglob("*"):
                        if entry.is_file():
                            try:
                                mtimes[entry] = entry.stat().st_mtime
                            except OSError:
                                pass
            except OSError:
                pass
        return mtimes

    def _check_directory_mtimes(self) -> bool:
        """Check if any files in watch directories have been modified, created, or removed.

        [returns]
        `bool`:: `True` if modification times changed relative to baseline, `False` otherwise.
        """
        new_mtimes = self._get_watch_mtimes()
        if self._last_mtimes is None:
            self._last_mtimes = new_mtimes
            return False
        if new_mtimes != self._last_mtimes:
            self._last_mtimes = new_mtimes
            return True
        return False

    def _start_watchfiles_listener(self) -> threading.Thread | None:
        """Launch a background worker using `watchfiles` to listen for filesystem changes.

        [returns]
        `threading.Thread | None`:: Started background thread if `watchfiles` is available, `None` otherwise.
        """
        try:
            import watchfiles  # type: ignore[import-not-found,import-untyped]
        except ImportError:
            return None

        existing_dirs = [str(d.resolve()) for d in self.watch_directories if d.exists()]
        if not existing_dirs:
            return None

        def worker() -> None:
            try:
                for _changes in watchfiles.watch(
                    *existing_dirs,
                    stop_event=self._stop_watcher,
                    debounce=30,
                    step=20,
                ):
                    if not self.is_running or self._stop_watcher.is_set():
                        break
                    self._change_event.set()
            except Exception as exc:
                logger.debug("[LiveReload] watchfiles listener exited: %s", exc)

        thread = threading.Thread(target=worker, daemon=True, name="golem-watchfiles")
        thread.start()
        return thread

    def _start_watchdog_listener(self) -> Any:
        """Launch a background observer using `watchdog` to listen for filesystem changes.

        [returns]
        `Any`:: Started watchdog Observer instance if `watchdog` is available, `None` otherwise.
        """
        try:
            from watchdog.events import FileSystemEventHandler  # type: ignore[import-not-found,import-untyped]
            from watchdog.observers import Observer  # type: ignore[import-not-found,import-untyped]
        except ImportError:
            return None

        existing_dirs = [d.resolve() for d in self.watch_directories if d.exists()]
        if not existing_dirs:
            return None

        change_event = self._change_event

        class _Handler(FileSystemEventHandler):
            def on_any_event(self, event: Any) -> None:
                if not getattr(event, "is_directory", False):
                    change_event.set()

        handler = _Handler()
        observer = Observer()
        for d in existing_dirs:
            observer.schedule(handler, str(d), recursive=True)
        observer.start()
        return observer

    def _watch_loop(self) -> None:
        """Run the background file system watcher loop with event-driven monitoring or adaptive polling."""
        logger.info(
            "[LiveReload] Starting file system watcher loop (backend=%s, paths=%s)...",
            self.watcher_backend,
            [str(p) for p in self.watch_directories],
        )

        watchfiles_thread: threading.Thread | None = None
        if self.watcher_backend == "watchfiles":
            watchfiles_thread = self._start_watchfiles_listener()
            if watchfiles_thread is None:
                logger.info("[LiveReload] Falling back to polling watcher backend.")
                self.watcher_backend = "polling"
        elif self.watcher_backend == "watchdog":
            self.observer = self._start_watchdog_listener()
            if self.observer is None:
                logger.info("[LiveReload] Falling back to polling watcher backend.")
                self.watcher_backend = "polling"

        min_interval = 0.1
        max_interval = 0.25
        current_interval = min_interval

        # Initialize baseline mtimes if using fallback check
        self._last_mtimes = self._get_watch_mtimes()

        while self.is_running and not self._stop_watcher.is_set():
            try:
                # If event-driven watcher is active, wait on _change_event.
                # If polling, wait acts as sleep interval while remaining wakeable on shutdown.
                triggered = self._change_event.wait(timeout=current_interval)
                if not self.is_running or self._stop_watcher.is_set():
                    break

                has_changed = False
                if triggered:
                    self._change_event.clear()
                    if self.debounce_interval > 0:
                        time.sleep(self.debounce_interval)
                    self._change_event.clear()
                    has_changed = True
                elif self.change_detected_func is not None:
                    try:
                        has_changed = self.change_detected_func()
                    except Exception as e:
                        logger.error("[LiveReload] Error evaluating change_detected_func: %s", e)
                        has_changed = False
                elif self._check_directory_mtimes():
                    has_changed = True

                if has_changed:
                    current_interval = min_interval
                    self._trigger_rebuild()
                else:
                    # Adaptive sleep interval backoff between 0.1s and 0.25s
                    current_interval = min(current_interval + 0.05, max_interval)
            except Exception as e:
                logger.error("[LiveReload] Error in watcher loop: %s", e)
                time.sleep(0.1)

    def run(self) -> None:
        """Launch the development server event loops and block until interrupted.

        Binds the HTTP server (if not already bound), launches the background filesystem watcher
        thread with event-driven or adaptive polling detection, and begins serving client requests
        concurrently with SSE live reloading.

        NOTE: This method blocks the calling thread on `serve_forever()` until `shutdown()`
        is invoked or a termination signal is received.
        """
        self.is_running = True
        self._stop_watcher.clear()
        self._change_event.clear()

        if self.httpd is None:
            self.bind()

        logger.info(
            "[LiveReload] DevServer active on http://%s:%d...",
            self.host or "127.0.0.1",
            self.port,
        )

        # 1. Start concurrent file system watcher thread
        self.watcher_thread = threading.Thread(target=self._watch_loop, daemon=True, name="golem-watcher")
        self.watcher_thread.start()

        # 2. Block on serving HTTP requests
        try:
            assert self.httpd is not None
            self._serving = True
            self.httpd.serve_forever()
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            self._serving = False
            self.shutdown()

    def shutdown(self) -> None:
        """Cleanly stop the running development server and terminate event streams.

        Sets `is_running` to `False`, unblocks the watcher loop, halts any active
        watchdog observer, dispatches `"shutdown"` messages to SSE client queues, and
        stops the underlying `ThreadingHTTPServer`.
        """
        self.is_running = False
        self._stop_watcher.set()
        self._change_event.set()

        if self.observer is not None:
            try:
                self.observer.stop()
                self.observer.join(timeout=1.0)
            except Exception:
                pass
            self.observer = None

        with self.queues_lock:
            for q in self.reload_queues:
                try:
                    q.put("shutdown")
                except Exception:
                    pass

        if self.httpd is not None:
            if getattr(self, "_serving", False):
                try:
                    self.httpd.shutdown()
                except Exception:
                    pass
                self._serving = False
            try:
                self.httpd.server_close()
            except Exception:
                pass
            self.httpd = None
