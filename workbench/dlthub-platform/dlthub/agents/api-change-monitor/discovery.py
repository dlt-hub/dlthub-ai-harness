"""Find the APIs the production pipelines call, and where the workspace uses each.

Production code is what `__deployment__.py` imports, followed through the workspace's
own modules; a workspace without one is scanned whole. An API is found by a url its
code or config names, or by a source module it imports, and matched to the registry.
"""

from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .redact import redact
from .registry import IGNORED_HOSTS, KnownApi, load, match_host, match_module

DEPLOYMENT_MODULE = "__deployment__.py"
SUFFIXES = {".py", ".sql", ".yml", ".yaml", ".toml", ".json"}
SKIPPED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".claude",
    ".cursor",
    ".agents",
    "dbt_packages",
    "target",
    "_storage",
    ".var",
    ".pytest_cache",
    "tests",
}
# a model folder holds the transformations that read the loaded tables
MODEL_DIRS = {"models", "transformations", "transforms", "marts", "staging"}

# a host whose labels may be templated, as `https://{subdomain}.example.com`
_URL = re.compile(r"https?://((?:[A-Za-z0-9-]+|\{[^}/]*\})(?:\.(?:[A-Za-z0-9-]+|\{[^}/]*\}))+)")
# a url on such a line is one the pipeline calls, not a link in a docstring
_CALLED = re.compile(r"base_url|api_url|api_base|endpoint|\burl\b|_URL|client", re.I)

MATCHES_PER_API = 40
MODEL_FILES = 120
LINE_CHARS = 160
FILE_BYTES = 400_000


@dataclass
class FoundApi:
    name: str
    known: Optional[KnownApi]
    hosts: Set[str] = field(default_factory=set)
    evidence: List[str] = field(default_factory=list)
    # `configured` when the `apis` input names it, else `discovered`
    origin: str = "discovered"
    url: str = ""
    # the url was found at a common changelog location, not given or known
    guessed: bool = False


def _readable(path: Path) -> bool:
    # credential files are never read, whatever they would match
    if path.name.endswith("secrets.toml") or path.name.startswith(".env"):
        return False
    return path.suffix in SUFFIXES and path.stat().st_size <= FILE_BYTES


def workspace_files(root: Path) -> List[Path]:
    """Text files of the workspace, outside environments, caches and agent folders."""
    found = []
    for folder, dirs, names in os.walk(root):
        # pruned in place so a virtual environment is never walked
        dirs[:] = sorted(d for d in dirs if d not in SKIPPED_DIRS)
        found.extend(p for p in (Path(folder) / n for n in sorted(names)) if _readable(p))
    return found


def _imports(path: Path, root: Path) -> List[str]:
    """Absolute module names a Python file imports, relative ones resolved."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return []
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                package = path.parent.relative_to(root).parts
                package = package[: len(package) - (node.level - 1)]
                base = ".".join(filter(None, [*package, base]))
            names.append(base)
            names.extend(f"{base}.{alias.name}" for alias in node.names)
    return names


def _module_file(root: Path, module: str) -> Optional[Path]:
    if not module:
        return None
    relative = Path(*module.split("."))
    for candidate in (root / f"{relative}.py", root / relative / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def production_files(root: Path) -> List[Path]:
    """Python files the deployment module reaches, or every one without a deployment."""
    deployment = root / DEPLOYMENT_MODULE
    if not deployment.is_file():
        return [p for p in workspace_files(root) if p.suffix == ".py"]
    seen: Dict[Path, None] = {deployment: None}
    queue = [deployment]
    while queue:
        current = queue.pop()
        for module in _imports(current, root):
            rel = os.path.relpath(current.parent, root)
            # an absolute name resolves from the root, a sibling import from the file's folder
            for base in (root, root / rel):
                found = _module_file(base, module)
                if found and found not in seen:
                    seen[found] = None
                    queue.append(found)
    return list(seen)


def config_files(root: Path) -> List[Path]:
    """The workspace's dlt config files, which hold base urls and api versions."""
    folder = root / ".dlt"
    return sorted(p for p in folder.glob("*.toml") if _readable(p)) if folder.is_dir() else []


