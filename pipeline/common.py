"""Shared primitives: errors, JSON/hash IO, config checks, attempt directories.

This is a research script for one user. It keeps only primitives that several
modules really need; anything used once lives in the module that uses it.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile


class PipelineError(RuntimeError):
    """Fatal pipeline error with a stable machine-readable code.

    ``fatal=True`` marks global failures a batch must not swallow: instead of
    recording the case and moving on, the whole batch stops. Used when the Abaqus
    process tree of a timed-out case could not be terminated — starting another
    Abaqus job while that case's solver still runs would overlap CPU/memory/
    licenses.
    """

    def __init__(self, code: str, message: str, fatal: bool = False):
        self.code = code
        self.fatal = bool(fatal)
        super().__init__(message)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, obj):
    """Atomic JSON write (UTF-8, one trailing newline)."""
    text = json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    atomic_text(path, text)


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


def safe_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,47}", value):
        raise PipelineError("CONFIG_INVALID",
                            "ID must start with a letter and use ASCII letters/digits/_/- (max 48).")
    return value


def require_keys(config, path, required=(), optional=(), label="config"):
    """Reject unknown keys and report missing/unknown keys together.

    A typo in a config key must fail fast: a silently ignored key means the model
    that runs is not the model the file describes. Keep it simple - name the file,
    the offending keys and the allowed key set.
    """
    if not isinstance(config, dict):
        raise PipelineError("CONFIG_INVALID",
                            label + " must be a JSON object: " + str(path))
    allowed = set(required) | set(optional)
    missing = sorted(key for key in required if key not in config)
    unknown = sorted(key for key in config if key not in allowed)
    if missing or unknown:
        problems = []
        if missing:
            problems.append("missing keys " + repr(missing))
        if unknown:
            problems.append("unknown keys " + repr(unknown))
        raise PipelineError("CONFIG_INVALID",
                            label + " " + str(path) + " has " + " and ".join(problems)
                            + "; allowed keys are " + repr(sorted(allowed)))
    return config


def finite(value, name, *, positive=False, minimum=None, maximum=None, code="CONFIG_INVALID"):
    """Require a real finite number (NaN/Inf rejected).

    NaN is a scientific safety issue, not a style issue: comparisons against NaN
    are always False, so a NaN parameter silently disables whatever it feeds.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PipelineError(code, name + " must be a number, got " + repr(value))
    number = float(value)
    if not math.isfinite(number):
        raise PipelineError(code, name + " must be finite (NaN/Inf rejected), got " + repr(value))
    if positive and number <= 0:
        raise PipelineError(code, name + " must be > 0, got " + repr(value))
    if minimum is not None and number < minimum:
        raise PipelineError(code, name + " must be >= " + repr(minimum) + ", got " + repr(value))
    if maximum is not None and number > maximum:
        raise PipelineError(code, name + " must be <= " + repr(maximum) + ", got " + repr(value))
    return number


def positive_int(value, name, *, maximum=None):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise PipelineError("CONFIG_INVALID", name + " must be an integer >= 1, got " + repr(value))
    if maximum is not None and value > maximum:
        raise PipelineError("CONFIG_INVALID", name + " must be <= " + repr(maximum))
    return value


def boolean(value, name):
    if not isinstance(value, bool):
        raise PipelineError("CONFIG_INVALID", name + " must be true or false, got " + repr(value))
    return value


def reserve_directory(path):
    """Create a NEW attempt directory; existing results are never overwritten."""
    path = Path(path)
    try:
        path.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise PipelineError("OUTPUT_EXISTS",
                            "Use a new attempt directory; existing outputs are never "
                            "overwritten: " + str(path)) from exc
    return path


def git_provenance(root):
    """Best-effort git commit/dirty record; never fatal, never a scientific input."""
    def run(*args):
        try:
            result = subprocess.run(["git", *args], cwd=str(root), capture_output=True,
                                    text=True, timeout=20)
        except (OSError, subprocess.SubprocessError):
            return None
        return result.stdout.strip() if result.returncode == 0 else None

    commit = run("rev-parse", "HEAD")
    status = run("status", "--porcelain")
    return {"git_commit": commit,
            "git_dirty": None if status is None else bool(status)}
