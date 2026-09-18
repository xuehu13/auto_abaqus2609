"""Abaqus side: runtime config, launcher gate, deck staging, Data Check, solve.

Two stages, one implementation of every shared rule:

* Data Check consumes a ``build_report.json`` and runs ``abaqus ... datacheck``.
* Solve consumes an ACCEPTED datacheck attempt and runs ``abaqus ... analysis``.

Both copy the deck from their source attempt into a NEW attempt directory and
verify every SHA on the way in and on the way out, so "the solve ran the deck the
data check accepted" is checked against bytes, not against folder names.

Runtime values (Abaqus launcher, cpus, standard_parallel, wall limit) come from
``config/runtime.json`` (machine-local, git-ignored) with CLI overrides; they are
never scientific inputs and never enter the deck.

Scope guards: no long unattended solve is started by default behaviour, no retry,
no watchdog (the wall limit terminates the case's process tree; it does not
restart anything), no ODB reading (that is the extraction stage), and a job is
never judged by its return code alone.
"""
from __future__ import annotations

import ctypes
import hashlib
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from .build import (DECK_ROOT, EXPLICIT_DYNAMIC, STANDARD_DYNAMIC_IMPLICIT, include_paths)
from .common import (PipelineError, boolean, file_hash, finite, positive_int,
                     read_json, require_keys, write_json)

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PATH = ROOT / "config" / "runtime.json"
RUNTIME_EXAMPLE_PATH = ROOT / "config" / "runtime.example.json"

STAGES = ("datacheck", "solve")
#: Per-stage runtime defaults. Conservative on purpose: one process unless the
#: machine-local runtime file says otherwise.
RUNTIME_DEFAULTS = {"datacheck": {"cpus": 1, "standard_parallel": "solver",
                                  "mp_mode": None, "timeout_s": 3600},
                    "solve": {"cpus": 4, "standard_parallel": "solver",
                              "mp_mode": None, "timeout_s": 14400}}
ALLOWED_STANDARD_PARALLEL = ("all", "solver")
#: Optional Abaqus parallel mode; 'threads' avoids the MPI/smpd path that failed
#: on this machine during the Explicit A/B experiment.
ALLOWED_MP_MODE = ("threads", "mpi")
_RUNTIME_KEYS = ("abaqus", "cgal", "results", "datacheck", "solve")
_ABAQUS_KEYS = ("launcher", "release_required")
_CGAL_KEYS = ("executable",)
#: Disk policy, not a scientific parameter: dropping a solved ODB is allowed only
#: after extraction succeeded, and never for a failed case.
_RESULTS_KEYS = ("keep_odb", "curve_qa_policy")
_STAGE_KEYS = ("cpus", "standard_parallel", "mp_mode", "timeout_s")

# --- Abaqus stays an EXTERNAL runtime ---------------------------------------
# The Pixi controller must not leak its Python, site-packages, DLL search path or
# activation markers into the launcher (mixing the two Python environments is the
# documented way to get subtly wrong imports). Only a known block list is removed;
# everything else is inherited, because the Windows batch launcher needs the
# normal system environment.
BLOCKED_ENV_VARS = (
    "PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONUSERBASE", "PYTHONEXECUTABLE",
    "PYTHONNOUSERSITE", "PYTHONDONTWRITEBYTECODE", "PYTHONIOENCODING", "PYTHONUTF8",
    "PYTHONLEGACYWINDOWSSTDIO",
    "PIXI_ENVIRONMENT_NAME", "PIXI_ENVIRONMENT_PLATFORMS", "PIXI_PROJECT_NAME",
    "PIXI_PROJECT_ROOT", "PIXI_EXE", "PIXI_IN_SHELL",
    "CONDA_PREFIX", "CONDA_PREFIX_1", "CONDA_DEFAULT_ENV", "CONDA_PROMPT_MODIFIER",
    "CONDA_SHLVL", "CONDA_EXE", "CONDA_PYTHON_EXE",
    "VIRTUAL_ENV", "VIRTUAL_ENV_PROMPT",
)


def abaqus_env(base=None):
    """Child environment for the Abaqus launcher (block list removed)."""
    source = os.environ if base is None else base
    return {name: value for name, value in source.items() if name not in BLOCKED_ENV_VARS}


def blocked_env_vars(base=None):
    """Names of block-listed variables actually present (recorded in reports)."""
    source = os.environ if base is None else base
    return sorted(name for name in BLOCKED_ENV_VARS if name in source)


def _utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_runtime(path=None):
    """Load config/runtime.json, or the example template when it does not exist."""
    resolved = Path(path) if path else RUNTIME_PATH
    if not path and not resolved.is_file():
        resolved = RUNTIME_EXAMPLE_PATH
    if not resolved.is_file():
        return {"path": None, "abaqus": {}, "cgal": {}, "results": {}}
    configured = require_keys(read_json(resolved), resolved, (), _RUNTIME_KEYS, "runtime config")
    abaqus = require_keys(configured.get("abaqus", {}), resolved, (), _ABAQUS_KEYS,
                          "runtime.abaqus")
    cgal = require_keys(configured.get("cgal", {}), resolved, (), _CGAL_KEYS, "runtime.cgal")
    results = require_keys(configured.get("results", {}), resolved, (), _RESULTS_KEYS,
                           "runtime.results")
    if "keep_odb" in results:
        boolean(results["keep_odb"], "runtime.results.keep_odb")
    for stage in STAGES:
        require_keys(configured.get(stage, {}), resolved, (), _STAGE_KEYS, "runtime." + stage)
    configured["path"] = str(resolved)
    configured["abaqus"] = abaqus
    configured["cgal"] = cgal
    configured["results"] = results
    return configured