def _lines(path: Path) -> List[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except (UnicodeDecodeError, OSError):
        return []


def code_strings(path: Path) -> List[Tuple[int, str]]:
    """`(line, text)` of every string literal in Python code, docstrings left out."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return []
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                docstrings.add(id(first.value))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in docstrings:
                found.append((node.lineno, node.value))
        elif isinstance(node, ast.JoinedStr):
            # an f-string keeps its literal parts, each value becomes a `{}` label
            parts = [v.value if isinstance(v, ast.Constant) else "{}" for v in node.values]
            found.append((node.lineno, "".join(str(p) for p in parts)))
    return found


def discover(root: Path) -> List[FoundApi]:
    """The APIs production code calls, known ones by name and others by host."""
    found: Dict[str, FoundApi] = {}

    def add(known: Optional[KnownApi], name: str, evidence: str, host: str = "") -> None:
        api = found.setdefault(name, FoundApi(name=name, known=known))
        if host:
            api.hosts.add(host)
        # one piece of evidence per file is enough to find it
        files = {e.split(" ")[0] for e in api.evidence}
        if len(api.evidence) < 5 and evidence.split(" ")[0] not in files:
            api.evidence.append(evidence)

    known_apis = load(root)
    code = production_files(root)
    called = [(p, n, text) for p in code for n, text in code_strings(p)]
    # a config file has no syntax tree, so a url counts on a line naming a url or client
    called += [
        (p, n, line)
        for p in config_files(root)
        for n, line in enumerate(_lines(p), start=1)
        if _CALLED.search(line)
    ]
    for path, number, text in called:
        rel = path.relative_to(root).as_posix()
        for host in _URL.findall(text):
            host = re.sub(r"\{[^}]*\}", "*", host.lower())
            if IGNORED_HOSTS.search(host) or host.strip("*.").count(".") < 1:
                continue
            known = match_host(host, known_apis)
            add(known, known.name if known else host.lstrip("*."), f"{rel} line {number}", host)
    for path in code:
        rel = path.relative_to(root).as_posix()
        for module in _imports(path, root):
            known = match_module(module, known_apis)
            if known:
                add(known, known.name, f"{rel} imports `{module}`")
    return sorted(found.values(), key=lambda api: api.name)


def configure(given: str, discovered: List[FoundApi], root: Optional[Path] = None) -> List[FoundApi]:
    """The APIs the `apis` input names, `name` or `name=url`, with what discovery found."""
    by_name = {api.name: api for api in discovered}
    chosen = []
    for item in (part.strip() for part in given.split(",")):
        if not item:
            continue
        name, _, url = (piece.strip() for piece in item.partition("="))
        name = name.lower()
        api = by_name.get(name) or FoundApi(name=name, known=load(root).get(name))
        api.origin, api.url = "configured", url
        chosen.append(api)
    return chosen


def _pattern(api: FoundApi) -> "re.Pattern[str]":
    words = [re.escape(h) for h in api.hosts] + [re.escape(api.name)]
    if api.known:
        words.append(api.known.modules.pattern)
    return re.compile("|".join(words), re.I)


def usage(root: Path, apis: List[FoundApi]) -> Dict[str, List[str]]:
    """`path:line: text` of every workspace line naming each API, per API."""
    patterns = {api.name: _pattern(api) for api in apis}
    hits: Dict[str, List[str]] = {api.name: [] for api in apis}
    for path in workspace_files(root):
        rel = path.relative_to(root).as_posix()
        for number, line in enumerate(_lines(path), start=1):
            for name, pattern in patterns.items():
                if len(hits[name]) < MATCHES_PER_API and pattern.search(line):
                    # a backtick would close the code span the line is rendered in
                    shown = redact(line.strip())[:LINE_CHARS].replace("`", "'")
                    hits[name].append(f"{rel}:{number}: {shown}")
    return hits


def model_files(root: Path) -> List[str]:
    """SQL files and Python files under a model folder: the downstream models."""
    found = []
    for path in workspace_files(root):
        rel = path.relative_to(root)
        folders = {part.lower() for part in rel.parts[:-1]}
        if path.suffix == ".sql" or (path.suffix == ".py" and MODEL_DIRS & folders):
            found.append(rel.as_posix())
    return found[:MODEL_FILES]


def render_usage(root: Path, apis: List[FoundApi]) -> str:
    """Matching lines per API, then the model files, as markdown."""
    parts = []
    for name, lines in usage(root, apis).items():
        parts.append(f"### {name}\n")
        parts.extend(f"- `{line}`" for line in lines)
        if not lines:
            parts.append("No workspace file names this API.")
        elif len(lines) == MATCHES_PER_API:
            parts.append(f"- (first {MATCHES_PER_API} matches only; `Grep` for the rest)")
        parts.append("")
    models = model_files(root)
    parts.append("### Downstream model files\n")
    parts.extend(f"- `{m}`" for m in models)
    if not models:
        parts.append("None found.")
    return "\n".join(parts)


_PATH_LITERAL = re.compile(r"[\"']([A-Za-z0-9_{}.:\-]*/[A-Za-z0-9_{}.:/\-]*)[\"']")
# a `path` key or argument names an endpoint even when it has no slash
_PATH_KEY = re.compile(r"[\"']?path[\"']?\s*[:=]\s*[\"']([^\"']+)[\"']")


def api_files(root: Path, api: FoundApi) -> List[Path]:
    """The files where an API is used, or all production code when none is known."""
    named = {root / e.split(" ")[0] for e in api.evidence}
    files = [p for p in named if p.is_file() and p.name != DEPLOYMENT_MODULE]
    return sorted(files) or production_files(root) + config_files(root)


def resource_paths(root: Path, files: Optional[List[Path]] = None) -> List[Tuple[str, str]]:
    """`(path, where)` for every literal path the given code calls, urls included."""
    found = []
    for path in files if files is not None else production_files(root) + config_files(root):
        rel = path.relative_to(root).as_posix()
        for number, line in enumerate(_lines(path), start=1):
            for url in re.findall(r"https?://[A-Za-z0-9.-]+(/[^\s\"'`]*)", line):
                if url.strip("/"):
                    found.append((url, f"{rel} line {number}"))
            literals = _PATH_LITERAL.findall(re.sub(r"https?://\S+", "", line))
            for literal in dict.fromkeys(literals + _PATH_KEY.findall(line)):
                # an import path or a file name is no endpoint
                if not literal.endswith((".py", ".sql", ".toml", ".json")) and literal.strip("/"):
                    found.append((literal, f"{rel} line {number}"))
    return found


def model_lines(root: Path) -> List[Tuple[str, str]]:
    """`(where, line)` for every line of the downstream model files."""
    found = []
    for rel in model_files(root):
        for number, line in enumerate(_lines(root / rel), start=1):
            found.append((f"{rel} line {number}", line))
    return found


_DATASET = re.compile(r"""dataset_name\s*[=:]\s*f?["']([A-Za-z_][\w]*)["']""")


def datasets(root: Path, api: "FoundApi") -> List[str]:
    """The datasets the files calling an API load into, from their `dataset_name`."""
    found: List[str] = []
    for path in api_files(root, api):
        for line in _lines(path):
            found.extend(_DATASET.findall(line))
    return list(dict.fromkeys(found))


def downstream(root: Path, api: "FoundApi", models: List[Tuple[str, str]]) -> Optional[List[str]]:
    """Model files reading an API's datasets, or None when its datasets are unknown."""
    names = datasets(root, api)
    if not names:
        return None
    pattern = re.compile(rf"\b({'|'.join(map(re.escape, names))})\b")
    files = [where.rsplit(" line ", 1)[0] for where, line in models if pattern.search(line)]
    return list(dict.fromkeys(files))


_PIN = re.compile(
    # a name holding `version` set to a date or a dotted number, or a version segment in a url
    r"(?i)version[\w-]*[\"']?\s*[:=]\s*[\"']?(\d{4}-\d{2}(?:-\d{2})?|v?\d+(?:\.\d+)+)"
    r"|/api/(\d{4}-\d{2})/|/(v\d+(?:\.\d+)?)/"
)


def pinned_tokens(pins: List[str]) -> List[str]:
    """The version values the pin lines hold, such as `2022-11-28` or `v39.0`."""
    return list(dict.fromkeys(next(g for g in m.groups() if g) for p in pins for m in _PIN.finditer(p)))


def pinned_versions(root: Path, api: "FoundApi") -> List[str]:
    """Lines of the files that call an API that pin the API version it is served."""
    files = {e.split(" ")[0] for e in api.evidence}
    pins = []
    for rel in sorted(files):
        path = root / rel
        if not path.is_file():
            continue
        for number, line in enumerate(_lines(path), start=1):
            if _PIN.search(line):
                shown = redact(line.strip())[:LINE_CHARS].replace("`", "'")
                pins.append(f"`{shown}` ({rel} line {number})")
    return pins[:6]


def code_lines(root: Path, files: Optional[List[Path]] = None) -> List[Tuple[str, str]]:
    """`(where, line)` for every line of the given code, skipping imports and comments."""
    found = []
    for path in files if files is not None else production_files(root):
        rel = path.relative_to(root).as_posix()
        for number, line in enumerate(_lines(path), start=1):
            if not line.lstrip().startswith(("import ", "from ", "#")):
                found.append((f"{rel} line {number}", line))
    return found
