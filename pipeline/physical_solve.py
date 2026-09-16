"""Single-job real Abaqus/Standard solve (M3): one accepted deck, one analysis.

Answers exactly one question: can the pipeline submit the deck that M2 already
data-checked, run it to completion without CAE, and reliably judge completed
vs failed from real evidence? The attempt stages the accepted inputs, records
M2 provenance, invokes `abaqus job=<name> input=physical.inp analysis
interactive cpus=<n> standard_parallel=<mode>` and writes solve_report.json.

Scope guards: completion is judged from return code + stdout token + .sta
completion marker + fatal diagnostics + required artifacts + target step time
(never the return code alone); no ODB is opened here (that is M4); no
watchdog/retry/orchestration; dataset eligibility stays false.
"""
from __future__ import annotations

import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from .common import PipelineError, atomic_json, atomic_text, file_hash, read_json, reserve_directory
from .diagnostics import FATAL
from .physical_datacheck import categorize, enforce_release_gate, query_release, resolve_launcher

_INPUT_NAME = "physical.inp"
_DEFAULT_JOB_NAME = "fig1_m3_solve"
_DEFAULT_TIMEOUT_S = 14400
_JOB_NAME_RE = re.compile(r"^[A-Za-z0-9_]{1,64}$")
_ERROR_PREFIX = "***ERROR"
_WARNING_PREFIX = "***WARNING"
_CONTEXT_STOP = ("***", "*", "THE ANALYSIS", "END OF")
_REQUIRED_ARTIFACTS = ("dat", "msg", "sta", "odb")
_STDOUT_COMPLETED_FMT = r"\bAbaqus\s+JOB\s+{job}\s+COMPLETED\b"
_STA_COMPLETED_MARKER = "THE ANALYSIS HAS COMPLETED SUCCESSFULLY"
_ACCEPTED_DATACHECK_STATUSES = ("DATACHECK_PASSED", "DATACHECK_COMPLETED_WITH_WARNINGS")

# M3 conservative execution profile. Element operations run serial, so the
# machine-specific General Contact parallel preprocessing failure observed on
# the development machine (see docs/HANDOFF_CURRENT.md) is kept out of the way;
# this is NOT the future M3 performance policy and never touches the model.
_SAFE_EXECUTION_POLICY = {"cpus": 1, "standard_parallel": "solver"}
_ALLOWED_STANDARD_PARALLEL = ("all", "solver")
_POLICY_LOCAL = Path(__file__).resolve().parents[1] / "config" / "solve_runtime.local.json"

# Staged inputs mirror the M2-accepted attempt; provenance keeps the full chain.
_STAGED_DECK_FILES = (
    "physical.inp",
    "ingredients/shell_mesh.inc",
    "ingredients/lateral_pbc.inc",
    "blocks/material_section.inc",
    "blocks/rigid_platens.inc",
    "blocks/boundary_conditions.inc",
    "blocks/contact.inc",
    "blocks/step_loading.inc",
    "blocks/outputs.inc",
    "blocks/step_end.inc",
)
_PROVENANCE_FILES = (("datacheck_report.json", "source_datacheck_report.json"),
                     ("source_model_manifest.json", "source_model_manifest.json"),
                     ("source_build_report.json", "source_build_report.json"))