def resolve_runtime(stage, runtime, *, cpus=None, standard_parallel=None, timeout_s=None,
                    mp_mode=None):
    """Resolve one stage's runtime values: CLI > runtime file > built-in default."""
    if stage not in STAGES:
        raise PipelineError("CONFIG_INVALID", "Unknown stage: " + repr(stage))
    values = dict(RUNTIME_DEFAULTS[stage])
    source = "default"
    configured = runtime.get(stage) or {}
    for key in values:
        if configured.get(key) is not None:
            values[key] = configured[key]
            source = "runtime_file"
    if cpus is not None:
        values["cpus"] = cpus
        source = "cli"
    if standard_parallel is not None:
        values["standard_parallel"] = standard_parallel
        source = "cli"
    if mp_mode is not None:
        values["mp_mode"] = mp_mode
        source = "cli"
    if timeout_s is not None:
        values["timeout_s"] = timeout_s
        source = "cli"
    values["cpus"] = positive_int(values["cpus"], "cpus", maximum=1024)
    parallel = values["standard_parallel"]
    if not isinstance(parallel, str) or parallel.strip().lower() not in ALLOWED_STANDARD_PARALLEL:
        raise PipelineError("CONFIG_INVALID", "standard_parallel must be one of "
                            + repr(list(ALLOWED_STANDARD_PARALLEL)) + ": " + repr(parallel))
    values["standard_parallel"] = parallel.strip().lower()
    mode = values["mp_mode"]
    if mode is not None:
        if not isinstance(mode, str) or mode.strip().lower() not in ALLOWED_MP_MODE:
            raise PipelineError("CONFIG_INVALID", "mp_mode must be null or one of "
                                + repr(list(ALLOWED_MP_MODE)) + ": " + repr(mode))
        values["mp_mode"] = mode.strip().lower()
    timeout = finite(values["timeout_s"], "timeout_s", positive=True)
    if int(timeout) != timeout:
        raise PipelineError("CONFIG_INVALID", "timeout_s must be whole seconds: " + repr(timeout))
    values["timeout_s"] = int(timeout)
    values["source"] = source
    return values


# --- launcher and release gate ----------------------------------------------

#: The release year must be attached to an "Abaqus" token. A bare 20xx would match
#: the year inside an install path such as "E:/ABAQUS/2026/Commands/abaqus.bat"
#: and report it as the solver's release. The 2026 launcher prints its release with
#: the digits spaced out ("Abaqus 2 0 2 6"), so spaces between digits are allowed.
_RELEASE_PATTERN = re.compile(r"\bAbaqus(?:\s*/\s*\w+)?[\s:]+((?:2\s*0\s*2\s*\d))\b", re.I)


def parse_release_year(text):
    if not isinstance(text, str):
        return None
    match = _RELEASE_PATTERN.search(text)
    return int(re.sub(r"\s+", "", match.group(1))) if match else None


def resolve_launcher(runtime, explicit=None):
    """Resolve the Abaqus launcher: --abaqus-command > runtime.abaqus.launcher."""
    candidate = explicit or (runtime.get("abaqus") or {}).get("launcher")
    if not candidate:
        raise PipelineError("EXTERNAL_TOOL_MISSING",
                            "No Abaqus launcher configured. Set abaqus.launcher in "
                            + str(RUNTIME_PATH) + " (see config/runtime.example.json) or pass "
                            "--abaqus-command.")
    path = Path(candidate)
    if not path.is_absolute() or not path.is_file():
        raise PipelineError("EXTERNAL_TOOL_MISSING",
                            "Abaqus launcher must be an existing absolute file path: "
                            + repr(candidate))
    return {"path": str(path)}


def query_release(launcher_path):
    """Ask the launcher for its release; failure is recorded, never fatal here."""
    try:
        completed = subprocess.run([str(launcher_path), "information=release"],
                                   capture_output=True, text=True, encoding="utf-8",
                                   errors="replace", timeout=120, env=abaqus_env())
    except (OSError, subprocess.SubprocessError) as exc:
        return {"release_string": None, "release_year": None, "return_code": None,
                "error": str(exc)}
    text = (completed.stdout or "") + (completed.stderr or "")
    year = parse_release_year(text)
    return {"release_string": ("Abaqus %d" % year) if year else None,
            "release_year": year, "return_code": completed.returncode}


def enforce_release_gate(launcher_path, required, release=None):
    """Refuse to submit a job against an unknown or unexpected Abaqus release."""
    info = release if release is not None else query_release(launcher_path)
    year = info.get("release_year")
    gate = {"release_required": None if required is None else str(required),
            "release_reported": info.get("release_string"),
            "release_year": None if year is None else str(year)}
    if not required:
        gate["gate"] = "not_configured"
        return gate
    if year is None:
        raise PipelineError("ABAQUS_RELEASE_MISMATCH",
                            "Cannot determine the launcher's Abaqus release (reported: "
                            + repr(info.get("release_string")) + "); required release: "
                            + repr(required) + ". Set abaqus.launcher in "
                            + str(RUNTIME_PATH) + " or fix abaqus.release_required.")
    if str(year) != str(required):
        raise PipelineError("ABAQUS_RELEASE_MISMATCH",
                            "Required Abaqus release " + repr(required)
                            + " but the launcher reports " + str(year) + ".")
    gate["gate"] = "enforced"
    return gate


# --- job naming -------------------------------------------------------------

_JOB_NAME_RE = re.compile(r"^[A-Za-z0-9_]{1,64}$")
_STAGE_SUFFIX = {"datacheck": "dc", "solve": "solve"}


def validate_job_name(job_name):
    if not isinstance(job_name, str) or not _JOB_NAME_RE.match(job_name):
        raise PipelineError("CONFIG_INVALID",
                            "job name must be ASCII letters/digits/underscore (max 64): "
                            + repr(job_name))
    return job_name


def derive_job_name(case_id, stage):
    """Derive ``<case_id>_<stage suffix>``.

    Sanitising is lossy ("a-b" and "a.b" both become "a_b"), so a short hash of the
    ORIGINAL case id is appended whenever a character had to be replaced or the name
    had to be truncated: two different case ids never collapse onto one job name and
    the same case id always produces the same name.
    """
    if stage not in _STAGE_SUFFIX:
        raise PipelineError("CONFIG_INVALID", "Unknown job-name stage: " + repr(stage))
    raw = str(case_id or "").strip()
    if not raw:
        raise PipelineError("CONFIG_INVALID",
                            "Cannot derive a job name: the source records no case id. "
                            "Pass --job-name.")
    short_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:6]
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", raw)
    if cleaned != raw:
        cleaned = cleaned + "_" + short_hash
    limit = 64 - len(_STAGE_SUFFIX[stage]) - 1
    if len(cleaned) > limit:
        cleaned = cleaned[:limit - 7] + "_" + short_hash
    return validate_job_name(cleaned + "_" + _STAGE_SUFFIX[stage])


