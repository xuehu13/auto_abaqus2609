from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile


class PipelineError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def canonical(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False)


def digest(obj):
    return hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def tree_hash(root):
    root = Path(root)
    return digest({str(p.relative_to(root)).replace("\\", "/"): file_hash(p)
                   for p in sorted(root.rglob("*")) if p.is_file()
                   and not any(x in {"__pycache__", "build", ".git", "cases"}
                               for x in p.relative_to(root).parts)})


def atomic_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def atomic_json(path, obj):
    atomic_text(path, json.dumps(obj, indent=2, ensure_ascii=False,
                                 allow_nan=False) + "\n")


def safe_id(value):
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,47}", value):
        raise PipelineError("CONFIG_INVALID", "ID must start with a letter and use ASCII letters/digits/_/- (max 48).")
    return value


def reserve_directory(path):
    path = Path(path)
    try:
        path.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise PipelineError("OUTPUT_EXISTS", "Use a new attempt directory; existing outputs are never overwritten: " + str(path)) from exc
    return path