def _utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_accepted_datacheck(datacheck_dir):
    """A solve may only start from an M2 attempt that Abaqus accepted."""
    datacheck_dir = Path(datacheck_dir)
    report_path = datacheck_dir / "datacheck_report.json"
    if not report_path.is_file():
        raise PipelineError("SOURCE_DATACHECK_INVALID",
                            "Source datacheck attempt lacks datacheck_report.json: " + str(datacheck_dir))
    report = read_json(report_path)
    if report.get("status") not in _ACCEPTED_DATACHECK_STATUSES:
        raise PipelineError("SOURCE_DATACHECK_INVALID",
                            "Source datacheck status must be one of "
                            + repr(list(_ACCEPTED_DATACHECK_STATUSES)) + ", got: "
                            + repr(report.get("status")))
    diagnostics = report.get("diagnostics", {})
    if diagnostics.get("error_count") != 0:
        raise PipelineError("SOURCE_DATACHECK_INVALID",
                            "Source datacheck carries %s errors." % diagnostics.get("error_count"))
    claims = report.get("claims", {})
    if claims.get("physical_datacheck") == "FAIL" or claims.get("solve") != "NOT_RUN":
        raise PipelineError("SOURCE_DATACHECK_INVALID",
                            "Source datacheck claims are not an accepted, unsolved datacheck.")
    if claims.get("dataset_eligible") is not False:
        raise PipelineError("SOURCE_DATACHECK_INVALID", "Source datacheck claims dataset eligibility.")
    deck = datacheck_dir / _INPUT_NAME
    recorded = report.get("source_build", {}).get("physical_inp_sha256")
    if not deck.is_file() or not recorded or file_hash(deck) != recorded:
        raise PipelineError("SOURCE_DATACHECK_INVALID",
                            "physical.inp is missing or its SHA256 does not match the datacheck report.")
    return datacheck_dir, report


def _stage_solve_inputs(datacheck_dir, attempt):
    """Copy the exact accepted deck/include set plus provenance, SHA-verified after copy."""
    staged = []
    for rel in _STAGED_DECK_FILES:
        src, dst = datacheck_dir / rel, attempt / rel
        if not src.is_file():
            raise PipelineError("SOURCE_DATACHECK_INVALID", "Source datacheck attempt is missing: " + rel)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
        if file_hash(src) != file_hash(dst):
            raise PipelineError("STAGING_SHA_MISMATCH", "Staged file differs from source: " + rel)
        staged.append({"path": rel, "sha256": file_hash(dst), "role": "input"})
    for src_name, dst_name in _PROVENANCE_FILES:
        src, dst = datacheck_dir / src_name, attempt / dst_name
        if not src.is_file():
            raise PipelineError("SOURCE_DATACHECK_INVALID", "Source datacheck attempt is missing: " + src_name)
        dst.write_bytes(src.read_bytes())
        if file_hash(src) != file_hash(dst):
            raise PipelineError("STAGING_SHA_MISMATCH", "Staged file differs from source: " + dst_name)
        staged.append({"path": dst_name, "sha256": file_hash(dst), "role": "provenance"})
    return staged

def _run_process_to_files(argv, cwd, timeout_s, stdout_path, stderr_path):
    """Run the launcher with stdout/stderr streamed straight into the attempt.

    Long analyses must not accumulate output in Python memory; blocking
    subprocess.run with file handles keeps this simple (no watchdog this stage).
    """
    with open(stdout_path, "wb") as out_stream, open(stderr_path, "wb") as err_stream:
        completed = subprocess.run([str(part) for part in argv], cwd=str(cwd),
                                   stdout=out_stream, stderr=err_stream, timeout=timeout_s)
    return completed.returncode


def _stdout_job_completed(text, job_name):
    """Completion token must name THIS job; other jobs' tokens are not evidence."""
    pattern = re.compile(_STDOUT_COMPLETED_FMT.format(job=re.escape(job_name)), re.I)
    return bool(pattern.search(text))


def _resolve_execution_policy(cpus, standard_parallel, policy_path):
    """Solve runtime policy: CLI > machine-local solve_runtime file > safe default.

    Machine/runtime-local only; never part of the physical model or the M1
    identity keys, and never silently inherited from the M2 datacheck profile.
    """
    resolved = dict(_SAFE_EXECUTION_POLICY)
    source = "safe_default"
    path = Path(policy_path) if policy_path else _POLICY_LOCAL
    if path.is_file():
        configured = read_json(path)
        unexpected = set(configured) - {"schema_version", "cpus", "standard_parallel"}
        if configured.get("schema_version") != 1 or unexpected:
            raise PipelineError("CONFIG_INVALID",
                                "solve runtime policy file must use schema 1 with only "
                                "schema_version, cpus and standard_parallel: " + str(path))
        if configured.get("cpus") is not None:
            resolved["cpus"] = configured["cpus"]
        if configured.get("standard_parallel") is not None:
            resolved["standard_parallel"] = configured["standard_parallel"]
        source = "local_environment"
    if cpus is not None:
        resolved["cpus"] = cpus
        source = "cli"
    if standard_parallel is not None:
        resolved["standard_parallel"] = standard_parallel
        source = "cli"
    value = resolved["cpus"]
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise PipelineError("CONFIG_INVALID", "cpus must be an integer >= 1: " + repr(value))
    mode = resolved["standard_parallel"]
    if not isinstance(mode, str) or mode.strip().lower() not in _ALLOWED_STANDARD_PARALLEL:
        raise PipelineError("CONFIG_INVALID",
                            "standard_parallel must be one of "
                            + repr(list(_ALLOWED_STANDARD_PARALLEL)) + ": " + repr(mode))
    return {"cpus": value, "standard_parallel": mode.strip().lower(), "source": source}