def resolve_job_name(stage, case_id, explicit=None):
    """Return (job name, source) where source is ``cli`` or ``derived``."""
    if explicit:
        return validate_job_name(explicit), "cli"
    return derive_job_name(case_id, stage), "derived"


# --- deck staging -----------------------------------------------------------
# Two checks, both by SHA: the source still holds the bytes an earlier stage
# recorded, and the copy in the new attempt holds those same bytes.

def verify_deck(deck_dir, report, code):
    """Check the deck on disk still holds the bytes the report recorded.

    Nothing is copied anywhere in this pipeline: Data Check and Solve run in the
    same directory the build wrote, so this only has to prove that the deck was not
    edited (by hand or by another tool) between the stages.
    """
    deck_dir = Path(deck_dir)
    if not isinstance(report, dict) or "deck" not in report:
        raise PipelineError("SOURCE_REPORT_INVALID",
                            "Source report does not describe a deck (missing 'deck').")
    files = dict(report["deck"].get("files") or {})
    files.update(report["deck"].get("provenance") or {})
    if not files.get(DECK_ROOT):
        raise PipelineError(code, "Source report records no physical.inp SHA256.")
    for rel, expected in sorted(files.items()):
        path = deck_dir / rel
        if not path.is_file():
            raise PipelineError(code, "Deck artifact is missing: " + rel)
        if file_hash(path) != expected:
            raise PipelineError(code, "Deck artifact changed since the build: " + rel)
    includes = include_paths((deck_dir / DECK_ROOT).read_text(encoding="utf-8"))
    unrecorded = [rel for rel in includes if rel not in files]
    if unrecorded:
        raise PipelineError(code, "The deck references artifacts with no recorded SHA256: "
                            + ", ".join(unrecorded))
    return files


# --- diagnostics ------------------------------------------------------------

_ERROR_PREFIX = "***ERROR"
_WARNING_PREFIX = "***WARNING"
_CONTEXT_STOP = ("***", "*", "END OF", "THE ANALYSIS")
_FATAL = re.compile(r"\*{3}\s*ERROR\b|\bTHE ANALYSIS HAS NOT BEEN COMPLETED\b"
                    r"|\bABAQUS/(?:STANDARD|EXPLICIT) ANALYSIS EXITED WITH AN ERROR\b", re.I)
_ABORT_MARKERS = ("exited with errors", "aborted", "abend")
_KNOWN_KINDS = ("dat", "msg", "log", "sta", "odb", "prt", "mdl", "stt", "res", "com",
                "sim", "cax", "pac", "psr", "par", "pes", "023", "lck", "ipm")
#: Light keyword classification for triage. A category never makes a warning safe;
#: every message is preserved verbatim in the stage report.
CATEGORY_RULES = (
    ("STRAINFREE", ("strainfree", "strain-free")),
    ("CONTACT", ("contact", "overclosure", "copen", "cpress")),
    ("PBC_CONSTRAINT", ("equation", "periodic")),
    ("OVERCONSTRAINT", ("overconstraint", "conflicting constraint", "duplicate",
                        "redundant constraint")),
    ("ZERO_PIVOT", ("zero pivot", "numerical singularity", "singularity", "zero force")),
    ("RIGID_BODY", ("rigid body", "rigid")),
    ("MATERIAL", ("material", "plastic", "elastic", "density")),
    ("ELEMENT", ("element", "mesh", "distort")),
    ("OUTPUT", ("output", "odb", "request", "variable")),
)


def categorize(message):
    """First matching category of an Abaqus message; OTHER when none applies."""
    lowered = message.lower()
    for category, keywords in CATEGORY_RULES:
        if any(keyword in lowered for keyword in keywords):
            return category
    return "OTHER"


def text_of(path):
    """Read a log/deck file as text; Abaqus/Explicit logs may be UTF-16 (NUL-spaced).

    Non-ASCII bytes are replaced, never fatal: these files are diagnostics, and a
    decoding error must not be reported as a solver failure.
    """
    if not path or not Path(path).is_file():
        return ""
    text = Path(path).read_bytes().decode("utf-8", errors="replace")
    return text.replace("\x00", "") if "\x00" in text else text


def _entries(path, prefix):
    """One entry per line carrying the prefix, with a short continuation snippet."""
    entries = []
    lines = text_of(path).splitlines()
    for index, line in enumerate(lines):
        if prefix not in line:
            continue
        message = [line.strip()]
        for follow in lines[index + 1: index + 8]:
            stripped = follow.strip()
            if not stripped or stripped.startswith(_CONTEXT_STOP):
                break
            message.append(stripped)
        joined = "\n".join(message)
        entries.append({"source_file": Path(path).name, "line_number": index + 1,
                        "message": joined, "category": categorize(joined)})
    return entries


def parse_diagnostics(paths):
    """Errors, warnings and fatal lines of the given log files."""
    errors, warnings, fatal = [], [], []
    for path in paths:
        if path is None or not Path(path).is_file():
            continue
        errors.extend(_entries(path, _ERROR_PREFIX))
        warnings.extend(_entries(path, _WARNING_PREFIX))
        for number, line in enumerate(text_of(path).splitlines(), 1):
            if _FATAL.search(line):
                fatal.append({"source_file": Path(path).name, "line_number": number,
                              "message": line.strip()})
    return {"error_count": len(errors), "warning_count": len(warnings),
            "errors": errors, "warnings": warnings, "fatal": fatal,
            "categories": sorted({entry["category"] for entry in errors + warnings}),
            "note": "A lack of ERROR lines is not proof of completion."}


