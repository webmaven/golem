import hashlib
import json
import os
from pathlib import Path
from golem.config import GolemConfig
import asciidoctrine

class BuildEngine:
    def __init__(self, config: GolemConfig, cache_file: Path = None):
        self.config = config
        self.content_dir = Path(config.content_dir).resolve()
        self.cache_file = cache_file or Path(config.content_dir).parent / ".golem" / "cache.json"
        self.cache_data = self._load_cache()

    def _load_cache(self) -> dict:
        if self.cache_file.exists():
            try:
                with open(self.cache_file, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"files": {}, "dependencies": {}}

    def save_cache(self):
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_file, "w") as f:
            json.dump(self.cache_data, f, indent=2)

    def _get_sha256(self, path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(8192):
                h.update(chunk)
        return h.hexdigest()

    def get_outdated_files(self) -> set[Path]:
        outdated = set()
        all_files = list(self.content_dir.glob("**/*.adoc"))
        
        # 1. Map current file hashes and identify immediately changed files
        current_hashes = {}
        changed_directly = set()
        for f in all_files:
            f_abs = f.resolve()
            h = self._get_sha256(f)
            current_hashes[str(f_abs)] = h
            cached_hash = self.cache_data["files"].get(str(f_abs))
            if cached_hash != h:
                changed_directly.add(f_abs)
                outdated.add(f_abs)

        # 2. Re-verify the DAG: pull and resolve all native inclusions
        # Create adjacency: included_file -> parents_set
        reverse_deps: dict[str, set[str]] = {}
        for f in all_files:
            f_abs = str(f.resolve())
            cached_deps = self.cache_data["dependencies"].get(f_abs, [])
            for dep in cached_deps:
                reverse_deps.setdefault(dep, set()).add(f_abs)

        # Recursively propagate changed files back up to their parents (ancestors)
        queue = list(changed_directly)
        visited = set(queue)
        while queue:
            curr = str(queue.pop(0))
            parents = reverse_deps.get(curr, set())
            for p in parents:
                p_path = Path(p)
                if p_path not in visited:
                    outdated.add(p_path)
                    visited.add(p_path)
                    queue.append(p_path)
                    
        return outdated

    def update_cache_for_file(self, path: Path, included_files: list[str] = None):
        p_abs = str(path.resolve())
        self.cache_data["files"][p_abs] = self._get_sha256(path)
        if included_files is not None:
            self.cache_data["dependencies"][p_abs] = [str(Path(f).resolve()) for f in included_files]
        else:
            deps = []
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                ast = asciidoctrine.parse_to_ast(content, base_dir=str(path.parent))
                deps = ast.included_files
            except Exception:
                # Fallback to regex-based robust include parser
                import re
                include_regex = re.compile(r'^include::([^\[]+)\[(.*)\]\s*$')
                seen = set()
                def find_includes(f_path: Path):
                    f_abs = str(f_path.resolve())
                    if f_abs in seen:
                        return
                    seen.add(f_abs)
                    if not f_path.exists():
                        return
                    try:
                        with open(f_path, "r", encoding="utf-8") as f_in:
                            for line in f_in:
                                m = include_regex.match(line.strip())
                                if m:
                                    inc_name = m.group(1).strip()
                                    inc_path = (f_path.parent / inc_name).resolve()
                                    deps.append(str(inc_path))
                                    find_includes(inc_path)
                    except Exception:
                        pass
                find_includes(path)
            
            # De-duplicate and make sure all are absolute paths as strings
            unique_deps = list(dict.fromkeys(str(Path(d).resolve()) for d in deps))
            self.cache_data["dependencies"][p_abs] = unique_deps
        self.save_cache()