def _scan_diagnostic_file(path, prefix):
    """Line-oriented ERROR/WARNING extraction with short continuation context."""
    entries = []
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    for index, line in enumerate(lines):
        if prefix not in line:
            continue
        message = [line.strip()]
        for follow in lines[index + 1: index + 8]:
            stripped = follow.strip()
            if not stripped or stripped.startswith(_CONTEXT_STOP):
                break
            message.append(stripped)
        entries.append({"source_file": Path(path).name, "line_number": index + 1,
                        "message": "\n".join(message)})
    return entries


def parse_solve_diagnostics(paths):
    """Extract errors[], warnings[] and fatal/not-completed evidence from solve files."""
    errors, warnings, fatal = [], [], []
    for path in paths:
        if path is None or not Path(path).is_file():
            continue
        errors.extend(_scan_diagnostic_file(path, _ERROR_PREFIX))
        warnings.extend(_scan_diagnostic_file(path, _WARNING_PREFIX))
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
        for number, line in enumerate(lines, 1):
            if FATAL.search(line):
                fatal.append({"source_file": Path(path).name, "line_number": number,
                              "message": line.strip()})
    for entry in errors + warnings + fatal:
        entry["category"] = categorize(entry["message"])
    return {"error_count": len(errors), "warning_count": len(warnings),
            "errors": errors, "warnings": warnings, "fatal": fatal,
            "categories": sorted({entry["category"] for entry in errors + warnings + fatal})}


def parse_sta(path):
    """Narrow Abaqus/Standard .sta parser: successful increment rows only.

    A data row starts with seven integer fields (STEP INC ATT SEVERE-DISCON
    EQUIL-ITERS TOTAL-ITERS plus the solver-iteration variant) followed by one
    to three float time columns (TOTAL TIME, STEP TIME, INC OF TIME); rows with
    cutback markers (e.g. 'U' suffixes) are not successful increments.
    """
    info = {"sta_exists": bool(path) and Path(path).is_file(),
            "increment_count": 0, "last_step": None, "last_increment": None,
            "last_total_time": None, "last_step_time": None,
            "sta_completion": False}
    if path is None or not Path(path).is_file():
        return info
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    info["sta_completion"] = _STA_COMPLETED_MARKER in text
    for line in text.splitlines():
        parts = line.split()
        # A successful-increment row starts with at least six integer fields
        # (STEP INC ATT SEVERE-DISCON EQUIL-ITERS TOTAL-ITERS, optionally the
        # DOF/IF monitor) followed by float time columns (TOTAL TIME, STEP
        # TIME, INC OF TIME). Cutback rows (e.g. '1U') break the integer run
        # early and are skipped.
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
        info["last_total_time"] = times[0]
        info["last_step_time"] = times[1]
    return info