def collect_outputs(attempt, staged):
    """Every file Abaqus produced, with size and SHA256."""
    attempt = Path(attempt)
    generated = []
    for path in sorted(attempt.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(attempt).as_posix()
        if rel in staged:
            continue
        suffix = path.suffix.lower().lstrip(".")
        generated.append({"path": rel, "size_bytes": path.stat().st_size,
                          "sha256": file_hash(path),
                          "kind": suffix if suffix in _KNOWN_KINDS else "other"})
    return generated


def job_artifact(attempt, job_name, suffix):
    """Path of ``<job>.<suffix>`` in the attempt when it exists."""
    path = Path(attempt) / (job_name + "." + suffix)
    return path if path.is_file() else None


def parse_sta(path, solver=STANDARD_DYNAMIC_IMPLICIT):
    """Parse an Abaqus .sta file for the last completed step time.

    The two solvers write different tables:

    * Standard: STEP INC ATT SEVERE-DISCON EQUIL-ITERS TOTAL-ITERS then the time
      columns; a cutback row ('1U') breaks the integer run and is skipped.
    * Explicit: INC TOTAL TIME STEP TIME ... (one integer, then the times), so the
      first two float columns are the step time of interest.

    Both give (last_step_time, increment_count, sta_completion) for the same
    completion judgement.
    """
    info = {"sta_exists": bool(path) and Path(path).is_file(), "increment_count": 0,
            "last_step": None, "last_increment": None, "last_step_time": None,
            "sta_completion": False}
    if not info["sta_exists"]:
        return info
    text = text_of(path)
    info["sta_completion"] = "THE ANALYSIS HAS COMPLETED SUCCESSFULLY" in text
    if solver == EXPLICIT_DYNAMIC:
        for line in text.splitlines():
            parts = line.split()
            if not parts or not parts[0].isdigit() or len(parts) < 3:
                continue
            try:
                step_time = float(parts[2])
            except ValueError:
                continue
            info["increment_count"] += 1
            info["last_increment"] = int(parts[0])
            info["last_step_time"] = step_time
            info["last_step"] = 1
        return info
    for line in text.splitlines():
        parts = line.split()
        integers = 0
        while integers < len(parts) and parts[integers].isdigit():
            integers += 1
        if integers < 6:
            continue
        times = []
        for value in parts[integers:]:
            try:
                times.append(float(value))
            except ValueError:
                break
        if len(times) < 2:
            continue
        info["increment_count"] += 1
        info["last_step"] = int(parts[0])
        info["last_increment"] = int(parts[1])
        info["last_step_time"] = times[1]
    return info


# --- stages -----------------------------------------------------------------

def _run_launcher(argv, cwd, timeout_s, stdout_path, stderr_path):
    """Run the launcher with output streamed into the attempt (never buffered in memory).

    The child environment is sanitized so the Pixi controller's Python/DLL and
    activation variables never leak into the external Abaqus runtime.

    On wall-time expiry the WHOLE case process tree is terminated before the call
    returns (see ``_terminate_case_tree``): the launcher is the direct child, but
    ``standard.exe`` and friends are detached descendants that would otherwise keep
    running and hold CPU/memory/licenses while the batch starts the next case.
    Evidence files (.sta/.msg/.dat/partial ODB) are never touched. If the tree
    cannot be fully terminated, a fatal ``ABAQUS_TREE_NOT_TERMINATED`` stops the
    batch instead of allowing overlapping Abaqus jobs.
    """
    # Absolute on purpose: the solver's own command line carries the RESOLVED deck
    # dir (-indir/-outdir), so a relative --work-root would blind the sweep and,
    # worse, let verification "confirm" a clean tree it cannot actually see.
    case_key = (str(Path(cwd).resolve()), _job_name_of(argv))
    job = _job_create()
    try:
        with open(stdout_path, "wb") as out_stream, open(stderr_path, "wb") as err_stream:
            proc = subprocess.Popen([str(part) for part in argv], cwd=str(cwd),
                                    stdout=out_stream, stderr=err_stream, env=abaqus_env())
            _job_attach(job, proc)
            try:
                returncode = proc.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                survivors = _terminate_case_tree(case_key, proc, job)
                if survivors:
                    raise PipelineError(
                        "ABAQUS_TREE_NOT_TERMINATED",
                        "Case process tree did not terminate after the %ss wall limit; "
                        "still running / unverifiable (matched by case directory/job "
                        "name; %d = the process enumeration itself failed): %s. No new "
                        "Abaqus job may start; clear these processes, then re-run. "
                        "Evidence files are kept: %s"
                        % (timeout_s, _ENUMERATION_FAILED, survivors, cwd), fatal=True) from None
                raise
    finally:
        _job_close(job)
    return returncode


# --- case process tree control (Windows; the RB-014 kill-tree gap) ------------
#
# A timeout kills the launcher process, but Abaqus's real workers (standard.exe,
# the DAE/packager, mpirun siblings) are detached descendants: they keep the CPU,
# memory and license AND keep writing into the case directory. Everything here is
# scoped to ONE case: identification is by the case's own deck directory and job
# name in the process command line (never by image name), termination is per PID,
# and the caller may only continue once verification finds nothing left.

_TREE_GRACE_S = 60.0
_TREE_POLL_INTERVAL_S = 2.0
#: Survivor sentinel meaning "the process enumeration itself failed" — unverifiable
#: is treated as NOT safe to continue, never as a clean tree.
_ENUMERATION_FAILED = -1
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_JobObjectExtendedLimitInformation = 9


class _IO_COUNTERS(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in
                ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                 "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", ctypes.c_uint32),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", ctypes.c_uint32),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", ctypes.c_uint32),
                ("IoInfo", _IO_COUNTERS)]


class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", _IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t)]


def _job_create():
    """A kill-on-close Windows job object: every descendant the launcher spawns
    inherits it, so one TerminateJobObject ends them all. ``None`` when unavailable
    (non-Windows or creation failure) — the PID-targeted sweep then terminates on
    its own and verification still decides whether it is safe to continue.

    Windows builds disagree about sizeof(JOBOBJECT_EXTENDED_LIMIT_INFORMATION)
    (192 with the modern BASIC layout, 144 without IoInfo), so the size that this
    kernel accepts is probed; the KILL_ON_JOB_CLOSE flag sits at offset 16 in both
    layouts, so one buffer serves either. A wrong size fails cleanly with
    ERROR_BAD_LENGTH, never with a partial write."""
    if os.name != "nt":
        return None
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.restype = ctypes.c_void_p
        kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        kernel32.SetInformationJobObject.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                                     ctypes.c_void_p, ctypes.c_uint32]
        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            return None
        limits = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        limits.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        for size in (ctypes.sizeof(limits), 144):
            if kernel32.SetInformationJobObject(handle, _JobObjectExtendedLimitInformation,
                                                ctypes.byref(limits), size):
                return handle
        kernel32.CloseHandle(handle)
        return None
    except Exception:
        return None


