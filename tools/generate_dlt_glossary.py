#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from nltk.stem import PorterStemmer

# ---------------------------------------------------------------------------
# Griffe filter — inlined from filter_griffe.py
# ---------------------------------------------------------------------------

EXCLUDED_NAMESPACES: tuple[str, ...] = (
    "dlt.common.libs",
    "dlt.extract.exceptions",
    "dlt.common.exceptions",
    "dlt.destinations.exceptions",
    "dlt.pipeline.exceptions",
    "dlt.pipeline.progress",
    "dlt.dataset.utils",
    "dlt.common.arithmetics",
    "dlt.common.wei",
    "dlt.common.data_types.type_helpers",
    "dlt.common.typing.TypedDict",
    "dlt.common.known_env",
    "dlt.common.schema.utils",
    "dlt.common.utils",
    "dlt.common.normalizers.typing",
    "dlt.common.normalizers.naming",
    "dlt.common.storages",
    "dlt.common.time",
    "dlt.common.versioned_state",
    "dlt.common.warnings",
    "dlt.destinations.queries",
    "dlt.destinations.typing",
    "dlt.extract.items_transform",
    "dlt.extract.items",
    "dlt.extract.utils",
    "dlt.helpers",
    "dlt.pipeline.helpers",
    "dlt.common.configuration.exceptions",
    "dlt.common.configuration.inject",
    "dlt.common.data_writers.escape",
    "dlt.common.data_writers.exceptions",
    "dlt.common.data_writers.writers",
    "dlt.common.runners",
    "dlt.common.runtime",
    "dlt.common.schema.exceptions",
    "dlt.common.schema.normalizers",
    "dlt.sources.helpers.rest_client.detector",
    "dlt.common.json",
    "dlt.common.jsonpath",
    "dlt.common.logger",
    "dlt.common.pendulum",
    "dlt.common.typing",
    "dlt.dataset.exceptions",
)

_KEY_MAP: dict[str, str] = {
    "parameters": "params",
    "annotation":  "type",
    "returns":     "ret",
    "docstring":   "doc",
    "target_path": "path",
    "labels":      "tags",
    "decorators":  "decos",
}

_DROP_ALWAYS = frozenset([
    "name", "filepath", "relative_filepath", "relative_package_filepath",
    "git_info", "source_link", "lineno", "endlineno", "runtime", "analysis",
    "exports", "imports", "public", "is_deprecated", "is_private",
    "is_class_private", "is_special", "is_imported", "is_exported",
    "is_wildcard_exposed", "inherited",
])

_DROP_EXPR = frozenset(["cls", "member", "function", "implicit", "is_async"])


def _clean_expr(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _clean_expr(v) for k, v in value.items() if k not in _DROP_EXPR}
    if isinstance(value, list):
        return [_clean_expr(item) for item in value]
    return value