def _collect_artifacts(attempt, job_name, staged_paths):
    """Keep every generated file; classify the diagnostic ones and hash them."""
    known_kinds = ("dat", "msg", "sta", "odb", "prt", "mdl", "stt", "res", "com",
                   "sim", "cax", "pac", "psr", "par", "pes", "023")
    generated, classified = [], {"dat": None, "msg": None, "sta": None, "odb": None,
                                 "log": None, "exception": None}
    for path in sorted(attempt.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(attempt).as_posix()
        if rel in staged_paths:
            continue
        suffix = path.suffix.lower().lstrip(".")
        generated.append({"path": rel, "size_bytes": path.stat().st_size,
                          "sha256": file_hash(path),
                          "kind": suffix if suffix in known_kinds else "other"})
        if rel == job_name + "." + suffix and suffix in classified:
            classified[suffix] = path
        elif rel == job_name + ".log":
            classified["log"] = path
        elif ".exception" in path.name:
            classified["exception"] = path
    return generated, classified


def run_solve(datacheck_dir, output, abaqus_command=None, job_name=_DEFAULT_JOB_NAME,
              environment_path=None, timeout_s=_DEFAULT_TIMEOUT_S,
              cpus=None, standard_parallel=None, policy_path=None):
    """Stage an accepted M2 datacheck attempt and run one real Abaqus analysis.

    Returns the solve report dict (status SOLVE_COMPLETED /
    SOLVE_COMPLETED_WITH_WARNINGS / SOLVE_FAILED). Pre-condition failures raise
    PipelineError and leave no partial attempt.
    """
    if not _JOB_NAME_RE.match(job_name or ""):
        raise PipelineError("CONFIG_INVALID",
                            "job_name must be ASCII letters/digits/underscore only: " + repr(job_name))
    datacheck_dir, datacheck_report = _load_accepted_datacheck(datacheck_dir)
    source_manifest = read_json(datacheck_dir / "source_model_manifest.json")
    launcher = resolve_launcher(abaqus_command, environment_path)
    policy = _resolve_execution_policy(cpus, standard_parallel, policy_path)
    release = query_release(launcher["path"])
    # Release gate BEFORE any attempt directory is created: a wrong or unknown
    # Abaqus version must never start an expensive analysis job.
    release_gate = enforce_release_gate(launcher["path"], environment_path, release)
    attempt = reserve_directory(output)
    staged_entries = _stage_solve_inputs(datacheck_dir, attempt)
    staged_paths = {entry["path"] for entry in staged_entries}
    argv = [launcher["path"], "job=" + job_name, "input=" + _INPUT_NAME,
            "analysis", "interactive",
            "cpus=%d" % policy["cpus"],
            "standard_parallel=%s" % policy["standard_parallel"]]
    started = _utc_now()
    monotonic_start = time.monotonic()
    try:
        returncode = _run_process_to_files(argv, attempt, timeout_s,
                                           attempt / "stdout.txt", attempt / "stderr.txt")
    except subprocess.TimeoutExpired as exc:
        raise PipelineError("SOLVE_TIMEOUT",
                            "Abaqus analysis exceeded the %ss wall limit; the attempt is "
                            "kept for inspection." % timeout_s) from exc
    wall_time_s = time.monotonic() - monotonic_start
    ended = _utc_now()
    stdout_text = (attempt / "stdout.txt").read_text(encoding="utf-8", errors="replace")
    atomic_json(attempt / "command.json", {
        "launcher": launcher, "release": release, "arguments": argv[1:],
        "execution_policy": policy,
        "cwd": str(attempt), "job_name": job_name, "input": _INPUT_NAME,
        "analysis_flag_present": "analysis" in argv,
        "datacheck_flag_present": "datacheck" in argv,
        "continue_flag_present": any(flag in argv for flag in ("continue", "recover")),
        "start_time": started, "end_time": ended, "return_code": returncode,
        "source_physical_inp_sha256": datacheck_report["source_build"]["physical_inp_sha256"],
        "source_datacheck_status": datacheck_report["status"],
        "source_build_key": datacheck_report["source_build"]["build_key"],
    })
    generated, artifacts = _collect_artifacts(attempt, job_name, staged_paths)
    diagnostics = parse_solve_diagnostics([artifacts["dat"], artifacts["msg"],
                                           artifacts["sta"], artifacts["exception"],
                                           attempt / "stdout.txt", attempt / "stderr.txt"])
    stdout_completed = _stdout_job_completed(stdout_text, job_name)
    sta_info = parse_sta(artifacts["sta"])
    missing = [kind for kind in _REQUIRED_ARTIFACTS if artifacts[kind] is None]
    zero_byte_odb = (artifacts["odb"] is not None
                     and artifacts["odb"].stat().st_size == 0)
    physics = source_manifest["physics"]
    target_step_time = float(physics["time_period_s"])
    last_step_time = sta_info["last_step_time"]
    target_time_reached = (last_step_time is not None
                           and last_step_time + 1e-6 >= target_step_time)
    failed = bool(returncode != 0 or not stdout_completed or not sta_info["sta_completion"]
                  or diagnostics["error_count"] or diagnostics["fatal"] or missing
                  or zero_byte_odb or not target_time_reached)
    if failed:
        status, claim = "SOLVE_FAILED", "FAIL"
    elif diagnostics["warning_count"]:
        status, claim = "SOLVE_COMPLETED_WITH_WARNINGS", "COMPLETED_WITH_WARNINGS"
    else:
        status, claim = "SOLVE_COMPLETED", "COMPLETED"
    odb = artifacts["odb"]
    report = {
        "schema_version": 1,
        "status": status,
        "staged_files": staged_entries,
        "source_datacheck": {
            "path": str(datacheck_dir),
            "status": datacheck_report["status"],
            "physical_inp_sha256": datacheck_report["source_build"]["physical_inp_sha256"],
            "warning_count": datacheck_report["diagnostics"]["warning_count"],
            "warning_categories": datacheck_report["diagnostics"]["categories"],
        },
        "source_model": {
            "model_key": source_manifest["identity"]["model_key"],
            "scaffold_key": source_manifest["scaffold_key"],
            "build_key": source_manifest["build_key"],
            "target_compression_strain": physics["target_compression_strain"],
            "target_displacement_mm": source_manifest["target_displacement_mm"],
            "time_period_s": target_step_time,
        },
        "execution": {
            "launcher": launcher, "release": release, "release_gate": release_gate, "job_name": job_name,
            "cpus": policy["cpus"], "standard_parallel": policy["standard_parallel"],
            "policy_source": policy["source"],
            "command": argv, "cwd": str(attempt), "return_code": returncode,
            "wall_time_s": wall_time_s,
            "start_time": started, "end_time": ended,
        },
        "completion": {
            "stdout_completed": stdout_completed,
            "sta_completed": sta_info["sta_completion"],
            "last_step": sta_info["last_step"],
            "last_increment": sta_info["last_increment"],
            "last_step_time": sta_info["last_step_time"],
            "target_step_time": target_step_time,
            "target_time_reached": target_time_reached,
        },
        "artifacts": {
            "required_presence": {kind: artifacts[kind] is not None
                                  for kind in _REQUIRED_ARTIFACTS},
            "odb": ({"path": odb.relative_to(attempt).as_posix(),
                     "size_bytes": odb.stat().st_size, "sha256": file_hash(odb)} if odb else None),
            "generated_files": generated,
        },
        "diagnostics": diagnostics,
        "claims": {
            "solve": claim,
            "odb_exists": odb is not None,
            "odb_results_qa": "NOT_RUN",
            "mechanics_qa": "NOT_RUN",
            "dataset_eligible": False,
        },
        "warning": "The ODB here is an artifact produced by a successfully completed Abaqus job. "
                   "It has NOT yet been opened or validated by odbAccess (that belongs to M4), and a "
                   "completed solve does NOT prove quasi-static validity, correct contact/PBC behavior "
                   "under load, or any scientific result; dataset eligibility stays false.",
    }
    if status == "SOLVE_FAILED":
        report["failure_reasons"] = (
            (["return_code=%d" % returncode] if returncode != 0 else [])
            + (["stdout completion token missing"] if not stdout_completed else [])
            + ([".sta completion marker missing"] if not sta_info["sta_completion"] else [])
            + (["%d ***ERROR entries" % diagnostics["error_count"]] if diagnostics["error_count"] else [])
            + (["fatal: " + "; ".join(f["message"] for f in diagnostics["fatal"][:3])]
               if diagnostics["fatal"] else [])
            + (["zero-byte odb"] if zero_byte_odb else [])
            + (["missing required artifacts: " + ", ".join(missing)] if missing else [])
            + (["target step time not reached (%r of %r)" % (last_step_time, target_step_time)]
               if not target_time_reached else []))
    atomic_json(attempt / "solve_report.json", report)
    return report