def _job_attach(job, proc):
    """Put the launcher (and, by inheritance, everything it spawns) into the job."""
    handle = getattr(proc, "_handle", None)
    if not job or handle is None:
        return False
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        return bool(kernel32.AssignProcessToJobObject(job, int(handle)))
    except Exception:
        return False


def _job_terminate(job):
    if job:
        try:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.TerminateJobObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
            kernel32.TerminateJobObject(job, 1)
        except Exception:
            pass


def _job_close(job):
    if job:
        try:
            ctypes.windll.kernel32.CloseHandle(job)
        except Exception:
            pass


def _job_name_of(argv):
    """The Abaqus job name from a command line like [launcher, "job=x", ...]."""
    for part in argv:
        text = str(part)
        if text.startswith("job="):
            return text[4:]
    return ""


def _system_processes():
    """(pid, ppid, command line lowercased) of every process, backslashes normalized.

    Returns ``None`` when the enumeration itself fails: "cannot see any process"
    must never be confused with "confirmed no process" — an unverifiable state
    keeps the caller in the fatal branch instead of continuing the batch."""
    script = ("Get-CimInstance Win32_Process | ForEach-Object "
              "{ \"{0}`t{1}`t{2}\" -f $_.ProcessId, $_.ParentProcessId, $_.CommandLine }")
    try:
        completed = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                                   capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    rows = []
    for line in completed.stdout.splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3 and parts[0].isdigit():
            rows.append((int(parts[0]), int(parts[1] or 0),
                         parts[2].replace("/", "\\").lower()))
    return rows


def _case_pids(processes, case_key):
    """PIDs whose command line references THIS case (its deck dir and/or job name)."""
    keys = [key.strip().replace("/", "\\").lower() for key in case_key if key]
    mine = os.getpid()
    hits = []
    for pid, _ppid, cmdline in processes:
        if pid == mine or not cmdline:
            continue
        text = cmdline.replace("/", "\\").lower()
        if any(key and key in text for key in keys):
            hits.append(pid)
    return hits


def _terminate_pid(pid):
    """Kill one PID and its children. Never image-name based, never our own PID."""
    if pid == os.getpid():
        return False
    try:
        completed = subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                                   capture_output=True, text=True)
        return completed.returncode == 0
    except OSError:
        return False


def _terminate_case_tree(case_key, proc, job, grace_s=None):
    """Terminate the whole case tree and verify nothing is left. Returns the list
    of surviving PIDs (empty = safe to continue). Never deletes any file: the
    .sta/.msg/.dat/partial ODB of a timed-out attempt are diagnostics.

    Survivors are re-killed on every poll; only if the tree is still alive (or the
    process enumeration itself keeps failing — unverifiable is not "clean") when
    the grace period ends is the fatal path taken."""
    grace_s = _TREE_GRACE_S if grace_s is None else grace_s
    _job_terminate(job)              # OS-level: every descendant inside the job
    _terminate_pid(proc.pid)         # belt and braces (also covers a failed attach)
    sweep = _system_processes()
    for pid in (_case_pids(sweep, case_key) if sweep is not None else []):
        _terminate_pid(pid)          # sweep breakaways / later spawns of THIS case
    deadline = time.monotonic() + grace_s
    while True:
        rows = _system_processes()
        if rows is None:
            if time.monotonic() >= deadline:
                return [_ENUMERATION_FAILED]
            time.sleep(_TREE_POLL_INTERVAL_S)
            continue
        alive = _case_pids(rows, case_key)
        if not alive:
            proc.poll()
            return []
        for pid in alive:
            _terminate_pid(pid)      # keep trying within the grace window
        if time.monotonic() >= deadline:
            return alive
        time.sleep(_TREE_POLL_INTERVAL_S)


def _source_report(folder, name, code):
    path = Path(folder) / name
    if not path.is_file():
        raise PipelineError(code, "Source attempt lacks " + name + ": " + str(folder))
    return read_json(path), file_hash(path)


def _model_block(build_report):
    """The model facts a later stage needs (never recomputed downstream)."""
    simulation = build_report["simulation"]
    kind = simulation["solver"]["type"]
    return {"case_id": build_report.get("case_id"),
            "target_displacement_mm": build_report["model"]["target_displacement_mm"],
            "target_compression_strain": simulation["loading"]["target_compression_strain"],
            "time_period_s": simulation["solver"][kind]["time_period_s"],
            "shell_element_type": simulation["shell"]["element_type"],
            "solver": kind}


def abaqus_run_argv(launcher_path, job, input_name, mode, values, solver=None):
    """Command line for one Abaqus run (mode is 'datacheck' or 'analysis').

    ``standard_parallel`` is a Standard-only option, so it is passed for Standard
    runs only; an Explicit run takes ``cpus`` (plus ``mp_mode`` when the runtime
    config sets one).
    """
    argv = [str(launcher_path), "job=" + job, "input=" + input_name, mode, "interactive",
            "cpus=%d" % values["cpus"]]
    if solver is None or solver == STANDARD_DYNAMIC_IMPLICIT:
        argv.append("standard_parallel=%s" % values["standard_parallel"])
    if values.get("mp_mode"):
        argv.append("mp_mode=%s" % values["mp_mode"])
    return argv


def _deck_names(recorded):
    """Deck artifacts of a report, as a set of relative paths (for output filtering)."""
    return set(recorded)