def _expr_to_str(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_expr_to_str(v) for v in value]
    if not isinstance(value, dict):
        return value

    cls = value.get("cls")

    if cls == "ExprName":
        return value["name"]
    if cls == "ExprAttribute":
        parts = [_expr_to_str(p) for p in value.get("values", [])]
        if all(isinstance(p, str) for p in parts):
            return ".".join(parts)
    if cls == "ExprSubscript":
        left = _expr_to_str(value.get("left"))
        slice_ = _expr_to_str(value.get("slice"))
        if isinstance(left, str) and isinstance(slice_, str):
            return f"{left}[{slice_}]"
    if cls == "ExprBinOp":
        left = _expr_to_str(value.get("left"))
        op = value.get("operator", "|")
        right = _expr_to_str(value.get("right"))
        if isinstance(left, str) and isinstance(right, str):
            return f"{left} {op} {right}"
    if cls == "ExprBoolOp":
        op = value.get("operator", "and")
        parts = [_expr_to_str(v) for v in value.get("values", [])]
        if all(isinstance(p, str) for p in parts):
            return f" {op} ".join(parts)
    if cls == "ExprTuple":
        elements = [_expr_to_str(e) for e in value.get("elements", [])]
        if all(isinstance(e, str) for e in elements):
            inner = ", ".join(elements)
            return inner if value.get("implicit", False) else f"({inner})"
    if cls == "ExprList":
        elements = [_expr_to_str(e) for e in value.get("elements", [])]
        if all(isinstance(e, str) for e in elements):
            return "[" + ", ".join(elements) + "]"
    if cls == "ExprSet":
        elements = [_expr_to_str(e) for e in value.get("elements", [])]
        if all(isinstance(e, str) for e in elements):
            return "{" + ", ".join(elements) + "}"
    if cls == "ExprCall":
        func = _expr_to_str(value.get("function"))
        args = [_expr_to_str(a) for a in value.get("arguments", [])]
        if isinstance(func, str) and all(isinstance(a, str) for a in args):
            return f"{func}({', '.join(args)})"
    if cls == "ExprKeyword":
        name = value.get("name")
        val = _expr_to_str(value.get("value"))
        if isinstance(val, str):
            return f"{name}={val}"
    if cls == "ExprVarPositional":
        val = _expr_to_str(value.get("value"))
        if isinstance(val, str):
            return f"*{val}"
    if cls == "ExprVarKeyword":
        val = _expr_to_str(value.get("value"))
        if isinstance(val, str):
            return f"**{val}"
    if cls == "ExprUnaryOp":
        op = value.get("operator", "")
        val = _expr_to_str(value.get("value"))
        if isinstance(val, str):
            sep = " " if op.isalpha() else ""
            return f"{op}{sep}{val}"
    if cls == "ExprSlice":
        lower = _expr_to_str(value.get("lower")) or ""
        upper = _expr_to_str(value.get("upper")) or ""
        step = value.get("step")
        s = f"{lower}:{upper}"
        if step is not None:
            s += f":{_expr_to_str(step)}"
        return s
    if cls == "ExprIfExp":
        body = _expr_to_str(value.get("body"))
        test = _expr_to_str(value.get("test"))
        orelse = _expr_to_str(value.get("orelse"))
        if all(isinstance(x, str) for x in (body, test, orelse)):
            return f"{body} if {test} else {orelse}"

    return _clean_expr(value)


def _filter_docstring(ds: dict) -> dict:
    out: dict[str, Any] = {"value": ds.get("value", "")}
    parsed = ds.get("parsed")
    if parsed:
        out["parsed"] = parsed
    return out


def _filter_decorator(dec: dict) -> Any:
    raw = dec.get("value")
    return _expr_to_str(raw) if raw is not None else None


def filter_object(
    obj: dict,
    public_only: bool = False,
    seen_targets: set[str] | None = None,
    current_path: str = "",
) -> dict | None:
    if seen_targets is None:
        seen_targets = set()

    if not isinstance(obj, dict):
        return obj

    kind = obj.get("kind")

    if kind == "alias":
        target = obj.get("target_path")
        if (
            target is None
            or not target.startswith("dlt")
            or target.startswith(EXCLUDED_NAMESPACES)
            or target in seen_targets
        ):
            return None
        seen_targets.add(target)
        result: dict[str, Any] = {_KEY_MAP["target_path"]: target}
        if obj.get("path"):
            result["path"] = obj["path"]
        return result

    if public_only and not obj.get("is_public", True):
        return None

    result = {}
    for key, value in obj.items():
        if key in _DROP_ALWAYS:
            continue
        if key == "docstring" and isinstance(value, dict):
            result[_KEY_MAP["docstring"]] = _filter_docstring(value)
        elif key == "decorators" and isinstance(value, list):
            filtered_decs = [_filter_decorator(d) for d in value if d]
            if filtered_decs:
                result[_KEY_MAP["decorators"]] = filtered_decs
        elif key == "parameters":
            continue
        elif key == "members" and isinstance(value, dict):
            filtered_members: dict[str, Any] = {}
            for member_name, member_val in value.items():
                if member_name.startswith("_") and member_name not in ("__init__", "__call__"):
                    continue
                member_path = f"{current_path}.{member_name}" if current_path else member_name
                if member_path.startswith(EXCLUDED_NAMESPACES):
                    continue
                filtered = filter_object(member_val, public_only=public_only, seen_targets=seen_targets, current_path=member_path)
                if filtered is not None:
                    filtered_members[member_name] = filtered
            if filtered_members:
                result["members"] = filtered_members
        elif key == "bases":
            if value:
                result["bases"] = [_expr_to_str(b) for b in value]
            continue
        elif key in ("returns", "annotation", "value") and value is not None:
            result[_KEY_MAP.get(key, key)] = _expr_to_str(value)
        else:
            result[_KEY_MAP.get(key, key)] = value

    if result.get("kind") == "attribute":
        del result["kind"]
        tags = result.pop("tags", None)
        if tags:
            result["kind"] = tags

    return result

