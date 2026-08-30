"""Provide persistent cache management, file hashing, and advisory locking for Golem builds.

== Cache Architecture

Golem uses JSON-based persistent caching to enable fast incremental builds. The cache records:
- Content digests (SHA-256) of source documents, partials, templates, and configuration files.
- Document include dependencies forming the Directed Acyclic Graph (DAG).
- Extracted document metadata and structural ASG node types.
- Filesystem modification times and file sizes for fast timestamp-based digest memoization.

Advisory cross-process locking (`filelock.FileLock`) and atomic temporary file replacement guarantee
cache database integrity across concurrent build processes.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from filelock import FileLock

__all__ = [
    "BuildCache",
]


class BuildCache:
    """Persistent DAG cache database and file digest tracker for Golem builds.

    Manages JSON-based disk caching of file content hashes, include dependencies,
    parsed metadata, and ASG node types. Provides atomic disk persistence, cross-process
    advisory locking, and timestamp-memoized SHA-256 calculations.

    [attributes]
    `cache_file` (Path):: Path to the JSON cache storage file.
    `data` (dict[str, Any]):: In-memory cache dictionary containing files, dependencies, metadata, and mtimes tables.
    `_sha_cache` (dict[str, tuple[float, int, str]]):: In-memory lookup mapping absolute file paths to `(mtime, size, sha256)` tuples.

    === Examples

    [source,python]
    ----
    >>> from pathlib import Path
    >>> from golem.cache import BuildCache
    >>> cache = BuildCache(Path(".golem/cache.json"))
    >>> isinstance(cache.data, dict)
    True
    ----
    """

    def __init__(self, cache_file: Path) -> None:
        """Initialize the build cache database.

        Loads existing cache records from disk under an advisory lock, or initializes
        an empty cache schema if the cache file does not exist or is corrupt.

        [parameters]
        `cache_file` (Path):: Path to the JSON cache storage file.
        """
        self.cache_file = cache_file
        self._sha_cache: dict[str, tuple[float, int, str]] = {}
        self.data: dict[str, Any] = self._load_cache()

    def _load_cache(self) -> dict[str, Any]:
        """Load and parse the DAG dependency JSON cache from disk.

        Reads cached file hashes, include dependencies, metadata, and modification
        timestamps under an advisory lock. Initializes an empty schema if the cache
        file does not exist or is corrupted.

        [returns]
        `dict[str, Any]`:: Deserialized cache dictionary containing `"files"`, `"dependencies"`, and `"metadata"` tables.
        """
        with self._cache_lock():
            if self.cache_file.exists():
                try:
                    with open(self.cache_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        data.setdefault("files", {})
                        data.setdefault("dependencies", {})
                        data.setdefault("metadata", {})
                        if "mtimes" in data and isinstance(data["mtimes"], dict):
                            self._sha_cache = {
                                k: (v[0], v[1], v[2])
                                for k, v in data["mtimes"].items()
                                if isinstance(v, (list, tuple)) and len(v) == 3
                            }
                        return data
                except Exception:
                    try:
                        self.cache_file.unlink()
                    except Exception:
                        pass
            return {"files": {}, "dependencies": {}, "metadata": {}}

    def save_cache(self) -> None:
        """Persist DAG compilation hashes and metadata atomically to disk.

        Serializes cache records and timestamp caches to JSON. Uses atomic temporary
        file replacement under an advisory cross-process file lock (`_cache_lock`)
        to guarantee cache integrity.

        [raises]
        `OSError`:: If writing or renaming the temporary cache file fails.

        === Examples

        [source,python]
        ----
        from pathlib import Path
        from golem.cache import BuildCache

        cache = BuildCache(Path(".golem/cache.json"))
        cache.data["files"]["content/index.adoc"] = "abc123"
        cache.save_cache()
        ----
        """
        with self._cache_lock():
            if hasattr(self, "_sha_cache") and self._sha_cache:
                self.data["mtimes"] = {k: list(v) for k, v in self._sha_cache.items()}
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            dir_path = self.cache_file.parent
            with tempfile.NamedTemporaryFile("w", dir=dir_path, delete=False, encoding="utf-8") as tf:
                json.dump(self.data, tf, indent=2)
                temp_name = tf.name

            try:
                os.replace(temp_name, self.cache_file)
            except Exception:
                if os.path.exists(temp_name):
                    os.unlink(temp_name)
                raise

    def clean(self) -> None:
        """Purge persistent cache database and file locks.

        Unlinks the DAG cache file (`cache_file`) and lockfile (`cache.lock`),
        and resets the in-memory cache data structures.

        === Examples

        [source,python]
        ----
        from pathlib import Path
        from golem.cache import BuildCache

        cache = BuildCache(Path(".golem/cache.json"))
        cache.clean()
        ----
        """
        if self.cache_file.exists():
            try:
                self.cache_file.unlink()
            except OSError:
                pass

        lock_path = self.cache_file.parent / "cache.lock"
        if lock_path.exists():
            try:
                lock_path.unlink()
            except OSError:
                pass

        self.data = {"files": {}, "dependencies": {}, "metadata": {}}
        self._sha_cache = {}

    @contextmanager
    def _cache_lock(self) -> Generator[None, None, None]:
        """Acquire an advisory cross-process lock on the cache lockfile.

        Uses `filelock.FileLock` for cross-platform compatibility (POSIX and Windows).
        Creates the lock file under `<cache_file_dir>/cache.lock`.

        [yields]
        `None`:: Yields control while holding the exclusive lock.
        """
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.cache_file.parent / "cache.lock"
        with FileLock(str(lock_path)):
            yield

    def get_sha256(self, path: Path) -> str:
        """Compute the SHA-256 hexadecimal digest of a file.

        Reads file content in 8192-byte chunks and computes its SHA-256 digest.
        Utilizes an in-memory cache keyed by path, `mtime`, and `size` to avoid
        redundant disk reads when file attributes are unmodified.

        [parameters]
        `path` (Path):: Path to the target file.

        [returns]
        `str`:: Hexadecimal SHA-256 digest string, or empty string `""` if the file cannot be accessed.

        === Examples

        [source,python]
        ----
        from pathlib import Path
        from golem.cache import BuildCache

        cache = BuildCache(Path(".golem/cache.json"))
        digest = cache.get_sha256(Path("content/index.adoc"))
        assert isinstance(digest, str)
        ----
        """
        p_abs = str(path.resolve())
        try:
            stat = path.stat()
            mtime = stat.st_mtime
            size = stat.st_size
        except OSError:
            return ""

        if hasattr(self, "_sha_cache"):
            cached = self._sha_cache.get(p_abs)
            if cached and cached[0] == mtime and cached[1] == size:
                return cached[2]
        else:
            self._sha_cache = {}

        h = hashlib.sha256()
        try:
            with open(path, "rb") as f:
                while chunk := f.read(8192):
                    h.update(chunk)
        except OSError:
            return ""
        hexdigest = h.hexdigest()
        self._sha_cache[p_abs] = (mtime, size, hexdigest)
        return hexdigest

    def _get_sha256(self, path: Path) -> str:
        """Compute the SHA-256 hexadecimal digest of a file (internal alias)."""
        return self.get_sha256(path)