def run_datacheck(deck_dir, *, abaqus_command=None, job_name=None, cpus=None,
                  standard_parallel=None, mp_mode=None, timeout_s=None, runtime_path=None):
    """Run one real Abaqus Physical Data Check on the deck in ``deck_dir``.

    ``deck_dir`` is the case's own Abaqus directory (``<work_dir>/abaqus``); the
    deck is not copied anywhere. Returns the datacheck report (status
    DATACHECK_PASSED / DATACHECK_COMPLETED_WITH_WARNINGS / DATACHECK_FAILED).
    Pre-condition failures raise PipelineError and write nothing.
    """
    deck_dir = Path(deck_dir)
    build_report, build_report_sha = _source_report(deck_dir, "build_report.json",
                                                    "SOURCE_BUILD_INVALID")
    if build_report.get("status") != "BUILT":
        raise PipelineError("SOURCE_BUILD_INVALID",
                            "Source build status must be BUILT, got: "
                            + repr(build_report.get("status")))
    recorded = verify_deck(deck_dir, build_report, "SOURCE_BUILD_ARTIFACT_MISMATCH")
    solver = build_report["simulation"]["solver"]["type"]
    runtime = load_runtime(runtime_path)
    values = resolve_runtime("datacheck", runtime, cpus=cpus, standard_parallel=standard_parallel,
                             timeout_s=timeout_s, mp_mode=mp_mode)
    name, name_source = resolve_job_name("datacheck", build_report.get("case_id"), job_name)
    launcher = resolve_launcher(runtime, abaqus_command)
    release = query_release(launcher["path"])
    gate = enforce_release_gate(launcher["path"],
                                (runtime.get("abaqus") or {}).get("release_required"), release)
    argv = abaqus_run_argv(launcher["path"], name, DECK_ROOT, "datacheck", values, solver)
    started = _utc_now()
    try:
        returncode = _run_launcher(argv, deck_dir, values["timeout_s"],
                                   deck_dir / "datacheck_stdout.txt",
                                   deck_dir / "datacheck_stderr.txt")
    except subprocess.TimeoutExpired as exc:
        raise PipelineError("DATACHECK_TIMEOUT",
                            "Abaqus datacheck exceeded the %ss wall limit; the run directory is "
                            "kept for inspection: %s" % (values["timeout_s"], deck_dir)) from exc
    ended = _utc_now()
    write_json(deck_dir / "datacheck_command.json",
               {"stage": "datacheck", "launcher": launcher, "release": release,
                "arguments": argv[1:], "runtime": values, "solver": solver, "job_name": name,
                "job_name_source": name_source, "cwd": str(deck_dir), "input": DECK_ROOT,
                "datacheck_flag_present": "datacheck" in argv,
                "analysis_flag_present": any(f in argv for f in ("analysis", "continue")),
                "start_time": started, "end_time": ended, "return_code": returncode,
                "source_physical_inp_sha256": recorded[DECK_ROOT],
                "abaqus_env_blocked_vars": blocked_env_vars()})
    generated = collect_outputs(deck_dir, _deck_names(recorded))
    dat = job_artifact(deck_dir, name, "dat")
    log = job_artifact(deck_dir, name, "log")
    diagnostics = parse_diagnostics([dat, job_artifact(deck_dir, name, "msg"), log])
    # The completion token differs by product: Abaqus/Standard writes "ANALYSIS
    # DATACHECK COMPLETE", Abaqus/Explicit writes "THE ANALYSIS HAS COMPLETED
    # SUCCESSFULLY" (measured on the 2026 install with both decks).
    haystack = "\n".join([text_of(log), text_of(dat),
                          text_of(deck_dir / "datacheck_stdout.txt")]).lower()
    complete = ("analysis datacheck complete" in haystack
                if solver == STANDARD_DYNAMIC_IMPLICIT
                else "the analysis has completed successfully" in haystack)
    abort = [marker for marker in _ABORT_MARKERS if marker in haystack]
    odb = job_artifact(deck_dir, name, "odb")
    required = {"dat": dat, "odb": odb}
    missing = sorted(kind for kind, path in required.items() if path is None)
    zero_byte = sorted(kind for kind, path in required.items()
                       if path is not None and path.stat().st_size == 0)
    failed = bool(returncode or diagnostics["error_count"] or abort or missing or zero_byte
                  or not complete)
    if failed:
        status, claim = "DATACHECK_FAILED", "FAIL"
    elif diagnostics["warning_count"]:
        status, claim = "DATACHECK_COMPLETED_WITH_WARNINGS", "COMPLETED_WITH_WARNINGS"
    else:
        status, claim = "DATACHECK_PASSED", "PASS"
    document = {
        "stage": "datacheck",
        "status": status,
        "case_id": build_report.get("case_id"),
        "solver": solver,
        "model": _model_block(build_report),
        "job": {"name": name, "source": name_source},
        "deck": {"root": DECK_ROOT, "files": recorded},
        "source": {"dir": str(deck_dir), "stage": "build", "status": build_report["status"],
                   "build_report_sha256": build_report_sha,
                   "physical_inp_sha256": recorded[DECK_ROOT]},
        "runtime": values,
        "launcher": launcher, "release": release, "release_gate": gate,
        "command": argv, "cwd": str(deck_dir), "return_code": returncode,
        "start_time": started, "end_time": ended,
        "diagnostics": diagnostics,
        "completion": {"datacheck_complete_marker": complete, "abort_evidence": abort},
        "abaqus_output": {"required_present": {kind: required[kind] is not None
                                               for kind in required},
                          "generated_files": generated},
        "provenance": {"case_id": build_report.get("case_id"),
                       **dict(build_report.get("provenance") or {})},
        "claims": {"datacheck": claim, "solve": "NOT_RUN", "dataset_eligible": False},
        "warning": "A Physical Data Check only proves Abaqus input-stage acceptance on this "
                   "machine. It does NOT prove convergence, a completed compression, correct "
                   "contact/PBC behavior under load or dataset eligibility; the datacheck .odb "
                   "is not a results ODB.",
    }
    if failed:
        document["failure_reasons"] = (
            (["return_code=%d" % returncode] if returncode else [])
            + (["%d ***ERROR entries" % diagnostics["error_count"]]
               if diagnostics["error_count"] else [])
            + (["abort evidence: " + ", ".join(abort)] if abort else [])
            + (["datacheck completion marker missing"] if not complete else [])
            + (["missing required artifacts: " + ", ".join(missing)] if missing else [])
            + (["zero-byte required artifacts: " + ", ".join(zero_byte)] if zero_byte else []))
    write_json(deck_dir / "datacheck_report.json", document)
    return document