# ---------------------------------------------------------------------------
# Step 1: dump griffe API to dlt-api.json
# ---------------------------------------------------------------------------

result = subprocess.run(
    ["uv", "run", "griffe", "dump", "dlt"],
    capture_output=True,
    text=True,
    check=True,
)

# ---------------------------------------------------------------------------
# Step 2: filter to filtered.json
# ---------------------------------------------------------------------------
data = json.loads(result.stdout)
seen_targets: set[str] = set()
if isinstance(data, dict) and "kind" not in data:
    filtered = {
        k: filter_object(v, seen_targets=seen_targets, current_path=k)
        for k, v in data.items()
    }
else:
    filtered = filter_object(data, seen_targets=seen_targets)

filtered_str = json.dumps(filtered, indent=2, ensure_ascii=False)
Path(".vocabulary/dlt-api.json").write_text(filtered_str, encoding="utf-8")

# ---------------------------------------------------------------------------
# Step 3: compress to dlt-api-compressed.json
# ---------------------------------------------------------------------------
compressed_str = json.dumps(filtered, ensure_ascii=False)
Path(".vocabulary/dlt-api-compressed.json").write_text(compressed_str, encoding="utf-8")
# ---------------------------------------------------------------------------
# Step 4: mine words to frequency.txt
# ---------------------------------------------------------------------------
FILTER_WORDS = {
    "kind", "value", "n", "attribute", "the", "type", "function", "params",
    "str", "ret", "to", "instance", "null", "self", "name", "doc", "class",
    "optional", "path", "a", "none", "of", "membersis", "be", "bases", "with",
    "and", "if", "decos", "that", "or", "dict", "common", "on", "get", "will",
    "key", "true", "false", "not", "by", "are", "used", "as", "this", "is",
    "in", "for", "bool", "any", "from", "tags", "it", "can", "use",
    "classmethod", "kwargs", "all", "when", "set", "abstractmethod", "union",
    "nargs", "keys", "tuple", "arguments", "staticmethod", "should", "string",
    "nreturns", "members", "module", "list", "only", "an", "which", "into",
    "typing", "callable", "args", "raise", "cls", "has", "at", "may", "base",
    "method", "other", "x", "no", "you", "return", "more", "after", "ie",
    "uses", "param", "nthis", "before", "such", "same", "each", "also",
    "whether", "nif", "f", "via", "e.g.", "like", "was", "s", "we", "so",
    "within", "per", "then", "def", "during", "non", "nall", "they", "c",
    "otherwise", "here", "its", "once", "your", "nin", "nto", "being", "them",
    "t.", "but", "most", "either", "kw", "their", "v", "sig", "impl",
    "you're",
}

harper_absolute_path = str(Path().home() / ".cargo/bin/harper-cli")
mine_result = subprocess.run(
    [harper_absolute_path, "mine-words", "dlt-api.json"],
    capture_output=True,
    text=True,
    check=True,
)

words = [line.strip() for line in mine_result.stdout.splitlines()[::-1] if line.strip()]
words_filtered = [w for w in words if w.lower() not in FILTER_WORDS]

stemmer = PorterStemmer()
seen_stems: set[str] = set()
deduplicated = []
for w in words_filtered:
    stem = stemmer.stem(w.lower())
    if stem not in seen_stems:
        seen_stems.add(stem)
        deduplicated.append(w)

Path(".vocabulary/frequency.txt").write_text("\n".join(deduplicated) + "\n", encoding="utf-8")