_ACCEPTED_DATACHECK = ("DATACHECK_PASSED", "DATACHECK_COMPLETED_WITH_WARNINGS")


def run_solve(deck_dir, *, abaqus_command=None, job_name=None, cpus=None,
              standard_parallel=None, mp_mode=None, timeout_s=None, runtime_path=None):
    """Run one real Abaqus analysis on the ACCEPTED deck in ``deck_dir``.

    ``deck_dir`` is the same case directory the build and the data check used, so
    the solve runs exactly the bytes Abaqus already accepted; ``verify_deck``
    re-proves that against the datacheck report's SHAs. The command line follows
    the solver: Standard gets ``standard_parallel``, Explicit gets ``cpus`` (and
    ``mp_mode`` when the runtime config sets one). Returns the solve report
    (SOLVE_COMPLETED / SOLVE_COMPLETED_WITH_WARNINGS / SOLVE_FAILED); completion is
    judged from the return code AND the stdout token AND the .sta completion marker
    AND the target step time AND the required artifacts.
    """
    deck_dir = Path(deck_dir)
    source_report, source_report_sha = _source_report(deck_dir, "datacheck_report.json",
                                                      "SOURCE_DATACHECK_INVALID")
    status = source_report.get("status")
    if status not in _ACCEPTED_DATACHECK:
        raise PipelineError("SOURCE_DATACHECK_INVALID",
                            "Source datacheck status must be one of "
                            + repr(list(_ACCEPTED_DATACHECK)) + ", got: " + repr(status))
    claims = source_report.get("claims") or {}
    if (source_report.get("diagnostics") or {}).get("error_count") != 0:
        raise PipelineError("SOURCE_DATACHECK_INVALID", "Source datacheck carries errors.")
    if claims.get("solve") != "NOT_RUN" or claims.get("dataset_eligible") is not False:
        raise PipelineError("SOURCE_DATACHECK_INVALID",
                            "Source datacheck claims are not an accepted, unsolved datacheck.")
    recorded = verify_deck(deck_dir, source_report, "SOURCE_DATACHECK_ARTIFACT_MISMATCH")
    solver = source_report.get("solver") or source_report["model"]["solver"]
    model = source_report.get("model") or {}
    target_step_time = finite(model.get("time_period_s"), "source model time_period_s",
                              positive=True, code="SOURCE_DATACHECK_INVALID")
    runtime = load_runtime(runtime_path)
    values = resolve_runtime("solve", runtime, cpus=cpus, standard_parallel=standard_parallel,
                             timeout_s=timeout_s, mp_mode=mp_mode)
    name, name_source = resolve_job_name("solve", source_report.get("case_id"), job_name)
    launcher = resolve_launcher(runtime, abaqus_command)
    release = query_release(launcher["path"])
    gate = enforce_release_gate(launcher["path"],
                                (runtime.get("abaqus") or {}).get("release_required"), release)
    argv = abaqus_run_argv(launcher["path"], name, DECK_ROOT, "analysis", values, solver)
    started = _utc_now()
    monotonic_start = time.monotonic()
    try:
        returncode = _run_launcher(argv, deck_dir, values["timeout_s"],
                                   deck_dir / "solve_stdout.txt",
                                   deck_dir / "solve_stderr.txt")
    except subprocess.TimeoutExpired as exc:
        raise PipelineError("SOLVE_TIMEOUT",
                            "Abaqus analysis exceeded the %ss wall limit; the run directory is "
                            "kept for inspection: %s" % (values["timeout_s"], deck_dir)) from exc
    wall_time_s = time.monotonic() - monotonic_start
    ended = _utc_now()
    stdout_text = text_of(deck_dir / "solve_stdout.txt")
    write_json(deck_dir / "solve_command.json",
               {"stage": "solve", "launcher": launcher, "release": release,
                "arguments": argv[1:], "runtime": values, "solver": solver, "job_name": name,
                "job_name_source": name_source, "cwd": str(deck_dir), "input": DECK_ROOT,
                "analysis_flag_present": "analysis" in argv,
                "datacheck_flag_present": "datacheck" in argv,
                "continue_flag_present": any(f in argv for f in ("continue", "recover")),
                "start_time": started, "end_time": ended, "return_code": returncode,
                "source_physical_inp_sha256": recorded[DECK_ROOT],
                "source_datacheck_status": status,
                "abaqus_env_blocked_vars": blocked_env_vars()})
    generated = collect_outputs(deck_dir, _deck_names(recorded))
    dat = job_artifact(deck_dir, name, "dat")
    sta_path = job_artifact(deck_dir, name, "sta")
    odb = job_artifact(deck_dir, name, "odb")
    diagnostics = parse_diagnostics([dat, job_artifact(deck_dir, name, "msg"), sta_path,
                                     deck_dir / "solve_stdout.txt", deck_dir / "solve_stderr.txt"])
    stdout_completed = bool(re.search(r"\bAbaqus\s+JOB\s+" + re.escape(name) + r"\s+COMPLETED\b",
                                      stdout_text, re.I))
    sta = parse_sta(sta_path, solver=solver)
    target_time_reached = (sta["last_step_time"] is not None
                           and sta["last_step_time"] + 1e-6 >= target_step_time)
    required = {"dat": dat, "msg": job_artifact(deck_dir, name, "msg"), "sta": sta_path,
                "odb": odb}
    missing = sorted(kind for kind, path in required.items() if path is None)
    zero_byte_odb = odb is not None and odb.stat().st_size == 0
    failed = bool(returncode or not stdout_completed or not sta["sta_completion"]
                  or diagnostics["error_count"] or diagnostics["fatal"] or missing
                  or zero_byte_odb or not target_time_reached)
    if failed:
        solve_claim, solve_status = "FAIL", "SOLVE_FAILED"
    elif diagnostics["warning_count"]:
        solve_claim, solve_status = "COMPLETED_WITH_WARNINGS", "SOLVE_COMPLETED_WITH_WARNINGS"
    else:
        solve_claim, solve_status = "COMPLETED", "SOLVE_COMPLETED"
    document = {
        "stage": "solve",
        "status": solve_status,
        "case_id": source_report.get("case_id"),
        "solver": solver,
        "model": model,
        "job": {"name": name, "source": name_source},
        "deck": {"root": DECK_ROOT, "files": recorded},
        "source": {"dir": str(deck_dir), "stage": "datacheck", "status": status,
                   "datacheck_report_sha256": source_report_sha,
                   "physical_inp_sha256": recorded[DECK_ROOT]},
        "runtime": values,
        "launcher": launcher, "release": release, "release_gate": gate,
        "command": argv, "cwd": str(deck_dir), "return_code": returncode,
        "start_time": started, "end_time": ended, "wall_time_s": wall_time_s,
        "diagnostics": diagnostics,
        "completion": {"stdout_completed": stdout_completed,
                       "sta_completed": sta["sta_completion"],
                       "last_step": sta["last_step"], "last_increment": sta["last_increment"],
                       "last_step_time": sta["last_step_time"],
                       "target_step_time": target_step_time,
                       "target_time_reached": target_time_reached},
        "abaqus_output": {
            "required_present": {kind: required[kind] is not None for kind in required},
            "odb": ({"path": odb.name, "size_bytes": odb.stat().st_size,
                     "sha256": file_hash(odb)} if odb is not None else None),
            "generated_files": generated},
        "provenance": {"case_id": source_report.get("case_id"),
                       **dict(source_report.get("provenance") or {})},
        "claims": {"solve": solve_claim, "odb_exists": odb is not None,
                   "odb_results_qa": "NOT_RUN", "dataset_eligible": False},
        "warning": "A completed Abaqus job only proves the solver finished. The ODB has NOT been "
                   "read or validated here, and completion says nothing about quasi-static "
                   "validity, contact/PBC behavior under load or dataset eligibility.",
    }
    if failed:
        document["failure_reasons"] = (
            (["return_code=%d" % returncode] if returncode else [])
            + (["stdout completion token missing"] if not stdout_completed else [])
            + ([".sta completion marker missing"] if not sta["sta_completion"] else [])
            + (["%d ***ERROR entries" % diagnostics["error_count"]]
               if diagnostics["error_count"] else [])
            + (["fatal: " + "; ".join(entry["message"] for entry in diagnostics["fatal"][:3])]
               if diagnostics["fatal"] else [])
            + (["zero-byte odb"] if zero_byte_odb else [])
            + (["missing required artifacts: " + ", ".join(missing)] if missing else [])
            + (["target step time not reached (%r of %r)"
                % (sta["last_step_time"], target_step_time)] if not target_time_reached else []))
    write_json(deck_dir / "solve_report.json", document)
    return document


def run_mesh_datacheck(mesh_result, *, abaqus_command=None, cpus=None, mp_mode=None,
                       timeout_s=None, runtime_path=None, log=print):
    """Data check the frozen vendor's mesh-check INP and run vendor validator 07.

    The mesh check is a Standard analysis of the mesh-only INP (no step), so no
    ``standard_parallel`` is passed. Returns a small report written next to the
    mesh attempt.
    """
    from .mesh import validate_meshcheck

    mesh_dir = Path(mesh_result["engine"]).parents[0]
    check_dir = Path(mesh_result["meshcheck_dir"])
    job = mesh_result["meshcheck_job"]
    runtime = load_runtime(runtime_path)
    # The mesh check is a Standard run of a mesh-only INP; only cpus/mp_mode apply.
    values = resolve_runtime("datacheck", runtime, cpus=cpus, timeout_s=timeout_s,
                             mp_mode=mp_mode)
    launcher = resolve_launcher(runtime, abaqus_command)
    release = query_release(launcher["path"])
    gate = enforce_release_gate(launcher["path"],
                                (runtime.get("abaqus") or {}).get("release_required"), release)
    argv = [launcher["path"], "job=" + job, "input=" + job + ".inp", "datacheck",
            "interactive", "cpus=%d" % values["cpus"]]
    if values.get("mp_mode"):
        argv.append("mp_mode=%s" % values["mp_mode"])
    started = _utc_now()
    try:
        returncode = _run_launcher(argv, check_dir, values["timeout_s"],
                                   mesh_dir / "meshcheck_stdout.txt",
                                   mesh_dir / "meshcheck_stderr.txt")
    except subprocess.TimeoutExpired as exc:
        raise PipelineError("DATACHECK_TIMEOUT",
                            "Abaqus mesh datacheck exceeded the %ss wall limit: %s"
                            % (values["timeout_s"], check_dir)) from exc
    ended = _utc_now()
    dat = job_artifact(check_dir, job, "dat")
    diagnostics = parse_diagnostics([dat, job_artifact(check_dir, job, "msg")])
    failed = bool(returncode or diagnostics["error_count"])
    document = {"stage": "mesh_datacheck", "status": "FAILED" if failed else "PASSED",
                "job": {"name": job}, "solver": "standard (mesh check)",
                "runtime": values, "command": argv, "cwd": str(check_dir),
                "return_code": returncode, "start_time": started, "end_time": ended,
                "release": release, "release_gate": gate,
                "diagnostics": diagnostics,
                "launcher": launcher, "abaqus_env_blocked_vars": blocked_env_vars()}
    if failed:
        document["failure_reasons"] = (
            (["return_code=%d" % returncode] if returncode else [])
            + (["%d ***ERROR entries" % diagnostics["error_count"]]
               if diagnostics["error_count"] else []))
        write_json(mesh_dir / "meshcheck_report.json", document)
        raise PipelineError("MESH_DATACHECK_FAILED",
                            "Abaqus rejected the mesh-check INP; details in "
                            + str(mesh_dir / "meshcheck_report.json"))
    report = validate_meshcheck(mesh_result, log)
    document["vendor_validation"] = report
    document["status"] = "PASSED" if report.get("pass") else "VENDOR_VALIDATION_FAILED"
    write_json(mesh_dir / "meshcheck_report.json", document)
    if not report.get("pass"):
        raise PipelineError("MESH_DATACHECK_FAILED",
                            "Vendor stage 07 rejected the mesh data check logs.")
    return document
